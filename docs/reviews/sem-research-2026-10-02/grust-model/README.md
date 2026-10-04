# Grust's data model: why it is what it is, what it costs, and a dense alternative

A report for Sem, 2026-10-02. Code references are to Grust 0.24.0
(`querygraph/grust` tag `v0.24.0`). Numbers are from the graph500-24 records
of the same day unless marked as estimates.

## Summary

- The model was not chosen for analytics. Grust began as a backend-neutral
  property-graph API over a dozen stores, where a node id is whatever the
  store has, so it is a string. The algorithm crate was added three months
  later on top of that model and inherited its identity type at the
  boundary.
- The kernels themselves do not touch `NodeId`. They run on a CSR with
  4-byte targets. Strings are at the door (input), in the dense-to-origin
  vector, in the lazily built id map, and in every result column.
- On graph500-24 the projection admits 4.99 GB. A CSR of the same topology
  is 1.08 GB. The difference is the edge table kept beside the CSR
  (2.08 GB), the per-arc edge slot (1.04 GB) and identity (0.79 GB, 89
  bytes a node against 8 for an Int64 column).
- On the `OnceLock<HashMap<NodeId, usize>>`: Sem is right. It serves only
  point lookups of a source by id. Two sorted Arrow columns do the same in
  a fraction of the memory, are immutable and shareable, and their natural
  operation is the join.
- The alternative Sem describes (ids and maps only in the logical LPG
  description; every group stored as dense arrays, CSR plus a mapping to
  the origin id, as in GraphAr) fits the kernels as they are. What it
  replaces is everything around them: the projection build, the string
  results, the edge table, and the extension's staging.

## 1. The questions

Translated from Sem's message:

1. "Why `OnceLock<HashMap<NodeId, usize>>`? Why not a `RecordBatch` with two
   columns (origin_id, dense_id)? The structure is immutable, the data would
   sit in dense arrays, not scattered over the heap. Our operations are
   always full mappings (joins); Arrow's cache locality only wins, and the
   memory load is much lower."
2. "I have a firm feeling that Grust's original contract on NodeId and
   EdgeId weighs on us. Evaluate dropping it in favour of dense CSR and a
   mapping, keeping NodeId and EdgeId only for the logical description of
   LPG structures."
3. "A full report on why this base model was chosen (vectors of NodeId and
   EdgeId, most likely reference types with all that follows: pointer
   chasing, poor cache locality), and an analysis of a different model
   where ids and hash maps describe the LPG only, and the groups are strictly
   dense CSR plus mappings to the origin id. Take inspiration from the
   GraphAr format specification."

## 2. What the model is today

### The property-graph layer (`grust-core`)

| Type | Definition | Where |
|---|---|---|
| `NodeId`, `EdgeId`, `Label` | a newtype over `Arc<str>` | `crates/grust-core/src/lib.rs:58` (`string_newtype!`) |
| `Props` | `BTreeMap<String, Value>` | `lib.rs:26` |
| `Node` | `{ id: NodeId, label: Label, props: Props }` | `lib.rs:1398` |
| `Edge` | `{ id: Option<EdgeId>, from: NodeId, to: NodeId, label: Label, props: Props }` | `lib.rs:1420` |
| `Graph` | `{ nodes: Vec<Node>, edges: Vec<Edge> }` | `lib.rs:1635` |

This is an array of records. Every id is a reference-counted heap string.
Every element carries a tree map. Sem's description of it is accurate.

### The algorithm layer (`grust-algorithms`)

`GraphProjection` is built once from a snapshot and then read by kernels
(`crates/grust-algorithms/src/projection.rs:69`):

| Field | What it holds | Width |
|---|---|---|
| `nodes: Buffer<NodeId>` | dense row to origin id | 16-byte pointer plus a heap string, per node |
| `node_by_id: OnceLock<HashMap<NodeId, usize>>` | origin id to dense row, built on first use | about 25 to 50 bytes a node when built |
| `edges: EdgeTable` | the original edges as columns: source row, target row, and ordinal and external id only when needed | 8 bytes an edge |
| `outgoing: Adjacency` | CSR: row offsets, a target and an original-edge slot per arc, optional weight | 4-byte offsets, 8 bytes an arc, 16 weighted |
| `incoming` | the transpose, built on first use | same |

Where identity appears:

- **Input.** `from_graph` reads a `Graph`. `from_arrow_batches` reads Utf8
  ids, or since 0.24.0 Int64 ids, which it resolves through a direct table
  or a sorted lookup without hashing.
