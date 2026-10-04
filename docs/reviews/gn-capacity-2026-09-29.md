# Graph Nuts capacity campaign, 2026-09-29 (in progress)

Where the four Graph Nuts paths stop on Graph500 scale 24, 25 and 26 and on
cit-Patents, on morrobay's gate VM (32 CPUs, 110 GiB, containers of 32 CPUs
and 100 GiB; Sail memory pool 96 GiB per process, native quota 80 GiB, cell
timeout 5400 s). A shared, virtualized host: every timing here is an
observation, not a publishable number. Every refusal, error and timeout is a
result and is kept with its receipt. The map is
[`GRAPH-NUTS.md`](../GRAPH-NUTS.md); the scaling plan is
[`FABLE-ON-ASTRA.md`](../FABLE-ON-ASTRA.md).

Evidence root on morrobay: `~/src/sail-extensions-gates/graph-nuts-b87fb27ac/`
(baseline) and `~/src/sail-extensions-gates/graph-nuts-gate-next/` (the new
gate, the chain logs, `capacity_findings.py`, `pick_sources.py`). Volume paths
are under `/targets/`.

Correction recorded UTC: 2026-09-30T18:11:37.461276+00:00. This review preserves recorded
measurements and failed outcomes while correcting causal and comparison claims.
Shared-host observations do not establish dedicated-host performance or a
completed-run ratio for a failed cell. Later stream/allocation evidence is in
[the focused results](sail-stream-experiments-2026-09-30/RESULTS.md).

## 1. Inputs

| Input | Vertices | Edges | Files | Source vertex | Why that source |
|---|---|---|---|---|---|
| Graph500 scale 24 (seeds 42/54, edge factor 16) | 16,777,216 | 268,435,456 | 1024 | 13507776 | highest sampled degree (46,207 in 1/16 of the edges); vertex 0 is isolated |
| Graph500 scale 25 | 33,554,432 | 536,870,912 | 2048 | 13507776 | same vertex is the top of the scale-25 sample too (34,993) |
| Graph500 scale 26 | 67,108,864 | 1,073,741,824 | 4096 | `max-degree` (fixture-chosen) | the new fixture policy records the source's degree |
| cit-Patents (SNAP, pinned `d2a11214…`) | 3,774,768 | 16,518,948 | 64 | 3569341 (dense id) | highest out-degree, 770 citations; directed |

The first capacity matrix used `source: 0`, copied from the harness example.
Vertex 0 is isolated in these Kronecker graphs: the one passed cell reported
`reached = 1` after one empty round, so it measured graph loading, not
traversal. That matrix was stopped after five cells (kept under
`capacity/`, with `STOPPED-2026-09-29.md`), the inputs were re-prepared with
the sources above (the fixtures pin `traversal.source` in the manifest and
the cell asserts it), and the harness now has `--source max-degree` and
records the source's degree and the reached count in every manifest and
summary (`work/s0-source-degree`).

## 2. What the baseline (`b87fb27ac`) could not do at scale 25

Both found by the first two source-0 cells, before any traversal ran.

- **Banda refuses to stage.** The canonical staging sort admits its working
  space from the memory budget before sorting: 8.6 GB of permutation, about
  396 GB of sort keys, 141 GB for the sorted copy, 404 GB in all against the
  80 GiB quota; refused in 92 s at scale 25 and 65 s at scale 24. The
  sort-key bound (`admission.rs`: 16 times the key buffers plus 128 bytes per
  row per key column) is about 25 times the Arrow row-format size for these
  short Utf8 ids. The library already offers `order = asStaged`, but the Sail
  extension hard-coded canonical and its request schema rejected the option.
  Fix on `work/s2-stage-order`; the next matrix runs Banda `asStaged`.
- **Relational results cannot be certified at scale 25.** `decoded message
  length too large: found 8234561 bytes, the limit is: 4194304 bytes`: Sail's
  internal gRPC clients keep Tonic's 4 MiB decode default while its servers
  accept 128 MiB. The hub-source cells later showed where it bites: the
  traversal itself completes and writes its result, and the error is raised
  in the distributed certificate (`traversal_certificate.certify`), at its
  very first query, `vertices.count()` over the 33.5M-vertex frame, always
  with a message of about 8.23 MB. The same count succeeded in the one cell
  that passed, so the message is not the count's own data; what the session
  carries by then differs (Pecan's retained checkpoints, Grenada's native
  tables). Scale 24 certifies fine. The result files of the three uncertified
  cells are retained, so they can be certified separately on the new gate.
  Fix on `work/grpc-client-decode-limit` (one hunk, upstream candidate,
  verification pending on the next matrix).

## 3. Baseline matrices with the hub source (running)

