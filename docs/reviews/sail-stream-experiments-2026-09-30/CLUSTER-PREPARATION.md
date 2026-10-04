# Argentea and Grenada cluster preparation

Recorded UTC: 2026-09-30T16:29:42.286808+00:00

Source review, not a new cluster measurement. This note proposes a small
experiment after the current stream diagnostic cell and its implementation
changes are qualified. No remote workload was launched for this review.

Reviewed `querygraph/sail` runtime `ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73`
through checkout `837a8ecf5c2c3b8ad24e044c72c1cb69d9fc71f4`; their only difference
is nine environment-passthrough lines in `argentea/python/qualify.py`.
Reviewed Grust handoff at `b91828b2765ec2018e21011aea686e931af68c99`.
Both canonical remotes were fetched before this inspection. Line numbers name
this reviewed source. Short paths starting `argentea/`, `nutmeg/` or
`graph-algorithms/` are under `examples/extensions/`; `job_graph/`, `driver/`
and `task_runner/` are under `crates/sail-execution/src/`. Sibling file paths
within a paragraph use the directory established at its first citation.

The three priorities below are structural costs with measurable controls.
Their relative wall-time contribution is unmeasured. None is established as
the cause of the existing stream losses. The Done relay and duplicated SSSP
overflow join are being handled separately and are excluded from these proposals.

Subsequent implementation and qualification are recorded in
[RESULTS.md](RESULTS.md). The final section adds a separate control against
follow-up source `200d1cf8`; the original source references below remain pinned
to the baseline named above.

## 1. Bound and measure adjacency construction memory per worker

Argentea buffers every owned vertex and arc before building adjacency.
The BFS adapter accumulates 16-byte `(source,target)` tuples and passes the
whole vector by reference into the builder
(`examples/extensions/nutmeg/src/argentea/bfs/input.rs:30-82`). The weighted
adapter does the same with 24-byte tuples (`sssp/input.rs:30-83`). The core
copies and sorts vertex IDs, builds offsets and a cursor, then allocates an
8-byte target per BFS arc or a 16-byte target/weight per SSSP arc
(`examples/extensions/argentea/src/adjacency.rs:40-78`,
`examples/extensions/argentea/src/sssp/adjacency.rs:49-105`).

On the reviewed 64-bit targets, simultaneous raw-edge and final-edge payloads
alone are therefore at least **24 bytes per owned BFS arc** and **40 bytes per
owned SSSP arc** while constructing that partition. These are live allocation
lower bounds, not RSS predictions or native admission totals. They exclude
vertices, offsets, cursor, values, input Arrow batches, shuffle buffers and
allocator slack. Undirected traversal explicitly duplicates input edges into
two arcs, including self-loops (`argentea/python/argentea_bfs_client.py:176-179`;
`argentea/src/bfs.rs:181-184`). Both builders also perform two binary searches
over local vertex IDs per arc (`adjacency.rs:52-72`, `sssp/adjacency.rs:61-92`).

This does **not** copy the entire graph into every worker or phase. The adapter
checks each source's owner; registry access clones an `Arc` to the one local
partition, and duplicate initialization is rejected
(`nutmeg/src/argentea/bfs/input.rs:48-71`, `bfs/state.rs:110-126`). A worker's
peak depends on its assigned partitions and how many initialize concurrently.

Active rounds also copy full local label arrays, even when only a small
frontier changes: BFS `argentea/src/bfs/protocol.rs:301-318` calls `Values::copy`
(`bfs.rs:138-144`); SSSP `sssp/partition/protocol.rs:185-210` copies labels and
creates a dense pending mask (`sssp/partition.rs:105-125`). Measure active-round
copy/scan work per local vertex as well as work per active edge. Any sparse
update prototype must retain the immutable producer view and atomic publication
of a completed round. This observation concerns active rounds, separately from
the pending Done relay change.

