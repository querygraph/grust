# Sem review: completion evidence on Morrobay

This report joins the Oct 1 review board, the native Oct 2 comparison, and
the additional Oct 3 controls. It records observed outcomes and the limits
of each experiment. The canonical task list is
[SEM-REVIEW-2.md](../../SEM-REVIEW-2.md#9-work-division-and-status-board-2026-10-01).

## Execution contract

All new graph timings use native macOS release binaries. No benchmark VM
was started. Root serializes engine jobs, waits for their owned processes,
and runs independent full output comparisons after engine shutdown.
Software partition, thread, and memory-pool settings are recorded separately
from operating-system limits. This shared host does not provide dedicated
absolute performance results.

The original single-architecture Sail runtime is `9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3`, built with
`cargo build --locked --release -p sail-cli`, optimization level 3, full LTO,
one codegen unit, debug information disabled, and stripping enabled. The
native binary SHA256 is
`ee80ac3cf9d028639561f3cf32435985192719d629807fcf6a368324fa84946e`.
Algorithm and extension sources have separate identities in their receipts.
The C2 enabled-observer profile separately uses source `98de82ab` and its
pinned release CLI `a4842a8c`; its receipts and timings are distinct from
the native9f baseline. X1 uses the separately pinned native universal2 CLI
and extension wheel; its assembly and per-host identities are in the X1
appendix.

## Pregel programs and plans (E0)

**Implemented and checked.** [Sail PR #32](https://github.com/querygraph/sail/pull/32)
adds weighted distance-only SSSP and graphframes-rs landmark shortest paths
to the existing Pregel primitive. Existing traversal methods retain their
contracts. The new programs perform no input-validation data jobs.

The exact committed source is
`f2b297fc8443221891ce5f4afe88f955ed125b38`. Its detached source gate passed
227 tests; the test process and server were actually waited, and the source
remained unchanged. Eleven native cells have complete output oracles and
retained executed plans: PageRank, SSSP, and landmark paths on cit-Patents,
kgs, and wiki-Talk, plus two additional cit-Patents traversals using an
active source.

For kgs, the official weighted SSSP comparison covers all 832,247 vertices:
819,249 finite distances and 12,998 unreachable vertices. The largest finite
absolute difference is `8.881784197001252e-16`; no row exceeds the declared
`1e-12` relative/absolute tolerance. Official positive infinity is compared
with the program's unreachable NULL. This is numerical agreement, not
bitwise equality.

The original cit-Patents source 1 reaches only itself, so those traversal
cells are correctness controls. The additional source 5,795,784 reaches
126,298 vertices in 14 supersteps and supplies an active traversal control.
PageRank uses the matched GraphX delta contract with final normalization;
it does not stand in for LDBC's fixed-step power recurrence.

The plans join the active vertices to adjacency, aggregate messages, and
join state once per step. The state is the single materialized relation;
vote-to-halt adds an activity count. Complete plan and action records are in
[the E0 evidence](E0/README.md), including the full output inventories and
earlier attempts.

## Vortex as a checkpoint format

**Capability question answered; a checkpoint writer is unavailable.** The
unregistered native control reports no Vortex data source. Registering the
fork's byte-identical Python reader passes a complete six-row typed read,
filter, and projection control. Writing still returns NOT_IMPLEMENTED.
This reader experiment supplies neither a native Rust writer nor a
distributed or graph-scale checkpoint performance result.

[Vortex evidence](Vortex/README.md) retains successful controls, the failed
registration attempt, actual package/source identities, and waited process
closure. The executed server remains the pinned fork release CLI even when
a published Python package supplies the reader's import dependency.

## Distributed action costs (C2)

The original native release profile completed 60 fresh server trials: 20
cold/warm pairs at each of 4, 16, and 32 partitions. All 120 complete
4,096-row outputs passed. Every action executed on both workers, with an
actual hash exchange. The observed topology is one job, two stages, and
8/24/40 tasks respectively; input-file fanout is distinct from the final
exchange's partition count.

Median paired cold/warm collect ratios in the [original native04 profile](C2-D2-C4/C2-summary.json) are
0.445, 0.529, and 0.593. The second action is slower in this bounded workload;
these ratios do not identify its cause.

The separate enabled-observer profile at source `98de82ab` completed another
60 cold/warm pairs, 20 at each partition count, with 120 complete 4,096-row
answers and both actual workers. Typed error, pool refusal and tagged
cancellation controls also pass. Together they cover all 43 declared named
scopes with strict received identity, causal and delivery checks. The
[closed appendix](updates/source05/README-APPEND.md) retains operation-bound
event counts and p50/p95 inclusive interval summaries. These intervals
overlap across phases, tasks and processes: their sums are not an exclusive
wall budget. Complete server attribution remains unqualified. Observer
timings remain separate from the original profile's ratios, and earlier
failed source/runtime attempts remain preserved.

The profile has a driver and two workers, a 10 GiB greedy pool per process,
and 16 configured software threads per process. It is not an OS-enforced
16-CPU or 32-GiB envelope. Per-process RSS/physical-footprint samples have
their recorded omissions; they are not PSS or a cgroup peak.

## Checkpoint hash layout in a cluster (D2)

**Measured with actual plan predicates and full answers.** Safe checkpoint
preparation is `repartition(P, key).checkpoint()`, without a preceding
sort. With merge joins requested explicitly, all 180 repeated joins across
4, 16, and 32 partitions show the expected join-input hash exchanges:
two for plain/plain, one for checkpoint/plain, and zero for
checkpoint/checkpoint. Every round executes on both workers; all 420
complete answer checks pass. Two runtime sorts and the aggregate exchange
above the join remain.

| Partitions | Checkpoint/checkpoint over plain/plain, median paired collect ratio | 95th percentile paired ratio |
|---|---:|---:|
| 4 | 0.905 | 2.685 |
| 16 | 0.809 | 1.676 |
| 32 | 0.717 | 1.430 |

Read/write/setup controls are retained separately. The median
checkpoint/plain state-write ratio increases from 1.157 through 1.790 to
2.436; the corresponding state-read ratios are 1.018, 1.393, and 1.875.
Skipping an exchange therefore does not establish lower whole-algorithm
cost. These are 20 repeats over fixed state, not 20 advancing graph rounds.

The default hash-join smoke instead broadcasts the small state and does
not qualify partitionwise reuse. Both profiles are retained. The merge-join
control exercises native9f's generic checkpoint hash declaration; it does
not claim the historical Nutmeg17 sorted-scan API or elimination of sorts.
The earlier long harness failure occurred during evidence serialization;
the corrected profile stores each complete answer once outside its clock.

## Aggregate factories (C4)

The current native pair returns the same complete three-field winner for
all 4,096 groups. Executed plans show Partial and FinalPartitioned
aggregation, a hash exchange, and both workers. The actual `min_by` rewrite
is ordered `last_value` of the full struct with DESC NULLS FIRST and a
nonnull filter.

In this single ordered pair, min_by/MIN collect ratios are 1.621 cold and
1.543 warm; parent launch-to-exit ratio is 0.997. This bounded query does
not measure allocation per group.

**The separate full-Struct factory allocation controls are now qualified.**
Six fresh single-thread controls cover 4,096 and 100,000 groups with the same
nonnull `(distance DOUBLE, hops BIGINT, parent BIGINT)` payload and complete
key. At 100,000 groups, compact Struct MIN requests 5 allocations versus
6,500,283 for ordered Struct min_by. First-update additional live requested
bytes are 4,194,304 versus 155,815,680; cumulative requested bytes are
8,126,464 versus 622,458,304. All evaluate/state/merge semantic checks pass.
The [complete rows](C4-allocation/first-update-table.json) and
[factory source, logs and closure](C4-allocation/README.md) retain every
control and failed attempt.

The standalone source is committed at
`ef5fc415ab4b182fb3df4e238cf634cc9fc94cd9`. Its actual native committed
run04 passes Rust versions, fmt, Clippy, tests and release compilation with
the unchanged exact binary, reusing the six closed controls. The failed
run01's forced cleanup and unknown timed-out exit status remain unqualified;
run03's inherited GIT_PAGER refusal occurred before any command.

These counters count requested System allocations, not MiMalloc, native
Sail pools, physical storage or a whole-process memory envelope. Raw clocks
include reported-size/output-size sampling. The approximately 240 GB
reported ordered-accumulator size repeatedly accounts for shared buffers;
it is not unique live or physical storage. The original WCC Long/Long
min_by and whole-graph performance are outside this full-Struct control's
scope. Historical generic Struct MIN controls retain their own scopes.

## Resource reservation ownership (C3)

**The [original local native lease control](C3/README.md) passed.** A 192 MiB shared greedy host pool
admits a 128 MiB native lease, refuses a competing 128 MiB lease with only
64 MiB available, releases the first reservation, then admits and releases
the replacement. The audit binds both lease IDs to the same actual process
and native extension identity. All three degree rows pass the independent
physical output check.

The first session's participating native counters report 1,261 bytes used,
34,248 bytes peak, and 156 bytes staged; its projection accounts for
1,105 bytes. The replacement starts with zero used/peak/staged bytes and
empty graph/read registries. These counters differ from the coarse 128 MiB
host reservation. This small control establishes reservation ownership and
refusal/release semantics. It establishes neither nonpool headroom nor
transport/spill totals, PSS, an OS 32-GiB limit, or physical reclamation.

The closed observer smoke and main run also retain sampled RSS and physical
footprint observations. Of 249 PID/birth groups, 239 have verified identities
and 10 do not, including five unknown-birth groups; 244 groups have valid
footprint samples. Peaks are observed per-process samples. Process peaks
and footprints are not summed into a unique physical total.

All 61 metric observations contain `execution.spill_count`,
`execution.spill_size` and `execution.spill_row_count`. All lack
`execution.memory_used`, `execution.buffer.peak_memory_used` and
`execution.buffer.peak_queued_batch_count`; their peaks remain null.
Repeated exports are deduplicated by the complete series attributes and
start/timestamp, rather than summed. [The sampled reduction](updates/source05/README-APPEND.md)
preserves gaps and unverified identities. Complete operator/native memory
accounting, transport bytes, nonpool headroom, PSS, OS peaks and an
OS-enforced 32 GiB envelope remain unqualified.

## Banda in four phases (F2a)

**Both graphs, one and three calls, all eight outputs qualified.** The
ordinary released-0.24.0 lazy baseline remains
[a separate profile](../sem-review-morrobay-2026-10-01/F2a/Native024/README.md).
Its lazy/overlapping boundaries cannot be relabelled as four exclusive
phases.

The additional [four-phase evidence](F2/README.md) fully reads Parquet into
client Arrow, builds/stages through bounded inline Arrow checkpoint chunks,
fully drains each algorithm result, then writes Parquet. The CSR/build
phase includes the Arrow/checkpoint bridge, and the algorithm phase includes
full result transport. It is a disclosed alternative execution profile,
not an equivalent kernel-only or ordinary-lazy-baseline timer. All eight
full outputs are also preserved on Apo with matching SHA256 identities.



## Stream controls and native two-host replay (X1/X2)

The fresh two-worker reference BFS has 4,096 exact rows, 4,095 reached
vertices, depth 11, and 12 rounds. Its worker-task and job evidence is
retained. The separate small-pool control records ten typed allocation
failure-to-task-report witnesses before cleanup. Their process-local log
order does not establish a global first-fault order across workers.

Original setup and task-capacity failures remain distinct: extension
registration, a missing precreated staging directory, and a 17-slot region
refused by a 16-slot budget. The corrected P16 control declares two
nine-slot workers; neither worker can execute a complete 16-task region
alone. No failed or uncertain write is treated as a successful result.

The current X1 profile has now executed natively across Morrobay x86-64
and Capitola arm64 with a byte-identical universal2 CLI and extension wheel.
Tiny08 passes the complete signed 13-vertex/14-edge mathematical and
physical BFS certificate, including minimum signed parents and execution
on both workers. The BFS K0 control preserves its strict07 failure; the
native-bound qualifier08 proves the cap at the DataFusion FFI seam while
recording the actual RPC tag as Unknown and the execution wire tag as
not preserved. The separate plain DataFusion 1 MiB host-pool control
preserves its typed Execution allocation cause; it makes no Argentea
allocator claim.

The complete original generated scale24 replay is now qualified on both
physical hosts. It preserves all 16,777,216 vertices and 268,435,456 weighted
edge records, source 13,507,776, undirected BFS, K8 and P32. This is the
original generated X1 fixture; it is separate from the LDBC Parquet graph
used for the Pecan comparisons. All original weights remain in the files
and are unused by BFS.

All 16,777,216 output rows pass the independent physical and mathematical
certificate. It checks every original edge, exact distances, minimum
signed-ID parents, source-rooted parent paths, unreachable rows and full
input/output inventories. Reached vertices total 8,862,601; maximum distance
is 5 and the terminal level count is 6. All seven certificate flags pass,
and every one of the fourteen failure counters is zero.

The new composite qualification binds those results to both actual native
workers, all 32 owners, 640 successful native tasks and 672 owner events.
Original inner/outer waits, the independent process/source checks and both
natural memory-observer waits are closed. The original producer's physical
flag and the oracle's process/history flags stay false; the new separately
qualified conjunction supplies the combined evidence.

Original scale24-01 remains a closed failed attempt: the declared
3,600-second client lifetime elapsed with KeyboardInterrupt, owner and
inner/outer waits1, no final export and partial memory samples. The first
independent checker hit the inherited 256-file limit; the fresh checker
used 8,192 descriptors and the same native result. A metadata-conjunction
failure also remains preserved. The corrected conjunction composes the
already observed outer waiter closure and accepts the exact original
absolute input paths. No native graph run was repeated for these checker
or metadata fixes.

Store03 stopped through its normal lifecycle with original supervisor0
and server0, current group absence and its dedicated lock released.
Store02's earlier expiry remains failed. The temporary Capitola Sail
firewall entry is removed; Capitola's global state1, Morrobay's state0 and
unrelated application rules are unchanged. Output, backend data and
private credentials are retained.

[The final X1 report](updates/final-x1/README-APPEND.md) links the complete
qualification, original failures, native artifact assembly and cleanup
evidence. [X1's earlier preparation status](X1/README.md) and the dated
source05–07 appendices retain their original scopes. This report includes
no private credentials or credential hashes.

The requested experiment queue is closed for these disclosed profiles;
the additional F2a rerun remains paused. Per-process samples do not
establish PSS, an OS32GiB cap or unique whole-host physical memory.
Complete server phase attribution remains unqualified, Vortex writing is
unavailable, and the initiating causes of the historical X1/X2 failures
remain unknown. Current known-cause controls cannot diagnose those events
retrospectively.

## Evidence storage

Small source, receipt, event, plan, and review files are checked into this
directory with metadata manifests. Large Parquet outputs and native
binaries remain on Apo or the benchmark SSD, identified by byte counts and
SHA256 in the receipts. Copy verification proves identity; it is not a
second execution of the graph oracle. Original failed attempts are retained.