- **The dense-to-origin vector.** Always strings, also for Int64 input: the
  id `42` becomes the node `"42"`.
- **The id map.** Used by one function, `source(&str)`
  (`projection.rs:355`), which a kernel calls to find the row of a source
  given by id.
- **Results.** Every output names nodes by origin id as Utf8 columns
  (`crates/grust-algorithms/src/arrow_output.rs`), including a component
  label, which is a node id.

Where it does not appear: the kernel loops. About thirty kernel modules
run over rows and arcs. `NodeId` occurs in 11 source files of the crate:
the two inputs, the outputs, the projection, and a few result types.

## 3. Why it was chosen

The record, from the repository history:

| Date | Commit | What |
|---|---|---|
| 2026-05-31 | `f1e7ff19`, `b7a3ccef` | Grust starts as a graph API workspace with backend stores |
| June to August 2026 | | the backend adapters (PostgreSQL, SQL/PGQ, pgGraph, Turso, SurrealDB, FalkorDB, LanceDB, Sail, CocoIndex) and the GQL/Cypher layer; dates per adapter not looked up |
| 2026-08-08 | `62f48587` | ids become shared `Arc<str>` to stop cloning strings |
| 2026-09-13 | `7ec17f63` | graph analytics added, as Cypher procedures over a snapshot |
| 2026-09-23 | 0.23.0 | 4-byte CSR targets and offsets |
| 2026-10-02 | 0.24.0 | Int64 ids accepted at the door; columnar edge table |

The reasons, stated plainly:

1. **The first product was a neutral API, not an engine.** One node type
   had to stand for a row in PostgreSQL, a record in SurrealDB, a vertex in
   FalkorDB. Their keys are integers, UUIDs, strings and composite keys. A
   string is the type all of them can be written as. Per-element cost did
   not matter there: every operation ends in a network round trip.
2. **The in-memory reference graph is that API's oracle.** `Graph` as two
   vectors of records is the simplest structure a differential test can
   compare a backend against. It was built to be obviously correct.
3. **Analytics came later and as a guest.** The kernels were added as
   Cypher procedures (`CALL ... YIELD nodeId, score`). A procedure returns
   to a property-graph caller, so results had to name nodes the way the
   caller does. The projection maps ids to rows once and the kernels are
   dense, but the result contract stayed in the caller's identity.
4. **The Arrow path reused the same contract.** When an embedder (the Sail
   extension) handed over Arrow batches, the adapter kept the layout it
   knew: Utf8 `node_id`, `source`, `target`. That is where string identity
   met a graph of 260M edges. The 0.23.0 and 0.24.0 releases are both
   repairs of that meeting.

So there was no decision to build an analytics engine on string ids. There
was a decision to build a property-graph API on them, and no later decision
to give analytics its own model. That second decision is what Sem is now
asking for.

## 4. What it costs, measured

graph500-24 (8,870,942 nodes, 260,379,520 edges), outgoing projection,
Grust 0.24.0, Int64 input. The projection admits 4,994,066,945 bytes
(`F1/banda-024-released-graph500-24-int64-w8.json`, `admitted_bytes`).

| Part | Bytes | Share | Needed by |
|---|---|---|---|
| CSR offsets, 4 bytes a row | 35,483,772 | 0.7% | every kernel |
| CSR targets, 4 bytes an arc | 1,041,518,080 | 20.9% | every kernel |
| Original-edge slot, 4 bytes an arc | 1,041,518,080 | 20.9% | kernels that report edges (paths, trees, flows, bridges) |
| Edge table, 8 bytes an edge | 2,083,036,160 | 41.7% | the same kernels, and `edges()` |
| Identity: the id vector and the reserved id map | 792,510,853 | 15.9% | results; `source()` |

The first two rows are a CSR. They are 1.08 GB, 22% of what is held. The
identity line is 89 bytes a node. An Int64 column is 8.

The CSR and edge-table figures are exact (`projectionStats` reports
2,118,519,932 for the CSR; the edge table is two 4-byte columns). The
identity line is the remainder.

Beside the projection, the extension keeps the staged Arrow rows: 5.95 GiB
for this graph. So a resident graph500-24 costs about 11 GB today, for a
topology of 1.08 GB.

Time: with Int64 ids and 8 workers the outgoing build is 3.1 to 4.0 s and
the undirected one 4.7 s. The floor program of item F0 builds the
undirected CSR in 4.4 s on 4 threads, after reading and mapping ids. So
build time is no longer the model's main cost. Memory and the result path
are.

Results: a WCC answer is two Utf8 columns of 8.9M rows each. Formatting
those strings is in every call, and a caller that wants integers parses
them back. It was not timed apart.