There is a separate admission effect: the worker factory reserves the entire
configured native quota once per job/operation/worker, from that worker's
ordinary DataFusion memory pool (`crates/sail-session/src/extensions/worker.rs:
352-386`). The reservation is non-spillable and stays until the final lease
owner drops (`crates/sail-common-datafusion/src/native_resource.rs:89-106,
124-155`). For example, a configured 80 GiB quota in a 96 GiB pool leaves at
most 16 GiB for other accounted operators while the lease lives, irrespective
of native RSS. Two worker pools do not constitute one shared aggregate limit.

First control and change:

- Record per-partition input-complete/build-start/build-end times, arc counts,
  concurrent builds, native admitted/used peaks, and per-worker process memory.
  Correlate with pool reserved bytes and the encompassing hard memory limit.
  The existing `SAIL_NATIVE_RESOURCE_AUDIT` emits quota admitted/released and
  pool-reserved values (`native_resource.rs:65-85,134-145`).
- Split adjacency construction from partition-state initialization so owned
  raw input can be dropped before labels/frontier allocation; BFS currently
  allocates `Values` before the borrowed-input build returns
  (`argentea/src/bfs.rs:185-229`). An owned-vertex builder can also remove one
  vertex copy. Preserve existing ownership, duplicate and endpoint checks.
- If edge-copy peak or binary-search work dominates the measured build,
  prototype a builder over source-grouped owned input. Charge and measure the
  grouping cost; do not claim that changing the builder eliminates the input
  routing or sort cost. Test the same graph with identical output certificates.
  Avoid reducing scheduler slots as a substitute for limiting init work: a
  pipelined region must be schedulable as a whole.

## 2. Measure the unrolled graph and active-round barriers separately from slots

For cap `K`, both native BFS and SSSP construct `2K+4` native relations
(`argentea/python/argentea_bfs_client.py:60-64`,
`argentea/python/argentea_sssp_client.py:19-23,56-61`). At `P` partitions this
means `P(2K+4)` native partition-task instances, before ordinary routing,
snapshot and output tasks. At `P=32,K=30`, that is 2,048 native instances.
The lazy view composition serially registers each relation and later drops
each confirmed view (`argentea/python/argentea_views.py:50-78`); it does not
perform a Python RPC for every runtime round.

Task instances are not task slots. A task set shares one slot across stages
of the same sharing group (`crates/sail-execution/src/task/scheduling.rs:23-30`).
The scheduler counts worker task sets in the whole region, rejects an
impossible maximum and waits if it cannot place that entire region
(`driver/task_assigner/core.rs:93-109,122-135`). The historical scale-24 plan
required 96 slots at `P=32` (Grust `gn-capacity-2026-09-29.md:460-469`);
`3P` is a fact about that plan, not a general formula.

Active statistics barriers have a separate scaling cost. Every producer emits
eight statistics and one completion row to every owner: **9P² rows per
statistics exchange** in BFS and SSSP (`nutmeg/src/argentea/bfs/output.rs:
198-246`, `sssp/output.rs:196-244`). Contribution producers send one completion
per recipient in addition to data (`bfs/output.rs:302-318`). Each receiver
drains EOF and validates all producers before advancing
(`bfs/input.rs:142-182,204-242`). This establishes the barrier structure; it
does not establish that the small control payload dominates a large graph.

Owner affinity is already implemented: worker-extension stages sharing the
operation receive a common slot group (`job_graph/worker_groups.rs:35-68`),
and the scheduler validates identical owner locations across occurrences
(`driver/job_scheduler/worker_topology.rs:58-101`). Same-worker shuffle reads
already use the local stream manager; only another worker uses Flight
(`task_runner/actor/handler.rs:317-326`). Range routing replaces an existing
matching exchange instead of stacking copies
(`crates/sail-session/src/extensions/worker.rs:275-304`). The producer may emit
rows for every recipient, so its output is not owner-local simply because its
retained adjacency is local.

First control and change:

- Before running, export actual stage/task/task-set counts, maximum region
  slot demand, partition-to-worker placement and transport edges. Keep `P`
  fixed for the placement and strong-scaling comparison.
- At fixed graph, topology, `P` and resource limits, compare a correctness-
  qualified cap with a larger cap. Time registration, planning, source/build,
  active phases, terminal phases and output separately. The Done relay patch
  should be present in both cells; remaining plan/setup cost is then separable
  from its fix. Do not lower the cap until the existing run's exact answer
  establishes sufficiency; retain cap exhaustion as `nonconverged`.
