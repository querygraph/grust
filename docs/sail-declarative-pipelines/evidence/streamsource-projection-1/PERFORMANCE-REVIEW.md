# Streaming projection performance review

Read the full saved request, `STREAMSOURCE-PROJECTION.md`, repository `AGENTS.md`,
`LAKESAIL.md`, `SHEHAB.md`, `CLARITY.md` and `WRITING-RULES.md`, and source
development instructions. Inspected the current uncommitted projection operator,
logical node, planner/codec call sites and DataFusion 55.2 projection interfaces.
The source base is `06dd7e237eb5a343dcc6a6145e775f495e6c30de` in the detached
worktree `/Users/alexy/src/sail/tmp/streamsource-projection-20261105-06dd7e237`.
This is initial WIP inspection, not a final cumulative-source verdict.

## Scheduling and resource observations

The operator processes a contiguous data or marker run at a time. It finishes
asynchronous work before returning the next marker. It keeps at most the current
input batch, its pending suffix and the active evaluation future; slices may
retain their original Arrow buffers. Once a batch is exhausted, the scheduler
does not store it merely to wait for another consumer poll. Returned projection
columns can independently retain shared input buffers, which is expected.

The no-marker path avoids scanning individual rows and slicing the batch. It
still uses `try_unfold` and the immediately ready async projection function,
and clones the configuration `Arc` per data batch even for synchronous expressions.
These are costs to measure, not demonstrated regressions. There is no new
per-row global lock or scheduling service. Async results append temporary column
references and evaluate the final projector after completion; empty data avoids
calling async producers. Dropping the stream drops its pending local future,
without proving cancellation of external side effects.

Marker runs allocate projected placeholders without evaluating user functions.
Many alternating marker/data rows create many tiny projection calls and outputs,
like the known filter fragmentation case. Placeholder cost scales with schema
and marker-run length. Marker-only or dense-marker performance cannot be inferred
from the direct data path. Preserve delivery of the prior marker before evaluating
later data; gathering across that boundary is not a valid benchmark optimization.

Conservative partitioning and equivalence properties avoid advertising computed
constants or hashes that markers can contradict. This may inhibit optimizations,
but retaining invalid properties is not an acceptable speed tradeoff. The real
rewrite, optimizer and codec checks must qualify this behavior.

## Prepared bounded comparison

Prepared, but did not compile or run, the opt-in probe at
`review-logs/performance/projection_cost_probe_v1.rs` in the source worktree.
It remains outside the product test tree. The implementation owner must stage
and run it only after coordinating other builds and pinning the candidate.

The eight cells combine batch lengths 128 and 8192 with four layouts: data only,
one tail marker, two adjacent middle markers, and alternating data/markers. Every
sample processes 65,536 encoded rows. The operators are ordinary DataFusion
`ProjectionExec` and the new `StreamProjectionExec`, with identical expressions:
control-column passthrough, `value * 2`, and identifier passthrough. Marker payload
values are nonnullable zeros, making both results equivalent without invoking an
unsafe expression or inventing different predicates.

Before timing, the probe compares both schemas and exact ordered rows, including
marker bytes, retraction flags, calculated values and identifiers, with an
independently constructed expected output. Seven paired samples alternate
execution order; each cell has two warmups per operator. It records input/output
fingerprints, plans, output rows and output batch counts. Timing includes operator
execution and immediate draining; construction, validation and fingerprinting are
outside timing.

The owner should retain source/lock hashes, exact compiler/profile environment,
complete logs and every measured cell. Prefer optimized code generation and
report the actual profile. Shared-host ratios remain diagnostic, with no source
input/output, downstream retention, asynchronous function cost, distributed
execution or production memory envelope. The safe arithmetic fixture isolates
projection/scheduling cost; it does not establish the benefit of avoiding expensive
native or asynchronous work on markers. No performance result is claimed yet.

## Frozen cumulative source review

Independently verified all 52 file hashes in `candidate-snapshot-final.json`,
staged tree `52cbe5f4281bf74b9d54615504ce7eb9e062f80d`, increment SHA-256
`5fa79cdd5f911e5449ffb64b0991ef7a21d3d3101e2311576cddb0f143022ecc` against
`06dd7e237eb5a343dcc6a6145e775f495e6c30de`, and cumulative SHA-256
`70390f447d0b7425a49cc8cbec2649ec1a3a11a5f2cb5d5ea7a372c11dfc6b20` against
upstream `b52144955b629314a000b1fe49eeea97fa3d0c5c`.

Reviewed the final new operator, logical projection/source-adapter changes,
rewrite, planner and codec integrations, manifests and supporting scheduling and
ownership tests. Earlier foundation and scalar implementation files remain part
of the cumulative pin and retain their previously reviewed behavior.

