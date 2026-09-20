# Node properties for graph kernels (P6) — design for review

Status: **APPROVED WITH ONE CHANGE, 2026-09-20.** The operator answered the five
questions at the end: four as recommended, and **strings are in, for filters
only** (question 4). The answers are recorded at the end, and the "Types"
section is amended to match. No code exists yet; implementation follows "Order
of work".

## Why

`GraphProjection` carries topology and one optional edge weight. Every kernel
left in `docs/goals/graph-analytics-catalog.md` needs something per node that is
not topology:

| Kernel (catalog group) | Needs per node |
| --- | --- |
| `knn`, `knnFiltered` (15) | a vector, or several scalars |
| `nodeSimilarity` filters (16) | a boolean or a label: who may be a source, who a target |
| `modularity`, `conductance` (22) | a community id |
| seeded `louvain`, `leiden`, `labelPropagation`; `sllpa` (1, 7, 8, 24) | an initial community id |
| `linkPrediction` `sameCommunity` (30) | a community id |
| `kmeans`, `hdbscan` (31) | a vector |
| `node2vec`, `hashGNN`, `graphSage`, `fastRP` `featureProperties` (14, 32) | a vector or scalars |
| `astar` (9) | latitude and longitude |
| `minCostFlow` (28) | a supply or demand |

That is 20 of the 36 remaining catalog entries. Nothing in Tier B starts without
it.

## The decision that shapes everything: a sibling, not a field

The obvious design adds `node_properties` to `ProjectionOptions` and columns to
`GraphProjection`. I recommend against it, for two reasons, and I withdraw a
third that I had written before checking it:

1. **It welds two lifetimes together.** A projection is expensive to build and is
   cached per (graph, revision, labels, orientation, weight). Properties are
   cheap to read and vary per call: one call wants `embedding`, the next wants
   `seedCommunity`. Put them in the projection and either the cache key grows by
   every property list, and topology is rebuilt to change a column, or the cache
   serves a projection with the wrong columns.
2. **`projection.rs` has an owner, and it is not me.** quegee is about to
   parallelise the projection build in that file. A design that stays out of it
   lets both pieces of work proceed; one that goes through it serialises them.

*Not a reason:* source compatibility. I first wrote that a new field would break
every caller, as it would for `ExecutionLimits`. It would not. Of the ten places
that build `ProjectionOptions` by struct literal, across Grust and the algorithms
benchmark, nine end in `..Default::default()`; the one that does not is inside
`grust-algorithm-procedures`. A field would cost one line. The choice below is
about lifetimes and ownership, not about breakage.

So:

```rust
/// Typed columns, one row per projected node, in the projection's row order.
pub struct NodeProperties { /* graph: GraphProjection, columns, admission */ }

impl NodeProperties {
    pub fn from_graph(graph: &Graph, projection: &GraphProjection,
                      wanted: &[PropertyRequest<'_>]) -> Result<Self>;
    pub fn from_arrow_batches(node_batches: &[RecordBatch], projection: &GraphProjection,
                              wanted: &[PropertyRequest<'_>]) -> Result<Self>;
    pub fn projection(&self) -> &GraphProjection;
    pub fn numbers(&self, key: &str) -> Result<NumberColumn<'_>>;
    pub fn integers(&self, key: &str) -> Result<IntegerColumn<'_>>;
    pub fn vectors(&self, key: &str) -> Result<VectorColumn<'_>>;
}
```

A kernel that needs properties takes `&NodeProperties` and reaches the topology
through `properties.projection()`; a kernel that does not is untouched. Row
alignment is guaranteed by construction, not by convention: the properties are
built *against* a projection, hold a clone of it (an `Arc`), and look nodes up
through the projection's own id map, so a `NodeProperties` cannot be paired with
the wrong projection because it carries the right one.

`GraphProjection`, `ProjectionOptions` and `projection.rs` do not change.

## Types

Four column kinds. Three are chosen from what the table above needs; the fourth,
`Category`, was added by the operator for filters:

| Kind | Rust | Arrow in | Used by |
| --- | --- | --- | --- |
| Number | `f64` | `Float64`, `Float32`, any integer | coordinates, supplies, scalar features |
| Integer | `i64` | any integer | community ids, seeds, boolean filters as 0/1 |
| Vector | `f32` × fixed `d` | `FixedSizeList<Float32\|Float64>`, `List<…>` of constant length | embeddings, feature vectors |
| Category | `u32` code + dictionary | `Utf8`, `LargeUtf8`, dictionary-encoded `Utf8` | source and target filters, by equality only |

- **`f32` for vectors**, matching `fastRP`'s output, so an embedding written by
  one kernel is read by the next without conversion, and halving the largest
  allocation in the catalog. A `Float64` list is narrowed on read; a value that
  does not survive narrowing as finite is an error, not an infinity.
- **Strings are in for one purpose: equality filters** (operator decision,
  question 4). A fourth kind, `Category`, reads a `Utf8` column (or
  `Value::String`) and dictionary-encodes it on read into `u32` codes plus the
  distinct strings. A kernel may test a node's category for equality or
  membership — `nodeSimilarity`'s and `knn`'s source and target filters — and
  nothing else: no ordering, no arithmetic, no use as a feature. The dictionary's
  strings are admitted against the memory limit like any buffer, and codes are
  assigned in order of first appearance in row order, so they do not depend on
  the worker count. What I had recommended, no strings at all, would have made a
  Nutmeg user pre-encode a category column before filtering by it.