- Record per-phase first/last owner finish, useful data versus control rows,
  same-worker versus remote bytes, and wait-to-compute time. Only if active
  barrier cost matters, prototype hierarchical statistics reduction with
  producer identity/completeness preserved. Doubling `P` doubles the owner partition count but quadruples these
  control-row counts; available physical parallelism depends on placement and
  resources.

## 3. Preserve useful partitioning across Grenada checkpoint generations

In this harness Grenada (`nutmeg-datafusion`) wraps lazy ordinary relations
using `Nutmeg.tables` and then invokes the same `GraphAlgorithms` controller
as Pecan (`examples/extensions/benchmarks/traversal_cell.py:78-90`;
`nutmeg/python/sail_nutmeg/client.py:77-88`). It does not stage a whole graph
through Banda's native snapshot API.

Each `StagingRun.materialize` checks the staging capability with a server
request, calls `repartition(P)` without a key, writes a fresh Parquet generation,
opens it again, checks its schema, and optionally counts rows
(`graph-algorithms/src/pyspark_pecan/staging.py:19-59`). The returned Parquet
relation does not carry an explicit graph-key partitioning contract here.
Actual subsequent hash/range exchanges must be counted from the physical plan;
file count alone is not proof that a shuffle occurs or can be skipped.

The reference/frontier controller writes both the updated reached table and
the changed frontier each iteration, then counts that frontier before the
next iteration (`traversal.py:63-81`). Push-pull also computes frontier volume
before expansion, materializes/counts the next frontier and materializes the
grown reached set (`traversal_bfs.py:17,39-48`). These are serial controller
barriers and repeated storage work independent of the SSSP overflow join.
Input snapshot materialization and validation are additional shared costs
(`algorithms.py:34-51`); Argentea uses that same snapshot path too
(`argentea_bfs_client.py:197`).

First control and change:

- Attribute per-iteration write/read bytes, object-store requests, exchange
  bytes, operator time, and client gaps. Keep `record_plans` identical across
  compared cells; it adds a planning RPC per iteration (`algorithms.py:69-81`).
- Prototype a checkpoint representation that records a verified key partition
  mapping, then reuse immutable adjacency partitioning and avoid the final
  keyless repartition where the physical writer can preserve it. A keyed
  Parquet directory by itself does not make the optimizer trust distribution.
  Verify removed exchanges in plans and counters, not elapsed time alone.
- A smaller controller experiment can return frontier count in a bounded
  write receipt and remove the separate count action if the writer guarantees
  committed rows. Preserve uncertain-write ownership, cancellation and cleanup
  semantics (`staging.py:31-37,61-78`), and compare exact answer certificates.

## Minimal scaling matrix

Start with BFS reference in both Argentea and Grenada at Graph500 scale 22,
edge factor 16: `2^22` vertices and `2^26` input edge tuples. Use the same
immutable dataset manifest, graph direction, duplicate/self-loop policy,
source ID, cap and certificate settings for every same-scale cell. Fix `P=16`
for the first three rows. Register both native quotas and ordinary pool caps
as part of the execution class. Do not mix a preloaded native kernel timing
with a relational end-to-end timing.

The following is a proposed enforceable resource profile, not the existing
hosts' observed allocation. CPU entries are pinned or quota-enforced worker
capacity. Memory entries are encompassing hard worker-process limits; native
quota is included inside its DataFusion pool, not added to it. The native
quota column applies to Argentea; Grenada has no worker-native graph state in
this path. Both retain the same ordinary pool and encompassing worker limits.