No additional must-fix retention or synchronization issue was identified. Data
evaluation does not acquire a global lock. Async expressions remain sequential
within a data run. A following marker cannot be emitted before the pending data
future completes, and later data is not evaluated before that marker is returned.
Dropping the stream drops the pending future and owned input. The tests use
controlled futures and weak array ownership rather than timing races.

The final empty-input guard avoids evaluating both synchronous and asynchronous
expressions when no data rows exist. It returns an empty batch under the output
schema without changing the nonempty data path. Marker runs still allocate
placeholder arrays and emit independently. A current mixed input remains retained
until its last run is consumed; output slices can keep its buffers afterward.
This is bounded to the current batch, not a newly unbounded queue. Async evaluator
batching costs remain governed by the public helper and actual data-run sizes.

Conservative physical equivalences and unknown partitioning prevent downstream
optimizations from treating marker placeholders as computed constants. The codec
serializes the original expressions and metadata schema, reconstructing the same
evaluator at decode rather than retaining execution-time async results. Planning
and schema construction are outside the row-evaluation loop.

## Completed optimized comparison before the final empty-input change

Read `results-v1.json`, its measurement-source snapshot and the full successful
probe log. The log records `Finished` for the optimized test profile and one
passing exploratory test. Exact ordered schemas/rows matched for every cell before
timing. All seven paired samples per cell were retained. Ratios divide candidate
elapsed time by ordinary `ProjectionExec` elapsed time.

| Batch rows | Layout | Median ratio | Pair range | Output batches baseline/candidate |
| ---: | --- | ---: | ---: | ---: |
| 128 | none | 0.6542 | 0.5245–0.8020 | 512/512 |
| 128 | tail | 1.6883 | 1.6644–1.7706 | 512/1024 |
| 128 | middle pair | 2.2040 | 2.1898–2.3632 | 512/1536 |
| 128 | alternating | 73.0537 | 70.2298–75.2189 | 512/65536 |
| 8192 | none | 0.9270 | 0.9089–1.1190 | 8/8 |
| 8192 | tail | 4.0509 | 3.9873–4.2814 | 8/16 |
| 8192 | middle pair | 4.0506 | 4.0369–4.2852 | 8/24 |
| 8192 | alternating | 723.5454 | 424.5990–845.3663 | 8/65536 |

This comparison ran on a shared ten-logical-CPU Mac. The recorded one-minute
load average was 38.49 before the build/measurement and 25.14 after measurement.
There was no CPU isolation or steal measurement. Data-only medians below one
do not establish a general improvement. Large variability in some cells and
different host load also prevent comparing these ratios directly with earlier
filter timings. No absolute production throughput is claimed.

The sparse and dense mixed-marker gap is material. Extra scanning, slicing,
placeholder construction, evaluator calls and output dispatch all contribute
potential costs; the probe does not isolate their individual contributions.
This blocks broad performance/upstream readiness. The implementation can be
retained as a correctness reference while repairs are measured, with the same
ordered-event contract. Correctness success does not waive this gap.

A narrowly scoped next experiment can replace per-row boundary scanning with
Arrow 59.2's public validity-slice iterator, preserving contiguous run boundaries.
That may reduce sparse-marker scanning overhead without buffering or evaluating
across markers. It will not eliminate dense output fragmentation. Bounded assembly
is a separate measured choice, with copies, retained bytes, latency and cooperative
polling checked explicitly. Neither mechanism is a demonstrated improvement yet.

V1 precedes the final empty-input guard. Although these eight cells contain only
positive-sized input batches, its verdict is still pinned to that earlier source.
The implementation owner plans to repeat the identical probe on the frozen final
candidate. That repeat and immutable qualification remain pending; no final-source
timing verdict is inferred. This review performed no builds, tests or source edits.

## Revised final source and completed repeat

The revised final snapshot supersedes the preceding projection pin. Independently
verified all 54 cumulative file hashes, staged tree
`b67d1a9416d22241ab0359e2ef96dcdf3c678757`, increment SHA-256
`0a556ee174bbd47da7148e8ae8f999707482b8078b6fcabed553882fa015bea3` against
`06dd7e237eb5a343dcc6a6145e775f495e6c30de`, and cumulative SHA-256
`c34dcc56ba6d8f7260e7d6eb0997a7dd016fd07de6e79d5a2424da574d6cf1bf` against
`b52144955b629314a000b1fe49eeea97fa3d0c5c`. The increment now spans 26 paths.

