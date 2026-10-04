# F2a: current Banda source, admission and wrapper handoff

Prepared 2026-10-02T00:29:36.131845+00:00. Read-only source/evidence review; no Docker, engine, large download,
Sail changes, staging or profile execution. Governing repository: querygraph/grust
AGENTS.md. This is preparation for F2a **after B8** (SEM-REVIEW-2.md:603 and
codex-to-codex.md:10304–10308), not a measured result.

## Pins and existing ABI

- Controller source: `f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a`, host checkout
  `/Volumes/Apo/graph-tests/workspaces/sem-review-20261001/pecan-f3b3ef8fc`.
- Native source: `ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73`; binary source:
  `56194b170155301ba91077f0ba3df31fe2c78b6b`; frozen runtime harness:
  `6ae2e43a903c2cee02da170465c922c72b76198e`.
- A1 image: `sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e`;
  Sail binary SHA256 `5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec`;
  native `.so` SHA256 `eb0be839de652e059799dea3bba22cc0908998bd97cfa2f4cf04c67817e2ee50`.
- Banda native `nutmeg/src/lib.rs` blob is exactly `9863b3dcffc0ae17277e22d6eaaffa9b80467540`
  at ffcf and f3; runtime.py blob `11c0d0f57245b7d95bbd914c76f02d141ad33d36`
  is equal at frozen6ae and f3. Relevant ffcf/runtime561→f3 changes are Argentea
  input lifetime fixes, **not** a Banda rebuild. Guard actual installed package,
  extension module origin, native hash and loader receipt; do not infer wheel
  identity from matching one file.
- Manifest is API1/DataFusion55.1.0/Arrow59.3.0, driver placement, at most2inputs;
  native binding imports named repr(C) MemoryLease version/size/exact prepaid quota.
  Retained leases cover session, graph snapshots, native reads and Arrow outputs.
  Existing runtime validates versions before loading capsules.
- Published algorithm dependency is grust-algorithms/grust-algorithm-procedures
  **0.23.0**, registry VCS source `5c41bcb3c69e4cf4d285e6ec3a8ed239473ae1f1`,
  not current Grust HEAD.