| Cell | Compute hosts / workers | Graph | Per-worker CPU / hard RAM / pool / native quota | Total workers CPU / hard RAM | P | Contrast |
|---|---|---|---|---|---|---|
| A | 1 host / 2 workers | scale 22 | 4 / 16 GiB / 12 GiB / 8 GiB | 8 / 32 GiB | 16 | Baseline |
| B | 2 hosts / 1 worker each | same scale 22 bytes | same as A | 8 / 32 GiB | 16 | Placement with total resources fixed |
| C | 2 hosts / 1 worker each | same scale 22 bytes | 8 / 32 GiB / 24 GiB / 16 GiB | 16 / 64 GiB | 16 | Strong scaling against A; B separates placement |
| D | 2 hosts / 1 worker each | scale 23, same generator policy | same as C | 16 / 64 GiB | 32 | Weak scaling against A; graph and total resources double |

Keep driver/client on host A with a separate fixed budget (proposed 2 CPUs,
4 GiB RAM), and store on host A with a separately disclosed fixed budget
(provisionally 2 CPUs, 4 GiB RAM). The separate MinIO process must have its
CPU and memory limits enforced and its workload peaks measured independently;
this store budget has not yet been qualified. A changed store budget is a new
profile, not an undisclosed adjustment. With those budgets enforced, whole-service totals
are 12 CPUs/40 GiB for A/B and 20 CPUs/72 GiB for C/D, plus explicitly listed
OS reserve. Worker strong scaling doubles worker resources, not all service
resources. Keep storage endpoint, disk, caches policy and network path fixed;
moving a worker changes its storage access path as well as shuffle locality.
Record each host's limits and peaks separately and their simultaneous sum.
Do not call an unenforced macOS target a hard limit.

Scale 23 has `2^23` vertices and `2^27` input edge tuples. Use one declared
source-selection policy and seed policy for weak scaling and disclose resulting
source IDs, reached counts, levels and work. Its `P` change also changes barrier
cost, so D measures the weak-scaling configuration, not an isolated CPU effect.
The same cap must be sufficient and certified at both scales; otherwise D is
`nonconverged`, with no successful weak-scaling ratio.

This is **eight initial cells**: A-D for two engines. A is reused for both
scaling questions. Run one per cell for functional qualification; those are
single observations. After all pass, repeat the contrast of interest in
alternating order at least twice more before estimating its spread. Preserve
every original result. A timeout, memory refusal or cap failure does not trigger
an undisclosed cap, memory or timeout increase. Any changed profile is a new cell.

On the existing Capitola/Rosetta plus native Morrobay pair, this matrix is
heterogeneous functional qualification. Core counts do not normalize the two
processors or translation overhead. Do not report it as homogeneous strong
scaling. Publish absolute performance only on dedicated comparable hosts;
shared-host numbers remain explicitly qualified ratios with load and steal
where measurable. Verify the actual LAN route before execution, consistent
with the recorded operator instruction (`gn-capacity-2026-09-29.md:451-458`).

SSSP follows only after the cap/result protocol is qualified: reuse A and C
with fixed weighted fixture bytes, delta, source and cap. It does not initially
multiply all four rows. If an integer-weight fixture is chosen with path sums
below `2^53`, require exact distances; for general floating weights state the
tolerance and certificate policy explicitly. This note makes no proposal to
rerun the broader graph/algorithm matrix now.

## Evidence and acceptance

Each receipt should carry detached source revisions, binary/wheel hashes,
Cargo/Python lock hashes, actual launched environment and flags, network/store
locations, dataset manifest hashes, actual worker placement, and start/end
timestamps generated by the recording process. Record elapsed monotonic time
on that same host, clock/suspend events and CPU time. Existing discrepant
clocks remain timing uncertainty; do not replace a receipt value by inferred
wall time without reconciling suspend/clock behavior.

Retain three distinct boundaries: algorithm-ready, exported result, independent
verification. Include snapshots, registration and cleanup consistently in the
chosen end-to-end boundary. BFS acceptance requires complete vertex coverage,
source and unreachable semantics, exact distances, edge inequalities, and
rooted tight-edge witnesses/parent checks. Run a small independent oracle
comparison before scale-up. Neither reached-count equality nor output-written
alone is a pass. WCC is outside this first matrix; its partial certificate must
not become an exact component proof by reusing the word `passed`.