- **A `List` whose rows differ in length is an error** naming the first row that
  differs. Ragged vectors have no kernel that wants them.

From a `grust_core::Graph`, `Value::Float`/`Int` map to Number and Integer, and
`Value::FloatArray`/`IntArray` to Vector, by the same rules.

## Missing values

Explicit, as weights already are. Each request carries a policy mirroring
`MissingWeight`:

```rust
pub struct PropertyRequest<'a> { pub key: &'a str, pub kind: PropertyKind, pub missing: MissingProperty }
pub enum MissingProperty { Reject, Default(f64), Null }
```

- `Reject`: the first absent or null value is an error naming the node and key.
  The default, because a silent zero in a feature vector is a wrong answer that
  looks like a right one.
- `Default(x)`: substitute. For a vector, every component.
- `Null`: keep a validity bitmap; the column accessor returns `Option`. Only
  kernels that define what null means may ask for it — a seed column, where null
  means "no seed", is the motivating case. A kernel that did not ask for `Null`
  never sees an `Option`, so it cannot forget to handle one.

Arrow input follows the convention `from_arrow_batches` already uses for
weights: `property.<key>` with a non-nullable boolean `present.<key>`.

## Accounting

Same contract as every other buffer in the crate:

- Columns live in `Buffer<T>`, so their bytes are admitted against the
  execution's memory limit before they are allocated and released when the
  `NodeProperties` drops.
- Reading charges one work unit per node per requested column (per component
  for vectors), through a `WorkMeter`.
- A request for a million-node, 512-dimensional embedding is 2 GB. It is
  refused at admission with `BudgetExceeded { resource: "memory" }`, before any
  allocation, like any other over-budget request.

## Caching

`NodeProperties` gets its own cache entry, keyed by the projection's cache key
plus the sorted list of `(key, kind, missing)`. Two consequences worth stating:
changing the property list never rebuilds topology, and two calls that want the
same columns over the same projection share them.

## The procedure surface

Kernel-specific option names, as GDS has them, so Nutmeg's alias table stays a
table: `nodeProperties: ['x', 'y']` for `knn`, `seedProperty: 'community'` for
the community kernels, `latitudeProperty`/`longitudeProperty` for `astar`,
`featureProperties` for `fastRP`. Each registered kernel declares which of its
options name node properties, with their kind and missing policy; the provider
reads that declaration, builds the `NodeProperties`, and hands it to the kernel.

`run_on_projection` gains a sibling for embedders that hold their own data:

```rust
pub fn node_property_requests(name: &str, args: &ValidatedArguments) -> Result<Vec<PropertyRequest<'_>>>;
pub fn run_with_properties(name, &GraphProjection, &NodeProperties, &ValidatedArguments) -> Result<ArrowResultCursor>;
```

Nutmeg calls the first to learn which node columns to stage, builds
`NodeProperties` from its own Arrow batches, and calls the second. A kernel that
needs no properties keeps working through `run_on_projection` unchanged, so
**nothing in Nutmeg breaks when this lands**; it serves the new kernels once it
adopts the two functions.

## What is deliberately left out

- **Writing results back as properties** (GDS's `mutate` and `write` modes). A
  kernel's result is a table; composing kernels means passing one's output
  column as the next one's `NodeProperties`. I would add
  `NodeProperties::from_table(&NodeTable, columns)` for exactly that, in the
  first kernel that needs it (seeded Leiden from a Louvain result), not before.
- **Edge properties beyond the one weight.** `minCostFlow` needs a capacity and a
  cost per edge. That is a separate, smaller design (`EdgeProperties`, same
  shape) and should not ride along here.
- **Strings, ragged lists, nested types**, as above.

## Order of work, if approved

1. `NodeProperties`, the three column kinds, both constructors, accounting, and
   tests: row alignment under label selection (a projection that drops nodes
   must drop their property rows), every missing policy, narrowing, ragged
   lists, budget refusal, and release on drop. No kernel yet. About 600 lines.
2. The provider declaration and the two embedder functions, with a catalog test
   that every kernel declaring a property option can be run through both paths.
3. First consumer: **`modularity` and `conductance`** (group 22). Smallest
   kernel, integer column, and it is the oracle the community kernels' tests
   already reimplement privately, so it pays for itself at once.
4. Then `astar` (finishes catalog group 9), seeded community detection, and
   `knn`, in that order of increasing size.

Each step is its own pull request with a Linux `scripts/ci-local.sh` verdict.

## Questions for the operator, and the answers (2026-09-20)

1. **Sibling object rather than a field on the projection?** — **Yes, separate
   object.**
2. **Vectors as `f32`?** — **Yes.**
3. **`Reject` as the default missing policy?** — **Yes.** `Default(x)` and `Null`
   are asked for explicitly.
4. **No strings?** — **No: strings for filters only.** See `Category` under
   "Types". This is the one change to the proposal.
5. **First consumer `modularity` and `conductance`?** — **Yes.** Then `astar`,
   seeded community detection, and `knn`.

`Category` does not change the order of work: step 1 builds all four kinds, and
its first consumer is the `nodeSimilarity` filter (catalog group 16), after
`knn`.