Primary source links: [manifest/bind](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/nutmeg/python/sail_nutmeg/__init__.py#L12-L36),
[loader validation](https://github.com/querygraph/sail/blob/56194b170155301ba91077f0ba3df31fe2c78b6b/crates/sail-session/src/extensions/manifest.rs#L31-L46),
[lease ABI](https://github.com/querygraph/sail/blob/56194b170155301ba91077f0ba3df31fe2c78b6b/crates/sail-native-resource-ffi/src/lib.rs#L9-L94).

## Lifecycle and phase observation

1. Fresh owned engine process/server/session; create lazy Parquet relations from
   exact admitted original paths. Calling `spark.read.parquet` does not read all rows.
2. `Nutmeg.stage(graph,nodes,edges,order='asStaged')` eagerly collects its small
   mutation receipt; its execution consumes both input relations, normalizes
   structural IDs to UTF8 and commits an immutable revision. asStaged avoids
   canonical sorting; it still normalizes/admit-retains batches and ID strings.
3. `Nutmeg.run` returns a **lazy DataFrame**. First execution builds/caches the
   projection, executes the kernel, creates Arrow output and feeds a bounded
   channel to the Parquet writer. Full result write is the action.
4. Repeat the declared calls in the same session/revision; write **each** complete
   result to a distinct fresh directory. Drop graph, release output references,
   stop session/server and check staging payload/child closure. Whole engine
   launch→exit includes startup, staging, calls, diagnostics and cleanup.

Existing evidence cannot produce Sem's four separate wall phases:

| Required phase | Current observable fact |
|---|---|
| Parquet read | included in stage action with normalization/commit; no standalone reader elapsed counter |
| CSR and graph build | native projection_builds.seconds/admitted_bytes; outgoing only, transpose may build lazily on first kernel |
| Algorithm | lazy run() measures planning; read diagnostics have rows/batches/state/work/peak, not kernel elapsed |
| Parquet write | action includes projection+kernel+Arrow conversion and backpressure, not isolated exporter elapsed |

`graph_cell.py:155–159` adds an explicit projectionStats job and labels the later
write `kernel_and_output_seconds` (205–207). This composite is honest, but adding
that job changes the baseline call path and still does not separate read/kernel/write.
Do not subtract projection.seconds from write time and call the remainder kernel;
do not collect millions of Python rows to manufacture a separate write phase.

Exact four-phase observation is a **contract blocker** for the requested format.
Proposed instrumentation (requires root-reviewed source changes and new package
pins/gates): native build begin/end including separately identified lazy transpose;
kernel begin/end around the eager algorithm result construction; output-conversion
and emit-blocked intervals; Parquet scan/operator and writer spans/jobs identified
by the same call ID. Existing Grust kernels return a completed algorithm result to
an Arrow cursor, then `drain` converts/emits it. A span around all of run_each would
include conversion and blocked send, so its definition must be narrower. Streaming
scan/staging and conversion/write intervals may overlap: record monotonic begin/end
spans and inclusive/exclusive definitions, do not assert four disjoint additive times
without a materialization boundary. Retain coarse original E2E as the primary measure.

Sources: [stage execution](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/nutmeg/src/mutation.rs#L290-L352),
[lazy client](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/nutmeg/python/sail_nutmeg/client.py#L52-L75),
[projection cache/build](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/vendor/nutmeg-graph/src/lib.rs#L1338-L1407),
[kernel then Arrow cursor drain](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/vendor/nutmeg-graph/src/lib.rs#L1528-L1570),
[bounded blocking emission](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/vendor/nutmeg-graph/src/lib.rs#L3114-L3132),
[status fields](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/nutmeg/src/diagnostics.rs#L112-L134).

## Calls, semantics and reuse contract

Recommendation for a minimal reusable baseline: separate WCC and PageRank series;
within each, compare one call with **three repetitions of the same algorithm/options**.
A mixed WCC+PR+third sequence is a separately named workload only after root binds it.
Cache key is graph revision plus orientation,nodeLabels,relationshipTypes,
weightProperty,defaultWeight (`vendor/nutmeg-graph/src/lib.rs:2233–2247`), so graph
name alone does not establish CSR reuse. Retain build keys/counts and revision per call.
No unrelated projectionStats/count/cert/input-validation job belongs in the timer.

- Ordinary `wcc` is Grust concurrent/sequential union-find over original edges,
  ignoring direction, with O(V) scratch. Its component label is the original ID
  of the **minimum projection row**, not guaranteed minimum signed numerical ID
  under asStaged. Official partition equivalence is the necessary oracle; numeric
  canonical labels are a separately declared optional contract. Keep raw UTF8 labels
  and an explicitly lossless decimal→BIGINT adapter only if required by the comparator.
  Choose `wcc` versus experimental `wccRandomized*` explicitly; do not change methods.
- Ordinary `pagerank`: f64, uniform start/personalization, damping.85,
  dangling mass redistribution, outgoing orientation; options maxIterations10,
  tolerance0 match the external worker's cap/tolerance settings. **Tolerance0 is
  still a stopping rule** and may stop at an exact fixed point before10. Keep actual
  iterations/converged/residual, raw score and exact output IDs; do not describe this
  as unconditional fixed10. External worker also divides scores by their final sum.
  Establish full vector/tolerance equivalence before any comparative claim.
- Preserve original signed64 IDs including high-bit/2^53+1 through string adapters;
  inspect physical output types and exact IDs outside engine time, never float IDs.

Sources: [ordinary WCC](https://github.com/querygraph/grust/blob/5c41bcb3c69e4cf4d285e6ec3a8ed239473ae1f1/crates/grust-algorithms/src/traversal.rs#L216-L290),
[component output labels](https://github.com/querygraph/grust/blob/5c41bcb3c69e4cf4d285e6ec3a8ed239473ae1f1/crates/grust-algorithms/src/arrow_output.rs#L345-L352),
[PR options/recurrence](https://github.com/querygraph/grust/blob/5c41bcb3c69e4cf4d285e6ec3a8ed239473ae1f1/crates/grust-algorithms/src/pagerank.rs#L25-L55).

## Admission and envelope

Same A1 image,16CPUs/32GiB/noSwap/init, local server, declared native concurrency16,
partition16, greedy Sail pool30GiB. **Root must bind the native quota:** B8's256MiB
cannot retain these staged graphs. A possible24GiB prepaid native share leaves6GiB
in the Sail pool and2GiB cgroup headroom; it is a candidate, not evidence of fit.
Quota is admitted from the Sail pool, not additional to it. Native graph rows,
strings/maps, CSR/edge slots, temporary construction buffers, kernel vectors and
output/lease lifetimes must all fit simultaneously; admission refusal is retained.

Current0.23 CSR **targets and row offsets are both u32**, checked maxima u32::MAX
nodes/arcs, no64bit fallback. External IDs remain lossless and separate from dense
internal indices. This baseline limitation differs from the StageF proposal for
usize/u64 arc offsets plus64bit fallback; do not silently apply that proposed F1 change.

CsrEstimate is explicitly **not a peak memory estimate/admission**. For actual
footer V/E, outgoing unweighted floor is `4*(V+1)+12*arcs` bytes, plus `8*V`
construction positions. The declared three usize fields and Option<EdgeId>, with
EdgeId wrapping Arc<str>, imply an ordinary 64-bit ProjectionEdge layout of 40 bytes;
this is inferred and requires an actual target/compiler size_of receipt before
admission. For actual Graph500 counts the outgoing CSR plus40E edge-table floor
is 12.643 GiB; with unweighted incoming CSR it is 13.646 GiB. Input Arrow batches,
normalized UTF8 staged rows, NodeId vector/hashmap, allocator overhead and
kernels/output are additional and remain live alongside the cached projection. Undirected arcs <=2E; outgoing arcs E. Lazy reverse CSR adds
`4*(V+1)+4*arcs`. Two retained different projection keys add storage, not merely time.
Use actual admitted footers/rowgroup bounds, not Sem's historical counts, and refuse
when envelope/disk cannot be justified. No assertion that Graph500-24 fits32GiB.
See [staged retention and admission correction](STAGED-RETENTION.md) for exact
owners, normalized buffer fields, conditional width/capacity arithmetic and the
physical/native fit-or-refusal contract. A 20-digit packed stage+projection subtotal
is already 27.327 GiB before incoming CSR/kernel/capacity; this is conditional
arithmetic, not an observation of the actual graph's widths or memory use.

Sources: [CSR widths and checked ceilings](https://github.com/querygraph/grust/blob/5c41bcb3c69e4cf4d285e6ec3a8ed239473ae1f1/crates/grust-algorithms/src/projection/adjacency.rs#L9-L86),
[retained identity/topology](https://github.com/querygraph/grust/blob/5c41bcb3c69e4cf4d285e6ec3a8ed239473ae1f1/crates/grust-algorithms/src/projection.rs#L31-L79),
[scoped CSR estimate](https://github.com/querygraph/grust/blob/5c41bcb3c69e4cf4d285e6ec3a8ed239473ae1f1/crates/grust-algorithms/src/statistics.rs#L23-L68),
[prepaid pool/environment](https://github.com/querygraph/sail/blob/6ae2e43a903c2cee02da170465c922c72b76198e/examples/extensions/benchmarks/runtime.py#L126-L173).

## Proposed wrapper/receipt interfaces (not implemented)

Typed extra-forbid Config: run_id,dataset,absolute repo/harness/support/output/input
paths, exact source/harness/binary/native/helper SHA pins, input/reference receipt
SHA, graph_name, stage_order literalasStaged, algorithm/method/options typed,
calls literal1|3, partitions16,threads16,pool_bytes,native_quota,timeout,minimumfree.
Choose reference semantics/oracle/output adapter by explicit method, never dataset size.

EngineReceipt: initial checking→passed|error only after server exits; phase_definition,
monotonic spans/events, full staged receipt/revision, per-call raw plans/schema/options,
projectionkeys/buildrecords, read IDs/states/rows/batches/work/peaks, per-call result
paths, warning/log identities, cleanup/drop/session/server/staging evidence and error.
OutsideSupervisorReceipt: exact childlaunch→exit boundary+code; input hashes before/after;
all output schemas/member file hashes/full exact ID+semantic oracle per call;
resource samples/cgroup envelopes; no retries; timeout/kill/error artifacts retained.
OutsideHostReceipt: ownership/fresh ID+lock, exact inspected container ID, exit/remove/
absence and transport/archive verification. Positive verdict only after complete
collection/hash verification and closure. Hashing/oracles/reference generation are
outside engine timer. Archive every raw output/plan/log/receipt and validate payload
hashes before any scoped guest removal. Do not modify frozen A2/B8 helpers.

## External Sem receipts: observed source, unresolved comparability

Local read-only object `763ac3ae9b884957eb9f2408e21cf3b1639c8483` contains the WCC/PR
Graph500-24 icebug_mem_12G_threads_4 receipts. Their reported runner commit is
`0e6f39862da6450fc9ee29d22a2c78c365e1ec1b`; the worker source at those two commits
is the same blob `0f093a82560e979c76e222c5ae61b7f17bae78ec`. Compact raw observations
and independently recomputed five-run medians are preserved separately in
`/tmp/sem-f2a-external-receipts.json` (not fresh local timings).

Worker measures four sequential brackets: Arrow read; DuckDB CSR+NetworKit graph;
algorithm **plus Python vector conversion/PR normalization**; Parquet write.
Outer process timer additionally includes interpreter/import/start/exit. It rebuilds
from original Parquet in each fresh run, one warmup/five measurements,4threads,
DuckDB12GiB spill manager, icebug13.0/format1.0.1/Arrow25/DuckDB1.5.5/Python3.14.4.
WCC symmetrizes input; directed PR builds outgoing and incoming CSR. All retained
returncodes0; worker reports8,870,942V/260,379,520E and WCC2,901components.
Receipts do not bind input SHA/full membership or PR oracle, cgroup32GiB or an
instance model. The board attributes i3.xlarge; JSON independently gives4CPU/AWS
kernel only. Source-backed external observations belong beside F2a, not a qualified
same-hardware/semantics speed ratio. Shared Morrobay results remain ratios.

Primary links: [WCC receipt](https://github.com/SemyonSinchenko/graphframes-rs/blob/763ac3ae9b884957eb9f2408e21cf3b1639c8483/benches/results/ldbd/wcc/M/graph500-24/icebug_mem_12G_threads_4/benchmark.json),
[PR receipt](https://github.com/SemyonSinchenko/graphframes-rs/blob/763ac3ae9b884957eb9f2408e21cf3b1639c8483/benches/results/ldbd/pagerank/M/graph500-24/icebug_mem_12G_threads_4/benchmark.json),
[actual worker](https://github.com/SemyonSinchenko/graphframes-rs/blob/0e6f39862da6450fc9ee29d22a2c78c365e1ec1b/benches/python/lbdb_algorithms.py),
[runner](https://github.com/SemyonSinchenko/graphframes-rs/blob/0e6f39862da6450fc9ee29d22a2c78c365e1ec1b/benches/python/main_lbdb.py).

## Decisions required before launch

Root binds: ordinary/experimental kernel and1/3-call sequence; native quota+headroom;
four-phase span semantics/instrumentation source versus disclosed coarse baseline;
PR normalization/stopping oracle; graph/input admission and timeout/disk budget.
No frozen source or benchmark helper is changed or executed by this review.

Arithmetic correction recorded UTC: 2026-10-02T02:47:15.179378+00:00. Original generated preparation is retained unchanged at `/tmp/sem-f2a-source-admission-plan.md`; the correction changes source-layout arithmetic, with no runtime or benchmark evidence change.