Keep execution outcomes and verification outcomes separate. Preserve pass,
mismatch, unsupported, unavailable, timeout, error and nonconverged, and retain
resource-admission failures with their original typed cause. Verification RPC
failure means unverified output; it is not an algorithm mismatch. No successful
timing ratio includes a failed or unverified cell. Native quota admission,
native used bytes, worker RSS/PSS and encompassing memory events/peaks each
answer different questions and must not be substituted for one another.

Capture the first causal task/transport error on every process with job,
stage, partition, worker and peer identity. The local locked-version transport
controls in [`transport-control`](transport-control/) show that the identical
outer `h2 protocol error: error reading a body from connection` can arise from
induced keepalive expiry or a remote `RST_STREAM(INTERNAL_ERROR)`. Their
[`diagnostic-conclusions.json`](transport-control/diagnostic-conclusions.json)
contains the low-volume control-frame filter and the hyper tracing feature
constraint. These controls establish diagnostic visibility, not the cause of
any existing Sail failure.


## Implementation follow-up

Recorded UTC: 2026-09-30T17:33:41.632350+00:00

The source costs above describe the pinned initial review. The subsequent
[experiment report](RESULTS.md) identifies the tested commits and their limits.
The CSR cursor/dense-ID work and terminal SSSP relay are implemented; active-round
label copies, raw-input/CSR overlap, plan size and the partition control barrier
remain separate concerns.

The compact struct MIN implementation also removes a cost that can grow faster
than input size inside a partition. The original implementation allocates and
scans a scratch entry for every resident group on every input batch: additional
work is proportional to the sum of resident-group counts across batches. With
fixed batch size and growing distinct groups, that term can be quadratic. The
compact path visits incoming rows and initializes newly created groups, giving
amortized linear update work in rows plus groups between emissions. This is a
source-level bound for that accumulator, not a complexity or speedup claim for
the entire query, shuffle or cluster. [Derivation and counts](STRUCT-MIN-ALLOCATION.md).

The checkpoint controller's fused overflow change remains under evaluation:
the first small paired fixture did not improve elapsed time. Removing a repeated
action from the plan is not sufficient evidence of a net speedup. Its larger
isolated control is prepared separately, preserving the original runtime so the
compact accumulator does not confound that comparison.


## Follow-up: partition ceiling and high-degree ownership

Recorded UTC: 2026-09-30T20:17:41.470343+00:00. This section reviews source `200d1cf8` and the
[bounded control](cluster-ownership-control/receipt.json), not a new cluster run.
All five actual Python option validators accept 64 partitions and reject 65.
The native BFS, SSSP, WCC and delta-PageRank request validators also cap partitions
at 64 by source inspection; the fixed-round PageRank adapter and core operation
allow more. This is an Argentea API/admission boundary, not a general Sail
cluster limit. Raising only the Python constant would leave other checks and
the quadratic control protocol unchanged.

`Operation::owner` uses the Euclidean remainder of the signed vertex ID modulo
P; the clients route arcs by their source's owner. The BFS emission cursor visits
an owned source's adjacency in one cursor. Balanced vertex counts therefore do not establish balanced edge
storage or active work. The exact ownership model uses 65,536 vertices, center
0 and 65,535 undirected star edges. At P=64 every owner has 1,024 vertices, but
owner 0 holds 66,558 of 131,070 directed arcs (50.78%). Its first frontier emits
all 65,535 active arcs from that one owner. The sum/max active-work ratio is 1
at every tested P, from 1 through 64. These are arithmetic counts following the
pinned source rule, not native execution times or a Graph500 skew measurement.

This supplies a counterexample to unconditional near-linear scaling under
whole-vertex ownership. More workers or a different hash cannot split one
high-degree vertex's outgoing work. Record maximum and per-owner arc counts,
active-edge counts, memory and finish times before scaling. Include a skewed
fixture as well as the proposed Graph500 cells. If a heavy owner is the barrier,
prototype splitting its edge ranges across owners with explicit replicated
vertex state and exact reduction/completion rules; charge the extra state and
communication. That requires a protocol change and new correctness controls,
not just a higher partition cap. Local parallelism within an owner is a separate
option whose benefit remains limited to that owner's host resources.
