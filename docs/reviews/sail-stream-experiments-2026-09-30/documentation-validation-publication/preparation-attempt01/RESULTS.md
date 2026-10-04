# Focused Sail stream and resource experiments

Recorded UTC: 2026-10-01T00:18:59.317259+00:00

Work in progress. The compact aggregation has passed component and small-worker
checks. Its large matched replay is running; paired measurements remain pending.
The prior review is [REVIEW.md](../sail-graphs-2026-09-30/REVIEW.md).

## Stream loss: OOM in two replays, earlier failures still open

The logged scale-24 Pecan BFS frontier replay hit its 100 GiB container limit.
Docker reports `OOMKilled=true`, and `memory.events` gained one `oom_kill`.
The subsequently retrieved Linux kernel log names the **same full Docker cgroup
ID** and records a Sail process killed by the memory cgroup. This is evidence
of an actual killed server process, beyond the earlier pooled memory reading.

Kernel PID 130101 was killed at monotonic 131805.374507, with 52,138,228 KiB
anonymous RSS. In the sampler window spanning that kill, container PID 174
(worker 2 in the server startup log) disappears; driver 56 and worker 1/PID173
remain for the subsequent samples. The namespace mapping was not recorded live,
so identifying the victim as worker 2 is an inference from the matching cgroup,
process disappearance, and memory measurements. Both workers were near 50 GiB.

The first logged transport error was `ConnectionReset` at 16:46:28 UTC, followed
by failed shuffle tasks and the familiar `error reading a body from connection`.
The recorded `NO_ERROR` GO_AWAY appears after session teardown began, so it is
not evidence that GO_AWAY initiated this failure. Memory exhaustion explains
this replay; it does **not** establish a common cause for earlier runs with no
OOM event. The new runtime and logging also differ from the historical frontier
run, so this is not an isolated before/after timing experiment.

Evidence: [cell orchestration](logging01/cell/orchestration.json),
[receipt](logging01/diagnostics/receipt.json),
[kernel attribution](logging01/kernel-oom-attribution.json),
[kernel excerpt](logging01/kernel-oom-excerpt.txt),
[server log](logging01/diagnostics/server.log), and
[process samples](logging01/diagnostics/memory-samples.jsonl).

The replay used runtime/native `ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73`,
diagnostic harness `3a9028057c6c6c5034492845926fc4bc18f9626f`, two workers,
32 partitions and 96 GiB DataFusion pool **per process** inside a single 100 GiB
container. Those per-process limits do not bound their combined consumption.
The immutable input has 16,777,216 vertices and 268,435,456 undirected input
edge tuples. Settings and hashes are in the receipt; no dataset was regenerated.

The earlier h2 controls show why the outer error alone is insufficient:
ordinary cancellations do not consume the configured error-reset cap, and
keepalive expiry or abrupt peer loss can produce the same body-read message.
See [transport controls](transport-control/) and the preceding review. The
runtime diagnostic patch now retains bounded error sources, tonic status,
process, task and peer identity before error conversion. An additional actual
Tonic server control proved that `tonic::transport::server=debug` exposes
`http2 error: keep-alive timed out: operation timed out` without hyper tracing.
The same deliberately induced failure stays generic at `info`. This filter
was included in the instrumented SSSP replay; the earlier hyper-only controls did
not exercise this Tonic logger. See [verified control](tonic-keepalive-control/receipt.json)
and [server log](tonic-keepalive-control/tonic-debug-keepalive-verified.log).

## Instrumented SSSP replay: confirmed worker OOM

The second scale-24 replay ended with `oom` / producer `error` at
21:58:04 UTC. The same-boot kernel records kill both workers in the exact
container cgroup: host PID183784 (worker 1), then PID183782 (worker 2).
Their namespace/start-time identities were recorded live. Terminal counters
show two OOM kills and a peak of 107,374,235,648 bytes against the 100 GiB cap.
The client reported an h2 body-read error during iteration 2's Parquet write.
This diagnoses this replay; earlier zero-OOM failures remain unexplained.
[Kernel capture](logging02-host-closure.json),
[producer receipt](logging02/diagnostics/receipt.json), and
[collected-evidence integrity audit](closed-cell-audit/logging02-verification.json).
The [closed first-fault audit](logging02-first-fault-audit/README.md) records the
kill/disappearance/Flight-error sequence and its clock and cleanup boundaries.