## 5. The `OnceLock<HashMap<NodeId, usize>>`

**What it is for.** One thing: `source(id)`, the row of a node named by
id, for kernels that start from given sources (BFS, shortest paths,
personalised ranking). It is not used to map edges. Edge endpoints are
resolved at build time, by a direct table or a sorted lookup for Int64 and
by a build-time string map for Utf8.

**Why it is a hash map.** History. Ids were strings, and a string's lookup
is a hash. Until 0.24.0 it was built with every projection. Now it is
built by the first kernel that asks, because most never do. Its bytes are
still reserved at the build so that a projection's cost does not depend on
which kernel runs first.

**Is Sem's alternative better.** Yes, on every count that matters here.

| | `HashMap<NodeId, usize>` | Two Arrow columns, sorted by origin id |
|---|---|---|
| Bytes a node | 16-byte key, 8-byte value, control byte, load factor: about 25 to 50, plus the heap string the key points to | 8 (origin id) plus 4 or 8 (dense id); 0 for the dense id if dense order is origin order |
| Lookup of one id | hash the string, follow a pointer to compare | binary search, or a direct table when the ids are compact |
| Full mapping of a column | one random probe per row | a merge join, sequential on both sides |
| Sharing with the engine | none; it is a Rust heap structure | zero-copy; it is a table |
| Build | one insert per node | a sort, which the engine can do out of core |

The point lookup is slower by a logarithm and that does not matter: a
call has a handful of sources. For the operation Sem names, the full
mapping, the sorted columns are the right structure and the hash map is
the wrong one.

**Why it is not that already.** Because the other direction, dense to
origin, is `Buffer<NodeId>`: strings. A two-column mapping is natural only
once origin ids are a column of integers. 0.24.0 took integers at the door
and stopped there; its release notes list "integer identity through the
kernels and their outputs" as not done.

**The stronger form of Sem's point.** With the mapping as a table, it does
not need to live in the kernel process at all. The engine can hold it and
apply it. That is the model of section 6.

## 6. The alternative: logical LPG, physical dense groups