`gn-capacity-b87fb27a-hub` (36 cells: BFS reference/frontier/push_pull and
SSSP reference/frontier/delta_star, Pecan, Banda and Grenada, scale 24 and
25) and `gn-ranking-b87fb27a-hub` (30 cells on cit-Patents: PageRank and WCC
reference/optimized under the certificate policy, plus the traversal cells).
Results are filled in from `capacity_findings.py` as cells finish; this table
is the state at 15:35 UTC: the matrix stopped itself after cell 29 (`orchestration/cleanup failed; stopped before launching another cell`, the harness's refusal to launch a cell after a container cleanup step failed, on the swapped host), so 7 cells never ran: Pecan and Grenada SSSP frontier and delta_star at scale 25, Pecan delta_star at scale 24, Banda reference and delta_star at scale 25. They are queued as a `--resume` run before the scale-26 chain.

| Cell | Outcome | Time | Peak PSS | What happened |
|---|---|---|---|---|
| scale 25, Banda BFS push_pull (canonical) | refused | 112 s | 25.6 GiB | the staging sort's admitted working space, as in section 2 |
| scale 25, Grenada BFS push_pull | traversal done, certificate failed | 1516 s | 38.6 GiB | six BFS iterations from the hub to an empty frontier and the result written; the certificate then hit `decoded message length too large: found 8233665 bytes`, so the traversal time stands but the result is unverified |
| scale 24, Pecan BFS frontier | error | 465 s | 55.4 GiB | iteration 1 reached 407,203 active vertices; during iteration 2 the driver lost a worker connection (`h2 protocol error: error reading a body from connection`, worker 2 `ConnectionReset`); no OOM kill (cgroup peak 60 GiB of 100, workers at 27.4 and 23.7 GiB RSS); cause not identified from the driver log, which carries no worker output |
| scale 24, Grenada BFS push_pull | passed | 775 s | | six iterations from the hub, 8,862,601 of 16,777,216 vertices reached (the giant component), certificate validated |
| scale 24, Banda BFS frontier (canonical) | refused | 58 s | 13.8 GiB | staging sort admission, as at scale 25 |
| scale 25, Pecan BFS push_pull | traversal done, certificate failed | 1610 s | 39.6 GiB | six iterations to an empty frontier and the result written; the certificate hit the 4 MiB limit (8,234,369 bytes); unverified |
| scale 25, Banda BFS frontier (canonical) | refused | 125 s | | staging sort admission |
| scale 24, Banda BFS push_pull (canonical) | refused | 56 s | | staging sort admission |
| scale 25, Grenada BFS reference | error | 2730 s | 100 GiB | iteration 1 reached 640,062, iteration 2 reached 14,625,247 (932 s); iteration 3, relaxing all 15M reached vertices, drove the container to its 100 GiB limit (1610 `max` events, no OOM kill) with the workers at 42.8 and 43.3 GiB, and the driver lost the stream (`h2 protocol error`) |
| scale 24, Banda BFS reference (canonical) | refused | 60 s | | staging sort admission |
| scale 24, Grenada BFS reference | error | 480 s | 50.8 GiB | iteration 1 reached 407,203; iteration 2 failed with `h2 protocol error: error reading a body from connection` at a 51 GiB container peak with no `memory.max` events at all, so this one is not memory |
| scale 24, Pecan BFS push_pull | passed | 844 s | | six iterations, 8,862,601 reached, the same result as Grenada's push-pull (775 s); certificate validated |
| scale 24, Grenada BFS frontier | error | 786 s | 99.9 GiB | iteration 1 reached 407,203; iteration 2 ended with the `h2 protocol error` at the container limit (workers at 43.3 and 48.1 GiB, no `memory.max` event counted, no OOM kill) |
| scale 25, Pecan BFS frontier | **passed** | 2729 s | 75.1 GiB PSS, container peak 99.7 GiB | the baseline's first scale-25 pass: frontiers 640,062 / 14,625,247 / 1,777,122 / 6,267 / 28 / 0 over six iterations (iteration 2 alone took 949 s), 17,048,727 of 33,554,432 reached, certificate validated with 5 witness rounds; the workers peaked at 34.5 and 39.7 GiB, so it passed within about 300 MiB of the container limit |
| scale 25, Grenada BFS frontier | traversal done, certificate failed | 2764 s | 75.2 GiB | six iterations to an empty frontier and the result written, 35 s slower than Pecan's frontier; the certificate hit the 4 MiB limit (8,236,609 bytes); unverified |
| scale 25, Pecan BFS reference | error | 3144 s | 100 GiB | got through three iterations (frontiers 640,062 / 14,625,247 / 1,777,122, iteration 3 took 1197 s), then iteration 4, relaxing all 17M reached vertices, drove the container to its limit (3767 `max` events, no OOM kill; workers at 45.4 and 38.9 GiB) and the driver lost the stream |
| scale 24, Pecan BFS reference | error | 793 s | 99.9 GiB | iteration 1 reached 407,203; during iteration 2 the container hit its 100 GiB limit and the kernel OOM-killed a worker (`memory.events oom_kill 1`); the two workers were at 47.2 and 46.3 GiB RSS |

SSSP suite (weights are the generator's float32 values in [0, 1]; delta 0.1
for delta-star; source 13507776):

| Cell | Outcome | Time | Peak | What happened |
|---|---|---|---|---|
| scale 24, Banda SSSP reference, frontier and delta_star (canonical) | refused | 57 to 61 s | | staging sort admission |
| scale 24, Grenada SSSP delta_star | error | 1086 s | 47.8 GiB | one bucket done (84 s); the second bucket's job ran 8 minutes and ended with the `h2 protocol error` at 48 GiB with no `memory.max` events (workers at 15.0 and 21.3 GiB): not memory, a long stage |
| scale 24, Pecan SSSP frontier | error | 811 s | 48.4 GiB | iteration 1 relaxed to 407,203; iteration 2 ran 5 minutes and ended with the `h2 protocol error` at 48 GiB with no `memory.max` events (workers at 18.6 and 18.2 GiB) |
| scale 24, Grenada SSSP reference | error | 682 s | 50.3 GiB | iteration 1 relaxed to 407,203; iteration 2 ran 4 minutes and ended with the `h2 protocol error` at 50 GiB, no `memory.max` events (workers at 19.2 and 19.4 GiB) |
| scale 24, Grenada SSSP frontier | error | 730 s | 53.2 GiB | iteration 1 relaxed to 407,203; iteration 2 ran 5 minutes and ended with the `h2 protocol error` at 53 GiB, no `memory.max` events (workers at 21.9 and 19.5 GiB) |
| scale 24, Pecan SSSP reference | error | 1699 s | 27.4 GiB | loading alone took 1103 s (three to four times the other scale-24 cells), iteration 1 relaxed to 407,203, and iteration 2 ended with the `h2 protocol error` at only 27 GiB (workers at 5.5 and 12.2 GiB): the lowest-memory stream loss yet |
| scale 25, Banda SSSP frontier (canonical) | refused | 173 s | | staging sort admission |
| scale 25, Grenada SSSP reference | error | 2010 s | 90 GiB | iteration 1 relaxed to 640,062; iteration 2 ended with the `h2 protocol error` at a 90 GiB container peak with no `memory.max` events (workers at 32 GiB each) |
| scale 25, Pecan SSSP reference | error | 2663 s | 90 GiB | iteration 2 reached 15,202,839 (1437 s); iteration 3 ended with the `h2 protocol error` at 90 GiB, again with no `memory.max` events (workers at 33.6 and 31.6 GiB) |

Confounder: the default Colima VM (12 CPUs, 48 GiB) came back up at about
05:02 UTC beside the 110 GiB gate VM on the 128 GB host and was stopped at
06:25 UTC; it came back again at about 07:00 UTC and at 15:31 UTC was
running someone's `eigen-runner` container, with the host 46.8 GB into its
48 GB swap. Every cell from the seventh onward ran with the host memory
oversubscribed by about 30 GiB. That inflates load times (the Pecan SSSP
reference cell took 1103 s to load what other cells loaded in 300 to 500 s)
and is itself a way for a peer to stall past a 10 s keepalive window, so the
stream losses cannot be separated from it on this run; the reruns on the new
gate need a host without the second VM, or the note that it was there. At
16:14 UTC the default VM was stopped a third time. What restarts it is the
host's own Eigen Times nightly (`~/Library/LaunchAgents/com.eigen.nightly.plist`
running `~/bin/eigen-nightly.sh` hourly): it starts the default VM whenever
it is down and runs the `eigen-runner` container at 01:00, 03:00, 13:00 and
15:00 UTC for up to an hour each. The user chose to leave it in place, so
the overlaps are marked rather than avoided: in this campaign so far, the
baseline capacity cells from the seventh onward and the first ranking cells
ran with the second VM up; from here on, a cell whose interval crosses one
of those four hours ran alongside the nightly, and the record says so per
matrix. The rest of the host (Activity Monitor, three login sessions) is
the user's.

