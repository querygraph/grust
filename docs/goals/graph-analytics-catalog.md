# Graph analytics catalog — the road from twelve kernels to Neo4j's "65+"

Status: **PLANNED. Nothing here is implemented.** Written 2026-09-20 as a
long-horizon plan to be executed by a coding model over many sessions. It turns
the two requests in `codex-to-codex.md` (2026-09-19T20:30Z, groups 1–14, and
2026-09-19T23:10Z, groups 15–35) into an ordered, testable programme.

Read this file top to bottom once. After that, a session needs only
"[How to run one group](#how-to-run-one-group)", the group's own entry, and the
[progress ledger](#progress-ledger).

## Why

Nutmeg (`~/src/nutmeg`, `querygraph/nutmeg`) is graph analytics inside Sail:
Grust kernels as a Spark data source and SQL table functions. It takes its whole
catalog from Grust's procedure registry, so **an algorithm exists in Nutmeg the
day it is registered in Grust**. Today Grust registers twelve. Neo4j Graph
Analytics advertises "65+". This plan closes that gap in the order Nutmeg's
comparison page fills, GDS-usage order, so the most-used algorithms land first.

Counting, the same generous way Neo4j counts (every production, beta and alpha
catalog entry, utilities and ML included):

| Source | Entries |
| --- | ---: |
| The twelve on `main` | 9 |
| Groups 1–14 | 20 |
| Groups 15–35 | 36 |
| Row-wise utilities Nutmeg does in Sail SQL (no kernel) | remainder |
| **Total** | **65** |

## Design rules

These hold for every kernel. A kernel that breaks one is not done.

1. **Arrow is the foundation.** Topology is packed CSR in contiguous buffers;
   results leave as typed Arrow through `ArrowResultCursor`; nothing is boxed
   per row and nothing is copied that can be shared. This is the project's
   performance thesis. It is a thesis until the algorithms benchmark measures
   it: every speed claim names its dataset, protocol, envelope and execution
   class, per `AGENTS.md` "Benchmark Neutrality". Never state a result as a
   contest against a named engine.
2. **One contract.** Input a `GraphProjection`; options as named keys with
   unknown keys rejected; typed result struct with accessors; Arrow output;
   cooperative accounting; an independent oracle in the test. Details below.
3. **Semantics before speed.** Every kernel states, in its doc comment and its
   test names, what it does with parallel edges, self-loops, isolates,
   orientation, missing or zero weights, disconnected graphs and ties. GDS and
   NetworKit disagree on several of these; the choice is written down, not
   inherited by accident.
4. **Determinism.** Same projection, same options, same seed: byte-identical
   output, on one thread or many. Randomised kernels take `seed` and use a
   counter-based generator keyed by `(seed, node, iteration)` so parallel
   schedules cannot change results. Ties break toward the smaller node row.
5. **Accounting is part of correctness.** Charge one work unit per unit of
   graph work, in blocks of at most 1024 where a per-unit admit would cost more
   than the unit (the precedent is `PathBuffers::advance` and `binding_forms`).
   All scratch goes through `Buffer` so memory is admitted before allocation.
   A cancelled or exhausted kernel releases its scratch; test it.
6. **No reimplementation of expression or I/O layers.** Kernels know nothing
   about Cypher, Sail, DataFusion or GDS write/mutate modes. Nutmeg owns those.
7. **Provenance.** Ports come from NetworKit via icebug (MIT), or from the
   cited paper. `neo4j-labs/graph` may be read for ideas only; nothing is
   copied or translated from it, and no file cites it as a source.

## Where the work lives

| Repo | Role | Path |
| --- | --- | --- |
| `querygraph/grust` | **The deliverable.** Kernels, options, Arrow output, registry. | `crates/grust-algorithms`, `crates/grust-algorithm-procedures` |
| `querygraph/icecat` | Reference sources and the second Rust implementation. NetworKit C++ under `networkit/cpp`, `include/networkit`; Rust port under `rust/crates/icebug-algorithms`. | `~/src/icecat` (branch `feat/rust-rewrite`; `origin/main` is one badge commit ahead) |
| `querygraph/nutmeg` | The consumer. Path-depends on `../grust`. Has a test that fails when Grust registers a name it cannot dispatch. | `~/src/nutmeg` |
| `querygraph/adversarial-graph-algorithms` | The benchmark that measures every claim. | `~/src/adversarial-graph-algorithms` |

**Decision D1 (recommended, needs the operator's yes):** implement each kernel
**once, in `grust-algorithms`**, reading NetworKit as the reference. Port into
icecat's `icebug-algorithms` only the kernels the benchmark needs a second
independent implementation of (Louvain, betweenness, triangle count first), and
do that after the Grust kernel is merged, as a differential check. Writing every
algorithm twice doubles the work for no product gain; icecat's value here is as
an oracle and a benchmark participant, not as a second product.

## The contract, concretely

Facts from the source at `5e4572f`. Verify before relying on them.

**Projection.** `GraphProjection` exposes `node_count()`, `edge_count()`,
`node_ids() -> &[NodeId]`, `edges() -> &[ProjectionEdge]` (`source`, `target`,
`ordinal`, `id`), `orientation()`, `is_weighted()`, `execution()`. Crate-private:
`outgoing() -> &Adjacency` with `range(node) -> Range<usize>`, `targets.values`,
`edge_slots.values`, `weight(arc) -> f64` (1.0 when unweighted), and
`reverse() -> Arc<ReverseTopology>` (targets only: no weights, no edge slots).
`Orientation` is `Outgoing | Incoming | Undirected`, applied once at build time;
under `Undirected` each non-loop edge appears in both rows, loops once.

**Scratch.** `Buffer::filled(n, v, ctx)?`, `Buffer::capacity(n, ctx)?`,
`Buffer::adopt(vec, ctx)?`; data in `.values`. Never a bare `Vec` that scales
with the graph.

**Errors.** `AlgorithmError` is `grust_procedures::ProcedureError`:
`InvalidArguments`, `Numerical`, `BudgetExceeded`, `Cancelled`,
`DeadlineExceeded`, `OutputContract`, … New typed failures (negative cycle with
witness, cycle in a DAG algorithm) need a variant or a structured payload; see
[P4](#p4--typed-failure-payloads).

**Kernel shape**, copied from `pagerank.rs`:

```rust
pub struct FooOptions { /* validated in the kernel, not by the caller */ }
impl Default for FooOptions { /* the registry's defaults, one source of truth */ }
pub struct Foo { graph: GraphProjection, values: Buffer<T>, /* evidence */ }
impl Foo { pub fn projection(&self) -> &GraphProjection; pub fn values(&self) -> &[T]; }
pub fn foo(graph: &GraphProjection, options: FooOptions) -> Result<Foo> {
    let context = graph.execution();
    context.checkpoint()?;
    /* validate options -> InvalidArguments */
    /* n == 0 returns an empty, valid result */
}
```

**Arrow output.** `into_arrow_results()` on the result type, behind the `arrow`
feature, in `arrow_output.rs` / `arrow_output/`. Batches are bounded by
`ExecutionLimits::batch_rows` and keep their memory reservation alive
(`ArrowResultBatch::reserved_bytes`).

**Registration.** `grust-algorithm-procedures/src/lib.rs`: `register(builder,
name, source: Option<ValueType>, outputs: Vec<Field>, extra_options:
Vec<OptionField>, kernel)`. Options are declared in `options.rs` with a name, a
`ValueType`, a default and nullability, and read back with the same helper that
validates them. `AlgorithmOutput` in `output.rs` has one variant per result
shape and a row cursor over it.

**Tests.** `grust-algorithms/tests/*.rs` build projections with a local
`graph(...)` helper and an `ExecutionContext` with explicit limits. Existing
patterns to copy: exhaustive small-graph oracles (`degree.rs`,
`reachability_oracle.rs`), cancellation releasing scratch (`kernels.rs`), memory
envelope (`degree.rs`), Arrow batch bounds and retained admission
(`arrow_results.rs`), procedure-level Cypher round trip
(`grust-algorithm-procedures/tests/cypher.rs`).

## Prerequisites — shared machinery, built before the groups that need it

Each is its own commit with its own tests. None is an algorithm.

### P1 — `run_on_projection` and public projection options (do first)

The 23:10Z note asks `grust-algorithm-procedures` to expose
`projection_options(&ValidatedArguments) -> Result<ProjectionOptions>` and
`run_on_projection(name, &GraphProjection, &ValidatedArguments) ->
Result<ArrowResultCursor>`. Nutmeg's dispatch `match` in
`nutmeg-graph/src/lib.rs` (~line 700–795) re-parses options by hand for every
algorithm; with these two functions its per-algorithm code drops to zero and
every later group in this plan is served by Nutmeg the day it lands.

Do it before group 1, or thirty-five groups each need a Nutmeg change. Shape:
keep `Kernel` private; add a name → kernel lookup on the registered providers;
`run_on_projection` validates nothing itself (arguments arrive validated),
calls the kernel, converts `AlgorithmOutput` to an `ArrowResultCursor`. That
conversion is new: today `AlgorithmOutput` feeds a row cursor only. Add
`AlgorithmOutput::into_arrow_results`. Gate on the `arrow` feature. Then change
Nutmeg to call it and delete its `match`; its "no dispatch arm" test becomes
"every registered name runs on a two-node graph".

### P2 — incoming adjacency with weights

`reverse()` carries targets only. Betweenness on directed graphs, HITS,
closeness under `Incoming`, Katz and eigenvector all need weighted in-arcs;
bridges and flow need the edge slot. Add a cached `incoming() ->
Arc<Adjacency>` built like `outgoing` with the orientation flipped, charged and
admitted, memoised behind the same mutex as `reverse`. Keep `reverse()` for SCC,
which needs neither weights nor slots. For `Undirected` projections `incoming`
is `outgoing`; return the same `Arc`.

### P3 — a community result type and its Arrow shape

Louvain, Leiden, label propagation, modularity optimisation, k-cut, k-means and
HDBSCAN all return node → community. Add one `Communities` result:
`community_of: Buffer<usize>` (dense ids, canonicalised so community `c`'s id
is its smallest member row — the rule `Components` already uses), optional
`levels` for intermediate communities, a `modularity: f64`, `levels_run`,
`converged`. Arrow: `nodeId: Utf8`, `communityId: Utf8` (the external id of the
canonical member, matching `wcc`), plus scalar columns repeated per row the way
`pagerank` repeats `iterations`/`converged`. One shape, registered once,
reused by seven groups.

### P4 — typed failure payloads

Bellman–Ford needs "negative cycle, here is a witness"; longest-path needs
"cycle, here are `cycleNodeIds`". `topologicalSort` already reports a concrete
cycle through `TopologicalOrder::Cycle`. Follow that precedent: **a detected
cycle is a successful result of a different shape, not an error**. Add the
witness as a result variant and a declared nullable output column. Do not add
error variants for it.

### P5 — deterministic parallel RNG

One small module, `random.rs`: SplitMix64 or Philox keyed by
`(seed, stream, counter)`. No `rand` dependency in the kernel crate; no thread-
local generator. Used by Louvain node order, approximate betweenness, label
propagation, random walks, FastRP, KNN, CELF, generators. Test: identical
output under 1 and N threads.

### P6 — node properties on the projection (before group 15)

The 23:10Z note's one hard prerequisite. `GraphProjection` carries edge weights
only. Add named node property columns — `Float64`, `Int64`, fixed-size
`Float32`/`Float64` lists — admitted and charged like weights, read from
`property.<key>` / `present.<key>` on node batches in `from_arrow_batches` and
from node properties in `from_graph`. Missing values are explicit: a validity
bitmap, and a per-algorithm `MissingProperty` policy mirroring `MissingWeight`.
Needed by groups 15, 16 (filters), 22, 24 (seeds), 28, 30 (`SameCommunity`),
31, 32. Seeded Louvain/Leiden/label-propagation (`seedProperty`) can be added
to groups 1, 7, 8 once this exists; do not block them on it.

### P7 — parallel execution policy

The twelve kernels are single-threaded. NetworKit's community and centrality
kernels are OpenMP-parallel and that is where the speed is. Decide once:
`rayon` behind a `parallel` feature, thread count from `ExecutionLimits` (new
field, default 1), work charged from each worker through the existing atomic
meter. **Land every kernel sequential and correct first; parallelise as a
separate, measured commit** with the sequential result as its oracle
(rule 4). Do not introduce P7 before group 2; betweenness is the first kernel
where it pays.

## Option naming

**Decision D2 (recommended):** Grust names, camelCase, consistent with what is
registered today (`damping`, `tolerance`, `maxIterations`, `weightProperty`,
`orientation`), and a documented GDS alias table that **Nutmeg** applies. Grust
stays a graph library with its own vocabulary; Nutmeg is the compatibility
surface. Every group entry below lists the GDS name beside the Grust name so the
table can be generated rather than remembered.

## The groups

Each entry: what to port, semantics to pin, options (Grust name ← GDS name),
output columns, oracle, cost, and the traps. "NK" is the NetworKit class under
`~/src/icecat`. Sizes are rough kernel + test lines.

### Tier A — groups 1–14 (20 catalog entries)

#### 1. Louvain — `louvain`
- **NK:** `community/PLM.{hpp,cpp}` (320 lines): move phase, `coarsen`,
  `prolong`, optional refine. **Needs P3, P5.**
- **Semantics:** modularity on the projection as oriented. GDS Louvain runs on
  undirected or directed graphs; NetworKit PLM is undirected only. **Require
  `Undirected` orientation in v1 and reject others with `InvalidArguments`**;
  directed modularity (Leicht–Newman) is a later option, not a silent
  reinterpretation. Parallel edges sum their weights. Self-loops count once in
  the node's volume and once in its community's internal weight (NetworKit's
  convention) — assert it in a two-node test because it is the classic
  off-by-two. Isolates form singleton communities.
- **Options:** `resolution` ← `gamma` (default 1.0, finite, ≥ 0); `maxLevels`
  ← `maxLevels` (10); `maxIterations` ← `maxIterations` (10, per level);
  `tolerance` ← `tolerance` (1e-4, minimum modularity gain per level); `seed` ←
  `randomSeed`; `includeIntermediateCommunities` (false); `refine` (false, NK).
- **Output:** P3 `Communities`. Columns `nodeId`, `communityId`, `modularity`,
  `levels`, `converged`; `intermediateCommunityIds: List<Utf8>` when asked.
- **Oracle:** modularity recomputed by an independent O(m) routine in the test
  (this routine becomes group 22's kernel — write it carefully once);
  reported modularity equals recomputed to 1e-12; result modularity ≥ the
  singleton partition's and ≥ the all-in-one partition's; two disjoint cliques
  joined by one edge recover the cliques; fixed seed is byte-stable; exhaustive
  best partition by brute force for n ≤ 8 bounds the answer (Louvain is a
  heuristic: assert "within the optimum", never "equals").
- **Cost:** O(m) per sweep. Charge one unit per arc examined; coarsening one
  per arc. Coarse graphs are new `Buffer` CSRs, freed level by level.
- **Traps:** aggregation must not build a hash map per node — use the dense
  "neighbour community weight" scratch array reset by touched-list, as PLM's
  `turbo` mode does. Size ~600.

#### 2. Betweenness, exact and approximate — `betweenness`
- **NK:** `centrality/Betweenness.cpp` (Brandes), `EstimateBetweenness`
  (pivot sampling — this is what GDS's `samplingSize` does),
  `ApproxBetweenness` (Riondato–Kornaropoulos, ε/δ) and `KadabraBetweenness`
  exist; **port `Betweenness` and `EstimateBetweenness` only.** **Needs P5;
  P2 for directed; P7 pays here.**
- **Semantics:** unweighted uses BFS, weighted uses Dijkstra with exact `f64`
  tie detection — state that equal-cost paths are compared with `==` and that
  this is only meaningful for integral or dyadic weights. Parallel edges count
  as distinct shortest paths (they are distinct edges). Undirected scores are
  halved, as Brandes specifies and GDS does. Endpoints excluded.
- **Options:** `samplingSize` ← `samplingSize` (null = exact); `seed` ←
  `samplingSeed`; `normalized` (false).
- **Output:** `nodeId`, `score: Float64`. **Oracle:** all-pairs shortest-path
  counting by brute force for n ≤ 9 over every orientation; sampled run with
  `samplingSize = n` equals exact; a stated error bound test for the sampled
  run on a fixed graph and seed. **Cost:** O(nm); charge per arc relaxed per
  source. Size ~450.

#### 3. Node similarity — `nodeSimilarity`
- **NK:** no node-pair class (`JaccardSimilarityAttributizer` is absent from
  this tree). Implement directly: sorted-neighbour-set intersection.
- **Semantics:** neighbour **sets** — parallel edges collapse, which differs
  from every other kernel here; say so. Self-loops excluded from the set.
  Similarity is between source-side nodes sharing targets (GDS's bipartite
  reading); pairs with empty intersection are not emitted. Weighted Jaccard and
  cosine use weights when `weightProperty` is set.
- **Options:** `metric` ← `similarityMetric` (`jaccard`|`overlap`|`cosine`);
  `topK` (10); `topN` (0 = all); `similarityCutoff` (1e-42 in GDS; use 0 and
  exclude zeros); `degreeCutoff` (1); `upperDegreeCutoff`; `candidateLimit`
  (Grust-only guard: fail with `BudgetExceeded` rather than explode).
- **Output:** `node1`, `node2`, `similarity`. Streamed: never materialise
  all pairs. **Oracle:** O(n²) pairwise recomputation for n ≤ 12; top-K is a
  prefix of the full sorted list with deterministic tie order. **Cost:**
  Σ over targets of deg²; charge per comparison. Size ~400. Group 16 adds
  node filters as options here once P6 exists.

#### 4. Triangle count and local clustering coefficient — `triangleCount`, `localClusteringCoefficient`
- **NK:** `centrality/LocalClusteringCoefficient.cpp`,
  `edgescores/TriangleEdgeScore`. Two registry entries, one kernel.
- **Semantics:** undirected simple-graph semantics: **parallel edges count
  once, self-loops ignored**; require `Undirected`. Degree-ordered forward
  algorithm (orient each edge low → high degree, intersect sorted lists).
- **Options:** `maxDegree` ← `maxDegree` (skip nodes above; reported as null).
- **Output:** `nodeId`, `triangles: Int64`, `coefficient: Float64` (null when
  degree < 2), plus global `triangleCount`. **Oracle:** O(n³) exhaustive for
  n ≤ 12 including multigraph inputs; `grust-cypher`'s triangle counting
  (`read/count_triangle.rs`) as a second, differential oracle. Size ~300.

#### 5. k-core decomposition — `kCore`
- **NK:** `centrality/CoreDecomposition.cpp` (bucket peeling, O(m)).
- **Semantics:** undirected; parallel edges count toward degree (GDS does the
  same; state it); self-loops ignored.
- **Output:** `nodeId`, `coreValue: Int64`, plus `degeneracy`. **Oracle:**
  naive repeated-peeling. Size ~200. The easiest group; good first review of
  the whole pipeline end to end.

#### 6. Closeness and harmonic centrality — `closeness`, `harmonic`
- **NK:** `centrality/Closeness.cpp`, `HarmonicCloseness.cpp`. **P2** for
  incoming.
- **Semantics:** the disconnected-graph choice is the whole algorithm.
  `closeness`: GDS default is per-component with optional `useWassermanFaust`;
  NetworKit offers `standard` vs `generalized`. Implement GDS's two and name
  the formula in the doc comment. `harmonic`: Σ 1/d, zero for unreachable,
  normalised by n−1.
- **Options:** `useWassermanFaust` (false); `normalized` (true for harmonic).
- **Oracle:** from this crate's own `bfs`/`dijkstra` distances, all sources,
  n ≤ 40. **Cost:** O(nm); charge per arc per source. Shares group 2's
  multi-source scaffolding — build it once. Size ~300.

#### 7. Leiden — `leiden`
- **NK:** `community/ParallelLeiden.{hpp,cpp}`. **Needs P3, P5, group 1.**
- **Semantics:** as Louvain plus the refinement phase; the guarantee is
  **every community is connected** — assert it in the test with this crate's
  `wcc` on each community's induced subgraph.
- **Options:** Louvain's plus `theta` ← `theta` (0.01, refinement randomness).
- **Oracle:** group 22's modularity; connectivity; Leiden's modularity ≥
  Louvain's is *not* guaranteed — do not assert it. Size ~500.

#### 8. Label propagation — `labelPropagation`
- **NK:** `community/PLP.cpp`. **P3, P5.**
- **Semantics:** synchronous vs asynchronous updates give different answers;
  NetworKit is asynchronous-parallel (nondeterministic). **Use a deterministic
  schedule**: fixed node order per iteration from the seed, ties to the
  smallest label. Directed: follow the projection's orientation.
- **Options:** `maxIterations` (10); `seed`; later `seedProperty`,
  `nodeWeightProperty` (P6).
- **Oracle:** fixed point check — at convergence every node holds a label of
  maximal weight among its neighbours; disjoint cliques separate. Size ~200.

#### 9. A\* and Bellman–Ford — `astar`, `bellmanFord`
- **NK:** `distance/AStar.hpp` exists; **`BellmanFord` is absent** — from the
  textbook (queue-based SPFA with a relaxation counter). **P4.**
- **Semantics:** `bellmanFord` is the only kernel that admits negative weights.
  The projection rejects negative weights today (`finite nonnegative`): add a
  `WeightSelection` mode that permits them, off by default, and have every
  other kernel refuse such a projection explicitly. A negative cycle reachable
  from the source is a **result** carrying a witness cycle (P4).
- **A\* heuristic:** a callback cannot cross the registry. GDS's A\* is
  haversine over `latitudeProperty`/`longitudeProperty`. **Do that** (needs
  P6) and also expose the Rust API generically over `Fn(usize) -> f64` with an
  admissibility note. Without P6, land the Rust API and defer registration.
- **Output:** as `shortestPaths`. **Oracle:** `dijkstra` on nonnegative
  graphs; brute-force path enumeration for n ≤ 7 with negatives. Size ~450.

#### 10. Eigenvector, Katz, HITS, ArticleRank — `eigenvector`, `katz`, `hits`, `articleRank`
- **NK:** `EigenvectorCentrality`, `KatzCentrality` exist; **`HubAuthority`
  is absent** — HITS from Kleinberg. ArticleRank is **an option on
  `pagerank`'s code** (`articleRank: true`, or a second registered name
  sharing the kernel) — not a port. **P2.**
- **Semantics:** power iteration with L2 normalisation; report `iterations`,
  `converged`, `residual` like `pagerank` — never assert convergence silently.
  Eigenvector on a disconnected or bipartite graph may not converge: return
  `converged = false`, do not loop. Katz requires α < 1/λ_max; validate against
  a cheap bound (α < 1/maxDegree) and say the bound is sufficient, not tight.
- **Output:** `nodeId`, `score`; HITS `hub`, `authority`. **Oracle:** dense
  matrix power iteration in the test for n ≤ 10. Size ~450 for the four.

#### 11. Biconnected components, articulation points, bridges — `bridges`, `articulationPoints`, `biconnectedComponents`
- **NK:** `components/BiconnectedComponents`. One iterative Tarjan low-link
  pass produces all three; **iterative, never recursive** (the repo's long-
  chain test exists because recursion overflows). Require `Undirected`.
- **Semantics:** parallel edges mean the pair is *not* a bridge — the
  multigraph case NetworKit's simple-graph code does not face; track the
  parent **edge slot**, not the parent node.
- **Output:** bridges: `edgeOrdinal`, `sourceNodeId`, `targetNodeId`;
  articulation points: `nodeId`; components: `edgeOrdinal`, `componentId`.
- **Oracle:** remove each edge/node and recount `wcc`, n ≤ 12. Size ~350.

#### 12. Minimum/maximum spanning forest — `spanningTree`
- **NK:** `graph/KruskalMSF`, `SpanningForest`, `RandomMaximumSpanningForest`.
  **Kruskal with union-find** (path halving, union by size). GDS is Prim from
  a source node; offer `sourceNode` optional and return the forest otherwise.
- **Options:** `objective` (`minimum`|`maximum`); `sourceNode`.
- **Output:** `edgeOrdinal`, `sourceNodeId`, `targetNodeId`, `weight`, plus
  `totalWeight`. **Oracle:** brute-force over spanning trees n ≤ 7; cut
  property check; total weight equals Prim's. Ties by edge ordinal. Size ~250.

#### 13. Max flow / min cut — `maxFlow`
- **NK:** `flow/EdmondsKarp`. Consider **Dinic** instead: same interface,
  O(V²E), and it is what makes this kernel usable past toy sizes. Port
  Edmonds–Karp first as the oracle for Dinic.
- **Semantics:** capacities are the projection weights (`capacityProperty` ←
  GDS); directed; parallel edges are separate capacities; residual graph needs
  a reverse-arc index per edge slot (**P2**).
- **Output:** `maxFlow` scalar; per edge `edgeOrdinal`, `flow`; min cut as
  `nodeId`, `side`. **Oracle:** max-flow = min-cut on every test graph; flow
  conservation and capacity constraints verified; brute-force min cut n ≤ 10.
  Size ~450.

#### 14. FastRP embeddings — `fastRP`
- **NK:** none. From Chen et al. 2019, matching GDS's parameterisation.
  **P5.** First fixed-size-list output: the registry already
  has `ValueType::Numbers` for the declared column; the Arrow output layer needs
  a `FixedSizeList<Float32>` writer, which is new.
- **Options:** `embeddingDimension`; `iterationWeights` (list);
  `normalizationStrength` (0); `nodeSelfInfluence` (0); `seed` ← `randomSeed`;
  later `featureProperties`, `propertyRatio` (P6).
- **Oracle:** dense matrix computation in the test for n ≤ 12 with the same
  seeded projection matrix; determinism; norm bounds. Do not assert embedding
  "quality". Size ~350.

### Tier B — groups 15–35 (36 catalog entries)

Start only after P6 and a checkpoint with the operator. Entries are shorter;
expand each into Tier-A detail when its turn comes.

| # | Registry names | Source | Depends on | Oracle | Note |
| --- | --- | --- | --- | --- | --- |
| 15 | `knn`, `knnFiltered` | NN-descent (Dong et al.) | P5, P6 | brute-force top-k; stated recall bound | metrics: cosine, euclidean, pearson, jaccard, overlap |
| 16 | `nodeSimilarity` filters | — | 3, P6 | as 3 | an option, not a kernel |
| 17 | `yens` | Yen 1971 on `dijkstra` | — | exhaustive simple paths n ≤ 8 | output `shortestPaths` + `index` |
| 18 | `deltaStepping` | Meyer–Sanders | P7 | **`dijkstra`, exactly** | parallel; bucket width option `delta` |
| 19 | `allPairsShortestPaths` | NK `distance/APSP` | — | per-source `dijkstra` | streamed; **never n×n**; charge per pair |
| 20 | `randomWalk` | node2vec walks | P5 | transition frequencies vs exact probabilities, χ² bound | `walkLength`, `walksPerNode`, `returnFactor`, `inOutFactor` |
| 21 | `k1Coloring` | greedy | P5 | no edge joins equal colours; colours ≤ Δ+1 | |
| 22 | `modularity`, `conductance` | NK `community/Modularity`, `Conductance` | P6 | hand-computed small cases | **the oracle for 1, 7, 8, 23, 24 — extract from group 1's test** |
| 23 | `modularityOptimization` | GDS variant | 21, 22 | 22 | output as Louvain |
| 24 | `sllpa` | Xie et al. | P5 | membership sanity | `communityIds: List<Utf8>` |
| 25 | `maxKCut` | GRASP (+VNS) | P5 | brute force n ≤ 10 bounds it | cut cost scalar |
| 26 | `steinerTree`, `kSpanningTree` | on 12 | 12 | brute force small | directed Steiner is a heuristic: say so |
| 27 | `longestPath` | on `topologicalSort` | P4 | DP recomputed | cycle is a result with `cycleNodeIds` |
| 28 | `minCostFlow` | successive shortest paths (absent in NK) | 13, 9, P6 | LP-free check: complementary slackness on small graphs | |
| 29 | `influenceMaximization` | CELF | P5 | greedy without lazy evaluation equals CELF | Monte Carlo: fixed seed |
| 30 | `linkPrediction` | NK `linkprediction/*` (all six present) | P6 for `sameCommunity` | pairwise recomputation | **one kernel**, `metric` option, candidate pairs as an Arrow batch |
| 31 | `kmeans`, `hdbscan` | Lloyd + k-means++; Campello et al. | P5, P6 | k-means: inertia non-increasing, fixed seed; HDBSCAN: small hand cases | |
| 32 | `node2vec`, `hashGNN`, `graphSage` | NK `embedding/Node2Vec`; papers | 20, P6 | determinism and shape only | GraphSAGE last, mean aggregator, inductive only |
| 33 | `randomWalkWithRestarts`, `commonNeighbourAwareRandomWalk` | on 20 | 20 | sampled subgraph is a subgraph; sizes | output node and edge ordinals |
| 34 | `collapsePath`, `generateGraph` | NK `generators/ErdosRenyi`, `BarabasiAlbert`, `Rmat` | P5 | degree-distribution and edge-count bounds | emits grust-arrow edge batches |
| 35 | ML pipelines | — | — | — | **Do not start. Check back.** The likely answer under Sail is to hand the feature DataFrame to an ML library. |

## How to run one group

This is the loop a coding session follows. One group per branch, per PR.

1. **Sync.** `git pull` in `grust`, `nutmeg`, `icecat`. Read the last entries of
   `codex-to-codex.md`. Check the [progress ledger](#progress-ledger).
2. **Read the reference** in `~/src/icecat` (NK path in the group entry). Read
   for the algorithm, not the code shape: NetworKit is OpenMP C++ over a
   mutable graph; this crate is sequential-first Rust over immutable CSR.
3. **Write the semantics first**, as the doc comment and as test names.
4. **Write the oracle and the tests before the kernel.** The oracle must share
   no code with the kernel.
5. **Implement** in `grust-algorithms/src/<group>.rs` (new file; keep files
   under ~500 lines per `AGENTS.md`). Export from `lib.rs`.
6. **Arrow output** under the `arrow` feature; test batch bounds and retained
   admission as `arrow_results.rs` does.
7. **Register** in `grust-algorithm-procedures`: options in `options.rs`,
   variant in `output.rs`, `register(...)` in `lib.rs`, a Cypher round-trip in
   `tests/cypher.rs`.
8. **Gates:** `cargo fmt --all -- --check`; `cargo test -p grust-algorithms
   -p grust-algorithm-procedures --all-features`; `cargo clippy -p
   grust-algorithms -p grust-algorithm-procedures --all-targets --all-features
   -- -D warnings`; then `cargo test` in `~/src/nutmeg` (it path-depends on
   this checkout — before P1 lands its dispatch test **will fail** until an arm
   is added there).
9. **Docs:** `CHANGELOG.md` under `## Unreleased`; the book's algorithms
   chapter (`docs/book/chapters/generalized-algorithms.md`); the ledger below.
10. **Tell the consumer:** append to `codex-to-codex.md` — name, options,
    output columns, semantics that differ from GDS, anything Nutmeg must alias.
11. **Do not release per group.** See cadence.

Required tests for every kernel, by name:

- `<name>_matches_an_independent_oracle` (exhaustive over small graphs,
  all three orientations where the kernel accepts them)
- `<name>_states_multigraph_and_self_loop_semantics`
- `<name>_handles_empty_single_node_and_isolates`
- `<name>_is_deterministic_under_a_fixed_seed` (randomised kernels)
- `<name>_rejects_invalid_options_without_leaking_admission`
- `<name>_observes_cancellation_and_budget_and_releases_scratch`
- `<name>_arrow_batches_keep_bounds_and_admission`

## Order of work and checkpoints

| Milestone | Contents | Checkpoint with the operator |
| --- | --- | --- |
| M0 | P1, then Nutmeg switched to `run_on_projection` | confirm D1, D2 |
| M1 | P3, P5; groups **5, 4, 1** (easy → hard: prove the pipeline on k-core, then triangles, then Louvain) | first Nutmeg comparison rows |
| M2 | P2; groups 6, 2, 8, 3 | P7 decision, with betweenness timings |
| M3 | groups 7, 10, 11, 12 | |
| M4 | P4; groups 9, 13, 14 | **Tier A complete: 29 of 65.** Release. |
| M5 | P6 | design review of node properties before any Tier-B kernel |
| M6 | groups 22, 17, 19, 21, 27, 30 (no randomness, no P7) | |
| M7 | groups 20, 15, 16, 18, 23, 24, 29, 33 | |
| M8 | groups 25, 26, 28, 31, 32, 34 | |
| M9 | group 35 | decide, do not assume |

Group 5 before group 1 is deliberate: the 20:30Z note orders by GDS usage, and
Nutmeg's page should fill in that order, but the *first* kernel through the
pipeline should be the one least likely to fail for algorithmic reasons, so
that pipeline problems surface alone. Groups still **ship** in usage order
within a milestone.

## Measuring

Every kernel joins `~/src/adversarial-graph-algorithms` as cells in the existing
families (path, hub, clusters, layered, uniform, rmat) once it is merged, in the
`grust_upstream_direct` and `grust_arrow` classes, with the C++ NetworKit
participant as the validating reference where NetworKit has the algorithm. That
harness — warmup plus five samples, medians and dispersion, every sample
validated, failures retained — is what may say a kernel is fast. Community
detection validates by modularity within a tolerance and by partition
similarity (NMI), not by equality: two correct Louvain runs differ.

Known hazards from the last round, to not rediscover: per-unit accounting can
cost more than the work (charge in blocks); a clock read per charge is ruinous
on a paravirtual clock (already sampled); results keyed by snapshot position
instead of node id are silently permuted under concurrent loading (key by id).

## Release cadence

Grust releases are named, documented and published as a unit (`PUBLISH.md`).
Do not publish per algorithm. **Release at M1 (first three, proves the path),
M4 (Tier A), then per milestone.** Each is a minor version: new public API.

## Risks

- **Scope.** Thirty-five groups at ~350 lines plus tests is ~25–30k lines.
  Tier A alone is a multi-week programme. The checkpoints exist to stop early.
- **Semantic drift from GDS.** Users will compare numbers. Every deliberate
  difference goes in the kernel doc, the changelog and the coordination note.
- **Heuristics cannot be tested by equality.** Oracles assert invariants and
  bounds. A test that pins a heuristic's exact output is a change detector;
  keep those few, seeded, and labelled as such.
- **Parallelism vs determinism.** Rule 4 is non-negotiable; if a parallel
  schedule cannot be made deterministic, the kernel stays sequential.
- **`f64` ties** in weighted betweenness and k-shortest-paths: stated, tested,
  not hidden.
- **Two implementations.** See D1.

## Decisions (operator, 2026-09-20)

- **D1 — one implementation, in `grust-algorithms`.** icecat gets a port only
  where the benchmark wants a second independent implementation.
- **D2 — Grust option names.** Nutmeg applies the GDS alias table.
- **D3 — directed modularity now.** Louvain and Leiden accept every
  orientation: undirected modularity on `Undirected` projections, Leicht–Newman
  directed modularity otherwise. Triangles, k-core and the bridges family are
  defined on undirected graphs only and still reject other orientations. This
  supersedes the "require `Undirected` in v1" sentences in groups 1 and 7.
- **D4 — Dinic for max flow**, Edmonds–Karp as its oracle (recommendation taken).
- **D5 — rayon from the start.** Kernels are written parallel where the
  algorithm allows, behind a `parallel` feature that is on by default, with the
  thread count taken from `ExecutionLimits`. Rule 4 still binds: a kernel whose
  parallel schedule cannot be made deterministic runs that phase sequentially.
  Every parallel kernel keeps a one-thread path, and the one-thread result is
  the oracle for the many-thread result. This supersedes P7's "sequential
  first".
- **D6 — group 35 decided at M9** (recommendation taken).

## Progress ledger

Update in the same commit as the work. `—` not started, `wip`, `done <commit>`.

| Item | State | Item | State | Item | State |
| --- | --- | --- | --- | --- | --- |
| P1 | done (Grust side) | P2 | — | P3 | — |
| P4 | — | P5 | — | P6 | — |
| P7 | — | 1 Louvain | — | 2 Betweenness | — |
| 3 Node similarity | — | 4 Triangles/LCC | — | 5 k-core | — |
| 6 Closeness/harmonic | — | 7 Leiden | — | 8 Label propagation | — |
| 9 A\*/Bellman–Ford | — | 10 Eigenvector family | — | 11 Bridges family | — |
| 12 Spanning forest | — | 13 Max flow | — | 14 FastRP | — |
| 15–35 | — (see Tier B) | | | | |
