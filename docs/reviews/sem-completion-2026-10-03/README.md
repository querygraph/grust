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

The Sail runtime is `9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3`, built with
`cargo build --locked --release -p sail-cli`, optimization level 3, full LTO,
one codegen unit, debug information disabled, and stripping enabled. The
native binary SHA256 is
`ee80ac3cf9d028639561f3cf32435985192719d629807fcf6a368324fa84946e`.
Algorithm and extension sources have separate identities in their receipts.

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

Median paired cold/warm collect ratios are 0.445, 0.529, and 0.593. Thus
the second action is slower in this particular bounded workload. These
ratios do not identify planning, serialization, scheduling, or cleanup as
the cause. A separate opt-in Rust observer is undergoing exact source gates
and native qualification to measure those inclusive intervals directly.

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
not measure allocation per group. The current same-struct 100,000-group
allocator control is being gated separately; historical generic struct
MIN controls retain their own controller, allocator, and memory scopes.

## Resource reservation ownership (C3)

**The native lease control passed.** A 192 MiB shared greedy host pool
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

## Stream controls and remaining external dependency (X1/X2)

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

SSH access to Capitola is restored. The hosts use different native CPU
architectures, so CLI/package identity and data/lifecycle admission are
being checked before the two-host replay. [X1 status](X1/README.md) records
its execution status. The old non-OOM
stream failures remain
unexplained: the retained logs do not record an initiating cause before
teardown. A new known-cause control cannot retrospectively diagnose them.

## Evidence storage

Small source, receipt, event, plan, and review files are checked into this
directory with metadata manifests. Large Parquet outputs and native
binaries remain on Apo or the benchmark SSD, identified by byte counts and
SHA256 in the receipts. Copy verification proves identity; it is not a
second execution of the graph oracle. Original failed attempts are retained.