### The `h2 protocol error` failures

Eleven relational cells so far ended with `h2 protocol error: error reading a
body from connection` in the driver, four of them in BFS: Pecan frontier at scale 24 (60 GiB peak,
iteration 2), Grenada reference at scale 24 (51 GiB, no `memory.max` events,
iteration 2), Grenada frontier at scale 24 (99.9 GiB, iteration 2) and
Grenada reference at scale 25 (100 GiB, iteration 3). At least the Grenada
reference at scale 24 is not memory; the others sit near the limit, so both
causes may be in play. The two scale-25 SSSP reference cells add a pattern:
both lost the stream in their heaviest iteration (15M active vertices) at a
90 GiB container reading with no `memory.max` events and the workers at
32 GiB each, which points at the long-running stream rather than at memory
(an h2 connection dropped mid-body, whether by an idle timeout or a peer
error the worker never logged). A concrete candidate from the source: every
Sail gRPC server (`sail-common/src/server/builder.rs`) runs h2 keepalive
pings every minute with a 10 s timeout. A peer whose tokio runtime is
starved by a heavy stage (these cells run 32 tokio and 32 rayon threads on
32 vCPUs at full load) can miss a ping's 10 s window, the server then
closes the connection, and the reader sees exactly this error. To be tested
on the new gate by lengthening the timeout. The worker processes leave no log lines in the
driver's log (they never initialize logging), so the worker side is
invisible; the working hypothesis is that a worker's own shuffle read hit the
same 4 MiB client decode limit (a worker is a Flight client of its peer), its
task stream ended abruptly, and the driver reported the broken body instead
of the limit message. The next matrix reruns exactly these cells (scale-24
relational reference and frontier, BFS and SSSP, both engines) with the
client limit raised; if they pass, that is the cause.

Addendum (2026-09-30, 04:15 UTC): a second, separate mechanism produces the
same error text. Sail's driver removes a worker whose task slots have all
been vacant for `cluster.worker_max_idle_time_secs` (default 60) together
with the shuffle output it holds, and the harness runs extension jobs with
`SAIL_CLUSTER__TASK_MAX_ATTEMPTS=1`, so the next stage that reads from the
removed worker fails with the body error instead of recomputing. The gate-3
Argentea scale-24 frontier cell shows this exactly (worker 1 stopped at
3.8 minutes, worker 3 started ten minutes later, failure at 41 minutes).
The baseline's eleven relational cells show no mid-run worker replacement,
so they stay with the keepalive hypothesis, which the gate-3 relational
rerun tests; all gate-3 matrices from 04:16 UTC also run with the idle
removal disabled for the cell (86400 s), so a cell can no longer lose a
worker to a quiet minute.

### Pecan's second iteration at scale 24

Both Pecan BFS cells so far (frontier and reference) failed in iteration 2,
the expansion of the hub's 407,203 first-level neighbors, with the two worker
processes at 47 GiB each (reference, OOM-killed) or 27 and 24 GiB (frontier,
connection lost at 60 GiB). Grenada's push-pull BFS on the same materialized
adjacency passed at a 25 GiB container peak. The relational expansion is
`adjacency.join(active, adjacency.src == active.id)` over the materialized
undirected adjacency (536,870,912 rows at scale 24, both directions). A local
explain on Capitola (`scratchpad/join-side/explain.py`, single-process mode,
1.6M-edge adjacency, 1-row frontier) shows DataFusion choosing the frontier as
the hash-join build side in either join order (`HashJoinExec: mode=CollectLeft`
with the frontier as the left input), so at small scale the planner does not
build on the adjacency. What the workers hold at scale 24 in process-cluster
mode, where the join is partitioned and both inputs are shuffled, is not
established by these receipts: the harness records no plan. Next step for S5:
the gate now records the cluster-mode physical plan of the expansion join
per iteration (`work/s5-iteration-plans`); compare push-pull's pull-side
joins with the reference join at the same frontier from the scale-25 receipts.

### Ranking matrix on cit-Patents (complete: 29 passed, 1 certificate mismatch)

`gn-ranking-b87fb27a-hub`, 30 cells on the baseline host and wheel with the
S0 harness: PageRank and WCC, reference and optimized, on Pecan, Banda and
Grenada under the certificate policy (no reference vector; an independent
fixed-point residual for PageRank), plus BFS and SSSP from source 3569341.
cit-Patents has 3,774,768 vertices and 16,518,948 directed edges.

| Cell | Outcome | Time | Peak PSS | Note |
|---|---|---|---|---|
| Banda PageRank optimized (`pagerankDelta`) | passed | 92 s | 3.9 GiB | staging 25 s; fixed-point residual 2.6e-9. This is the call Sem reported as a crash on his budget: on an 80 GiB quota the canonical staging is admitted and the delta kernel runs in about a minute |
| Banda PageRank reference (power iteration) | passed | 32 s | | faster than Banda's own delta kernel on this graph |
| Pecan PageRank reference (power iteration) | passed | 729 s | | 20 iterations |
| Grenada PageRank reference (power iteration) | passed | 480 s | | 20 iterations |
| Pecan PageRank optimized (delta) | passed | 502 s | | 20 iterations |
| Grenada PageRank optimized (delta) | passed | 489 s | | 20 iterations |
| Banda WCC optimized (randomized) | passed | 39 s | | |
| Pecan WCC optimized (randomized) | passed | 312 s | | 19 rounds |
| Grenada WCC optimized (randomized) | passed | 397 s | | 19 rounds |
| Banda WCC reference (min-label) | mismatch | 30 s | | the partition is edge-consistent (0 crossing edges), but 1731 of its labels are not the numeric minimum of their component: Banda's min-label kernel takes the minimum in canonical Utf8 order (`"10"` before `"9"`), which the harness documents for the reference-vector path and normalizes there, while the S0 certificate I wrote asserts numeric minimality. A certificate convention, not a wrong partition; the certificate is being corrected to require that a label names a member of its component |
| Pecan WCC reference (min-label) | passed | 500 s | | 20 rounds |
| Grenada WCC reference (min-label) | passed | 566 s | | 20 rounds |

Peak PSS was 2.8 to 4.0 GiB for every ranking cell, on every path. Four
ranking cells overlapped the 15:00 UTC nightly hour (Grenada WCC both
variants, Banda delta PageRank, Pecan power PageRank).