Read from the GraphAr format specification
(https://graphar.apache.org/docs/specification/format), used here as a
memory layout rather than a file layout.

### What GraphAr fixes

- A vertex type is a logical table. A vertex's **internal id is its row
  number in that table, starting at 0**. The table is cut into chunks of a
  fixed size.
- Properties are split into **property groups**: column groups stored
  apart, aligned by internal id. The original key is an ordinary property
  marked `is_primary`.
- An edge type `(src_type, edge_type, dst_type)` has an **adjList table of
  two columns, the internal ids of source and destination**. Stored
  `ordered_by_source` it is CSR, `ordered_by_dest` CSC, unordered COO. The
  ordered forms have an **offset table** giving each vertex's first edge.
- Edge properties are groups aligned with the adjList rows.
- The descriptions (graph, vertex and edge info files) carry names, types,
  chunk sizes and paths. Nothing in them is per-element.

The specification page defines the internal id per vertex type. I did not
find the 16-bit-type plus 48-bit-id packing on that page; the dense-id
report in this folder looks at where it comes from.

### The model

Two layers, with identity moved to the first:

**Logical.** Vertex types, edge types, property groups, which property is
the primary key. This is where `NodeId`, `EdgeId`, labels and maps belong:
as schema and as the values of a key column. Grust's LPG API, Cypher and
the backend adapters live here.

**Physical, per vertex type.** `n` and columns of length `n`. The dense id
is the position. The origin id is one of the columns. The mapping origin
to dense is that column with its positions, sorted, held by the engine.

**Physical, per edge type and orientation.** `offsets[n + 1]` and
`targets[m]`, optionally `weights[m]`, each a plain Arrow buffer. Edge
property groups aligned with the same order.

**The kernel contract.**

```text
Topology { n, offsets: &[u64 or u32], targets: &[u32 or u64], weights: Option<&[f64]> }
  -> result columns of length n (or m), indexed by dense id
```

No id type, no string, no map. Buffers are borrowed from the engine over
the Arrow C data interface, not copied. A result is a dense array: WCC
returns `component[n]`, PageRank `score[n]`. The engine attaches origin
ids by position, which is a zip with the vertex table, not a join, as long
as the table keeps its order.

**Widths.** i64 at every interface, as the project's rule says. Inside, a
target is u32 while `n` is below 2^32, under a checked bound, as now.

**Several vertex types in one projection.** Concatenate their dense
ranges: global id = `base[type] + local id`, with `base` the prefix sums
of the type sizes. The ids stay contiguous, which a CSR needs. A packed
(type, id) handle is for the outside.

### What each side does

| Step | Today | In this model |
|---|---|---|
| Dense ids for vertices | the kernel process, at projection build | the engine (the dense-id report) |
| Map edge endpoints | the kernel process | the engine: two joins |
| Order edges by source | the kernel process: count, prefix sum, fill | the engine: a sort, external if needed |
| Offsets | the kernel process | a grouped count and a prefix sum, or one linear pass over the sorted sources |
| Hold the mapping | the kernel process | the engine |
| Run the kernel | the kernel process | the kernel process |
| Map results back | the kernel process formats strings | the engine, by position |

### What it does to the numbers

For graph500-24, estimated from the structures:

| | Today | Dense model |
|---|---|---|
| Resident for one orientation | 4.99 GB projection plus 5.95 GiB staged rows | 1.08 GB (offsets and 4-byte targets) |
| Edge identity for kernels that report edges | 3.12 GB (edge table and arc slots) | 0 for outgoing: an arc's position is the edge's row in the ordered adjList. A 4-byte permutation per arc for the transpose, built only when such a kernel runs on it |
| Build inside the kernel process | 3.1 to 4.0 s, 8 workers | none: borrow the buffers |
| Result | two Utf8 columns | one numeric array of length `n` |

The sort moves to the engine and is not free there. What the engine pays
for it is the open number; the dense-id report and the Delta ordering
report are about exactly that.

## 7. What survives of Grust, and three ways to get there

What carries over unchanged: the kernels. They already take rows and arcs.
The work budgets, cancellation and the parallel primitives are independent
of identity.

What does not: `from_graph` and `from_arrow_batches` as the main door, the
`nodes` vector and its map, the Utf8 result writers, the edge table as a
mandatory part of a projection, and the extension's staging of rows.

| Option | What changes | Cost | What it leaves |
|---|---|---|---|
| **A. A second door.** Add `Topology::from_csr(n, offsets, targets, weights)` and dense result arrays to `grust-algorithms`. The LPG path stays as an adapter that builds a topology and maps results back. | additive; edge table and id structures become optional parts built only by the adapter | small; one release | two paths in one crate; the public API still shows `NodeId` |
| **B. Split the crate.** A kernel crate with no dependency on `grust-core` identity, owning CSR, budgets and kernels. `grust-algorithms` becomes the LPG adapter over it. | the dependency direction; kernels addressed by dense ids only | moderate; a breaking release | a clean kernel library; Grust's LPG API unchanged for its other users |
| **C. From scratch.** Design "graphs on Sail" around the dense layout: engine-side tables in the GraphAr shape, a kernel library, and no LPG layer on the hot path. | everything outside the kernels | large | Grust as a separate product for the API and Cypher |

My assessment. Sem's criticism of the model is correct for analytics, and
the measured waste is in the layers around the kernels, not in them. B is
the option that removes the contract he objects to and keeps the thirty
tested kernels. A is B's first step and can be taken at once to measure
the dense path end to end. C is a decision about the whole system, to be
taken with the other reports of this folder in hand; if it is taken, B's
kernel crate is still the piece that C would reuse.

## 8. Costs and risks of the dense model

- **Dense ids belong to a snapshot.** Adding vertices appends ids. Removing
  one leaves a hole or forces re-indexing. GraphAr's layout is for
  immutable or append-only data. An LPG with updates needs a rule.
- **Position is the contract.** "Result row i is vertex i" holds only
  while the vertex table keeps its order between the build and the join
  back. The engine must guarantee that order, or carry the dense id as a
  column and join.
- **One type per vertex.** GraphAr puts a vertex in one type's table. An
  LPG node with several labels needs a convention.
- **The engine has to deliver order.** A CSR handed over as sorted
  `(src, dst)` pairs is only cheap if the engine sorts once and remembers
  it. Whether Sail does is the subject of the Delta ordering report.
- **Two id spaces to keep apart.** Dense ids are meaningless outside their
  projection. Every interface has to say which one it speaks.

## 9. Limits of this report

- The memory figures are for one graph and one orientation. The identity
  line is a remainder, not a direct measurement, and includes the id map's
  reservation.
- The dense model's figures are estimates from widths. Nothing was built.
- The GraphAr specification was read from its public page today, through a
  page fetch; the YAML field names were not checked against the reference
  implementation.
- The history in section 3 is from commit subjects and dates. The reasons
  are mine, stated after the fact; no design document of the time records
  a choice between string and integer identity.