Reviewed the new attributed nullable-array constructor and its call sites.
It preserves Arrow's original null layouts and uses checked size multiplication,
offset addition, signed run/union conversions and allocation-layout checks. Ordinary
primitive, variable-width, list, struct and union construction still allocates
storage appropriate to the requested type and length; checked arithmetic does
not cap aggregate allocations. Nested fixed-size children can multiply storage,
so successful representability checks are not a memory-admission mechanism.
Allocation exhaustion remains subject to the caller's budget, as documented.

Run-end null arrays remain compressed: nonempty logical arrays use one physical
run and one null physical value. Empty arrays use empty children. Field metadata
is retained through the exact requested data type. The helper does not allocate
a logical-row-sized bitmap for a run-end parent. Its capacity checks add work
per buffer/schema node rather than per data value. The existing data-event Binary
marker construction retains Arrow's original direct constructor; the helper's
new use is restricted to generic payload placeholders and empty-output paths.
No new queue, lock or persistent cache was introduced by this correction.

The completed repeat is retained in `results-final-v2.json`, its receipt and raw
log. It used tree `0fd5f5e69cf79ce8afed06474219ef81730a84de`; inspected the direct
tree diff and `source-equivalence-v3.json`, confirming that only three Python
query statements changed afterward. All runtime code is identical to the revised
final tree. The optimized build completed and the exploratory test passed with
unchanged measured source and exact ordered outputs for all eight cells.

| Batch rows | Layout | Median ratio | Pair range | Output batches baseline/candidate |
| ---: | --- | ---: | ---: | ---: |
| 128 | none | 0.6510 | 0.6421–0.6550 | 512/512 |
| 128 | tail | 1.7066 | 1.6793–1.8524 | 512/1024 |
| 128 | middle pair | 2.2712 | 2.2122–2.3134 | 512/1536 |
| 128 | alternating | 76.2801 | 74.1989–76.9086 | 512/65536 |
| 8192 | none | 0.9490 | 0.8372–1.1433 | 8/8 |
| 8192 | tail | 4.0212 | 3.9426–4.6435 | 8/16 |
| 8192 | middle pair | 4.0493 | 4.0212–4.3397 | 8/24 |
| 8192 | alternating | 712.0118 | 637.0010–865.5604 | 8/65536 |

Every cell retains seven paired samples, including all slower cases. The same
probe source was used. The profile was test opt-level 3, debug information and
incremental compilation disabled. This shared ten-logical-CPU Mac had recorded
one-minute load averages 18.25 before the build/measurement and 40.76 afterward.
CPU isolation and steal measurement were unavailable. These are diagnostic
ratios, not a dedicated-host throughput or broad improvement claim.

The mixed-marker gaps remain material and block production/upstream performance
readiness. The data-only path and exact results remain useful reference evidence.
The safe-arithmetic probe uses nonnullable primitive payloads; it does not measure
the new nullable constructor across schemas or async/native kernel workloads.
Those costs have source inspection and correctness coverage here, not a measured
performance envelope. Whole-tree qualification remains pending. No source edits,
builds or timing runs were performed by this reviewer.

## Observability correction and final source review

The observability correction supersedes all preceding projection source pins and
their timing verdicts. Independently verified 58 cumulative file hashes, 31 increment
paths, staged tree `5a8f4f67535644e0cb8e4eb52389cfb4395bc3d9`, increment SHA-256
`e0ed57aa267daafbc6c4517a2712c4b1e9cbc050bf544bc62e4f7a1e9e4200f5`, and cumulative
SHA-256 `450642c939973266f80b2e7bcb52fe60dad7bc0f69fac5d733b9e18f34c77023`.
Reviewed the complete updated operator, baseline metric tests, typed telemetry
emitter selection and projection emitter test. Saved request and governing-file
compliance remains confirmed.

The earlier candidate omitted standard baseline output rows, batches and bytes,
and its operator elapsed-compute work. Ordinary `ProjectionExec` performed that
observability work. Therefore the earlier candidate's data-only ratios cannot
support an equivalent-work improvement claim. Preserve the raw results and their
source pins, but supersede their application to the final implementation. Exact
output equality alone did not detect this missing operational behavior.

The final stream owns one `BaselineMetrics`. It records each encoded output once,
including marker batches and rows, through the standard `RecordOutput` path.
The state moves between yields rather than cloning baseline owners per run.
The baseline is dropped at EOF, error or consumer cancellation, so terminal
metrics do not finish after the first output. Source tests cover output counters,
memory-size accounting and the end-timestamp lifecycle. These are inspected tests,
not execution performed by this reviewer.