The matched compact-host replay is now running after
[fresh admission](logging03-admission01.json). Input manifest, controller,
native package, resources, logging and timeouts match; the host changes from
`2894a962` to `56194b1`. Its final outcome remains pending.

A [host-memory comparison](logging02-monitor/host-memory-comparison.json)
shows that host paging was already substantial before this run. Between
20:03:47 and 20:45:12 UTC, used swap fell from 35,658.50 to 23,259.50 reported
MiB, while physical compressor occupancy grew from 18.18 to 49.08 GiB.
Swap-in and swap-out counters advanced by 117,575,606 and 114,476,972 pages.
These compressor-related page counts are not measured physical disk traffic;
the host-wide activity is not attributed to one workload. A container's zero
swap setting and guest steal counter do not describe host paging of the VM.
No performance ratio is qualified by this replay.

The [sampler audit](sampler-observation-audit/receipt.json) finds 427 unique
complete scans in sparse captured tails, with durations from 72.469 ms to
42.082 seconds. The configured 50 ms is a wait after scanning and bookkeeping,
not a guaranteed cadence; transition rows skip that wait. This is neither a
full-run distribution nor a CPU-overhead measurement. The later closed audit
finds 6,836 original scans, with a maximum duration of 62.490 seconds; its peak
process-memory row spans both worker kills. Preserve actual scan windows and
distinguish sampled process peaks from the kernel's cgroup peak.

The [runtime source audit](scheduler-starvation-source-audit/source-audit.json)
confirms that task polling and worker gRPC share the primary Tokio runtime,
but also identifies blocking-pool preparation, separate object-store I/O and
DataFusion's cooperative scan wrappers. Synchronous work within one poll is
not preempted by cooperation; its duration here is unmeasured. Captured
[received PING acknowledgements](scheduler-starvation-source-audit/monitor-ping-audit.json)
also continue during the observer timeout interval. Their missing process and
connection IDs prevent attribution to a particular peer. Scheduler starvation
and host-pressure explanations remain hypotheses, not observed stream causes.

## Concrete aggregation allocation cost

The failing iteration's physical plan contains grouped
`min(struct(distance,hops,parent))`. DataFusion 55.1 has a specialized struct
group accumulator, but its state stores a separately copied singleton Arrow
struct per group. Its update builds scratch indexed by all resident groups,
constructs row slices, and compares via temporary Arrow structures. This is not
a claim that DataFusion falls back to one generic scalar accumulator per group.

The standalone probe compiles the unchanged pinned implementation and uses a
counting System allocator. At 100,000 groups it records:

| Quantity | Requested allocation bytes / count |
|---|---:|
| Three dense input columns retained | 2,401,010 bytes |
| Additional retained state after first grouped update | 204,831,488 bytes |
| Accumulator's own reported size | 68,800,000 bytes |
| First update allocations | 5,000,109 |
| Identical repeat allocations | 1,800,104 |
| Improving repeat allocations | 5,600,104 |
| Additional transient peak during final output | 84,852,196 bytes |

These are requested heap allocations on the local arm64 System allocator,
not RSS or a full-pipeline memory prediction. The dense input is a representation
control, not yet a production replacement. Exact output equality passed at
1,000, 10,000 and 100,000 groups. Prefix emission also leaves incorrect reported
remaining bytes; the current unordered failing plan's final emission is a
separate path, so that accounting defect is not assigned as its cause.

