# Graph Nuts at scale: review of the built paths and a sequence to push them

Written 2026-09-28 against `sail-extensions-poc` at `bd8ce9ae8`
(`work/extensions-datafusion-graphs`), `sail-large-graphs` at its remote tip
`b87fb27ac` (`work/extensions-traversal-bench`), Grust 0.23.0, Nutmeg 0.1.0,
and Sem's `querygraph/sail` PR 30 at `b772a112c8`. It answers
[`SCALING-NUTS.md`](SCALING-NUTS.md), Astra's diagnosis of why Nutmeg Banda
fails on large graphs, and it turns that diagnosis into an ordered list of
changes with a measurement gate after each one. The register of every
repository, branch and document this touches is [`GRAPH-NUTS.md`](GRAPH-NUTS.md)
beside it. Both live in `grust/docs`, the home of the Graph Nuts documents;
the Sail fork holds code and evidence, not plans.

Nothing below is a benchmark claim. Every number is either quoted from a
retained evidence file named here, or is an estimate derived from type sizes
and marked as such. Estimates are things to measure, not results.

## Summary

Four execution paths exist and all four run PageRank and WCC end to end:
Pecan (relational, Python-controlled rounds, distributes on Sail workers),
Nutmeg Banda (driver-resident native CSR and Grust kernels), Nutmeg Grenada
(Nutmeg graph tables into Pecan's controller), and Argentea (native
partitions on Sail workers, rounds unrolled into one Sail job). Argentea also
has BFS, WCC and weighted SSSP passing process-cluster qualification, and BFS
passing physical two-host qualification.

The statement "we can't run on large graphs" is true for Banda at the default
budget and false for Pecan. Pecan completed Graph500-24 (8.8 M vertices,
260 M edges) in Sem's 24 GB envelope and completed all four 2 M / 4 M vertex
Graph Kernels inputs in the 180-trial Morrobay campaign. Banda completed the
same 4 M-vertex inputs once its native allowance was raised from 8 GiB to
32 GiB, and it was faster than the relational paths on every PageRank cell
there. Banda has never run Graph500-24, because staging refuses it before the
kernel starts.

Astra's diagnosis is correct and I would sharpen it in three places:

- **Staging is the first wall, but not the only one.** The refused sort
  workspace is about 700 bytes per edge, measured. Behind it sit two further
  tiers that also scale with string identity: the staged Arrow batches Banda
  keeps after projection, and Grust's projection itself, which stores every
  node ID as an owned string plus a hash-map entry and every edge as a
  multi-word record beside the CSR. Fixing the sort alone moves the wall from
  33 M edges to somewhere near 100 M edges. Getting to a billion arcs on one
  driver needs integer identity all the way down and the CSR off the heap.
- **Delta/frontier PageRank is not where the time goes.** In the large
  campaign, the delta method took longer than power iteration for every path
  on every input. On these fixtures the kernel is already fast enough; the
  work is in staging and in the relational shuffle per round.
- **Argentea's iteration model is the structural limit for distributed
  Banda.** Unrolling rounds into one Sail job is bounded by the stage budget,
  now qualified at 32 native phases for PageRank and 128 for BFS. A graph
  needing more rounds than the budget cannot finish in one job, and the
  fallback rebuilds the CSR per job. The plan below asks Sail for the smallest
  thing that removes this: native state that lives as long as a session
  algorithm invocation, not as long as one job.

The sequence, in order and with its gate, is: separate staging from kernel
measurements (S0); integer identity through staging (S1); no sort for kernels
that do not need order, and a spilling sort for those that do (S2); a dense
integer projection with the edge record dropped after CSR construction (S3);
a file-backed CSR so Banda runs a billion arcs on a driver with 16 GB (S4);
Pecan hardening, including checkpoint purge and Sem's delta messaging as a
Pecan method (S5); Argentea continuation across jobs, then the session-scoped
native state ask to Sail (S6). Section 6 lists all 36 Grust kernels and the 3
experimental ones, and says for each which path can carry it to what size once
the sequence lands.

## 1. What exists, with its evidence