Traversal cells (directed, from patent 3569341; every cell reached the same
126,298 patents and passed the certificate; peak PSS 2.4 to 4.0 GiB):

| Kernel | Banda | Pecan | Grenada |
|---|---|---|---|
| BFS reference | 31 s | 164 s, 14 levels | 160 s, 14 levels |
| BFS frontier | 30 s | 125 s | 133 s |
| BFS push-pull / direction | 33 s | 114 s | 113 s |
| SSSP reference (Bellman-Ford) | 30 s | 184 s, 14 rounds | 183 s |
| SSSP frontier (Dijkstra) | 30 s | 128 s | 128 s |
| SSSP delta-star | 31 s | 209 s, 14 buckets | 204 s |

On a graph this size the relational reference and frontier variants
complete without incident, so the stream losses of the Graph500 cells are
tied to long, saturated stages, not to those variants as such. Banda's
30 s is almost entirely staging and projection: its kernels run in well
under a second at 16.5M edges. Pecan and Grenada are within a few percent
of each other on every traversal, as expected since they run the same
controller on the same materialized adjacency.

## 4. The new gate (`work/gate-core-tests`, `2557feaf1`)

### First rerun cell: Pecan BFS reference, scale 25

| Outcome | Time | Peak | What happened |
|---|---|---|---|
| timeout | 5400 s | 100 GiB (workers 43.7 and 47.0 GiB; 4,882 `memory.max` events, no OOM kill) | frontiers 640,062 / 14,625,247 / 1,777,122 / 6,267 in 712 / 1729 / 3216 / 4568 s, then iteration 5 (the empty-frontier check) ran into the cell timeout. No stream loss: on the baseline this cell died with the `h2 protocol error` at 3144 s in iteration 4. One cell, but the first one that ran past the point where the baseline lost its stream, with the 120 s keepalive window and nothing else changed on that path |

### Decode limit verified: Grenada BFS push-pull, scale 25

| Outcome | Time | What happened |
|---|---|---|
| **passed** | 1593 s | six iterations, 17,048,727 reached, and the certificate completed. On the baseline the same cell finished its traversal in 1516 s and then failed the certificate's first query with `decoded message length too large: found 8233665 bytes, the limit is: 4194304 bytes`. The only change on that path is the client decode limit (`work/grpc-client-decode-limit`), so the fix is verified and the upstream candidate can go out |

Pecan BFS frontier at scale 25 also passed on this gate (2746 s, same reach
and certificate as its baseline run).