Evidence and reproduction: [probe source](min-struct-probe/src/main.rs),
[locked build receipt](min-struct-probe/build-receipt.json),
[100,000-group observations](min-struct-probe/100000-groups.jsonl).
The compact implementation is committed as
`56194b170155301ba91077f0ba3df31fe2c78b6b` on `work/compact-struct-min`, based on
the `2894a962` diagnostic/resource changes described below. At the same
100,000 groups it retains 4,194,304
requested heap bytes (48.8 times less), reports 4,194,730 bytes including fixed
schema/state storage, and performs 70 first-update allocations. An identical
repeat has an additional temporary peak of 504 requested bytes instead of
10,401,232; final output adds
2,400,000 bytes transiently instead of 84,852,196. All tested output values match.

The independent oracle exercises 64 seeds across 12 batches, child/root nulls,
filters, floating-point special values, signed IDs, prefix emission and state
merge. [STRUCT-MIN-ALLOCATION.md](STRUCT-MIN-ALLOCATION.md) records the method,
source fingerprints and every size. These are isolated requested allocations;
no whole-query or Linux RSS reduction is yet claimed.

The exact committed gate passed formatting, strict all-target Clippy for all
three changed crates, 149 execution, 328 function and 13 planner tests, and 46 Pecan
unit tests. The in-process worker codec test serializes and executes a physical
aggregate plan through the production worker decoding path and checks the
concrete compact accumulator. The subsequent Linux two-worker smoke passed,
as recorded below; the compact scale-24 replay remains pending.
[Exact gate](compact-min-committed/receipt.json). Other `min` types
retain the original planner implementation and its metadata optimizations.

## Qualified implementation snapshot