| Path | Entry point | Where graph work runs | Largest input with retained passing evidence |
| --- | --- | --- | --- |
| Pecan | `pyspark_pecan.GraphAlgorithms` (`examples/extensions/graph-algorithms`) | Python controls rounds; Sail/DataFusion executes joins and aggregates on workers; Parquet checkpoints between rounds | Graph500-24, 8.8 M v / 260 M e, 24 GB pool, single c5d.4xlarge (Sem's `sem_benchmark`, PR 30); uniform-4194304, 33.6 M e, Morrobay campaign |
| Nutmeg Banda | `sail_nutmeg.Nutmeg.stage/run/drop` over `vendor/nutmeg-graph` | Staging and CSR on the driver; Grust 0.23.0 kernels plus `pagerankDelta`, `wccRandomized`, `wccRandomizedFused` | hub/uniform-4194304 under 32 GiB native / 48 GiB pool / 56 GiB container; refused at 8 GiB native |
| Nutmeg Grenada | Nutmeg `GraphTables` adapted to `GraphAlgorithms` | Same as Pecan; no native staging | Same as Pecan on the Morrobay campaign |
| Argentea | `examples/extensions/argentea` (Rust core, Python client, worker adapters) | Native CSR partitions on Sail workers for one job; Flight shuffle carries messages; rounds unrolled as native stages | Functional fixtures only: eight-vertex two-host BFS, 32-phase residual PageRank, 128-stage WCC and SSSP in process clusters. No performance or capacity evidence |

The Morrobay campaign
(`sail-large-graphs` tip, `docs/development/extensions/pecan-nutmeg-large-benchmark.md`)
is the one place all three driver paths meet on the same inputs, envelope and
timer. Its own reading is the right one: Banda's reference PageRank has the
lowest median full-call time on all four inputs with higher sampled PSS;
delta/frontier is slower than reference for every path; relational WCC fusion
saves 11 to 25 percent of time for 6 to 24 percent more memory. One Pecan WCC
cell timed out at 1,800 s with two passing repetitions at 33 s and an
unexplained cause. Those are the facts a scaling plan starts from.

### Argentea, as of the remote tip

The local `sail-large-graphs` checkout is 76 commits behind
`querygraph/work/extensions-traversal-bench` and carries five modified host
files that are not committed. The remote tip is where Argentea actually
stands. The 76 commits add, in order: job-lifetime binding of native worker
relations and route restoration through optimization; a residual PageRank
core and worker protocol v2 with typed cap failures; bounded BFS in reference,
frontier and direction-switching forms; WCC cores (reference min-label and
seeded star) with cancellation and worker-loss qualification; producer-complete
weighted SSSP; two-host quota refusal and reuse; and Linux ARM64 and Intel
functional qualification with retained evidence bundles. The BFS phase budget
was raised to 128 native stages. The integration document's own list of what
remains is physical two-host WCC/SSSP, resource gates on Linux and physical
hosts, and the larger phase bound on Linux. It states plainly that larger
phase budgets and performance are unqualified.

The design choice that matters for scale is recorded under "Why not keep the
client loop unchanged?": keeping Pecan's job-per-round shape would need an
operation-scoped owner map, a liveness pin between rounds, authenticated state
lookup, abort on owner loss and cleanup on session expiry. Argentea avoided
all of that by unrolling. That was the right first move for a functional
proof. It is also exactly the list of what a session-scoped native state
facility in Sail would have to provide, and section 5 S6 turns it into the
ask.

### Sem's PR 30 against Pecan

PR 30 is a pure-PySpark Pregel (`gfrs-poc/pregel.py`, `pagerank.py`) with
GraphX-style delta messages and a `skip_dest_state` switch, a checkpointer
without purge, and a harness (`sem_benchmark`). It runs on any Spark Connect
server without an extension, which is its portability argument. Its retained
results are Graph500-24 in 172 s at 8.0 GB peak RSS and 7.7 GB written over
19 iterations at tolerance 1e-5, and cit-Patents in 14.7 s at 1.3 GB. It ran
the Nutmeg engine only on a ten-vertex example.

Pecan and PR 30 are the same shape: a Python loop, one relational round per
job, Parquet between rounds. The genuine differences are the message form
(PR 30 sends deltas and can skip re-reading destination state; Pecan's
`optimized` selector is a relational delta/frontier that the campaign found
slower than power iteration), and that PR 30 has been run at 260 M edges while
Pecan has been run at 33.6 M in the audited campaign. The disagreement about
whether "our ideas are different" is settled by running both on Graph500-24 in
the same envelope with the same timer boundary, which S5 schedules. Until
then neither side has evidence that the other's message form is worse.

## 2. Where the memory goes in Banda

Astra's finding is that Banda fails in staging, before the kernel. That is
correct and the refusal record proves it. The rest of this section is the
part `SCALING-NUTS.md` does not say: staging is the first of three tiers that
all scale with the same design decision, which is that node identity is a
Utf8 string from ingestion to kernel.

**Tier 1, the canonical sort.** `normalize_nodes` and `normalize_edges` cast
IDs to Utf8. `canonicalize` then sorts the whole part through Arrow's row
format and admits, up front, a permutation of `(usize, usize)` per row plus
the larger of the encoded keys and a full sorted copy. For uniform-4194304
that admission was 23,511,075,308 bytes for 33,554,395 edges, about 700 bytes
per edge, refused under an 8 GiB allowance and accepted under 32 GiB. Sem's
cit-Patents run reported an 11.6 GB estimate for 16.5 M edges, the same order.
Graph500-24 at that rate is roughly 180 GB. No budget on a single host clears
it.

**Tier 2, the staged batches.** After the sort, the part keeps the sorted
Arrow copy: two Utf8 columns of decimal-encoded integers with offsets, plus
label and edge-id columns, per edge. Estimate from types: 30 to 40 bytes per
edge, so 8 to 10 GB at 260 M edges, held for as long as the graph is staged.

**Tier 3, the projection.** `GraphProjection::from_arrow_batches` requires
Utf8 `node_id`, `source` and `target`. It builds `node_by_id: HashMap<NodeId,
usize>` and `nodes: Buffer<NodeId>` where `NodeId` is an owned string, so
each node costs a string allocation plus a hash-map slot, on the order of 80
to 100 bytes. It keeps `edges: Buffer<ProjectionEdge>` beside the CSR, a
multi-word record per edge holding both endpoints, the ordinal and the
external ID. Estimate: 32 to 48 bytes per edge, so 8 to 12 GB at 260 M edges,
before the CSR itself (4 bytes per arc with `u32` targets in 0.23.0, doubled
if a kernel builds the transpose). Grust's own limit is explicit at 2^32
nodes and 2^32 arcs.

Add the three tiers and Banda at Graph500-24 needs on the order of 200 GB
with the sort, and 20 to 25 GB without it, on a design where the useful
structure, the CSR, is 1 to 2 GB. That ratio is the whole scaling problem for
Banda, and it is why the sequence in section 5 attacks identity encoding
first rather than the sort algorithm.

Two more observations from the evidence:

- **The kernel is not the bottleneck at this scale.** Banda's reference
  PageRank on 33.6 M edges completes the full call, including staging, in
  43 to 45 s. Sail's relational paths take 80 to 83 s. The delta kernel is
  slower than power iteration on every path. Optimizing frontier work before
  fixing staging would be measuring the wrong thing, which is what
  `SCALING-NUTS.md` item 3 already says.
- **Banda's PSS is higher than Pecan's on the same input.** 4.7 GiB against
  3.3 GiB for reference PageRank at 4 M vertices. That gap is the three tiers
  above; it should close to below Pecan once identity is integral, because a
  CSR is smaller than the relational state Pecan materializes.

## 3. Where Pecan's ceiling is

Pecan is the path that already runs at 260 M edges, so its limits are the
ones that matter for going further.

- **Checkpoint purge is host-owned, and PR 30 lacks it.** The Connect API
  has no filesystem list or delete. Pecan removes each round's stage through
  the host-owned `gf.utils.v1` relation (`crates/sail-session/src/extensions/graph_utils`);
  PR 30's checkpointer has no purge. Sem's Graph500-24 run wrote 7.7 GB; a
  1,000-iteration cap at that rate is a disk problem before it is a memory
  problem. (Corrected 2026-09-28; an earlier revision said Pecan had no
  purge.)
- **No declared layout.** Every round re-joins edges to state. The optimizer
  does not know the edge relation is sorted or partitioned by source, so
  there is no way to keep a sort-merge join from re-sorting or to pin a hash
  partitioning across rounds. `prefer_hash_join` is server-wide.
- **No aggregate UDFs from an extension.** The loader registers scalar UDFs
  only, so message reduction must be a builtin (`sum`, `min`), which is fine
  for PageRank and min-label WCC and is not fine for anything with a custom
  combiner.
- **Tolerance is absolute.** With `f64` this is a correctness footnote; with
  `f32` scores on 10^8 vertices a fixed absolute tolerance can stall. Scale
  the tolerance with N or use the L1 residual normalized by mass, as
  `pagerankDelta` already does.
- **Round cost is a full shuffle of the edge relation.** At 260 M edges and
  19 rounds that is what the 172 s is. Delta messaging cuts the message
  volume as the frontier shrinks; it cannot cut the edge scan unless the
  edges are partitioned and the active set is joined to them locally, which
  brings back the layout point.

Argentea is the answer to the last two points and Pecan hardening is the
answer to the first three. They are not competing.

## 4. Where Argentea's ceiling is

- **Bounded rounds per job.** 32 native phases qualified for PageRank, 128
  for BFS in process clusters. A hub graph converges in tens of rounds; a
  chain or a high-diameter road network does not. The fallback of a new job
  per budget rebuilds the CSR from the shuffled input each time.
- **One attempt for native regions.** A worker loss during a job fails the
  query rather than replaying, by design. At scale, that means the expected
  run length is bounded by the mean time to worker failure.
- **Placement through slot groups.** Ownership is validated per job. There is
  no mechanism for a second job to find the partition the first one built.
- **Functional fixtures only.** Eight vertices. Nothing about throughput,
  message volume or memory per partition has been measured.

The first two are consequences of the third. Section 5 S6 orders the work so
that a checkpointed continuation gives adaptive iteration without any Sail
change, and the Sail ask that follows removes the rebuild.

## 5. The sequence

Each step names what changes, why it is next, the gate that decides whether
it landed, and what it is expected to enable. Estimates are marked. Do not
skip a gate.

### S0. Separate staging from kernel in every measurement

This is `SCALING-NUTS.md` items 3 and 6, and it goes first because every later
step is judged by it.

- Record, per trial: staging wall time, staging peak PSS, bytes admitted by
  tier (sort workspace as its three components, retained batches, projection,
  CSR, transpose), temporary file count and descriptor high-water mark; then
  kernel wall time, rounds, active vertices and edges per round, and kernel
  peak PSS. Emit the tiers from `nutmeg-graph`'s existing admission messages
  as structured fields rather than prose.
- Add the two real inputs Astra names, cit-Patents and Graph500-24, to
  `LARGE-GRAPHS.md`'s matrix with the same 24 GB envelope Sem used, so that
  the refusal is reproduced under our harness and the number is ours.
- Set and record `ulimit -n`.

Gate: one run of each path on cit-Patents with the tiered accounting in the
CSV. Banda is expected to refuse; the refusal record with the three components
is the deliverable.

### S1. Integer identity through staging

Change `normalize_nodes` and `normalize_edges` to keep `Int64` IDs as `Int64`
when the input column is integral, and to keep the Utf8 path only for inputs
that are strings. Give the staged schema two shapes, `node_id: Int64` and
`node_id: Utf8`, and make every downstream consumer accept both. The
canonical sort's row-format keys become fixed-width and the sorted copy is a
primitive column.

Estimate from types: sort workspace drops from about 700 to about 90 bytes
per edge, roughly 24 GB for Graph500-24 with the sort still on. That alone
does not clear a 24 GB budget; S2 does. But it makes cit-Patents fit at
8 GiB and the 4 M-vertex inputs fit at the default budget, which is what the
next campaign needs.

Gate: uniform-4194304 stages under the default 8 GiB allowance; `pagerank`
result is bit-identical to the Utf8-staged result (the fixed-point check in
the campaign harness); the tiered accounting shows the sort component.

### S2. Sort only when a kernel needs order, and spill when it does

Canonical order exists so that a staged part is the same whatever order its
rows arrived in, which matters for kernels whose output depends on edge order
(anything with tie-breaks by ordinal: `dfs`, `topologicalSort`, `spanningTree`,
`yens`, `k1Coloring`, `louvain`, `leiden`, `labelPropagation`, `fastRP` seeds)
and does not matter for kernels whose output is order-independent
(`pagerank`, `wcc`, `scc`, `degree`, `bfs` distances, `dijkstra` distances,
`triangleCount`, `kCore`, and the rest of the value-only kernels). Today
order is a staging property. Make it a kernel property:

- Stage with `order = asStaged` by default and record the arrival order as a
  stable ordinal. This is the path the refusal message already points at, and
  its determinism caveat is answered by the ordinal.
- Declare, per kernel in `grust-algorithm-procedures`, whether it reads the
  ordinal. A kernel that does gets a sorted view built on first use, and the
  sort runs through DataFusion's `SortExec` under the session's memory pool
  with disk spill, instead of Nutmeg's in-memory permutation. Sail already
  owns a spilling sort; Nutmeg should not carry a second one.

Estimate: the sort tier disappears for PageRank, WCC, BFS, SSSP and degree;
the ordered kernels pay a spill to local disk at the size of the edge list.

Gate: Graph500-24 stages on a 24 GB pool with `pagerank` and `wcc` producing
results that pass the campaign's fixed-point and union-find checks; the
ordered-kernel path is exercised by `topologicalSort` on cit-Patents with the
spill directory and file count recorded.

### S3. A dense integer projection

`GraphProjection::from_arrow_batches` is where strings become the working
representation. Add an `Int64` entry that builds the projection without owned
strings: a dense remap from sparse `i64` IDs to `u32` indices (a sorted
`Vec<i64>` with binary search, or a hash map of `i64`, both under admission),
`u32` CSR offsets and targets, and no `ProjectionEdge` buffer unless the
kernel declared it needs ordinals or external edge IDs. Results map back to
the original `i64` on emission.

This is a Grust change, not a Nutmeg one, so it goes on a Grust branch with
the same discipline as `work/narrow-targets` and `work/pagerank-f32`, and it
is the change that makes the `precision` and index-width discussion concrete:
`u32` indices with `i64` external IDs, `f64` scores by default.

Estimate from types: 8 to 12 bytes per node and 4 bytes per arc plus 4 for
the transpose when built; Graph500-24 undirected is about 4 GB. With the
staged batches dropped after projection (they are re-readable from the
caller's tables), Banda on a 16 GB driver holds Graph500-24 with room for
state vectors.

Gate: Graph500-24 `pagerank`, `wcc`, `bfs` and `dijkstra` complete on Banda
in a 24 GB pool; tiered accounting shows projection bytes per edge below 16;
results match Pecan's on the same input under the campaign checks.

### S4. A file-backed CSR for Banda beyond memory

Once the projection is integers, the CSR is two flat arrays and can live in a
file. Write the CSR (offsets, targets, optional weights, optional transpose)
to the driver's local disk at staging and memory-map it; keep vertex state in
RAM. A PageRank sweep is then one sequential read of the target array, which
at Graph500-24 is about 1 GB per sweep and runs at SSD bandwidth. Vertex
state for 10^9 vertices in `f64` is 8 GB per vector; frontier kernels need a
bitset and one or two vectors.

This gives one driver a ceiling near Grust's 2^32 arcs on a machine with 16
to 32 GB, for every kernel whose access pattern is a sweep over adjacency or
a frontier expansion. Random-access kernels (`betweenness`, `closeness`,
`harmonic`, `maxFlow`, `nodeSimilarity`) run but pay page faults; they are
listed with that caveat in section 6.

Gate: Graph500-25 (33.5 M v / 537 M e) `pagerank` and `bfs` on Banda with a
16 GB pool and the CSR on disk; page-cache bytes and read bytes per sweep
recorded; results checked against Pecan on the same input.

### S5. Pecan hardening, and settling the PR 30 question

- **Purge.** Already done for Pecan through the host-owned `gf.utils.v1`
  relation; what remains is a session-scoped temporary directory that Sail
  deletes on session close, so that a client that dies mid-run leaves
  nothing behind. Propose it through the same channel as the session
  factory hook (merged upstream as lakehq/sail#2630).
- **Layout.** This is the item that carries graphframes-rs's speed, and it
  has its own document: [`GRAPHFRAMES-RS-PARITY.md`](GRAPHFRAMES-RS-PARITY.md).
  In short: write every checkpoint hash-bucketed and sorted by its key, read
  it back through a provider that declares that partitioning and order, so
  the round's joins need no shuffle and no sort; fix the job planner's
  left-join rule that repartitions regardless; measure against the
  graphframes-rs CLI on the same host.
- **Message form.** Port PR 30's delta message with `skip_dest_state` into
  Pecan as a third PageRank method beside `reference` and `optimized`. Then
  run all three, and PR 30 itself, on cit-Patents and Graph500-24 in one
  envelope with one timer boundary. Publish the table with the same neutrality
  rules as the campaign. This is the only way to answer whether the ideas are
  different in a way that matters.
- **Tolerance.** Make Pecan's convergence test the mass-normalized L1
  residual, matching `pagerankDelta`, and scale any absolute tolerance by N.
- **Aggregate UDFs.** Ask for `AggregateUDF` registration in the extension
  loader alongside `ScalarUDF`. It is a loader change with no protocol
  change. It unblocks custom combiners (label propagation with weighted votes,
  HITS, Katz) on the relational path.

Gate: Graph500-24 with purge active leaves no checkpoint files at exit; the
four-method PageRank table exists with retained outcomes; one aggregate UDF
round-trips through the loader.

### S6. Argentea: continuation, then session-scoped native state

- **Continuation without a Sail change.** When a job reaches its phase
  budget unconverged, have each owner write its partition's CSR and state to
  local disk under a job-scoped path and emit the path in its result stage.
  The client submits the next job with those paths as inputs; owners re-read
  their own partition locally when placement puts them on the same worker,
  and fall back to the shuffled rebuild otherwise. This makes iteration
  adaptive today, at the cost of a local disk write per budget, and it
  measures how often placement is stable, which is the number the Sail ask
  needs.
- **The ask.** Native state that lives for one algorithm invocation across
  jobs in a session: an owner map keyed by `(operation, partition)`, a
  liveness pin, abort on owner loss, cleanup on session close. This is the
  list already written in the integration document. It is the same family of
  change as the session factory hook and the memory-lease ABI: an embedding
  hook, nothing graph-specific. File it as a maintainer request in the same
  form as `maintainer-request.md`, with the continuation measurements as the
  motivation.
- **Retry.** With state on local disk, a lost owner can be replaced by
  rebuilding one partition rather than failing the query. That is the second
  half of the ask.

Gate: an Argentea PageRank on a chain fixture that needs more than 32 rounds
completes through continuation; placement stability recorded over 20 runs;
the maintainer request drafted with those numbers.

### Order and dependencies

S0 first, always. S1 to S3 are strictly ordered and are the critical path;
they are all Nutmeg or Grust changes with no Sail dependency, and S3 is
where "Banda cannot run on large graphs" stops being true at the 24 GB
envelope. S4 depends on S3. S5 is independent of S1 to S4 and can run in
parallel; its message-form comparison should wait for S0's harness so it is
measured the same way. S6 depends on S3, because Argentea partitions share
Grust's projection.

## 6. Every kernel, and how far each path can carry it

Grust 0.23.0 registers 36 kernels through `grust-algorithm-procedures`; Nutmeg
adds three experimental ones. Ceilings below are what the sequence targets,
not what is measured today. "Sweep" means the kernel's inner loop is a pass
over adjacency in index order and suits S4's file-backed CSR; "random" means
it follows pointers and would page-fault on it. "Pregel" means one message
per edge per round with a builtin or UDAF reduce, so Pecan and Argentea can
carry it. "Join" means it is naturally a relational self-join. "Global"
means it is sequential or needs whole-graph random access and belongs on
Banda alone, with a sampled or approximate variant for scale.

| Kernel | Shape | Banda in-core after S3 (24 GB) | Banda file-backed after S4 | Pecan after S5 | Argentea after S6 | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| degree | sweep | 2^32 arcs | 2^32 arcs | yes, one aggregate | yes | trivial on every path |
| pagerank | sweep, Pregel | Graph500-24 | Graph500-26 | yes, at 260 M e today | yes | reference method is the fast one on measured inputs |
| pagerankDelta | sweep, Pregel | same | same | as Pecan `optimized` | residual core exists | slower than reference on all measured inputs; keep for high-diameter graphs |
| articleRank | sweep, Pregel | same as pagerank | same | yes | same core, different normalization | one-line variant of pagerank |
| eigenvector | sweep, Pregel | same | same | yes | yes | power iteration with normalization barrier |
| katz | sweep, Pregel | same | same | yes | yes | bounded rounds by attenuation |
| hits | sweep, Pregel | same | same | needs transpose per round; yes | yes with two message types | two vectors, two sweeps per round |
| wcc | sweep, Pregel | Graph500-24 | Graph500-26 | yes, min-label; fused contraction measured | yes, both cores exist | union-find on Banda is not a sweep but is linear and in-core |
| wccRandomized / wccRandomizedFused | sweep, Pregel | same | same | yes, measured | yes | fusion helps relational, not native, on measured inputs |
| scc | sweep, Pregel (forward-backward) | Graph500-24 | Graph500-25 | yes, as coloring/FW-BW rounds | yes, two message directions | Tarjan on Banda is sequential and random; use FW-BW or coloring for scale |
| labelPropagation | sweep, Pregel | Graph500-24 | Graph500-26 | needs weighted-vote UDAF | yes | order-dependent tie-breaks: needs ordinal or seeded tie-break |
| bfs | frontier, Pregel | Graph500-24 | Graph500-26 | yes, level rounds | yes, three methods qualified | direction-optimizing needs the transpose |
| multiSourceBfs | frontier, Pregel | same, state × sources | same | yes, source-tagged messages | yes | state grows with source count |
| dijkstra (SSSP) | frontier, delta-stepping | Graph500-24 weighted | Graph500-25 | yes, Bellman-Ford rounds or delta buckets | yes, producer-complete core exists | classical heap Dijkstra is random; delta-stepping is the scalable form |
| bellmanFord | sweep, Pregel | Graph500-24 | Graph500-26 | yes | yes | negative cycles need the certificate |
| shortestPaths (unweighted) | frontier | as bfs | as bfs | yes | yes | bfs with path reconstruction |
| topologicalSort | sweep (Kahn) | Graph500-24 | Graph500-25 | yes, in-degree rounds | yes | needs ordinal for a stable order |
| longestPath (DAG) | sweep | as topologicalSort | as topologicalSort | yes, after topo rounds | yes | |
| kCore | sweep, peeling rounds | Graph500-24 | Graph500-25 | yes, degree rounds | yes | rounds bounded by max core |
| triangleCount | join | Graph500-24 with S3, memory-bound by degree | Graph500-25 | yes, two-hop self-join, the classic relational case | possible, partition by source | relational path is the natural one at scale |
| localClusteringCoefficient | join | as triangleCount | as triangleCount | yes | possible | |
| nodeSimilarity | join, all-pairs on neighborhoods | 10^7 nodes with top-k | random on file CSR | yes, with top-k pruning | possible | output size is the limit, not input |
| fastRP | sweep, Pregel | Graph500-24 with `f32` embeddings | Graph500-25 | yes, dense vectors per round | yes | embedding dimension × N dominates memory |
| k1Coloring | sweep, Pregel | Graph500-24 | Graph500-26 | yes | yes | needs seeded tie-breaks |
| closeness | global, one BFS per source | 10^6 nodes exact; sampled beyond | random | sampled sources as multiSourceBfs | sampled | exact is O(N·M); sampling is the scale answer |
| harmonic | global | as closeness | as closeness | sampled | sampled | |
| betweenness | global (Brandes) | 10^6 nodes exact; sampled beyond | random | sampled pivots, two passes per pivot | sampled | same as closeness, plus dependency accumulation pass |
| louvain | global, sequential moves | 10^7 nodes in-core | random | needs local-move rounds as UDAF; approximate | not without a new core | scalable form is a Pregel-style local move plus aggregation; semantics differ from sequential |
| leiden | global | as louvain | random | as louvain | no | refinement step is sequential |
| yens (k shortest) | global, repeated Dijkstra | 10^7 nodes | random | no | no | small-k only; not a scale target |
| allPairsShortestPaths | global, O(N·M) | 10^4 nodes | no | no | no | output is N^2; not a scale target beyond small graphs |
| dfs | global, sequential | 10^8 nodes in-core | random | no | no | inherently sequential |
| articulationPoints / bridges / biconnectedComponents | global (Tarjan DFS) | 10^8 nodes in-core | random | no | no | sequential DFS; a parallel variant (chain decomposition) would be new work |
| spanningTree | global (Kruskal/Prim) | 10^8 arcs in-core | sort-then-sweep with S2's spill | yes as Borůvka rounds | yes as Borůvka | Borůvka is the Pregel form |
| maxFlow / minCut | global, augmenting paths | 10^6 nodes | random | no | no | not a scale target |

Counting: of 36 Grust kernels plus 3 experimental, 25 are sweep, frontier,
Pregel or join shaped and can be carried by all four paths to Graph500-24 or
beyond once S1 to S6 land. Seven more (closeness, harmonic, betweenness,
louvain, leiden, spanningTree, scc's Tarjan form) have a scalable variant
that changes the algorithm and must be named as such. Seven (yens, APSP, dfs,
articulationPoints, bridges, biconnectedComponents, maxFlow, minCut) are
in-core Banda kernels whose reach is set by S3 and S4 and which should not be
described as distributed.

## 7. Fixtures and envelopes for the gates

| Input | Vertices | Edges | Purpose |
| --- | ---: | ---: | --- |
| hub/uniform-2097152, -4194304 | 2.1 M / 4.2 M | 16.8 M / 33.6 M | existing hash-pinned campaign inputs; regression floor |
| cit-Patents | 3.7 M | 16.5 M | Sem's real graph; S0 and S1 gates |
| Graph500-24 | 16.8 M (8.8 M non-isolated) | 268 M tuples | Sem's capacity graph; S2, S3, S5 gates |
| Graph500-25 | 33.6 M | 537 M tuples | S4 gate |
| Graph500-26 | 67.1 M | 1.07 B tuples | S4 ceiling probe; expect the 2^32-arc limit to be the next wall with the transpose |
| chain-10^6 | 1 M | 1 M | S6 continuation gate; diagnostic only, never a scaling claim |

Envelopes: 24 GB pool on one host to reproduce Sem's runs; the qualified
32 GiB native / 48 GiB pool / 56 GiB container for like-for-like with the
Morrobay campaign; a 16 GB pool for S4. Every run records host, envelope,
steal, command and timer boundary as the campaign does. Publishable timings
come from a dedicated host and none is available now, so S0 through S6 gates
are functional and capacity gates with times recorded as observations.

## 8. The design question: why build a CSR at all?

Sem's objection, after his `pagerankDelta` attempt failed, is not about
tuning. It is that if the data already sits in tables, gathering it into an
in-process CSR is the wrong concept: he measured a DuckDB-based CSR builder
that spills on sort, found it still could not take a billion edges, and found
that on graphs of a few hundred million edges the CSR construction consumed
the advantage the kernel then earned. His conclusion is that the work is to
make Sail skip sorting and repartitioning, not to make a native path faster.

Three things in that are simply right and the plan already depends on them:

- **His crash is the staging refusal, not the kernel.** `pagerankDelta`
  never ran; the default 8 GiB native allowance refused the canonical sort's
  workspace before any kernel code executed. The record must say "staging
  admission failure", as `SCALING-NUTS.md` requires. Calling it a
  `pagerankDelta` crash is what the tiered accounting in S0 exists to
  prevent.
- **The sort is the cost, and it is optional.** S2 makes canonical order a
  per-kernel property instead of a staging property. PageRank and WCC do not
  read edge order and should never pay for it. What is left after S1 to S3 is
  a dense remap and one counting pass, which is the same work a relational
  engine does to hash-partition the edge table once.
- **Skipping repartitioning is the relational path's problem too.** Every
  Pecan and PR 30 round re-shuffles the edge relation because nothing tells
  the optimizer the edges are already partitioned and sorted by source. S5's
  cached sorted edge view and the "declared layout" ask are exactly "make
  Sail skip sorting and repartitioning". That change helps his design as
  much as ours.

Where the plan disagrees is on "why at all". The answer is a crossover, and
it is measured rather than argued. On the 33.6 M-edge inputs, Banda's
complete call, including the sort it should not have paid for, took about
half the relational paths' time. That ratio is what a CSR sweep buys against
a per-round join once the graph is in memory, and it grows with the number
of rounds. It is worth nothing when the graph does not fit one machine,
which is Sem's regime and the reason Argentea and Pecan exist. So the plan
keeps both and puts the crossover into S0's gate: for each input, record
staging time and kernel time separately for Banda, and per-round time for
Pecan, so the point at which a CSR pays for itself is a number in the CSV.
If S3 does not bring Banda's staging below the relational path's first-round
cost on Graph500-24, that is evidence for Sem's position and the plan says
so.

One more of his claims should be tested rather than accepted: that a
spilling CSR builder cannot take a billion edges. A billion arcs of `u32`
targets is 4 GB; the offsets are 8 bytes per vertex. What could not be
taken was a billion edges through a sort with string or 16-byte keys. S4's
file-backed CSR is designed to find out whether the compact form fits where
the sorted one did not.

## 9. What is true today, per path

- Pecan runs Graph500-24 on one c5d.4xlarge in 24 GB and lacks purge,
  layout control and custom reducers. It is the path to say "yes" with today.
- Grenada is Pecan with a different entrance and inherits everything above.
- Banda runs 33.6 M edges in a 32 GiB native allowance and is the fastest
  driver path there. It refuses 33.6 M edges at 8 GiB and has never run
  260 M. Its limit is string identity in three tiers, not the kernels.
- Argentea has functional distributed PageRank, BFS, WCC and SSSP on tiny
  fixtures, bounded rounds per job, and no capacity or performance evidence.
- Sem's PR 30 runs Graph500-24 in 172 s and 8 GB with no extension, and has
  not been compared to Pecan on the same envelope.

The sequence above is written so that each of those sentences changes in
order: S3 changes Banda's, S5 changes Pecan's and PR 30's, S6 changes
Argentea's, and S0 decides whether section 8's crossover exists.
