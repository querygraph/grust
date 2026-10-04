# Review of Sem's second review

Recorded UTC: 2026-09-30T22:12:39.164319+00:00

Reviewed [SEM-REVIEW-2.md](../../SEM-REVIEW-2.md) at Grust
`0e6a0cbc3b9cf818d6b2edf6e5c8e6bf428cb623`, against Sail
`b569e75de625885b3d919fa4196b2e0bed14c618` and graphframes-rs results at
`ba2fdd8f51fa7fafdca15012d2741f5f8d80c024`. The external receipts identify
their runtime source as `b4da56dabe20bba8e29563e06acc5179b2113ce3`; the
algorithm, CLI and monitor files checked here are identical between those two
external commits. [Source receipt](sem-review2/source-receipt.json).

The right next experiment is a matched local/process-cluster control, after
the stream diagnostic and compact-aggregation qualification. The proposed
Stage A is not ready to run unchanged: it pairs different PageRank contracts,
requires harness changes, and cannot support its causal decision table.
Keep the explicit multi-host Argentea/Grenada qualification alongside it.

## Findings

### P1: the proposed PageRank comparison computes different finite-step answers

Document lines 74, 186–192 and 298–302 compare power PageRank with the external
ten-iteration result. The pinned external CLI uses incremental GraphX-style
delta propagation, threshold 0.01, with the participation filter still enabled
in fixed-iteration mode; it normalizes accumulated ranks at the end.
Pecan power initializes 1/N and redistributes dangling mass every iteration.
Equal damping and iteration count do not make these the same finite-step task.
[External PageRank](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/centrality/pagerank.rs#L125),
[Pecan power](https://github.com/querygraph/sail/blob/b569e75de625885b3d919fa4196b2e0bed14c618/examples/extensions/graph-algorithms/src/pyspark_pecan/algorithms.py#L180).

A source-derived exact-arithmetic control on a two-vertex directed cycle plus
one isolated vertex gives, after ten iterations:

| Recurrence | Cycle vertex, each | Isolated vertex |
|---|---:|---:|
| Power with dangling redistribution | 0.4651158397 | 0.0697683206 |
| Normalized delta with threshold 0.01 | 0.4586848225 | 0.0826303550 |

L1 difference is **0.0257240688**. This is an arithmetic counterexample, not
an engine execution or timing experiment. Independent closed forms and unit
mass assertions passed. [Script](sem-review2/semantic_control.py),
[result](sem-review2/semantic-control.json).

Specify either identical finite-step recurrences or a common stationary
residual/error target. Report distinct algorithms separately when they do not
meet that contract. The current Sail harness always passes a positive tolerance
and requires converged output and a fixed-point certificate; setting its cap
to ten does not create a fixed-ten benchmark. That needs an explicit mode and
a finite-step oracle, without weakening convergence assertions for other cells.
[Harness](https://github.com/querygraph/sail/blob/b569e75de625885b3d919fa4196b2e0bed14c618/examples/extensions/benchmarks/graph_cell.py#L185).

### P1: traversal and WCC certification need a common contract before timing

External shortest paths emit distances from a landmark selected as one quarter
of the benchmark catalog's approximate vertex count. The recorded cells have
`undirected=false`; Sail's scale-24 campaign uses an explicit hub and an
undirected graph, and produces/checks parents and hops as well as distance.
Input counts differ too. These published times are useful context, not a
matched BFS ratio. Fix input hashes, direction, source, duplicates, isolated
vertices, unreachable representation and requested output before comparing.
Verify the chosen source exists and record reached vertices and maximum depth;
an approximate catalog count does not establish source membership.
[External command construction](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/benches/python/main.py#L126),
[shortest-path output](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/connectivity/shortest_paths.rs#L150).

For WCC, the existing large-graph certificate explicitly reports
`component_count_verified=false`. Equal labels across every edge do not prove
that disconnected components were not merged. A constant label can pass that
part of the check. Stage A's “same result certified” therefore requires an
independent reference partition/component count or connectivity witness;
“certificates unchanged” in Stage B is insufficient for this claim.
[Current certificate](https://github.com/querygraph/sail/blob/b569e75de625885b3d919fa4196b2e0bed14c618/examples/extensions/benchmarks/graph_cell.py#L255).

### P1: summing operator pools does not bound process or container memory

F6 and C3 correctly identify per-process overcommit, but splitting 30 GiB of
pools inside 32 GiB cannot guarantee completion by spilling. Pool accounting
does not include all allocations; native quotas are prepaid, nonspillable
reservations. The local shuffle stream also retains an unbounded overflow
`VecDeque` of batches without a pool reservation. Merely blocking that queue
can deadlock execution; its existing comment records this constraint.
[Local stream buffering](https://github.com/querygraph/sail/blob/b569e75de625885b3d919fa4196b2e0bed14c618/crates/sail-execution/src/stream/local/memory.rs#L62),
[native reservation](https://github.com/querygraph/sail/blob/b569e75de625885b3d919fa4196b2e0bed14c618/crates/sail-common-datafusion/src/native_resource.rs#L104).

Budget driver, workers, client, native reservations and nonpool headroom;
measure process PSS, cgroup peak, pool reservations and actual spill separately.
Retain resource refusal, timeout and kernel kill as different outcomes. The
current harness gives driver and workers the same pool environment, so a small
driver plus differently sized workers requires a configuration change. Reducing
the driver pool without reducing its native quota can reject extension binding.
[Runtime configuration](https://github.com/querygraph/sail/blob/b569e75de625885b3d919fa4196b2e0bed14c618/examples/extensions/benchmarks/runtime.py#L143).

### P1: Stage A's ratios do not identify the cause assigned by its decision table

Lines 199–206 infer that a slow local result proves the client loop is the
problem. That result also contains algorithm choices, scans, physical plans,
aggregation, validation and checkpoint costs. Cluster/local changes scheduling,
serialization, routing, partition placement and optimizer behavior together.
Neither ratio separates those contributions. A no-op's overhead is not the
cost of serializing an unrolled iterative plan either.

Use the ratios to choose the next control, not to announce a cause. Record
plan bytes and planning time, submitted jobs/stages/tasks, local/remote exchange
bytes, writer time, scalar actions and source validation. Then ablate one
mechanism at a time. Preserve local and process-cluster cells; choosing a local
default does not qualify the distributed path or resolve the user's scaling
requirement. Keep the fixed-resource placement, strong-scaling and weak-scaling
controls in [CLUSTER-PREPARATION.md](CLUSTER-PREPARATION.md).

### P1: a footer receipt cannot establish that an uncertain write has committed

B2 can replace a count only for a successfully committed immutable generation
whose exact file inventory, schema and row total are owned by the host. The
current `write_uncertain` state intentionally retains ownership after a failed
RPC: neither file existence nor valid footers prove all writers have drained.
Session teardown is also not a detached-writer join barrier.
[Staging ownership](https://github.com/querygraph/sail/blob/b569e75de625885b3d919fa4196b2e0bed14c618/examples/extensions/graph-algorithms/src/pyspark_pecan/staging.py#L25),
[host cleanup](https://github.com/querygraph/sail/blob/b569e75de625885b3d919fa4196b2e0bed14c618/crates/sail-session/src/extensions/graph_utils/storage.rs#L314).

Keep partial/canceled writes pending. Test late writers, cancellation, retry,
zero rows, schema mismatch and file replacement. A total row count is not an
active-row count. Parquet min/max statistics are optional; ordinary footers
also do not supply PageRank's floating-point sum. B3 requires an explicit
aggregate output/receipt with its reduction semantics and commit relationship.
The dangling mass of state t is needed to form state t+1: a companion written
only after that update cannot supply it. Use an in-plan scalar or explicitly
bootstrap and pipeline the next round's mass. Fixed-step power currently omits
the convergence action, so B3's claimed two-action saving is not universal.

### P1: putting the loop in an extension does not automatically distribute it

Stage E's “parity is a build question” and “each round's plan is distributed”
are unproved. The current extension planning interface receives payload and
physical inputs, not the session's `JobService`. The normal Connect executor
explicitly submits a plan through the job runner. Calling a library's internal
`collect`/write actions on a DataFusion context does not provide that handoff.
[Extension interface](https://github.com/querygraph/sail/blob/b569e75de625885b3d919fa4196b2e0bed14c618/crates/sail-session/src/extensions/mod.rs#L87),
[explicit job submission](https://github.com/querygraph/sail/blob/b569e75de625885b3d919fa4196b2e0bed14c618/crates/sail-spark-connect/src/service/plan_executor.rs#L121).

Prototype one algorithm with an explicit driver loop, per-round submission,
worker codec support, checkpoint layout, cancellation, resource accounting and
cleanup. Demonstrate remote execution rather than inferring it from one API
request. Argentea state is scoped to job/operation; reusing it across newly
submitted jobs needs its own continuation design. A relational server loop
does not remove native full-label copies or all-owner control traffic.

### P1: the proposed dense representation must keep wide arc offsets

Stage F imports the earlier proposal for u32 CSR offsets and targets. Those
have different bounds: local vertex indices can fit u32 while the number of
arcs does not. Symmetrizing the cited Graph500-28 edge count exceeds u32's arc
range. Use checked u32 targets with usize/u64 offsets, or explicitly reject an
unsupported size. Do not narrow both because vertices fit. `asStaged` also
needs per-kernel order/determinism qualification; it is selected at staging,
before the algorithm is chosen, and some existing kernels depend on edge order.

### P2: reported disk, memory and timing boundaries need correction

The external monitor times subprocess launch through exit; the CLI includes
input setup, algorithm execution, final Parquet writing and cleanup. Independent
result verification is outside that measurement. Its RSS is sampled process
RSS; Sail's reported campaign PSS is a different metric. The external README
uses **GiB**, not GB.
[Monitor](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/benches/python/monitor.py#L105),
[published units](https://github.com/SemyonSinchenko/graphframes-rs/blob/ba2fdd8f51fa7fafdca15012d2741f5f8d80c024/benches/results/README.md).

The disk metric is a baseline-subtracted work-directory footprint containing
checkpoints, spills, outputs and logs. It does not establish 120 GiB of spill.
Likewise low sampled RSS alone does not prove zero spill. Use actual spill
counters and separately inventory checkpoint/output bytes. The two declared
write ranges quoted in F4 also do not establish an 8–20 ratio without the
matched cells; retain the paired observations instead of dividing range ends.

### P2: the proposed campaign and acceptance rules need an explicit manifest

F2's seven-to-nine job claim is not established by the controller. The unfused
WCC forward loop has six explicit write/count actions; its fused form has four.
The initial edge count is outside the loop, and ownership/schema RPCs are
additional. Client actions, server jobs and stages are different counts; record
all three rather than infer one from another. Tail-round wall time also does
not isolate a universal fixed cost per round.

Two inputs times three external, five local and five process-cluster
configurations already gives 26 configurations. Four measured samples each
would be 104 cells before warmups, builds and verification; separate ABBA-twice
contrasts would require more. “About two hours” is not supported by a dry plan.
Start with one small matched algorithm, retain every outcome, and estimate the
larger campaign from that pilot. Pin the source commit, image, binary, data,
allocator, pool type, disk budget and actual thread settings. The external CLI
uses FairSpillPool; the current Sail harness selects a greedy pool. Disclose
or deliberately control that difference.

Use engineering targets for setup latency, job count, bytes moved, bounded
memory, answer quality and scaling efficiency. Comparative ratios are evidence,
not predetermined acceptance outcomes against a named engine. Absolute latency
targets require a qualified host; Morrobay remains a shared-host ratio/control
environment. The document's two-times Banda conclusion also does not follow
from a five-second ingest goal plus its own 1.4–10.6-second kernel range.

## Answers to the five Astra questions

1. **Envelope/build:** 16 CPUs/32 GiB is a useful named qualification profile.
   Treat 30 GiB total pools as a proposed setting to test, not a proven safe
   admission policy. Use the same pinned image and toolchain with a separate
   detached graphframes-rs checkout, target directory and identity receipt.
   Do not fold it into the Sail/native build's identity.
2. **Footer receipt:** no, it is not a commit check for an uncertain write.
   It is acceptable row/schema evidence after confirmed writer completion and
   a host-owned immutable manifest. It cannot turn an uncertain write into a
   committed one or release ownership early.
3. **B1–B7 and layout:** B1 can be an isolated opt-in control now; removing
   keyless repartition does not declare keyed layout after a Parquet read.
   B2 should share the generation manifest. B3 must commit state and scalars
   consistently. B5/B6 must retain source generations until all lazy descendants
   finish and bound plan growth; B7 must distinguish an immutable validated
   input handle from an unchecked `trusted=True` assertion. Do not switch B4's
   public default until explicit variant measurements and correctness pass.
4. **100 ms target:** presently an aspiration. The stream-fault controls provide
   no supporting setup-latency measurement. Force the probe through real
   distributed stages and an exchange so optimization cannot remove its work;
   separate cold startup from warm jobs and report p50/p95 and task counts.
5. **Compact before Stage A:** yes, qualify the instrumented original and compact
   host with the same original controller first, then pin the qualified choice
   for Stage A. Retain the original control. The compact tuple MIN does not
   implement `min_by`; its qualification is a separate experiment. No completion
   date or end-to-end gain is assumed. Linux builds and small-worker checks have
   passed; large-control qualification remains in progress.

## Order that preserves the evidence

1. The instrumented replay has ended with both workers OOM-killed. Retain the
   original no-OOM question separately from these confirmed OOM replays.
2. Qualify the compact accumulator on the same controller/input, measuring the
   complete process envelope. Continue the bounded native allocation fixes.
3. Define shared algorithm/output contracts and validators; run a tiny semantic
   control before allocating the larger Stage A campaign.
4. Run a one-host local/process-cluster pilot with matched total resources and
   component counters. Evaluate B1, B2 and fused WCC as separate candidates.
5. Proceed to the explicit multi-host placement/strong/weak matrix. Measure
   per-worker work, skew, remote bytes, control rows, driver time and store load.
   Near-linear scaling remains an experimental question.

## Follow-up on the Stage A/F additions

Reviewed the subsequent Grust commits through
`5c1f7db290e3e1520015412474e8248b69df8d30`, which add Sem's validation-timer
and CSR-conversion comments. These additions were preserved during the review.

**Validation boundary:** a prevalidated-input execution class is useful, with
one immutable manifest and the same graph invariants established before both
runs. Record preprocessing separately and retain the public API end-to-end
boundary too. The external Int64 path omits Pecan's full duplicate/null/endpoint
scans, but it does check schema/types and perform input setup inside the timed
CLI (`src/main.rs:624–728`, `src/lib.rs:82–103`). Its string-ID ingestion has
additional validation and remapping. Thus “validation is not in the timer”
needs that qualification. A trusted-input entry needs a validated immutable
handle, not an unchecked boolean. Snapshotting also provides ownership and
stable input: it cannot all be classified as redundant validation. Measure
the agreed boundary directly; subtracting prior phase observations from a
different run does not establish a matched ratio. Neither exclusive
algorithm timing nor public-call timing is the only valid boundary.

**CSR control:** approve the native-only conversion experiment as a component
control. Pin the vertex table as well as `edges.parquet` so isolates and the
ID domain survive. Disclose direction, duplicate handling, weights, target
width, arc-offset width, transpose construction, edge order and memory
admission. Record Parquet read/decode, ID mapping, degree count, prefix sum,
fill and any required sort separately, plus the combined resident bytes and
wall boundary. A dense-ID, unsorted build that omits host ownership, validation
and staging performs a different amount of work; it is not a universal lower
bound for the complete API. The proposed one-second estimate remains
unmeasured. The 28-second phase includes staging and projection, and the
recorded WCC kernel/output range extends to 10.6 seconds, not only 3.3.
Measure cold construction, reuse and each complete algorithm call before
drawing a representation crossover conclusion. The first relational round
alone is not the total cost against which a reusable CSR is amortized.

**Fused WCC aggregation:** source review at Sail `b569e75` traces
`min_by(neighbor, priority)` through `MinByFunction::simplify`
(`crates/sail-function/src/aggregate/max_min_by.rs:263–288`) to ordered
`last_value`, with descending priority and a nonnull-priority filter.
DataFusion 55.1 admits its specialized grouped Int64 accumulator for this
ordered expression (`first_last.rs:199–236`). It stores contiguous Int64
values but one ordering `Vec<ScalarValue>` per group; every batch clears a
group bitmap and scans resident group indices (`556–560`, `617–624`).
The compact tuple MIN affects neither this path nor the separate Int64
`min(priority)`. Casting GF64 priorities to Double would lose exact ordering.

The subsequent [component probe](min-by-probe/README.md) uses the public pinned
DataFusion grouped-accumulator constructor. At 100,000 groups it retains
11,692,032 requested heap bytes but reports 10,946,304: the 745,728-byte
difference matches omitted spare capacity in the outer ordering vector. Two
semantic tests and allocation controls at 1k/10k/100k groups passed. This uses
the System allocator on the shared laptop, not Linux RSS or a full WCC query.
The subsequent [Linux worker control](wcc-fused-worker-plan/README.md) confirms
the ordered LAST_VALUE expression in both explain output and 24 successfully
executed aggregate tasks across both workers. Two input orders each return the
exact 17-row BIGINT oracle, including signed Int64 extrema and adjacent IDs
beyond 2^53. Source and dependency identities connect this runtime to the
component probe. This confirms the execution route, not its whole-query memory
cost or the occurrence of prefix emission.

The probe also confirms that `state()` uses the remaining group count for
output capacity after extracting emitted state (`first_last.rs:674,681`).
Emitting one of 100,000 groups adds an 8,025,376-byte transient peak and leaves
1,625,632 additional requested bytes live. An unordered WCC aggregation does
not establish that this prefix-emission path occurs. No implementation change
or WCC/stream-loss attribution follows from this component result.

## Latest input-snapshot feedback and publication

Reviewed Grust `1084eb6`, which adds Sem's three later comments and proposes
the DuckLab Parquet conversions of LDBC Graphalytics inputs. The five answers
above still apply. A subsequent bounded lookup identified the
[official Parquet catalog](https://ldbcouncil.org/benchmarks/graphalytics/datasets/)
and its 51 vertex/edge pairs; Sem's own article links that catalog. Its published
Graph500-24 counts are 8,870,942 vertices and 260,379,520 edges, matching the
external result's reported counts. This identifies the input pointer, not the
exact files used in either benchmark. The initial catalog check inspected four
tiny example files. [Source and schema evidence](sem-review2/input-catalog/README.md).

The subsequent [cit-Patents preparation](sem-review2/cit-patents-input-verification/receipt.json)
downloaded and hashed the official pair (73,899,325 bytes). Full streaming
validation found 3,774,768 unique non-null signed-i64 vertices and 16,518,947
edges, with no null or missing endpoints and no self-loops. The files contain
no weight column; duplicate edges were not counted. A separate
[bitmap-based audit](sem-review2/cit-patents-input-verification/independent-audit.json)
rehashed the original bytes and independently confirmed those row checks.
The originals remain private and unchanged; public receipts pin both files.
This prepares one shared input, not a historical-byte match or a Stage A result.
The subsequent [exact WCC reference](sem-review2/cit-patents-wcc-reference/README.md)
records 3,627 components and a largest component of 3,764,117 vertices, preserving
the full declared domain. Its tested union-find produces canonical membership;
the full output/all-edge readback is not an independent second WCC algorithm.
The hashed private result is an oracle for the pilot, not an engine comparison.
The larger selected pairs still need equivalent verification.
The catalog's documentation revision does not pin the data bytes,
and DuckDB writer metadata does not independently establish DuckLab authorship.
Both implementations should consume the same pinned vertex/edge bytes and
direction, duplicate, isolate and source contract. That can resolve the input
discrepancy; it does not remove the PageRank/output-contract differences.

I support a separate entry point for already materialized, immutable,
prevalidated input. It can avoid Pecan's initial rewrite when the caller already
provides the required snapshot and ownership guarantees. Keep the existing
materializing entry for arbitrary lazy DataFrames and mutable tables. A Parquet
suffix alone supplies neither those guarantees nor the validation result.
The host must distinguish borrowed input from owned staging so cleanup never
deletes the borrowed dataset, retain its lifetime for all lazy descendants,
and verify schema/manifest identity. Checkpoint layout declarations remain a
separate contract: simply reusing a Parquet file does not prove keyed partitioning.

This review and its completed evidence were committed and pushed in Grust
`51644023a02185679527304682ed41055ae1c4aa`, followed by the completed WCC/B1 and
worker-plan evidence at `f4443ba76c18c922698a060183c02ca65ce939c7`. The combined
code snapshot `200d1cf8` is pushed to `work/stream-review-followup` after its
exact detached combined gate and independent source audit. B1 remains opt-in
with scoped unit/local-SQL validation; distributed qualification and measured
benefit remain pending. No default change or speedup is claimed.

Current status is recorded in [RESULTS.md](RESULTS.md): both Linux host builds
and both two-worker smoke checks have passed. Their receipts are included in this follow-up documentation snapshot. The instrumented scale-24 replay subsequently ended
in confirmed OOM kills of both workers; its matched compact control is running.
[Closed replay evidence](RESULTS.md#instrumented-sssp-replay-confirmed-worker-oom).
Prepared configurations are not
benchmark results, and the differently loaded smoke runs do not establish a
performance ratio.

## Review of Sem's answers at `7bb00a2`

The new answers identify the input catalog and library entry point and report
Sem's confirmation of the published timing boundary. The five implementation
answers above remain in force. Source checks and remaining qualifications are
recorded in the [CLI/library/representation audit](sem-review2/latest-7bb-source-audit/)
and [input-claim control](sem-review2/latest-7bb-input-control/receipt.json).

**Input counts:** keeping the full `0..2^24-1` ID domain is established by our
manifest. The exact number of its isolated vertices is not established by the
cross-dataset ratio in section 2. Our 8,862,601 reached vertices divided by
LDBC's 8,870,942 vertices gives about 99.906%, but those are different inputs.
The five-vertex control has a 100% cross-graph ratio while two of its own
unreached vertices form another edge and none are isolated. This refutes the
inference, not the large graph's result. The retained certificate supports the
reported reach under our input contract. Count distinct endpoints and inspect
unreached components on that same input before quantifying its isolates or
giant-component share. Our manifest records 2,798 self-loops but explicitly
says duplicates were not counted; the 8,055,936-edge difference cannot yet be
decomposed into duplicate/self-loop removal across differently seeded inputs.
Use the same pinned LDBC files for the pilot and retain these historical
inputs as distinct. Reachable URLs and reported object sizes do not supply
immutable file hashes, schemas or the graph contract.

**CLI and join settings:** use the exact source, actual invocation and receipt
together. Defaults in `main.rs` and a stable toolchain channel alone do not pin
a run. Record the binary/toolchain identities, WCC selection and effective
settings. The configured sort-merge preference is not a physical-plan trace.
Sail's permitted hash-join pilot can measure the same logical task with a
disclosed physical strategy; record actual joins, sort/exchange work and spill.
A separate strategy ablation is needed to attribute a difference to the join.
Sem's confirmation supports the launch-to-exit timing interpretation already
checked in the source; it does not turn validation-subtracted estimates into
matched observations.

**Library embedding:** `GraphFrame` identifies the entry point (the source
method is `pagerank()`). The library still calls DataFusion count/write/read
operations internally; its hash-partitioned writer directly executes a
physical plan and spawns local writers. A Sail adapter needs explicit action
submission, worker placement, cancellation and ownership integration. Keep
Stage E's distributed prototype requirement. Identifying the library does not
establish that its existing execution path submits work through Sail.

**Integer representation:** retain signed i64 vertex IDs at the interfaces.
A checked local u32 index into an i64 ID map preserves that contract; its bound
is mapped cardinality, not the magnitude of the original IDs. An i64-only
storage control can separately measure representation cost, with mapping and
construction included at the declared boundary. Preserve exact round trips and
wide arc offsets. The current Banda projection uses u32 targets and offsets,
rejects oversized graphs and has no wide fallback; Argentea uses i64 targets
and usize offsets. A checked wider fallback is still an implementation task,
not an existing qualification. Keep compact and wide measurements explicitly
identified under the selected comparison protocol.

**Write-cost scaling:** the supplied observation covers one shared-host 16M-row
case; 64M and 268M remain proposed controls. The new larger-size experiment is
useful. Pin row schema/width, compression, input layout, output partition or
bucket count, cache boundary and total resources, then retain paired order,
every outcome, physical exchanges, output bytes/file counts and memory. Check
output equality and whether the produced layout actually removes the intended
read-side shuffle/sort. Measure the complete write/read tradeoff as well as
write cost. Ratios under load and a metadata-only layout claim cannot establish
a universal scaling curve or a validated physical layout.