The recorded plan of every iteration is the answer to section 3's memory
question. In process-cluster mode the expansion join is
`HashJoinExec: mode=Partitioned` with both inputs repartitioned by hash
(`Hash([#7], 32)` on the adjacency's `src`, `Hash([#4], 32)` on the
frontier's `id`), and the build side is the left input, which Pecan writes
as the adjacency: `adjacency.join(active, adjacency.src == active.id)`.
Per partition each worker builds a hash table over its share of the
1,073,741,824 undirected adjacency rows, which is the 44 to 47 GiB per
worker every failing cell showed and the O(|E|) build side Sem warned
about. The single-process explain on Capitola had shown `CollectLeft` with
the frontier chosen as the build side, so the trap is specific to the
partitioned plan at scale. The fix is to write the frontier as the left
input: `work/s5-frontier-build-side` (`ffcfbd569`) does that for every
expansion join, and gate 3, queued behind the scale-26 chain, reruns the 24
relational traversal cells at scales 24 and 25 with it.

The first build of this gate (17:57 to 18:00 UTC) failed in its first
step: the vendored `nutmeg-graph` library's own tests do not compile on the
S0 line (`graph_tables/tests.rs` still read `tx.finish()?.staged_nodes`
after S0 made `finish` return a `StageReport` with an `info` field). The
S0 branch had been verified with the Python harness tests only. The test was
fixed (`work/gate-core-tests`, `2557feaf1`), the gate's Rust test and
clippy steps pass on Capitola (85 nutmeg-graph tests), and the second build
passed all 17 steps between 18:08 and 18:44 UTC (host
`sail-linux-x86_64-2557feaf18e4-release`, sha256 `ff33c08838…`; wheel
sha256 `6fe0672a78…`). The 42-cell matrix started at 18:44 UTC.

Built from the fork after the baseline matrices: `work/s0-tiered-accounting`
plus the stage-order passthrough, the client decode limit, the `max-degree`
source policy, an `argentea` harness engine, per-iteration plan
recording for the relational paths (`--record-plans`), so the scale-25
relational receipts carry the physical plan of every expansion join, and a
120 s h2 keepalive timeout on every Sail server (host default 10 s) to test
the stream-loss hypothesis of section 3, and the corrected WCC certificate
(a label must name a member of its component; numeric minimality is
reported, not required). The Argentea engine passed a
Capitola smoke before being queued: five methods (BFS reference, frontier,
direction; SSSP reference, delta_star) on a 2000-vertex directed fixture in
process-cluster mode, all validated against the independent reference, about
7 s each, 1999 of 2000 reached.

Matrix `gn-capacity-2557feaf` (42 cells): the 12 scale-25 relational cells
again, 8 scale-24 relational reference/frontier reruns, 12 Banda `asStaged`
cells at scale 24 and 25, and 10 Argentea cells (30-round cap, 32
partitions). Then the baseline's 7 unrun cells, the 12 cit-Patents ranking-kernel cells
again on the new gate (`gn-ranking-2557feaf`), and `gn-capacity-scale26-2557feaf`
(23 cells) on scale 26.

_Pending._

### Reordered at 23:10 UTC

The user set two directions: cells must not be cut off by timeouts (every
queued matrix now allows 4 hours per cell, 8 at scale 26), and Argentea
runs first. The 42-cell matrix on gate 2 was stopped after its three cells
above (kept as evidence) rather than let its remaining reference cells run
into the 90-minute cap. Gate 3, which carries every fix including the
frontier-left joins, is building; then `chain-argentea.sh` runs the 10
Argentea cells beside the 12 Banda `asStaged` cells at scales 24 and 25,
then the 20 relational cells, then scale 26, the ranking rerun and the
baseline's 7 unrun cells.

### Gate 3, Argentea and Banda `asStaged` matrix (running since 23:47 UTC)

The matrix as configured ran its 12 Banda `asStaged` cells before its 10
Argentea cells, against the direction to run Argentea first; at 02:22 UTC on
2026-09-30 it was stopped in its fifth cell (Banda scale-25 frontier, no
result recorded, the four recorded cells kept) and `chain-argentea2.sh`
started `gn-argentea-first-gate3.json`: the 10 Argentea cells alone, with
`SAIL_CLUSTER__TASK_STREAM_CREATION_TIMEOUT_SECS=900` exported into every
cell container through a new `environment` map in `run_matrix.py`
(`work/matrix-environment`), because the scale-24 Argentea attempts on
Capitola had failed on Sail's 60 s default while the unrolled job's first
stages initialized. The 8 remaining Banda cells resume after it. First cell:
scale-24 BFS reference, 02:26 UTC.


| Cell | Outcome | Time | Peak PSS | What happened |
|---|---|---|---|---|
| scale 24, Banda BFS reference, `asStaged` | **passed** | 704 s | 31.3 GiB | Banda stages Graph500 scale 24 once the canonical sort is skipped: staging 48.5 s, 268,435,456 edges retained as 9.73 GiB of Utf8-id rows with every sort tier at zero (the S0 receipt), one projection built and reused; 8,862,601 reached, certificate validated with 5 witness rounds. The first Banda result on Graph500 at this scale. Its 704 s are within 10% of the relational push-pull cells (775 and 844 s) rather than the 4 to 20x of cit-Patents: at 268M edges the projection from Utf8 ids to a CSR dominates, which is what S1 (Int64 identity) and S3 (dense u32 projection) are for |

| scale 24, Banda BFS frontier, `asStaged` | passed | 742 s | | same reach and certificate |
| scale 24, Banda BFS push-pull (direction), `asStaged` | passed | 1213 s | | same reach and certificate; the direction-switching kernel builds both an outgoing and an incoming CSR, hence 1.7 times the reference variant's 704 s |
| scale 25, Banda BFS push-pull (direction), `asStaged` | error | 1641 s | 60.0 GiB | staging passed in 114 s (536,870,912 edges retained as 19.8 GiB of Utf8-id rows, unsorted); the projection then refused: `procedure memory budget exceeded (limit 85899345920)`, with the process at 60 GiB. So at scale 25 Banda's wall is now the projection's admitted bound inside the 80 GiB quota, the direction-switching kernel needing both an outgoing and an incoming CSR from Utf8 ids; S3's dense `u32` projection is the fix, S1's `Int64` identity halves the staged rows first |

### Gate 3, Argentea-first matrix (running since 02:26 UTC, 2026-09-30)

The 10 Argentea cells (two worker processes on 32 cores, 32 partitions,
64 task slots per worker, 30-round cap, task-stream creation timeout 900 s,
100 GiB container), then the 8 remaining Banda `asStaged` cells.

| Cell | Outcome | Time | Peak PSS | What happened |
|---|---|---|---|---|
| scale 24, Argentea BFS reference | **passed** | 1213 s | 65.1 GiB (cgroup peak 70.5 GiB) | the first Argentea result on Graph500 scale 24 on the Linux gate: native plan ready at 142 s, 6 BFS levels, 8,862,601 reached, the same count as Banda and the relational cells; certificate validated with 5 witness rounds, max edge slack 0, parent tree checked. The 30-round cap unrolled 64 phases of which 31 ran, 22 of them empty (about a second each on one host). No stream loss, no timeout; 7 stale-task warnings. Repeat in the relaunched matrix (04:20 to 05:05 UTC, idle removal disabled): passed, 1445 s, 57.7 GiB, same reach and certificate; the host carried the user's default VM and a load average of 15 during it, so 1213 to 1445 s is the spread this shared host gives |
| scale 24, Argentea BFS frontier | error | 2472 s | 22.3 GiB | **lost a worker to Sail's idle probe.** At 03:34:57 UTC, 3.8 minutes into ingest, the driver stopped worker 1 ("idle for too long": `cluster.worker_max_idle_time_secs`, default 60, fires when the driver sees every task slot vacant and no local stream for a minute; the worker aborted 91 task handles on the way down). Ten minutes later the plan needed a second worker again and the driver started worker 3; Argentea initialized 12 partitions on it, and at 04:11 the retry-disabled extension job (`SAIL_CLUSTER__TASK_MAX_ATTEMPTS=1`) failed with `h2 protocol error: error reading a body from connection`: the stage read shuffle output that had lived on worker 1. No other recorded cell (baseline, gate 2 or gate 3) shows a mid-run worker replacement, so the baseline's eleven relational `h2` losses are a different mechanism; this one is deterministic once a worker idles for a minute between stages of a long job. The matrix was relaunched at 04:16 UTC as `gn-argentea-first2-gate3.json` (host output `argentea-first2-gate3/`) with `SAIL_CLUSTER__WORKER_MAX_IDLE_TIME_SECS=86400` exported into every cell container beside the 900 s stream timeout, and the same environment goes into the Banda remainder (`gn-banda-rest-gate3.json`, 8 cells), the relational rerun, scale 26 and the ranking rerun. The interrupted third cell (scale-25 push-pull, 3 minutes in) reruns in the new matrix; the passed reference cell reruns as a repeat |

Read beside the same cell elsewhere on the same input and source:

| Path, host | Time | Peak PSS |
|---|---|---|
| Argentea, Linux gate, 32 cores, two workers | 1213 s (repeat 1445 s) | 65.1 GiB |
| Argentea, Capitola alone, x86_64 under Rosetta, 8 threads, two workers, 8-round cap | 1179 s (repeat 1409 s) | not sampled (macOS) |
| Banda reference, `asStaged`, Linux gate, one process | 704 s | 31.3 GiB |
| Pecan / Grenada push-pull, Linux gate (baseline) | 775 / 844 s | about 39 GiB |

These scale-24 observations compare different execution paths on a shared
host. Argentea took 1213 s on the Linux gate and 1179 s on Capitola; hardware
and runtime differences do not isolate the effect of core count. The
measurements do not separate kernel, initialization, scheduling and shuffle
costs. A placement comparison should hold the dataset, certified result,
protocol and resource envelope fixed and measure each component. Adjacency
construction remains a separate memory/work measurement for both native paths.

### The decision matrix (05:19 to 11:31 UTC, 2026-09-30; complete)

User direction: the question these runs answer is when to run Pecan,
Banda, Grenada or Argentea; answer it as soon as possible and do not
continue a long matrix unless it adds value and the user agrees. The
chain was stopped in the Argentea scale-24 frontier cell (15 minutes in),
and the queued Banda remainder, relational rerun, scale 26, ranking rerun
and baseline resume are parked. `gn-decide-gate3.json` (`chain-decide.sh`,
host output `decide-gate3/`, container root `/targets/gn-decide`, idle
removal disabled, 900 s stream timeout) runs five cells in this order and
stops:

| # | Cell | Question it settles |
|---|---|---|
| 1 | Argentea BFS reference, scale 25, one host | does the worker-partitioned path pass the ceiling Banda hits at scale 25 (80 GiB projection budget), or is memory per host the same wall |
| 2 | Banda SSSP delta-star, scale 24, `asStaged` | weighted traversal on the resident CSR at the largest scale Banda stages |
| 3 | Argentea SSSP delta-star, scale 24 | the same weighted traversal on worker partitions, beside Banda's |
| 4 | Pecan SSSP delta-star, scale 24 | the relational weighted traversal, which lost its stream on the baseline, now with frontier-left joins and the keepalive knob |
| 5 | Pecan BFS reference, scale 25 | whether the join-side fix cures the reference variant's memory failure at scale 25, which decides whether relational users need the push-pull or frontier variants |

Results:

| # | Cell | Outcome | Time | Peak PSS | What happened |
|---|---|---|---|---|---|
| 1 | Argentea BFS reference, scale 25 | error | 1767 s | 56.2 GiB | all 32 partitions initialized (native plan at 313 s), then the unrolled job failed in phase 0 with `h2 protocol error: error reading a body from connection`; no worker was replaced and no OOM event was recorded. The host carried the user's default VM (its nightly container had run since about 03:00 UTC) and was at 32.8 of 33.8 GB swap. The sampler recorded nothing between 302 s and 939 s of execution; the cause of that sampling gap was not measured. Worker memory peaked at 40 GiB and unwound from about 1250 s. The retry below stopped the default VM and changed keepalive interval/timeout to 300/600 s (`gn-decide2-gate3.json`, `chain-decide2.sh`, `decide2-gate3/`); changing both conditions does not isolate either cause |
| 2 | Banda SSSP delta-star, scale 24, `asStaged` | **passed** | 1615 s | 45.8 GiB | the weighted traversal on the resident CSR: 8,862,601 reached (the same set as BFS), certificate validated with 22 witness rounds, max edge slack 5.6e-12, conservative distance error bound 9.3e-5. 2.3 times the BFS reference on the same input (704 s), with the host again at a load average of 15 to 17 |
| 3 | Argentea SSSP delta-star, scale 24 | nonconverged (harness cap) | 4215 s | 67.8 GiB | the worker-partitioned traversal exhausted its 30-round harness cap (`--argentea-max-rounds 30`, delta 0.1, 992 decide/apply events over 32 partitions) with structured `sssp_round_cap` at bucket 3.0: 8,853,142 reached and 2,007,762 still active; native plan at 189 s. Banda's separate completed cell reached 8,862,601 in 1615 s at 45.8 GiB. The Argentea cell is nonconverged, so its 4215 s and 67.8 GiB are consumed resources, not a completed-run speed ratio. No higher-cap cell was run; completion time and certified output remain unmeasured |
| 4 | Pecan SSSP delta-star, scale 24 | error | 1752 s | 65.0 GiB | `h2 protocol error: error reading a body from connection` in iteration 2 (iteration 1 ended at 650 s), also seen in earlier reference/frontier cells. Frontier-left joins, 120 s keepalive timeout, idle removal disabled and 900 s stream timeout did not prevent this recorded failure; its originating cause was not captured and no OOM event was recorded. The harness then recorded an orchestration error when its 180 s `docker cp` of the 1 GB staging directory timed out; host free space was 17 GiB. Cell 5 did not run in that matrix and was queued separately as `gn-decide3-gate3.json` after the Argentea retry |
| 1 (retry) | Argentea BFS reference, scale 25, one host, keepalive 300/600 s, default VM stopped | **oom** | 8213 s | 99.8 GiB | the default VM was stopped and no comparable sampler stall was recorded; this does not establish absence of all shared-host interference. Native plan ready at 720 s, all 32 partitions initialized, then the first phase climbed through 74 GiB at one hour and 94 GiB at two hours. The 100 GiB container limit killed a worker at about 2 h 14 min (`memory.max` events 11,138, `oom_kill` 1), with 17 of 32 first-phase decisions done. This configuration exceeded its encompassing limit. Banda's separate scale-25 projection refused an 80 GiB admission quota. These distinct failed outcomes do not establish an intrinsic one-host ceiling or the memory required by another implementation or configuration |
| 5 | Pecan BFS reference, scale 25, frontier-left joins | error | 2318 s | 40.7 GiB | `h2 protocol error: error reading a body from connection` in iteration 2 (loading and iteration 1 took 1685 s), at about 41 GiB with no recorded memory event and no worker replaced. The baseline reference cell reached iteration 4 before the container limit stopped it. This run failed earlier despite the join-side change, but the two runs do not isolate a common stream-loss cause. Preserve this error separately from the baseline memory failure and from push-pull/frontier certification outcomes |

The reported completed traversal times for Pecan and Grenada at scales 24
and 25 were within 10% on corresponding variants. Certification status must
remain separate: completion alone is not a passed comparison. Both use the
same relational controller here, but these shared-host observations do not
establish performance equivalence. Further cells were parked under the user's
bounded decision-matrix scope. The two-host Argentea scale-24 outcome is below.

### Two hosts: Capitola and Morrobay (23:50 UTC)

The user asked for Argentea across two physical machines. Setup, all from
gate 3 (`ffcfbd569`): an x86_64 macOS Sail host cross-built on Capitola
(sha256 `fc1d87dcce…`, 804 MB, `sail 0.7.1`) and an x86_64 Nutmeg wheel
(sha256 `e3d9683172…`), the same bytes installed on both hosts (Capitola
runs them under Rosetta, Morrobay natively); one venv per host from the same
lock with the same CPython 3.12.13; clean checkouts of `ffcfbd569` on both;
MinIO on Morrobay as the shared object store, reached by both over
Tailscale; the driver and one worker on Capitola, the second worker on
Morrobay launched over ssh by the qualifier's supervisor. The qualifier's
own two-host BFS fixture passed (`smoke-bfs/receipt.json`: hosts
`Capitola.local` twice and `morrobay.local`, native audit clean). Scale 24
is on the object store; scale 22 is being prepared with the `max-degree`
source. The first scaled two-host run (`argentea_two_host_capacity.py`,
`scale22-bfs-reference/receipt.json`): Graph500 scale 22 (4,194,304
vertices, 67,108,864 edges, source 2301132 of degree 320,916), Argentea BFS
reference, 16 partitions, one worker per host, 8 GiB native quota per
worker.

| Outcome | Time | Result | Notes |
|---|---|---|---|
| **passed** | 2746 s | 6 levels, 2,394,613 reached, 4,194,304 owned rows | 64 native phases unrolled for the 30-round cap (31 executed), 1,040 native receipts, 1,598 completed worker tasks, worker 1 on Morrobay and worker 2 on Capitola; Capitola runs the x86_64 artifact under Rosetta, and the two hosts talk over Tailscale, so this is a functional and relative measurement only |

The same cell on one host, same artifacts (Capitola alone, the driver and
two worker processes, x86_64 under Rosetta, the dataset on local disk,
16 partitions, 8 GiB quota per worker):

| Run | Time | Result |
|---|---|---|
| Argentea, one host, two workers, 30-round cap (64 phases) | 288 s | 6 levels, 2,394,613 reached, certificate validated |
| Argentea, one host, two workers, 8-round cap (20 phases) | 268 s | same result |
| Argentea, two hosts, one worker each, 30-round cap | 2746 s | same result |
| Argentea, two hosts, one worker each, 8-round cap (20 phases) | 421 s | same result |
| Banda, single process on Capitola (x86_64 under Rosetta), `asStaged` | 120 s | same result; staging 52 s, 2.36 GiB retained |
| Argentea, two hosts, 8-round cap, input on local disk on both hosts (no object store) | 405 s | same result; zero object-store retries |
| Argentea, two hosts over the home LAN, 8-round cap, local inputs | 381 s | same result; this observation is about 6% below the 405 s Tailscale/local-input observation; it does not isolate network latency, shuffle work or shared-host load |
| **Scale 24**, Argentea, two hosts over the LAN, 8-round cap, local inputs, store on Capitola, 48 slots per worker, stream timeout 900 s, idle removal off (05:52 to 06:12 UTC, 2026-09-30) | failed at 1194 s | `argentea: operation cancelled while reading input`. The unrolled job initialized 22 of 32 partitions (16 on the Capitola worker, 6 on the Morrobay worker) in 20 minutes, then at 06:12:10 every running task on both workers flipped to FAILED in the same second (651 tasks), after which the driver's h2 client hit its locally-reset-streams limit (1024) and the session closed; five object-store body errors reading from the Capitola store at 06:04 were retried. The first failing task was on the Morrobay worker (job 37, stage 22). Sail logs worker failures only as task status, so the originating error is not in the log; the client saw Argentea's cancellation message. At scale 22 the same configuration passes in 381 s, so this is the first scale at which the two-host path does not complete on this setup (a 1 Gb LAN, the store on one of the two hosts, x86_64 under Rosetta on Capitola). Not retried without the user: a retry would need worker-side error logging first |

Network correction (2026-09-30, 02:30 UTC): the two-host runs above went
over Tailscale, which was set up while Capitola was away, although both
machines were back on the home LAN (Capitola 192.168.4.61, Morrobay
192.168.4.63; from Capitola, LAN ping 14 to 82 ms over Wi-Fi against 178 to
245 ms through the Tailscale relay at that moment). The user's rule from
here on: verify the network path before any distributed run and use the
LAN when both are home. The configuration now advertises the LAN addresses
(gRPC's resolver cannot resolve `.local` mDNS names, so IPs, not
hostnames) and launches the Morrobay worker through the existing `morrobay`
ssh alias; the qualifier's two-host fixture passed again over the LAN. The
scale-24 two-host run is the first on the LAN; scale 22 is rerun on the LAN
for a like-for-like number.

Scale 24 stopped twice before running: Argentea at 32 partitions needs 96
worker task slots (the harness default of 32 per worker gives 64), and with
48 per worker the one-host run then failed with `local stream is not
created within the expected time`, Sail's `cluster.task_stream_creation_timeout_secs`
(default 60 s), which the Argentea init stage exceeds on 268M edges under
Rosetta. The two-host run failed on its first write instead: Morrobay's
data volume is full (3.6 TiB, 37 GiB free), so its MinIO refuses writes
(`XMinioStorageFull`). The shared store moves to a MinIO on Capitola for
the two-host runs, and the qualifier gains a `SAIL_QUALIFY_EXTRA_ENV`
passthrough so the timeout can be raised for the supervised processes.

**Scale 24 on one host runs (2026-09-30, 02:11 to 03:07 UTC).** With 48
task slots per worker and the stream-creation timeout at 900 s, Argentea
BFS reference on Graph500 scale 24 (268M edges, source 13507776) on
Capitola alone, two workers, 32 partitions, 8-round cap:

| Run | Time | Result |
|---|---|---|
| Argentea, one host, two workers, 8-round cap, scale 24 (first run; receipt spoiled, see below) | 1409 s | 6 levels in 9 unrolled phases, 8,862,601 reached (the same count as Banda and the relational cells on the Linux gate), certificate validated: all-edge inequalities and rooted tight-edge reachability, max edge slack 0, parent tree checked, 5 witness rounds; the native plan was ready at 222 s, so the unrolled job took about 1180 s |

Its receipt says `mismatch`: HEAD moved during the run when
`work/matrix-environment` was committed in that checkout. The reported
traversal and certificate fields remain evidence, but 1409 s is not a passing
repeat of a frozen source revision. The subsequent run on `837a8ecf5`
(`capitola-scale24-argentea-reference-cap8-t900b`) **passed in 1179 s**
(native plan ready at 222 s, 8,862,601 reached, certificate validated,
max edge slack 0, parent tree checked). Preserve both outcomes. Rule from this: never
commit in a harness checkout while a cell runs on it; edit in another
worktree. Against scale 22 (268 s for 67.1M edges, 20 phases), scale 24 is
4 times the edges for 4.4 times the time (1179 s; corrected 2026-09-30: an
earlier version of this line said 16.8M edges and 16 times). The Linux gate runs the same
cell first in its Argentea matrix (started 02:26 UTC) for the 32-core
number, and the two-host scale-24 run waits on the shared store.

The cap-30 and cap-8 observations differ by 20 s on one host (288 versus
268 s) and 2325 s across two hosts (2746 versus 421 s). Dividing the latter
by 44 removed native relations gives about 53 s per relation, but this is
arithmetic over whole-run differences, not measured empty-phase or network
time. The cap changes plan size, task count and terminal work; placement,
store access and shared-host load also require controls. A cap must be
sufficient for a certified result and disclosed with every comparison.

In the longer two-host run, 152 of 153 Spark jobs took at most 255 s in
aggregate; the native job containing the unrolled phases spanned 2244 s.
The running status of its 1,598 pipelined tasks does not distinguish compute
from blocked input/output time. During the first two minutes, the object-store
client recorded 41 response-body retries. Later local-input (405 s) and LAN
(381 s) observations are retained above, but their differences do not assign
a fraction of total time to storage or shuffle. The corrected network
description is the dated LAN/Tailscale note above.

## 4b. External graphframes-rs context (2026-09-30)

Sem Sinchenko's in-process DataFusion implementation reports these results
on c5d.4xlarge, 16 vCPUs, 32 GiB, with `--max-memory 30G --num-workers 16`.
The [upstream record](https://github.com/SemyonSinchenko/graphframes-rs/blob/ba2fdd8f51fa7fafdca15012d2741f5f8d80c024/benches/results/README.md)
is pinned to `ba2fdd8f51fa7fafdca15012d2741f5f8d80c024`; it reports medians
of five runs and memory in GiB. These are external observations on a different
host and execution class. Sharing DataFusion does not establish a fixed or
data-independent difference in execution cost.

| Graph | WCC | PageRank (10 iterations) | Shortest paths |
|---|---|---|---|
| cit-Patents | 4.71 s / 1.46 GiB | 4.05 s / 1.06 GiB | 0.90 s |
| graph500-24 (8.9M non-isolated vertices, 260M edges) | 33.3 s / 14.0 GiB | 24.5 s / 5.0 GiB | 6.7 s |
| graph500-25 | 82.5 s / 18.6 GiB | 62.3 s / 12.4 GiB | 26.4 s |
| graph500-28 | 1009 s / 20.2 GiB | 912 s / 18.3 GiB | 783 s |

Ours on cit-Patents (baseline `b87fb27ac`, 32 cores, process-cluster mode,
two worker processes, 32 partitions): Pecan WCC 312 s (randomized) and
500 s (min-label), Grenada 397 and 566 s, Pecan PageRank 729 s for 20
iterations, Banda WCC 30 to 39 s and PageRank 32 s. These times have different
hardware, process topology and timing boundaries from the external results;
PageRank also has a different iteration count. The external scale-24 input
lists 8,870,942 vertices and 260,379,520 edges, versus this campaign's
16,777,216 vertices and 268,435,456 edge tuples. Even cit-Patents is listed
with 16,518,947 edges upstream versus 16,518,948 here. Establish identical
manifests and semantics before reporting comparative ratios.

Both implementations cite the Bögeholz, Brand and Todor (ICDE 2020) WCC
family and write/re-read Parquet checkpoints. This does not establish equal
algorithmic work or equal checkpoint costs. The following observed costs and
source differences identify controls to measure; they do not attribute the
external timing difference.

1. **Where the plan runs.** His is one process with 16 DataFusion
   partitions; a repartition hands record batches between threads. Every
   cell of ours ran Sail in process-cluster mode: a driver and two worker
   processes and 32 partitions, with jobs scheduled as distributed tasks.
   Same-worker stream reads use the local stream manager; cross-worker reads
   use Flight (`crates/sail-execution/src/task_runner/actor/handler.rs:317-326`). No cell of this campaign ran `--mode local`.
2. **A round has multiple data actions and control RPCs.** The unfused
   `wcc_randomized.py` contraction loop materializes three tables (priorities,
   representatives, relabeled edges), verifies only the representatives with
   `expected_rows`, and separately counts active vertices and next edges:
   six explicit write/count actions per round. The initial `remaining` count
   is outside the loop. `materialize` (`staging.py`) also requests owned-run
   capability/schema information and performs keyless `repartition(P)` before
   the write. These source counts are not measured server job/stage totals.
   Min-label writes and counts the new labels, then joins stored new/old label
   tables to test for change; that comparison does not repeat the adjacency
   expansion join. These source files are identical between campaign baseline
   `b87fb27ac` and checked controller `56194b170`.
3. **The per-round floor is 4.7 s, not a small constant.** In the
   randomized cell the last eleven rounds, on a contracted graph that is
   nearly empty, take 4.6 to 5.7 s each; 19 rounds of that floor are
   about 90 s as a simple extrapolation, not a measured removable component. Min-label's rounds are a flat
   22 to 25 s on 33M adjacency rows whatever changed.
4. **Setup before the first round.** `_snapshot` rewrites vertices and
   edges to Parquet and runs five validation jobs (null ids, id
   uniqueness by group-by, null endpoints, two anti-joins of every edge
   against the vertices) and a count: 28 s before round 1 of randomized
   WCC, 39 s before min-label, 58 s before PageRank. At scale 24 the
   source-0 cells measured this alone: 200 s (Pecan) and 372 s (Grenada)
   of loading. The external 6.7 s shortest-paths result uses a different
   input and timing boundary, so it does not measure the cost of this setup.
5. **Banda's time is ingest, not kernel.** WCC: staging 13.8 s, projection
   14.4 s, kernel and output 1.4 s (min-label) to 10.6 s. PageRank:
   13.8 + 14.6 + 3.3 s. Staging plus projection totals about 28 s in
   these observations. Kernel-only and whole-run boundaries must remain
   separate; they do not supply a cross-system speed comparison.

The split between execution-mode cost and controller actions is unmeasured.
A useful first control is Pecan WCC (randomized and min-label) on the same
cit-Patents manifest in local and process-cluster modes, with matched total
CPU/memory budgets and partition counts. A 16-CPU/32-GiB container does not
reproduce the external machine. Record setup, planning, tasks, transport,
checkpoint I/O and round counts; a local-mode change alone does not identify
one causal subsystem or explain the separate stream-loss errors. These cells
were not run for this record and should not overlap the active Linux build.

## 5. Findings so far

0. The relational paths traverse Graph500 scale 25 on this envelope: Pecan's
   and Grenada's push-pull BFS finished in 1516 and 1610 s at about 39 GiB
   PSS, the frontier variants in 2729 and 2764 s at 75 GiB (Pecan's within
   300 MiB of the 100 GiB container limit), all six iterations to an empty
   frontier. Only Pecan's frontier result was certified; the other three
   results are unverified because the certificate query itself hits the 4 MiB
   client limit at this scale. The reference variant (all reached vertices
   relaxed each round) fails on memory at scale 25 on both paths.

1. A benchmark fixture's default source has to be checked for degree zero;
   the harness now refuses to let that pass silently.
2. Recorded scale-25 refusals included a conservative sort admission bound
   and a client decode limit. Correcting those limits removes those specific
   refusals; it does not establish graph completion, a new capacity ceiling
   or a cause for other failures.
3. Argentea runs through the same harness as the other paths, so the four-way
   comparison the plan asks for can now be one matrix.
4. Argentea has certified scale-22 results across two physical hosts with
   identical artifacts. Recorded cap-8 times were 421 s across hosts and
   268 s with two workers on one host; Banda's separate single-process
   boundary was 120 s. Local-input and LAN observations were 405 s and
   381 s. Keep their store/network/load conditions with each result. These
   observations do not isolate per-phase transport time, establish an
   object-store percentage or demonstrate homogeneous cluster scaling.