Boundary scanning is timed after upstream input polling returns. Placeholder
construction and synchronous projection are timed directly. For async helpers,
each active future poll receives a timer; the timer drops when that poll returns,
including `Pending`, so suspension is excluded. Conversion of results to arrays,
final batch construction and projection are timed separately. No timer is held
across a wait. The source adds no shared lock or per-row metric update: timing
and standard output counting occur per run/poll/output, with existing projector
expression metrics retained. These timers and output-byte calculations add real
work and must remain enabled in the new comparison.

Output-byte accounting follows DataFusion's standard batch-memory metric; it is
not a retained-memory peak and may count shared buffers across multiple emitted
slices. It does not introduce a new owner of those payloads. The typed projection
emitter now recognizes the streaming node while retaining default metric handling.
This preserves operator and expression observability rather than replacing it
with an untyped metric-name fallback.

No additional correctness, lifetime or metric-scope defect was identified in
this delta. Material mixed-marker performance remains unresolved. Root's repeat
of the same eight-cell probe must use this exact final runtime with its standard
metrics enabled. Pending that receipt, neither earlier data-only ratios nor
earlier mixed-marker magnitudes qualify this final source. The whole immutable
gate also remains pending. No source edits, builds or measurements were performed
by this reviewer.

## Completed observability-enabled comparison

Read every cell in `results-final-v4.json`, the matching receipt and complete
successful optimized-test log. They identify the exact reviewed tree
`5a8f4f67535644e0cb8e4eb52389cfb4395bc3d9` and cumulative diff
`450642c939973266f80b2e7bcb52fe60dad7bc0f69fac5d733b9e18f34c77023`.
The source was unchanged during measurement. Exact ordered outputs passed for
all eight cells, with seven alternating-order paired samples retained per cell.
Standard output and expression observability was enabled. The log records a
completed optimized build and one passing exploratory test.

| Batch rows | Layout | Median ratio | Pair range | Output batches baseline/candidate |
| ---: | --- | ---: | ---: | ---: |
| 128 | none | 1.1658 | 1.1011–1.1950 | 512/512 |
| 128 | tail | 2.5338 | 2.4400–2.5583 | 512/1024 |
| 128 | middle pair | 3.6082 | 3.2241–3.6311 | 512/1536 |
| 128 | alternating | 125.1133 | 109.9082–127.6491 | 512/65536 |
| 8192 | none | 1.0428 | 1.0154–1.2600 | 8/8 |
| 8192 | tail | 4.1383 | 3.9433–4.4494 | 8/16 |
| 8192 | middle pair | 4.2587 | 4.2507–4.5973 | 8/24 |
| 8192 | alternating | 1233.0712 | 1118.8325–1541.4068 | 8/65536 |

Ratios divide candidate elapsed time by ordinary `ProjectionExec` elapsed time.
The shared ten-logical-CPU macOS host had load averages 9.91 before the
build/measurement and 17.75 afterward. CPU isolation and steal measurement remain
unavailable. These are diagnostic ratios and cannot establish absolute production
throughput. Earlier pre-observability data-only ratios remain retained historical
results but are superseded for final-source comparison; they do not demonstrate
an improvement with equivalent operational work.

The no-marker 128-row slowdown is meaningful: every pair was slower, with a
median overhead around sixteen percent and the minimum pair above ten percent.
The 8192-row median is also above one. Shared-host limitations do not justify
dismissing this consistent result as noise. Mixed-marker slowdowns remain much
larger and block production/upstream performance readiness independently.

A narrow synchronous data-only fast-path repair is justified. Source inspection
identifies avoidable candidate work: separate scan and projection compute timers,
a generic async state transition for immediately synchronous evaluation, and a
configuration `Arc` clone on each batch even when no async expression exists.
These are hypotheses to isolate, not measured attribution of the slowdown.

Prefer a direct synchronous poll/project path for no-marker batches, with one
compute timer covering that node's scan and projector work. Preserve standard
output rows/batches/bytes, projector expression metrics and typed telemetry.
Share event-boundary extraction with mixed and async paths rather than introducing
inconsistent ordering implementations. Keep existing error, marker, input-lifetime,
empty-input and terminal-metric checks. Compare the repaired candidate with both
this instrumented reference and ordinary `ProjectionExec`, retaining all cells.
Removing metrics to restore the old ratios would invalidate the comparison.

This finding calls for a bounded cost repair and remeasurement; it does not
authorize weakening event ordering or generalizing async capabilities. Whole-tree
qualification also remains pending. No source edits, builds or timing runs were
performed by this reviewer.

## V7 direct synchronous path and final comparative result

