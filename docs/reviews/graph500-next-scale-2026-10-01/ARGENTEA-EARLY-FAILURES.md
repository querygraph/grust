# Why Argentea can fail before the traversal gets far

Recorded UTC: 2026-10-01T05:04:25.620226+00:00

Argentea's first phase is already a large distributed operation: it builds
resident graph partitions and checks the destinations of every directed arc.
“Early” in the algorithm therefore need not mean little data or little work.
The records also contain different kinds of failure, which need different fixes.

## Four observed cases

| Case | Observed outcome | What it establishes |
|---|---|---|
| One-host BFS, scale 24 | Passed its certificate: six levels, 8,862,601 reached; 70.5 GiB container peak in the first recorded Linux run. | Argentea does complete this graph on that configuration. The repeat also passed. |
| One-host SSSP DeltaStar, scale 24 | Exhausted the 30-round harness cap at bucket 3.0, with 2,007,762 vertices still active; recorded peak PSS 67.8 GiB. | Nonconvergence under that cap, not an OOM or a certified completed answer. No higher-cap result was recorded. |
| One-host BFS reference, scale 25 | The first attempt lost a stream without recorded OOM. A separately configured retry initialized all 32 partitions, then reached the 100 GiB container limit and lost a worker to OOM, with 17 first-phase decisions complete. | The retry exceeded its encompassing memory limit. It does not establish the cause of the first attempt or an intrinsic one-host graph-size ceiling. |
| Two-host BFS, scale 24 | Cancelled while reading input after 22 of 32 partitions initialized; hundreds of tasks then failed together. | The initiating task error was not captured. The subsequent reset storm is not its diagnosis. |

The [capacity record](../gn-capacity-2026-09-29.md) retains the original cells:
scale-24 BFS in section “Gate 3, Argentea-first matrix,” the SSSP and scale-25
attempts in the decision matrix, and the two-host result in the LAN comparison.
Those measurements are from a shared host. Their consumed time and PSS are not
completed-run performance ratios for failed or nonconverged cells. The old
idle-worker removal incident is another separately explained failure, not a
common explanation for this table.

## What occupies memory before useful frontier work

This source inspection is pinned to `querygraph/sail`
`ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73`. It is not a fresh execution or a
claim that every historical cell used identical runtime settings.

The adapter gathers each owner's raw vertex and edge vectors, then builds its
CSR adjacency. Undirected input becomes two directed arcs, including self-loops.
The first BFS topology exchange sends one row per arc to its destination owner.
Each row has eleven Int64 fields: 88 bytes of numeric payload before overhead.

| Derived representation, summed over owner partitions | Scale 24 | Scale 25 |
|---|---:|---:|
| Vertices | 16,777,216 | 33,554,432 |
| Undirected input tuples | 268,435,456 | 536,870,912 |
| Directed arcs after expansion | 536,870,912 | 1,073,741,824 |
| BFS retained target payload, 8 bytes/arc | 4 GiB | 8 GiB |
| BFS raw tuples plus CSR target payload during construction, 24 bytes/arc | 12 GiB | 24 GiB |
| Weighted raw tuples plus CSR arc payload during construction, 40 bytes/arc | 20 GiB | 40 GiB |
| BFS topology exchange's total numeric payload, 88 bytes/arc | 44 GiB | 88 GiB |

These are arithmetic representation sizes and data volumes, **not simultaneous
RSS, measured peaks, or a sum to add together**. The construction figures assume
the listed raw and final payloads overlap; actual concurrent builds determine
the whole-worker peak. They omit Arrow/shuffle copies, identifiers, offsets,
dense state, capacity slack and charged file cache. The exchange may stream;
its total volume is not evidence that all its rows reside in memory together.