The complete review snapshot is
[`b569e75de625885b3d919fa4196b2e0bed14c618`](https://github.com/querygraph/sail/commit/b569e75de625885b3d919fa4196b2e0bed14c618)
on the fork's `work/stream-review-integrated` branch. It combines the changes
below, compact MIN and BFS completion validation. Its exact detached gate passed
490 host Rust tests, 103 core tests, 49 native adapter tests and 46 Pecan unit
tests. [Integrated gate](integrated-review/final-receipt.json). This is a scoped
local review snapshot, not a Linux cluster or release verdict. The individual
work branches are also [verified on the fork](fork-branches.json). No upstream
pull request or main merge was made.


Repository `querygraph/sail`, branch `work/stream-performance-review`, exact
commit `2894a962076d3cc404dd72ec736ebeb9239901f6` contains the diagnostic logging
and three focused resource changes:

- Argentea SSSP terminal relay reuses the already validated labels. It avoids
  allocating candidates and scanning/copying every local vertex after Done.
  Producer completion and local EOF checks remain enforced. The all-owner
  statistics exchange remains quadratic in partition count.
- CSR construction reuses offsets as its fill cursor, saving eight admitted
  scratch bytes per local vertex on 64-bit targets. Validated dense owner-local
  IDs use direct lookup; irregular IDs retain checked binary search.
- Pecan/Grenada weighted traversal writes overflow detection with its winning
  candidate aggregation, avoiding a separate expansion action. A persisted
  marker adds overhead; the small paired experiment below did not show a speedup.

For four terminal relays and 65,536 vertices, the Done change reduces charged
work from 262,152 to 8 at one partition; at 32 partitions it changes 270,336 to
8,192. The optimized count is independent of vertex count for the tested fixed
partition counts. These are charged-work counts, not elapsed-time ratios.

For 65,536 vertices and 262,144 arcs, CSR construction removes one allocation
and reduces both total requested allocation bytes and admitted peak by 524,288
bytes. The measured requested live peak falls by 524,184 bytes for BFS and
524,256 bytes for SSSP. Dense weighted charged work changes 10,158,080 to
1,769,472; irregular
lookup work is unchanged. Raw input and completed CSR still overlap in memory.

Evidence: [Done relay](argentea-done/), [CSR](argentea-csr/),
[combined native candidate](argentea-combined-candidate/),
[exact integrated host gate](integration-committed/),
[exact native gates](integration-native-committed/).

The exact integrated gate passed formatting, strict sail-execution Clippy,
147 execution tests and 46 Pecan unit tests. The exact native core passed 101
release tests and the adapter passed all 48 release tests, including 42 Argentea
tests. Three additional adapter runs under ten load processes each passed all 48;
source fingerprints match the integrated source. A prior parser undercount and
fmt/control failures are retained alongside their resolutions, not removed.
This is a scoped gate, not a verdict on every Sail crate or a multi-host run.


## Argentea completion validation

A separate four-line core fix at
`193e2a9035428cc707bf09c0d20a16c421f353ba` validates BFS Reference/Push completion
totals against the producer's previously recorded frontier-edge count. The
baseline accepted all 12 malformed cases that suppressed the sole candidate and
rewrote completion counts to zero; the fix rejects them before publication.
Valid duplicate edges, self-loops and already-reached targets remain accepted.

Exact detached core formatting/Clippy and 103 release tests passed, as did 49
native adapter tests including 43 Argentea tests. A saturated run under ten load
processes passed both suites. Full native formatting has an unrelated existing
failure in unchanged files, reproduced byte-for-byte against 289; changed-file
formatting passed. [Evidence](bfs-completion/final-receipt.json).
This is a protocol integrity correction. No observed HTTP/2 stream loss has
been attributed to this malformed-record fault.

## BFS inbox allocation by traversal mode

Follow-up `c6126c27aae1b6262be3b1ecd6271008cc64fc69`, branch
`work/argentea-bfs-inbox`, is based on the integrated b569 snapshot. Eight
production lines avoid allocating candidate parents in Topology/Done and
allocate ghost membership only in Pull. Completion, sequence, mode and EOF
validation remain enforced.

At three partitions and 65,536 local vertices plus 65,536 ghosts, Done's
requested allocations fall from 1,117,679 to 3,567 bytes; its admitted peak
falls from 1,121,512 to 7,400 bytes. The optimized Done measurements match the
one-vertex and 1,024-vertex controls at fixed partition count. Push saves exactly
65,536 requested/admitted bytes; Pull is unchanged. All twelve matched cells,
including unchanged controls, are retained in [the counters](bfs-inbox/matched-counters.json).
These are allocation/admission measurements, not RSS or elapsed-time claims.
The old work-meter-only Done test had passed despite the unused allocations.

The exact detached core gate passed formatting, strict Clippy and 108 release
tests; the adapter passed 49 tests including 43 Argentea tests. Both suites also
passed under ten load processes, which were reaped. Four new allocation/headroom
cases fail on unchanged b569, while the wrong-mode protocol control passes.
The host's 490-test verdict remains scoped to b569; no new Linux/cluster verdict
is claimed for this native-only follow-up. [Receipt](bfs-inbox/final-receipt.json).

## WCC inbox allocation by phase

[`b4babe87cb50d16b4d439a0841a6291991c433d2`](https://github.com/querygraph/sail/commit/b4babe87cb50d16b4d439a0841a6291991c433d2)
on `work/argentea-wcc-inbox`, based on c612, applies the same discipline to WCC.
Topology and Done do not read per-vertex candidate labels, so their inboxes
omit that buffer and its admission. The six active modes retain it.

With 65,536 total vertices across three owners, inbox construction in either
WCC algorithm changes requested allocation from 1,051,663 to 3,087 bytes and
peak admission from 1,056,528 to 7,952 bytes. Optimized costs agree at
1/1,024/65,536 vertices; all six active-mode controls are unchanged. These
counters cover `start_emission`. A separate 32-KiB-headroom test holds that limit
through Done publication. Topology still constructs its incoming CSR later.

Three new allocation/headroom tests fail on the baseline. The exact detached
candidate passed core formatting/strict Clippy, 113 core tests and 49 native
adapter tests, including 43 Argentea tests. Both suites also passed with ten
load processes; all 24 matched allocation cells were unchanged under load.
[Exact receipt](wcc-inbox/final-receipt.json),
[matched counters](wcc-inbox/matched-counters.json),
[fork delivery](wcc-inbox/delivery.json). This is local allocation/protocol
qualification, not a multi-host scaling or stream-cause result.

## Pecan production-path crosscheck and paired measurement

Both candidate production-path suites passed all 125 tests, once locally and
once with two process workers using the actual GraphUtils extension. The
baseline failed the same existing push-pull observer fixture in both modes
(115 passed, one failed each). Its observer consumed iteration-start events;
the candidate checks the intended iteration-end events and preserves assertions.
Those baseline suites remain `test_failure` in the evidence.

The immutable directed fixture has 16,384 vertices and 529,723 weighted edges,
seed42/source0. SSSP frontier uses an independent heap-Dijkstra reference and
parent-tree checks. All two warmups and eight measured cells passed. Both
labels use the same old runtime and native wheel; only the controller source
changes from ffcfbd569 to edc2c7c8. Every cell has a fresh container/server:
eight CPUs, 12 GiB hard memory, four partitions/threads, two workers, a 3 GiB
pool per process, and the same timeouts. The measured order is ABBA BAAB.

Morrobay is a **shared host**. Guest steal was zero in all these cells; that does
not establish an idle or dedicated physical host. The table reports each cell
relative to the measured baseline median in its own column, preserving slower
and larger-memory observations. Warmups are shown but excluded from medians.

| Cell | Outcome | Elapsed ratio | Execute PSS ratio | Execute cgroup ratio |
|---|---|---:|---:|---:|
| warmup-base | passed | 1.2559 | 0.9906 | 0.9956 |
| warmup-candidate | passed | 1.0735 | 1.0315 | 1.0547 |
| measured-1-base | passed | 0.9782 | 1.0004 | 0.9925 |
| measured-2-candidate | passed | 1.1776 | 1.0228 | 1.0606 |
| measured-3-candidate | passed | 1.1199 | 0.9620 | 0.9632 |
| measured-4-base | passed | 1.0072 | 0.9996 | 0.9948 |
| measured-5-candidate | passed | 1.0588 | 0.9686 | 0.9900 |
| measured-6-base | passed | 0.9928 | 1.0180 | 1.0403 |
| measured-7-base | passed | 1.0680 | 0.9980 | 1.0052 |
| measured-8-candidate | passed | 0.9852 | 0.9955 | 0.9908 |

The candidate median elapsed ratio is **1.0894** (slower), PSS is **0.9821**,
and sampled cgroup memory is **0.9904**. The narrow memory differences and
variable times do not establish an end-to-end improvement. Fixed marker/aggregate
cost on a small graph is a hypothesis, not a diagnosed explanation. A larger
isolated control is required before claiming benefit from this controller change.

All commands, package identities, raw cells and failures are retained in the
[plan](pecan-gate3/plan.json), [summary](pecan-gate3/summary.json), and per-cell
receipts beneath [pecan-gate3](pecan-gate3/). Raw times are measurement evidence;
the report makes only qualified shared-host ratio comparisons.


The subsequent Grenada crosscheck used the same fixture and limits, with one
baseline then one candidate and no additional warmups. Both passed independent
heap-Dijkstra/parent checks (distance tolerance 1e-12). Candidate/baseline ratios were 1.1359 elapsed,
1.0204 execute PSS, and1.0468 sampled cgroup memory. This is one shared-host
pair, not a statistical timing conclusion. It does not supply a performance
benefit for the fused controller on this fixture. [All outcomes](grenada-gate3/summary.json).

## WCC certificate outcome correction

The benchmark's WCC certificate verifies edge consistency and that labels name
input vertices. It does not prove that each label class is connected; merging
disconnected components can satisfy those predicates. The correction is
[`c8fe857848f3ba1698ee0f9d1daf000790d691d4`](https://github.com/querygraph/sail/commit/c8fe857848f3ba1698ee0f9d1daf000790d691d4),
pushed to `work/wcc-certificate-outcomes`, based on b569.

New certificate results are `partially_verified`. Summaries and resumed runs
preserve that distinction for valid historical receipts too. Completed partial
results receive source, binary, dataset and validation-policy integrity checks;
only exact passes enter success metrics. Original evidence is retained.
This changes reporting, not the incomplete certificate into a connectivity proof.

The exact detached gate passed 333 Python tests (39 optional tests skipped) and
six actual local SQL controls. Those SQL controls use installed Sail 0.7.0 with
its native binary hash recorded; no runtime source commit is inferred.
Independent corruption controls verified the old-pass transition, new/old exit
codes, malformed metadata, identity conflicts and resumed missing evidence.
[Implementation receipt](wcc-certificate/final-receipt.json),
[independent audit](wcc-outcome-audit/hardened-c8/README.md),
[fork delivery](wcc-certificate/delivery.json).

## Linux qualification in progress

The exact detached Linux build of diagnostic/runtime commit `2894a962` passed,
including its native tests and scoped Clippy checks. Exported Sail 0.7.1 binary
SHA-256 is `40a78182a420152e8e3651f9cdb38a4196eaf8bc7aead092d10e258a17ac3497`.
The original source, binary, wheel and build-cache seed guards passed unchanged.
[Build receipt](linux-builds/integration289/final/rebuild-receipt.json).
The compact `56194b1` host build also passed with its seed guards unchanged.
Exported binary SHA-256 is
`5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec`.
[Build and cache-retention handoff](linux-builds/BUILD-HANDOFF.json).

The small actual-worker checks use the same original controller, native wheel,
16k weighted input and independent Dijkstra/parent checks. A separate
[CPU16–23 configuration](worker-smoke-cpu16-23-preparation.json) lets the
instrumented-runtime correctness check run under an 8-CPU/12-GiB hard limit
beside the compact build's disjoint CPU0–15/48-GiB allocation. This concurrency
is disclosed; these checks are not isolated performance measurements. Original
prepared CPU0–7 configurations are retained. Large 100-GiB diagnostic replays
wait for all builds to stop and sufficient disk space.

The instrumented289 check has now **passed**: 24 iterations, 16,384 unique
vertices, independent heap-Dijkstra distances and rooted parent/hop checks.
Workers 1 and 2 logged 743 and 938 successful task notifications, respectively.
The dataset and original native identities match the retained control; there
were no OOM events or cleanup leftovers. All 24 recorded plans contain grouped
`min(struct(...))`. [Verified worker receipt](worker-smoke-instrumented289-cpu16-23/verification.json).
A late supplemental cgroup observation found the container already removed;
that failure is retained. Final Docker and cgroup records verify the limits.
The compact561 worker check subsequently **passed** the same 24-iteration,
16,384-vertex Dijkstra/parent validation with identical input and original
controller/native identities. Independent review correlates all 237 tuple-MIN
task plans with successful worker statuses. There were no recorded OOM events
or cleanup leftovers. A late supplemental PID capture missed the already
removed container; that failed observation is retained without a host-PID
mapping claim. [Verified compact worker receipt](worker-smoke-compact561-cpu16-23/verification.json).
The compact smoke ran after compilation ended, so its time and memory are not
compared with the earlier concurrent-build smoke.

After both builds passed, guarded cleanup removed only their task-owned host
build caches, preserving exported binaries, wheels, source, venv and original
baseline caches. It left 35.25 GiB free, below the desired 40 GiB. The subsequent
[logging02 admission check](logging02-admission.json) verified the runtime,
clean controller source, original native binary and more than 30 GiB free with
no running Docker containers. This is point-in-time admission, not a promise
that the whole run fits. The instrumented scale-24 SSSP replay ended in OOM;
the matched compact replay is running after its own fresh admission.

## B1 opt-in checkpoint experiment

[`fe44428c9bfb43680affed0abae07240220df852`](https://github.com/querygraph/sail/commit/fe44428c9bfb43680affed0abae07240220df852)
on `work/pecan-checkpoint-repartition` adds
`GraphAlgorithms(spark, repartition_checkpoints=False)`. The default remains
`True`. The option omits keyless repartition immediately before owned staging
writes, including snapshots and final results. Writer completion, uncertain
ownership, cancellation, schema and row-count checks remain in place. It does
not declare keyed partitioning or guarantee the output file count.

The exact detached gate passed 78 unit tests and four real SQL/Parquet controls
on the disclosed installed runtime. Independent review passed. These controls
do not qualify GraphUtils, all algorithms or distributed execution; 79 other
integration cases remain unrun in this gate. [Evidence and remaining checks](pecan-checkpoint-repartition/README.md).
No speed or memory benefit is claimed, and no benchmark default was changed.

## Combined follow-up snapshot and WCC worker control

[`200d1cf8eb1db5e9057e09e071ebd57391f4b376`](https://github.com/querygraph/sail/commit/200d1cf8eb1db5e9057e09e071ebd57391f4b376)
is pushed to `work/stream-review-followup`. It combines the BFS/WCC inbox
changes, corrected WCC outcome reporting and opt-in checkpoint experiment.
The exact detached gate passed 113 core and 49 native tests, both ordinarily
and with all ten local cores saturated, plus 333 benchmark and 78 Pecan unit
tests and ten focused local SQL controls. Optional exclusions and the installed
SQL runtime boundary are retained in the [gate receipt](followup-union/final-receipt.json).
An [independent source audit](followup-union/independent-exact-audit.json)
checked all 3,429 tree entries. Host Rust remains byte-identical to `b569e75`;
the earlier host gate is not reissued as a test verdict on this union.

A separate [production representative control](wcc-fused-worker-plan/README.md)
passed on Linux runtime `2894a962` with the original controller/native package.
Both input orders returned exact results for 17 signed BIGINT vertices,
including extrema and adjacent IDs beyond 2^53. All 24 aggregate task plans
correlate with successful worker statuses on both workers and contain ordered
LAST_VALUE. This confirms the source-derived `min_by` route used by the
[component allocation probe](min-by-probe/README.md). It does not measure full
WCC memory, establish prefix emission, or identify a stream-loss cause.

## Cluster preparation and remaining work

[The second Sem review response](SEM-REVIEW-2-RESPONSE.md) checks the proposed
local/process-cluster comparison and answers all five implementation questions.
An exact-arithmetic three-vertex control refutes equating ten-step delta
PageRank with ten-step power PageRank. It also identifies missing write-commit
semantics, nonpool memory and explicit job submission requirements. The source
review and control are separate from the large Linux outcome controls.
The subsequent `7bb00a2` answers have also been reviewed: the input pointer
and library entry point are identified, while the cross-input isolate claim,
per-action distributed embedding and wide-index fallback still need the
qualifications recorded in that response.

The [official Graphalytics Parquet catalog](https://ldbcouncil.org/benchmarks/graphalytics/datasets/)
has now been identified, including its 51 listed vertex/edge pairs and a bounded
inspection of four tiny examples. [Input pointer and remaining identity checks](sem-review2/input-catalog/README.md).
The subsequent [cit-Patents preparation](sem-review2/cit-patents-input-verification/receipt.json)
pins the official vertex/edge files by SHA-256 and validates all 3,774,768
vertices and 16,518,947 edges. A separate full-row
[audit](sem-review2/cit-patents-input-verification/independent-audit.json) confirms
unique non-null vertex IDs and non-null endpoints within that vertex set.
No self-loops or weight column were found; duplicate edges were not counted.
The private original files total 73,899,325 bytes. This is newly verified input
for a shared pilot, not proof of either historical run's bytes or a completed
benchmark comparison. Larger input pairs remain unverified.
The [local WCC reference](sem-review2/cit-patents-wcc-reference/run01/receipt.json)
finds 3,627 components; the largest contains 3,764,117 vertices. Its private
canonical membership output is hashed for the pilot. The tested union-find
construction supplies connectivity; full readback checks domain and edge-label
consistency, not a second independent full-graph algorithm.

[CLUSTER-PREPARATION.md](CLUSTER-PREPARATION.md) traces the remaining single-node
and distributed costs and defines an eight-cell qualification matrix. It
separates placement with fixed total resources, strong scaling, and weak scaling.
The first barriers are simultaneous raw/CSR storage, active-round full-label
copies, quadratic control traffic, unrolled plan size, and Grenada's repeated
checkpoint write/read and lost partitioning contracts. The compact aggregation
addresses another per-worker memory cost before it is amplified across workers.

A further [admission and ownership control](cluster-ownership-control/receipt.json)
confirms the five Python clients' 64-partition ceiling. A source-derived star
model shows that equal vertex counts can coexist with more than half the arcs
and the complete first-frontier expansion on one owner. The cluster plan adds
skewed-input qualification and treats splitting heavy vertices' edge ranges as
a protocol design task. This is not a measured cluster scaling result.

Near-linear cluster scaling has not been demonstrated. A homogeneous dedicated
cluster, per-worker hard limits, exact answers and partition/transport counters
are required for that claim. The available heterogeneous hosts can qualify
correctness and placement, not establish homogeneous scaling efficiency.


## Initialization and validation follow-up

Three further fixes are committed and pushed as separate Sail fork branches.
Argentea commit `7f5b80d0` releases raw vertex/edge vectors and their admission
after CSR construction, before allocating initial BFS/SSSP state. The matched
65,536-vertex, three-owner requested-heap controls reduce peaks by 0.5–2.5 MiB,
with identical allocation counts, total allocated bytes and metered work.
Raw/CSR overlap during construction remains; this is not an RSS or timing result.
The exact gate passes 120 core and 51 native tests, ordinarily and with all local
cores saturated. [Evidence](argentea-input-lifetime/README.md),
[post-gate push receipt](argentea-input-lifetime-delivery.json). The original
evidence folder retains its pre-push cutoff; the delivery receipt updates it.

PageRank commit `7df2f32f` rejects malformed per-row convergence/iteration
metadata that nullable certificate reductions previously hid, and combines
reference-policy row checks into one aggregate. A two-vertex fixed-point
control reproduces five old certificate acceptances rejected by the reference
policy. The exact gate passes 333 benchmark tests plus 58 actual local SQL
tests; the installed runtime is pinned separately from this Python-only change.
[Reproduction, controls and delivery](pagerank-certificate-metadata/README.md).

Those controls also isolate a separate Parquet reader issue: statistics-bearing
`[NaN, 0.5]` bytes can read back as `[0.5, 0.5]`. Omitting output statistics or
disabling reader statistics collection preserves NaN and makes both unchanged
validators reject it. A separate reader mitigation, `837e8e82`, now clears
floating file bounds before caching/aggregation; all 77 data-source tests pass
on the exact commit, including real Parquet readback. Counts and integer bounds
remain usable, but floating-bound optimizations are lost, including for
finite-only files. Raw footer pruning and other reader paths are outside scope.
[Evidence and exclusions](parquet-float-statistics/README.md),
[post-gate push receipt](parquet-float-statistics-delivery.json).
No historical-result or stream-loss attribution follows from this control.
The [combined source](resource-validation-union/README.md), `a3462345`, is also
committed and pushed after its separate exact gate: 77 host tests, 120 core and
51 native tests ordinarily and with all local cores saturated, 333 benchmark
unit tests, and 58 SQL tests against a freshly built local CLI. A separate actual
Parquet control with statistics enabled preserves NaN and both policies reject
it; a finite fixed point passes. Two failed gate attempts are retained: an
interleaved-log counting error and mismatched Python executable/library paths.
These are local checks; Linux, combined native loading in workers, performance
and multi-host scaling remain outside this verdict.