Independently verified all 58 cumulative file hashes, staged tree
`bb8699fdfbc4ca88fa6c0e816e189af80e560efd`, increment SHA-256
`9414d2b00491eedfd76e52e212459f92735963e46a6eb0d3c9f79b444e4693a2`, and cumulative
SHA-256 `7f2cf1d64419f8968e311f04b4b132bed8ee05e5e94be995dcf083b10dd9f8aa`.
Reviewed the complete revised operator and added pending/wake/error/drop test.
The earlier metric-preserving shared synchronous scope alone was insufficient;
this candidate additionally uses a direct synchronous poll path where no async
expressions exist. All prior source verdicts apply only through their named pins.

The direct path and async path share input acquisition, contiguous-boundary
extraction, the projector, placeholders and metric owner. Synchronous evaluation
does not create a per-run async future or clone configuration per batch. One
compute timer covers boundary extraction and synchronous projection. The existing
async path retains per-active-poll timing and excludes suspension. Standard encoded
output accounting and typed expression telemetry remain enabled.

The synchronous closure owns `Option<ProjectionStream>`. It consumes at most one
input batch or pending run per poll, delegates `Pending` and wake registration to
the upstream stream, and drops state immediately on EOF, upstream error or
projection error. Later polls return `None`. This avoids retaining unread input or
prematurely finishing metrics. A controlled channel test checks pending-to-wake,
successful output, an upstream error with unread buffered data, immediate receiver
and payload release, and repeated terminal polls. Source inspection found no new
lifetime, scheduling or metric-ownership defect. No test was run by this reviewer.

Reviewed `results-final-v7.json`, its successful optimized build/test log, raw
samples and staged probe. This is a three-way comparison in one binary: ordinary
`ProjectionExec`, the original instrumented projection at tree `5a8f4f67`, and
the final candidate. Each timed rotation changes the starting implementation;
all three receive identical inputs and expressions. All schemas and exact ordered
rows are checked before timing, with two warmups and seven rotations per cell.
Independently recomputed both ratio medians from the raw samples.

The original source has SHA-256
`91c8fd4e851a079f0de4b4625a0069206c24938f5bb38c3926cbb773c55f398a`.
The compiled reference module has SHA-256
`28e6ef77791b73fb569b2fd7491f96a8be00f85354af1219347130e653b4d16a`.
Direct comparison confirms its only adaptation removes four `cfg(test)` module
declarations; the production implementation is unchanged. This avoids attributing
cross-run host differences to the fast-path repair.

| Batch rows | Layout | Candidate/ordinary median | Pair range | Candidate/original median | Output batches ordinary/candidate |
| ---: | --- | ---: | ---: | ---: | ---: |
| 128 | none | 1.0303 | 0.7916–1.0900 | 0.9076 | 512/512 |
| 128 | tail | 2.2633 | 2.0970–2.4919 | 0.8554 | 512/1024 |
| 128 | middle pair | 3.1593 | 2.9970–3.1717 | 0.8805 | 512/1536 |
| 128 | alternating | 109.7386 | 102.8819–116.5615 | 0.8925 | 512/65536 |
| 8192 | none | 0.9580 | 0.5336–1.0456 | 0.9582 | 8/8 |
| 8192 | tail | 2.7122 | 2.5468–3.0050 | 0.6520 | 8/16 |
| 8192 | middle pair | 2.7610 | 2.7337–2.7941 | 0.6533 | 8/24 |
| 8192 | alternating | 1072.7504 | 894.3031–1292.2558 | 0.8994 | 8/65536 |

The measurement receipt pins the exact v7 tree and cumulative diff, with unchanged
source and exact-output success. The optimized test-profile build finished and
the exploratory test passed. The shared ten-logical-CPU Mac had one-minute load
averages 9.26 before the build/measurement and 11.48 afterward; CPU isolation and
steal measurement remain unavailable.

The same-process comparison supports keeping the direct path over the original
instrumented implementation for these fixtures. The formerly consistent small
data-only regression is reduced to a median ratio 1.0303 versus ordinary projection,
with pairs on both sides of one. This does not prove performance neutrality or a
production improvement; additional tuning merely to force a ratio below one is
not justified by this evidence. The larger data-only cell is also close to one.

Mixed-marker cost remains material, including sparse layouts, and still blocks
production/upstream performance readiness. Dense fragmentation is not repaired by
the direct path. Keeping v7 as a correctness reference is reasonable subject to
the final immutable gate, with this limitation explicit. The benchmark still does
not qualify async/native workloads, nullable placeholder schemas, retained-memory
peaks or distributed streaming. No source edits, builds or timing runs were
performed by this reviewer. The saved request and governing-file compliance remain
confirmed.