Source: [input vectors](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/nutmeg/src/argentea/bfs/input.rs#L30),
[CSR construction](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/argentea/src/adjacency.rs#L30),
[weighted CSR](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/argentea/src/sssp/adjacency.rs#L49),
[undirected expansion](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/argentea/python/argentea_bfs_client.py#L176),
[wire fields](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/nutmeg/src/argentea/bfs/wire.rs#L44).

Thirty-two partitions do not mean thirty-two copies of the graph. Each owner
holds a subset; the registry rejects duplicate initialization, and emission
cursors share adjacency through `Arc`. Nor do 64 unrolled phases mean 64 CSR
copies. A cap K constructs 2K+4 native relations, producing scheduling and stream
lifetime costs. Dense old/new state can overlap during publication, but the
source does not establish that every phase's dense state remains live together.
See [registry ownership](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/nutmeg/src/argentea/bfs/state.rs#L110),
[cursor ownership](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/argentea/src/bfs/emission.rs#L114)
and [phase construction](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/argentea/python/argentea_bfs_client.py#L60).

## What the source does and does not explain

The old raw Rust vectors drop when initialization returns. All 32 partitions
had initialized before the scale-25 retry's later growth, so raw-vector/CSR
overlap alone cannot explain that OOM. Retained upstream Arrow data or queued
protocol output would be separate storage with different lifetimes. BFS
reference validates topology without retaining the inverse-edge buffer; only
direction-optimizing BFS builds the incoming CSR. Blaming a second CSR for the
reference failure would be incorrect.
[Topology receiver](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/argentea/src/bfs/protocol.rs#L125).

The host's local stream sender has an explicitly unbounded overflow queue:
when a receiver is slow, batches can accumulate beyond the bounded channel.
That is a concrete buffering risk, **not measured attribution of this OOM**.
Replica batches share Arrow buffers, so replica count is not automatically a
multiplier for physical payload bytes. Native output batches also retain their
own memory admission and lease; calling all queued native data unaccounted
would be wrong. Queue retention, native charges, ordinary pool charges and
container memory need separate measurements.
[Overflow implementation](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/crates/sail-execution/src/stream/local/memory.rs#L62),
[native batch ownership](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/examples/extensions/nutmeg/src/argentea/batches.rs#L27).

Likewise, an 80 GiB native quota reserved from each worker's 96 GiB Sail pool
is an admission rule, not 80 GiB of allocated RSS. Two independent worker pools
do not enforce one shared 100 GiB container limit. That enclosing limit includes
both workers, the driver and charged cache.
[Worker reservation](https://github.com/querygraph/sail/blob/ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73/crates/sail-session/src/extensions/worker.rs#L352).

## Why Pecan's 33 GiB result is encouraging, but different

The successful scale-24 Pecan SSSP DeltaStar replay used compact runtime
`56194b170155301ba91077f0ba3df31fe2c78b6b`, controller `3a9028057`, and the older
native wheel from `ffcfbd569`. It completed 60 iterations and its certificate
and physical-output checks, with 33.05 GiB whole-container peak. The compact
accumulator removes a demonstrated expensive grouped struct-MIN representation.
The Argentea reference BFS observations use a different algorithm and execution
path. They are **not a matched comparison**, and the peak difference is not a
measured decomposition of Argentea's overhead.
[Replay identity and boundary](../sail-stream-experiments-2026-09-30/COMPACT-REPLAY-AND-SSSP.md).

Scale 25 doubles vertices and edge tuples. Doubling 33.05 gives 66.1 GiB as a
planning estimate, not a capacity prediction: frontier shape, skew, buffering
and concurrent operators can change. Grenada already has a certified scale-25
BFS push-pull result after the client decode-limit correction. Its weighted
relational path uses the same GraphAlgorithms controller through Nutmeg.tables,
so compact aggregation is relevant, but compact scale-25 SSSP still needs its
own measured result. Neither the Pecan success nor old Grenada BFS pass supplies it.

## What has improved, and the next discriminating observation

Delivered fork fixes reduce CSR scratch and dense-ID lookup work, drop raw
inputs before initializing dense state, avoid unused mode-specific inboxes and
Done relays, and reuse the SSSP candidate buffer. The later input/lease fixes
include `7f5b80d0` and `33adfce1d`; SSSP reuse is `fc094a0c`. Their local gates
and allocation controls are recorded in [RESULTS](../sail-stream-experiments-2026-09-30/RESULTS.md).
These later native fixes were not loaded by the old large-graph cells. They do
not remove raw/CSR construction overlap, full topology exchange, active full
scans, whole-vertex owner skew, or partition-count completion traffic.

The next cheap diagnostic is bounded counters, not another assumed cause:
record queued batches and retained Arrow bytes by job/stage/partition and
recipient, plus produced/consumed rows, phase completion counts, active input
builders and native admitted bytes. Distinguish shared buffer identities from
summed batch logical sizes. Correlate these with process/cgroup samples and the
first typed failure. A small delayed-consumer control can first verify those
counters and expose whether queue growth follows lagging consumers. No such
experiment was run for this note; the historical input cancellation remains
unexplained.
