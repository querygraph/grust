# Sem's second review: relational graph measurements and a controlled investigation

Written 2026-09-30 for review by Astra and Sem.
Corrected UTC: 2026-09-30T18:12:32.343558+00:00. It records Sem's numbers
and his argument, sets ours beside them, separates what is measured from
what is read from source and what is still unmeasured, and proposes a
staged plan with proposed changes, controls, engineering budgets and
qualification boundaries. It builds on
[`GRAPHFRAMES-RS-PARITY.md`](GRAPHFRAMES-RS-PARITY.md) (2026-09-28: where
graphframes-rs gets its speed, and the declared-layout work), on the
campaign record
[`reviews/gn-capacity-2026-09-29.md`](reviews/gn-capacity-2026-09-29.md)
section 4b, and on Astra's review and experiments of today
([`reviews/sail-graphs-2026-09-30/REVIEW.md`](reviews/sail-graphs-2026-09-30/REVIEW.md),
[`reviews/sail-stream-experiments-2026-09-30/RESULTS.md`](reviews/sail-stream-experiments-2026-09-30/RESULTS.md),
[`CLUSTER-PREPARATION.md`](reviews/sail-stream-experiments-2026-09-30/CLUSTER-PREPARATION.md)).
Sem's first review, his PR 30 and his objection to building a CSR at all,
is answered in [`FABLE-ON-ASTRA.md`](FABLE-ON-ASTRA.md) section 8.

No cell was run for this document. The gate was building
`work/stream-performance-review` when it was written. The subsequent
[detailed review and answers](reviews/sail-stream-experiments-2026-09-30/SEM-REVIEW-2-RESPONSE.md)
identify contract, ownership, accounting and comparison limits. The original
line references in that review refer to the document hash in its
[source receipt](reviews/sail-stream-experiments-2026-09-30/sem-review2/source-receipt.json).
The stages below describe the proposed investigation. The later
[day accounting](reviews/sail-stream-experiments-2026-09-30/SEM-REVIEW-2-DAY-ACCOUNTING.md)
records every A–F item's completed evidence and remaining work. Compact tuple
MIN has since passed its traversal controls and large replay; no fresh WCC
result has yet closed the performance question. Preparation is not a run.

## 1. What Sem says

Translated from his messages of 2026-09-30:

- His benchmarks are finishing; the numbers "should be 100% achievable in
  Sail. A constant overhead for plan serialization, the Python loop and so
  on cannot be avoided, but you must get about the same performance class."
- "On a nominal 30 GB machine it must survive, and if you add resources it
  must perform better (more memory, less spill)."
- "If WCC on cit-Patents runs 700 seconds for you on a 32-core machine,
  something is 100% wrong, because for me it is 4.7 seconds on a machine
  with 16 cores."
- "Same class simply because both are just DataFusion, and the whole
  Connect overhead adds about a constant per iteration (ser-de, gRPC, plan)
  that does not depend on data size, since the plan is the same for any
  graph."
- "If same class does not come out, or if it needs three times the memory
  to be same class, I would suggest rethinking all of it from scratch."
- Expected in Sail: "on the order of 10 seconds for cit-Patents and 30 to
  40 minutes for graph500-28."
- On spill: his runs spill too ("120 GB peak disk for WCC on graph500-28"),
  so "if similar numbers do not come out in Sail, with a small constant
  correction for Sail's overhead, then the problem is not only spill."
- On the input snapshot: "Pecan rewrites the inputs to Parquet? Why? The
  LDBC graphs are already available as Parquet files; I once asked the
  DuckLab people to make them, and they did." (Answered in Stage B7 and
  in Stage A's inputs.)
- On Banda: "I told you about this, and it matches what I saw when I
  benchmarked my tool: the conversion to CSR eats everything." (Stage F.)
- On the timer: "why on earth include validation in wall time." (Stage A,
  item 4.)

Sem's answers to section 6's questions (2026-09-30, translated):

- Timer: "yes, I ran it honestly": c5d.4xlarge, Ubuntu, stable Rust
  toolchain, entry point `benches/python/main.py`; the published numbers
  are that boundary.
- Settings: "everything goes through the CLI; let Astra look at `main.rs`,
  it is all pinned there." Sort-merge join is always on: "my philosophy is
  that we must be able to process a graph even when neither the vertices
  nor the edges fit in memory." For Sail's pilot he allows pinning the hash
  join, since on every graph500 the vertex set is small (tens of millions),
  "especially while you cannot yet write the edges so that the read needs
  no sort inside the merge join."
- Inputs: `benches/python/datasets.py` has everything: the LDBC
  Graphalytics graphs as Parquet from
  `https://datasets.ldbcouncil.org/graphalytics-parquet/{name}-v.parquet`
  and `{name}-e.parquet`.
- Stage E's API question: "I did not understand it. graphframes-rs exists
  as a CLI now; as a library it is `lib.rs`, `GraphFrame`, `g.page_rank()`
  and so on. Let Astra look at `main.rs` rather than have me retell it."
- On the u32 vertex targets in Stage F: "u32 is literally not serious; that
  the vertices of this benchmark fit u32 means nothing. In the real world
  ids are always i64 (`monotonically_increasing_id` returns i64 anyway). I
  would set a hard condition: you are building for big data, and cheating
  on benchmarks is not worth it."
- On the vertex counts: "did Astra make a mistake somewhere? These are
  Kronecker graphs whose giant component is 99.9% of the vertices; that
  only half of your vertices are reachable from the hub should raise
  suspicion. Anyway, LDBC has 8.87M vertices." Answered in section 2.
- On the write-cost gap in Stage D: "did Astra try this at a larger data
  size? It would be good to understand how that difference scales."
  Answered in Stage D.

His results (`SemyonSinchenko/graphframes-rs`, branch
`new-benchmark-results` at `ba2fdd8f51fa7fafdca15012d2741f5f8d80c024`,
`benches/results`; c5d.4xlarge, 16 vCPUs, 32 GiB,
`--max-memory 30G --num-workers 16`; wall time / peak RSS / peak disk,
medians of 5):

| Graph | WCC | PageRank delta, cap 10, threshold 0.01 | Shortest paths |
|---|---|---|---|
| cit-Patents (3.77M vertices, 16.5M edges) | 4.71 s / 1.46 GiB / 0.23 GiB | 4.05 s / 1.06 GiB / 0.33 GiB | 0.90 s / 0.95 GiB |
| graph500-24 (8.87M reported vertices, 260M edges) | 33.3 s / 14.0 GiB / 6.2 GiB | 24.5 s / 5.0 GiB / 2.3 GiB | 6.7 s / 5.0 GiB |
| graph500-25 | 82.5 s / 18.6 GiB / 12.2 GiB | 62.3 s / 12.4 GiB / 8.6 GiB | 26.4 s / 12.4 GiB |
| graph500-26 | 213 s / 20.5 GiB / 28.8 GiB | 149 s / 14.3 GiB / 19.3 GiB | 72.9 s / 13.8 GiB |
| graph500-28 (121M vertices, 4.24G edges) | 1009 s / 20.2 GiB / 120 GiB | 912 s / 18.3 GiB / 91.4 GiB | 783 s / 17.6 GiB |

`--num-workers` is DataFusion's `target_partitions` in one process;
`--max-memory` is the spill pool. His WCC follows Bögeholz, Brand and
Todor (ICDE 2020), randomized contraction, with Parquet checkpoints
written and re-read between iterations. The receipts identify runtime source
`b4da56dabe20bba8e29563e06acc5179b2113ce3`; the checked algorithm, CLI and
monitor files are identical between those commits. Wall time covers subprocess
launch through exit, including input setup, algorithm work, final Parquet
writing and cleanup, with independent verification outside it. Peak RSS is
sampled process RSS. Peak disk is baseline-subtracted work-directory footprint
(checkpoints, spills, output and logs), not an isolated spill counter.
[Source and receipt audit](reviews/sail-stream-experiments-2026-09-30/SEM-REVIEW-2-RESPONSE.md).

## 2. Our recorded observations and comparison boundaries

Baseline `b87fb27ac`, Linux gate on shared Morrobay, 32 cores, 100 GiB
container, Sail in process-cluster mode (driver and two worker processes,
32 partitions). The following are retained campaign observations, not dedicated
host timing results or matched ratios against the external table.

| cit-Patents | Recorded observation |
|---|---|
| Pecan WCC, randomized contraction | 312 s, 19 rounds |
| Pecan WCC, min-label | 500 s, 20 rounds |
| Grenada WCC (the same controller over graph tables) | 397 and 566 s |
| Pecan PageRank power | 729 s, 20 iterations (setup 58 s, first iteration 23 s) |
| Pecan BFS | 164 s |
| Banda WCC | 30 to 39 s: staging 13.8, projection 14.4, kernel and output 1.4 to 10.6 |
| Banda PageRank power | 32 s: 13.8 + 14.6 + 3.3 |

The scale-24 campaign recorded completed relational push-pull BFS cells at
775 to 844 s. The two source-isolated cells recorded setup of 200 s (Pecan)
and 372 s (Grenada). Other cap failures, stream errors and OOM outcomes remain
in the [capacity record](reviews/gn-capacity-2026-09-29.md); a capped or failed
cell is not a completion-time result.

The cit-Patents ranking cells recorded 2.8 to 4.0 GiB sampled peak PSS; the
scale-24 relational reference/frontier cells recorded roughly 40 to 100 GiB.
These are different metrics from the external process RSS. Low sampled PSS
does not establish zero spill: record actual spill counters and pool pressure.

The hosts, resource envelopes, timing boundaries and graph manifests differ.
The external cit-Patents README lists 16,518,947 edges; ours lists 16,518,948.
Its Graph500-24 lists 8,870,942 vertices and 260,379,520 edges; ours includes
16,777,216 vertices and 268,435,456 input edge tuples. The input contracts differ: our generator
keeps the complete `0..2^24-1` ID domain, while the cited LDBC table reports a
smaller vertex set. Our hub traversal reaches 8,862,601 vertices. Dividing that
by LDBC's 8,870,942 gives about 99.9%, but these are differently generated inputs;
that quotient does not establish our own isolate count or giant-component
fraction. Our manifest records 2,798 self-loops and explicitly says duplicates
were not counted. The 8,055,936-edge difference therefore cannot be assigned
solely to deduplication and self-loop removal. Count endpoints and unreached
components on the same graph to settle that question. Stage A uses the same
pinned official LDBC files on both sides instead.
External shortest paths
use directed edges and a catalog-derived landmark; the scale-24 Sail cells use
an explicit hub and undirected edges, and certify parent/hops as well as
distance. External finite-step PageRank uses thresholded delta propagation
and final normalization; Pecan power redistributes dangling mass each step.
Equal iteration limits do not produce equal finite-step answers. These
observations motivate matched controls; they do not support cross-system
ratios or assignment of the difference to a cause.

## 3. Where the time goes

Each factor is marked **measured** (a receipt or a recorded run), **source**
(read from code, no timing attached) or **unmeasured**.

**F1. Every campaign cell ran Sail as a cluster; the external run is one
process.** *Measured on different hosts and inputs.* No cell of the original
campaign used `--mode local`. The declared-layout work (parity document,
section 13) recorded local-mode Pecan PageRank on 2M vertices and 16M edges,
four partitions, one process on Capitola, at 2.9 s per round and 12.5 s setup.
The gate's cluster-mode cit-Patents cell recorded 23 to 34 s per round and
58 s setup. The external PageRank observation is 4.05 s for its complete
capped-ten delta run. None of these pairs isolates execution mode or supplies
a matched per-iteration ratio.

**F2. A round has multiple data actions and control RPCs.** *Source; timing
observations are separate.* `StagingRun.materialize` (`staging.py:25-58`)
does a keyless `repartition(P)`, a Parquet write, a read back and schema check,
and an optional `count()` when the caller supplies `expected_rows`.
The unfused randomized WCC loop (`wcc_randomized.py:67-109`) has three writes,
one expected-row count on representatives, and two explicit counts for active
vertices and next edges: six explicit data actions per contraction round.
The initial `remaining` count is outside the loop. The fused loop has two
writes and two counts. Owned-run and schema/planning requests are additional;
these source counts do not establish physical server job/stage totals.

Min-label writes and counts the new labels, then joins the stored new and old
label tables to test for change; that comparison does not repeat the adjacency
expansion join. PageRank power has a dangling-mass action, a state write and
its expected-row count; a convergence action occurs only when tolerance is
specified. Fixed iterations with `tolerance=None` omit it. The last eleven
randomized WCC rounds, on a nearly empty contracted graph, recorded 4.6 to
5.7 s each. Extrapolating that floor over nineteen rounds gives about 90 s;
it is not a measured removable component or a proven constant for every graph.

**F3. Setup before the first round.** *Measured.* `_snapshot`
(`algorithms.py`) rewrites vertices and edges to Parquet, then runs five
validation actions (null ids, id uniqueness by group-by, null endpoints, two
anti-joins of every edge against the vertices) and a count: 28 s before
randomized WCC's first round, 39 s before min-label, 58 s before
PageRank. These boundaries include setup work specific to this controller.

**F4. Checkpoint reads do not carry the required key-layout contract.**
*Source and separate parity-work measurements.* A plain Parquet read does not
declare the partition/key mapping needed to reuse the prior distribution.
Count actual repartitions from each physical plan; not every join is proved to
shuffle both sides merely because that declaration is absent. The parity work
reports declared scans, host restatement and shuffle-free joins for its tested
plans. Its bucketed/sorted write observations were 11.6 to 12.5 s for
`partitionBy`, versus 1.5 to 5.8 s for plain writes of 16M rows. The paired
local-mode round observation was 4.95 s with layout versus 2.9 s without.
The ranges alone do not establish an 8–20 ratio. The cluster-mode comparison
remains unmeasured, and the declared-layout branch is separate from this
campaign's baseline.

**F5. Aggregation and estimation costs inside the engine.** *Measured in
isolation by Astra.* DataFusion 55.1's grouped `min(struct(...))`, which
Pecan's traversals use, retained about 2 KB per group and scanned scratch
for every resident group on every batch in the exact-source probe. At 100,000
groups the original/compact retained requested-heap ratio was 48.8, with the
compact implementation at `56194b170`. This is an isolated macOS allocator
measurement, not Linux process or whole-query memory. The compact path has since passed a small
matched Pecan SSSP frontier control: compact/original median time 0.6078 and
sampled execution PSS 0.8389 on shared Morrobay. A scale-24 DeltaStar replay
also passed its certificate and physical-output check at 33.05 GiB whole-container
peak. The earlier original replay OOMed at 100 GiB, so that large pair has no
completed timing or uncapped-memory denominator. These traversal results do
not establish WCC performance; fused WCC uses a separate `min_by` path.
[Probe scope](reviews/sail-stream-experiments-2026-09-30/STRUCT-MIN-ALLOCATION.md),
[paired control](reviews/sail-stream-experiments-2026-09-30/host-pair-publication/README.md),
[large replay](reviews/sail-stream-experiments-2026-09-30/COMPACT-REPLAY-AND-SSSP.md).
Separately, the aggregate's output is estimated at O(E) rows, which
drives join-side and broadcast choices (parity document, section 8).

**F6. Process pools do not bound total container memory.** *Replay and source
evidence.* The harness configured a 96 GiB pool in each of three processes
inside a 100 GiB container. In the logged scale-24 Pecan frontier replay, the
kernel OOM record matches that container and one worker disappears from the
sampler; the two workers had approached roughly 50 GiB each. This establishes
the OOM outcome for that replay, not the cause of earlier no-OOM stream losses.
It also does not establish that nothing spilled. Pool allocations, native
reservations, transport queues and other nonpool memory must be accounted for
separately; even pools summing below the limit do not guarantee a spill-only
outcome. [Evidence](reviews/sail-stream-experiments-2026-09-30/RESULTS.md).

**F7. Banda's recorded ingest is substantial.** *Measured.* On cit-Patents,
staging plus projection totals about 28 s. Kernel and output observations
range from 1.4 to 10.6 s for WCC; PageRank's corresponding phase is 3.3 s.
Keep phase and whole-run boundaries separate.

What is **unmeasured** is the split between F1 and F2 on one host: how
much of a 22 s round is the cross-process exchange and how much is the
controller's extra jobs. Stage A supplies controls but cannot by itself
identify each contribution. No factor above is assigned that causal share.
Shared-host times are observations, and a removed action is not a speedup until a paired
run shows one (the fused overflow change measured 1.09 times slower on
its first fixture).

## 4. The plan

Use explicit engineering objectives: exact admitted answers, disclosed
execution classes, bounded memory and disk, fewer redundant actions and bytes,
and measured scaling efficiency. Ratios against another implementation are
reported evidence only after contracts and boundaries match; they are not
predetermined acceptance outcomes. The absolute budgets below are proposed,
unqualified experiment thresholds, not demonstrated capability. Shared-host
measurements remain paired controls with steal and interference disclosed;
publish absolute timing results only on a qualified dedicated host.

### Stage A. Establish matched contracts and a local/process-cluster control

1. Pin graphframes-rs source, image, toolchain and binary in a separate detached
   build with its own target and receipt. Inputs for both sides are the
   LDBC Graphalytics Parquet files his `datasets.py` downloads
   (`https://datasets.ldbcouncil.org/graphalytics-parquet/{name}-v.parquet`
   and `-e.parquet`; checked reachable 2026-09-30: cit-Patents 3.7 and
   66.8 MB, graph500-22 2.4 and 185 MB, graph500-24 8.7 and 798 MB,
   graph500-25 16.7 and 1628 MB, graph500-26 32.2 and 3288 MB), which
   removes the vertex and edge differences of section 2 at the source.
   His settings are pinned in `main.rs` (Astra reads it; no retelling):
   sort-merge join on for him, hash join permitted for Sail's pilot at his
   suggestion. His timer boundary is confirmed: process launch to exit,
   input read and final write included. Define common input manifests,
   direction, duplicates/isolates, traversal source and requested outputs.
   For WCC, supplement the existing large-graph certificate with an independent
   reference partition or connectivity witness: equal labels along edges alone
   do not prove disconnected components were not merged.
2. Start with one small matched algorithm. A proposed profile is 16 CPUs,
   32 GiB container memory and local disk. Record actual threads, allocator,
   pool type and sizes, native reservations and nonpool headroom. The external
   CLI uses FairSpillPool; Sail's current harness uses a greedy pool. A proposed
   30 GiB total pool requires admission and pressure tests; it is not a safe
   memory guarantee. Different driver/worker pool sizes need harness support.
3. Preserve explicit local and process-cluster Pecan variants. For WCC, keep
   `randomized`, `randomized_fused` and `min_label` distinct. Before PageRank,
   choose identical finite-step recurrences or a common residual/error target.
   The current harness's positive tolerance and fixed-point certificate do not
   support fixed-ten power merely by setting the iteration cap to ten; add an
   explicit finite-step mode and oracle if that is the chosen contract.
4. Record algorithm-ready, result-exported and result-verified boundaries,
   setup and per-round time. Input validation is not algorithm work and is
   not in the external tool's timer (Sem, 2026-09-30: "why include
   validation in wall time"): report Pecan's snapshot and validation
   actions as their own phase and exclude them from the compared wall
   time, and give the library a trusted-input entry (Stage B7) so the
   compared run does not perform them at all. Excluding them changes no
   conclusion on cit-Patents (rounds alone are 284, 461 and 671 s), but
   it is the only boundary under which the numbers are comparable. Also
   record jobs/stages/tasks, plan bytes/planning time,
   exchanges, writer time, scalar actions, pool/spill counters and whole-process
   memory. Freeze warmup and ABBA order and retain every outcome. Estimate the
   campaign from the pilot: two inputs times three external, five local and
   five cluster configurations is already 26 configurations, or 104 cells at
   four measured samples each before warmups. No two-hour duration is promised.

| Observation | Supported conclusion | Next control |
|---|---|---|
| Matched local implementations differ | Their full measured paths differ; no single cause identified | Inspect plans, validation, aggregation, checkpoint and controller counters |
| Matched process-cluster and local cells differ | The combined execution-mode change matters in this profile | Separate scheduling, exchange, placement and serialization costs |
| Repeated client actions dominate measured round latency | Removing those particular actions is a candidate | A scoped Stage B ablation with the same answers and resources |

Maintain the independent multi-host placement, strong-scaling and weak-scaling
matrix in [CLUSTER-PREPARATION.md](reviews/sail-stream-experiments-2026-09-30/CLUSTER-PREPARATION.md).

### Stage A result (A4, 2026-10-02)

Codex ran A1 to A3 on the gate: his binary and Pecan (typed, no validation,
B9) in the same 16-CPU, 32 GiB container on the LDBC cit-Patents files, two
ABBA blocks, four measured samples per engine, a full output oracle on every
cell, launch to exit including input read and output write.

| Contrast | Local mode | Process-cluster mode | Cluster over local |
|---|---|---|---|
| Pecan randomized WCC over graphframes-rs randomized WCC | 3.77 | 4.74 | 1.26 |
| Pecan frontier BFS over his directed unweighted hops | 2.51 | 2.99 | 1.19 |
| Pecan min-label WCC over his randomized WCC | 9.49 | 12.1 | 1.27 |

Sampled engine memory: 2.2 against 1.5 GiB for randomized WCC, equal for
BFS. Pecan's public algorithm call took 48 s for randomized WCC of which
5 s is the input snapshot; 18 s for BFS.

Reading, by the decision table: the local ratio is between 2.5 and 3.8,
so the client-driven controller is in or near his class in one process,
and the remainder is its per-round actions, which is Stage B. The cluster
ratio is 1.2 to 1.3, so cross-process execution is a quarter of the cost at
this size, not the tenfold the earlier cross-host indication suggested;
Stage C is not the priority. Stage E's trigger (a local ratio above 20) did
not fire: the loop inside the server is a design choice to make on its
merits, not a rescue.

What moved the number from the campaign's 66 to 120 times to 3.8: no
validation jobs, the paper's contraction (B9), 16 partitions instead of 32,
pools that fit the container, and his binary measured on our host instead of
his instance's published time.

Limits: one graph with no isolated vertices, a shared host, n = 4. The
graph500-24 comparison is not made yet, and B8's scale-24 adjacency build
ran out of a 32 GiB container where his WCC peaks at 14 GB, so memory at
scale 24 is the next thing to measure, before any claim there.

### Stage A repeated on Capitola (2026-10-02): the reading above is corrected

The reading "the remainder is its per-round actions" does not hold. The same
contrast was repeated on Capitola with release builds of both engines, the
same LDBC files, the same launch-to-exit boundary, two ABBA blocks and an
oracle on every pair
([`reviews/sem-review-capitola-2026-10-02/A2-local/README.md`](reviews/sem-review-capitola-2026-10-02/A2-local/README.md)).

| | Gate (A2) | Capitola |
|---|---|---|
| graphframes-rs randomized WCC | 13.75 s | 3.66 s |
| Pecan randomized WCC | 51.8 s | 5.00 s |
| Pecan over graphframes-rs, WCC | 3.77 | **1.37** |
| Pecan over graphframes-rs, PageRank (B11 against his `page-rank`, 10 steps) | not measured | **1.28** |
| Pecan round 1 of 16 | 23.2 s | 1.43 s |
| Pecan rounds 5 to 16 | 3.2 s | 0.26 s |

What this changes:

- On Capitola Pecan is within 1.3 to 1.4 times graphframes-rs on
  cit-Patents, with the client-driven controller and two writes and one
  count per round. The controller's actions are not what separates them.
- The gate slows graphframes-rs by 3.8 and Pecan by 10.4 relative to
  Capitola. Something on the gate costs Sail about 2.8 times more than it
  costs his binary. Both engines use the same volume there.
- A2's own per-round data already showed it: round 1 is 23 s of the 48 s
  call, and the twelve tail rounds together are 3 s. The time is in the
  heavy rounds' engine work, not in the number of round trips.
- Stage B's knobs, measured on Capitola: no keyless repartition saves 11%,
  inputs in place 13%, both with hashed labels 22%. Preferring sort-merge
  joins changes nothing at this size. These are refinements, not the gap.

What is open, and it comes before any further Stage B work: why Sail is
slower on the gate. One suspect is the gate's Sail binary: the extension
build script builds the host with the dev profile, and a dev-profile host on
Capitola reproduces the gate's shape (a 12.6 s first round, tail rounds of
0.1 to 0.2 s). Against it, every gate receipt names a binary called
`…-release`. **Cleared on 2026-10-02**: Codex found the build receipt. The
gate runtime was built with `cargo build --locked --release -p sail-cli`,
optimization level 3 and LTO. The gate's slowness for Sail is not a dev
build. Nor is it the hardware: a plain C baseline run natively on both
hosts puts Morrobay at half of Capitola on one thread and equal with 16
([`reviews/sem-review-capitola-2026-10-02/host-baseline/README.md`](reviews/sem-review-capitola-2026-10-02/host-baseline/README.md)).
What remains is the virtual machine the gate runs in (QEMU with HVF, 32
virtual CPUs on 18 cores). The user's decision, pending Codex's scheduling:
time on the raw machine and keep the VM as the Linux functional gate.

**Confirmed the same day.** Codex built Sail `9f0aa7d2a` natively on
Morrobay's macOS, with the same release profile, and ran the A2 Pecan cell
there (randomized WCC, cit-Patents, 16 partitions, snapshot on, full oracle):

| Pecan randomized WCC, cit-Patents | In the gate VM (A2) | Native on the same machine | Capitola |
|---|---|---|---|
| Launch to exit | 51.8 s | 8.86 s | 5.00 s |
| The algorithm call | 48 s | 5.07 s | 4.1 to 4.7 s |
| Round 1 | 23.2 s | 1.46 s | 1.43 s |
| Rounds 5 to 16 | 3.2 s | 0.59 s | 0.26 s |

Same machine, same cell: the VM cost a factor of 5.8 launch to exit and 16 in
the first round. That is one native run, on a controller six commits later
than A2's and a Mach-O build instead of an ELF one, so the factor is an
indication; its size leaves no doubt about the direction. graphframes-rs has
been built natively there too and not yet timed, so the native ratio between
the two engines on Morrobay is still open. Codex retired the benchmark VM at
the user's instruction; benchmarks run on the bare machine from here, and a
VM is kept only for Linux build testing
([`reviews/sem-review-morrobay-2026-10-01/A5/NATIVE-COMPLETION.md`](reviews/sem-review-morrobay-2026-10-01/A5/NATIVE-COMPLETION.md)).
Every time in this document measured in that VM (A2, A3, B8, and the
September capacity campaign) is a time in that VM. If the binary is a true release build, the second suspect is
Sail on x86 Linux in that VM, and one profiled cell in the A1 container
separates engine time from write time from round trips. Until that is
answered, the gate's 3.8, 2.5 and 9.5 should be read as upper bounds on
Pecan's distance from graphframes-rs, not as the distance.

At graph500-24 on Capitola (one ABBA block, the same oracle): randomized
WCC 30.4 s for Pecan against 27.7 s for graphframes-rs, ratio **1.10**;
PageRank, 10 delta steps, 24.5 against 20.5 s, ratio **1.20**; 13 GB at the
peak. So the class holds at 260M edges on this machine, and the 32 GiB
failure B8 met on the gate is not Pecan's randomized WCC running out of room
by itself.

With the inputs read in place, as his binary reads them
(`snapshot_inputs=False`, B7), and BFS no longer writing the edges twice
(`d0e4e422a`), launch to exit on Capitola:

| Graph | Contrast | graphframes-rs | Pecan | Pecan over graphframes-rs |
|---|---|---|---|---|
| cit-Patents | WCC | 3.45 s | 4.05 s | 1.17 |
| cit-Patents | PageRank, 10 delta steps | 2.78 s | 3.17 s | 1.14 |
| cit-Patents | BFS | 1.86 s | 1.21 s | 0.65 |
| graph500-24 | WCC | 25.5 s | 20.3 s | 0.80 |
| graph500-24 | PageRank, 10 delta steps | 18.1 s | 17.1 s | 0.95 |
| graph500-24 | BFS | 9.78 s | 8.53 s | 0.87 |

Every pair passed its oracle on every vertex. Four samples per engine on
cit-Patents, two on graph500-24, a laptop in use: these are indications of
class, not publishable ratios. What they indicate is parity. The input
snapshot was the largest cost Pecan added (10 s of the 30 s WCC at
graph500-24), which is the point Sem made about rewriting the inputs.

Banda on the same machine and files
([`reviews/sem-review-capitola-2026-10-02/F1/README.md`](reviews/sem-review-capitola-2026-10-02/F1/README.md)):

| One WCC, launch to exit | cit-Patents | graph500-24 |
|---|---|---|
| graphframes-rs | 3.7 s | 27.7 s |
| Pecan | 5.0 s | 30.4 s |
| Banda, first call | 8.4 s | 139 s |
| Banda, each further call | 0.26 s | 1.1 s |
| CSR floor (F0) | 0.4 s | 7.7 s |

This is Sem's position, measured: for one call the relational path beats the
resident CSR, by 4.6 times at graph500-24, because the projection build is
136 s on one thread. Banda pays off from the fifth call on the same staged
graph. Its ingest is in icebug's class (136 s against 179 to 186 s) and 18
times the floor. The decision guide's first two rows, which put Banda first
on every kernel, rest on gate cells where the relational path was the slow
one; they do not hold on Capitola.

### Stage B. Reduce redundant round work without weakening checkpoints

Each item is a separate opt-in candidate. Run the relevant unit tests plus
actual GraphUtils integration in local and process-cluster modes, lifecycle
failure controls and independent result checks. The existing 46 nonintegration
Pecan tests alone do not qualify checkpoint changes; the complete candidate
package's 125-test suite and its source/version boundary are recorded in the
[experiment results](reviews/sail-stream-experiments-2026-09-30/RESULTS.md).
Use matched paired controls; count actual jobs rather than inferring them from
Python actions. No public algorithm or execution-mode default changes here.

| # | Proposed experiment | Required boundary and evidence |
|---|---|---|
| B1 | Opt out of keyless `repartition(P)` before checkpoint writes | Inspect removed exchanges and resulting fanout/skew; preserve empty/schema/cancellation behavior. This can be tested now, but it does not declare key partitioning on the subsequent Parquet scan. |
| B2 | Add a bounded host write receipt with rows/files/bytes | Require confirmed writer completion and an exact immutable generation manifest with schema, file identity and ownership. Footer row totals can replace counts of that exact relation. Existing `gf.utils.v1` only supplies owned filesystem operations; a listing or valid footers cannot commit an uncertain write or authorize early cleanup. |
| B3 | Carry required round scalars with state | PageRank needs current dangling mass before the next rank; use an in-plan scalar or explicitly pipelined next-round mass with bootstrap, preserving the recurrence and reduction semantics. Commit state and scalar output consistently. Min-label may carry a nonnull changed flag; missing/unsupported footer statistics require a scan, never an assumption of convergence. Ordinary footers do not contain arbitrary floating-point sums. |
| B4 | Measure the existing `randomized_fused` variant explicitly | It adapts the PR 56 contraction approach while retaining original IDs. Existing integration tests compare each representative map. Keep the public default unchanged; qualify seed/duplicate/isolate behavior, `min_by` memory and certificates before any later default proposal. |
| B5 | Bounded contraction tail experiment below a measured threshold | Edge count alone does not bound plan growth or convergence. Preserve seeded representative choices, all reverse-expansion mappings, isolates, minimum original-ID labels, iteration caps and cancellation. Bound unrolling and retain a checkpoint fallback; eleven tail rounds are an observation, not guaranteed removable work. |
| B6 | Configurable checkpoint interval where plans remain bounded | Retain each immutable source generation until every lazy descendant has completed. Preserve uncertain-write ownership, cancellation and retry; cap plan bytes/depth and measure recomputation and peak memory. |
| B7 | Combine validation work and reuse a validated immutable input handle | Preserve BIGINT/schema, null/duplicate ID and both endpoint membership checks. A path or caller `trusted=True` assertion is not proof of immutability/validation. Pin the exact file generation and keep borrowed input ownership separate from run-owned outputs. Count physical scans/jobs; combining expressions does not prove one pass. |

B2 must test lost acknowledgments, partial/late writers, retries, cancellation,
empty stages, schema mismatch and file replacement. B3 companion output must
share a committed generation with state; it is not automatically client-only.
Total row count is an active-row count only for a relation containing exactly
those active rows. B5/B6 must not delete a checkpoint that a still-lazy plan
references; current deletion follows successful materialization.

Proposed pilot budgets on a qualified host are at most two data jobs per round,
round floor at most 1 s, setup at most 5 s, and cit-Patents randomized WCC at
most 30 s end to end. These are unqualified engineering budgets. A 60 s result
after B1–B4 would trigger review of measured remaining costs, not prove a
server loop necessary or license weakening semantics.

### Stage C. Measure distributed-job overhead and enforce resource envelopes

| # | Proposed experiment | Control and acceptance evidence |
|---|---|---|
| C1 | Compare local and process-cluster execution for one-host graph runs | Keep both explicit; decide any future default from qualified use cases and evidence. A local result does not qualify several hosts. |
| C2 | Measure planning/serialization, scheduling, stream creation and teardown at P = 4, 16, 32 with two workers | Force real distributed stages and an exchange that optimization cannot remove; 20 repetitions, cold/warm separation, p50/p95 and task counts. The proposed 100 ms warm-job budget at P = 16 is unqualified by current stream-fault controls. |
| C3 | Configure driver/worker pools with measured nonpool headroom inside a 32 GiB profile | Record pool reservations, native quotas, transport buffers, PSS, cgroup peak and spill separately. Preserve refusal, timeout and OOM as separate outcomes. Pool sums alone cannot ensure completion or spill instead of a kernel kill. |
| C4 | Qualify compact tuple MIN with the original controller, then probe `min_by` separately | Use the paired traversal control and certificates; report memory and time ratios, including regressions. The existing tuple MIN optimization does not cover fused WCC's `min_by`. |

The current harness copies the same pool setting to driver and workers; a
small driver pool plus larger workers requires configuration support, and a
native quota larger than the driver's pool can reject extension binding.

### Stage D. Stop re-shuffling the edges (the declared layout, write side)

Sem asks how the write-cost gap scales. The only observation is the parity
work's (Capitola, local mode, one frame of 16M rows, single runs, times
varying up to threefold under load): `partitionBy` 11.6 to 12.5 s against a
plain write of 1.5 to 5.8 s. Nothing larger was measured, by anyone. First
control here: the same plain-against-bucketed write at 16M, 64M and 268M
rows on the gate, paired, so the gap is a curve and not one point.

The read side is finished (`work/declared-layout`). What remains is
section 14 of the parity document, reordered by what the campaign showed:

1. Measure the declared layout in cluster mode on the gate, where a
   shuffle may cross processes; whether removal is more valuable than in
   the local-mode experiment remains to be measured.
2. Report Sail's slow `partitionBy` write with the existing probe
   (`layout-exp/partitionby_probe.py`); the user files it upstream.
3. Profile the driver-side writer's FFI crossing if 2 stalls.

Proposed, unqualified engineering budget: retain only required exchanges and
keep the checkpoint-write overhead within 50% of its matched plain-write
control. Verify distribution declarations and physical exchanges explicitly.

### Stage E. Evaluate an explicit server-side iterative controller

Sem's answer settles the API question: graphframes-rs is a CLI (`main.rs`)
over a library (`lib.rs`, `GraphFrame`, methods such as `page_rank`), so
the second form below is an embedding of that library, not a new protocol.

Today Grenada is Pecan's controller entered through graph tables. A single
Spark Connect request per algorithm is an architectural candidate, not a
performance guarantee. Evaluate it only if component measurements justify the
scope. Two possible prototypes are:

- a driver-placed controller that explicitly submits each round through the
  job runner, with verified checkpoint layout and bounded retained state; or
- a graphframes-rs adapter with an explicit Sail submission path for each
  internal action. A DataFusion context alone does not turn library `collect`
  or write calls into Sail distributed jobs.

The current extension interface does not itself provide the session's
`JobService`. Prove controller placement, per-round submission and worker codec
support, cancellation, resource accounting and cleanup on one tiny algorithm,
then demonstrate remote worker execution. Local integration is not merely a
build question: algorithm and result contracts, storage ownership and execution
boundaries still need qualification. Argentea's job/operation-scoped state also
cannot simply be retained across new jobs without a continuation design.
Check the pinned library's current license/API before adapting it (Apache-2.0
was recorded at `b4da56d`).

### Stage F. Investigate Banda ingest

Sem's standing objection (his first review, `FABLE-ON-ASTRA.md` section 8,
and again on 2026-09-30: what he saw benchmarking his tool, "the conversion
to CSR eats everything") matches the cit-Patents receipts: about 28 s of
staging and projection around a 1.4 to 3.3 s kernel. Whether that is the
conversion or our conversion is the first control, before any change: a
native-only CSR build from the same `edges.parquet` (Int64 ids, no Sail
tables, no FFI crossing, no canonical sort), timed on the gate with the
same boundaries. Degree count, prefix sum and fill over 16.5M edges are
expected on the order of a second; that measured number is the floor, and
the gap between it and 28 s is what the candidates below have to close.
The crossover test of `FABLE-ON-ASTRA.md` section 8 stands: if the ingest
does not come under the relational path's first-round cost on graph500-24,
that is evidence for Sem's position and the decision guide says so.

Sem's condition is adopted as the contract: vertex ids are i64 at every
interface, and no parity number is produced with a narrowed representation.
A dense internal target width inside one partition's CSR is an optimization
with a checked bound and a 64-bit fallback; it is measured beside the i64
form and never substituted for it in a comparison.

Evaluate Int64 identity and dense u32 vertex targets from `FABLE-ON-ASTRA.md`
as separate candidates. Preserve usize/u64 arc offsets: a graph may fit u32
vertex IDs while symmetrized arc count exceeds u32. Use checked conversions
and explicit unsupported-size errors. Qualify `asStaged` order/determinism per
kernel before any default proposal; staging chooses edge order before the
algorithm runs. A proposed 5 s staging-plus-projection budget on cit-Patents is
unqualified and does not imply a cross-system end-to-end ratio.

### Order and cost

Finish the instrumented failure and compact-aggregation qualification, define
shared contracts and validators, then run Stage A's small pilot. Choose B/C
ablations from measured components while preserving the multi-host program.
B2 requires a host protocol change; B3 may require a writer/commit change too.
D and F remain separate candidates. Estimate duration from frozen dry plans,
resource admission and pilot outcomes; no day/hour estimate is established.

## 5. Proposed engineering budgets and qualification

These budgets are proposals rather than achieved results. All require pinned
inputs/protocols and complete answer validation; shared-host observations are
reported as matched controls, not published absolute results.

| Property | Proposed budget or required evidence |
|---|---|
| Controller work | At most two data jobs per round, measured from logs and plans |
| Small-round latency | At most 1 s on a qualified dedicated host |
| cit-Patents setup | At most 5 s with the same validation and snapshot contract |
| cit-Patents randomized WCC | At most 30 s end to end on the qualified pilot profile |
| Memory | Enforce total process/container admission with measured nonpool headroom; distinguish spill, refusal and OOM |
| Scaling | Fixed-resource placement plus strong/weak controls, with per-worker skew, bytes and driver/store load |
| Larger Graph500 admission | Manifest, arc-index bounds, memory model and disk-capacity check before launch |

The external Graph500-28 work-directory observation is 120 GiB, which includes
more than spill. Morrobay's volume had about 40 GiB free when this plan was
written; it cannot admit that footprint. Recheck live capacity before any
future run; no scale-28 launch is authorized by this document.

## 6. Questions

For Sem (all four answered on 2026-09-30; see section 1):

1. Timer boundary: confirmed, launch to exit with input read and output
   write.
2. Settings: pinned in `main.rs`; sort-merge join on; hash join allowed for
   Sail's pilot.
3. Inputs: the LDBC Graphalytics Parquet files from `datasets.py`; the
   exact cit-Patents pair is now pinned. Historical Graph500 input counts
   remain distinct and do not alone establish our isolate count (section 2).
4. API: the library is `GraphFrame` in `lib.rs`; the CLI is `main.rs`.

Open for him: none at the moment. What he will see next is Stage A's
pilot on his inputs, with its receipts.

For Astra (answered in the [detailed response](reviews/sail-stream-experiments-2026-09-30/SEM-REVIEW-2-RESPONSE.md#answers-to-the-five-astra-questions);
C4's later qualification is reflected above):

1. Is Stage A's container (16 CPUs, 32 GiB, pools summing to 30 GiB) the
   appropriate proposed profile to qualify with nonpool headroom, and should the
   graphframes-rs build go through the same rebuild script as the gate?
2. B2 changes the host's graph-utils service. Is a footer-derived receipt
   acceptable as the commit check, given the uncertain-write ownership
   rules in `staging.py`?
3. Which of B1 to B7 conflict with the checkpoint-partitioning proposal
   in `CLUSTER-PREPARATION.md` section 3, and should B1 wait for it?
4. Is C2's target (100 ms per distributed job at P = 16) realistic given
   what the stream diagnostics already show about task and stream setup?
5. Does the compact accumulator's replay schedule allow C4 before
   Stage A, while retaining the instrumented original as a control?

## 8. Sem's code review of Pecan (2026-10-01): every remark, its status

Sem read the code on 2026-10-01 and sent screenshots (kept in iCloud under
`src/grust/`). Each remark below is listed with what was done, where the
answer lives, and who owns what is still open. Translated from Russian.

| # | Remark | Status | Where / owner |
|---|---|---|---|
| 1 | "Where is the current Pecan code? I get lost in your repository." | Answered | [`pecan-code-and-harness.md`](pecan-code-and-harness.md): the reading map; current package is `examples/extensions/graph-algorithms/src/pyspark_pecan/` at `6ae2e43a9` on `querygraph/sail` (`work/pecan-typed-integrated`, `work/stream-review-followup`) |
| 2 | "Where is the harness that measures this? It should be about a hundred lines: parse parameters, run, time." | Answered | same map, "Harness behind the reported measurement": `benchmarks/traversal_cell.py` and `graph_cell.py` time the call; `runtime.py` starts the server; the rest is certificates and receipts, which is why it is longer than a hundred lines |
| 3 | "Remove all this junk: a full scan, and if a check is not free do not do it; 99.9% of honest users pay for it." (the source-membership and weight checks) | **Done** | `work/pecan-typed` (`7145d107c`) removed every input-validation job; the schema check stays because it is free; `AGENTS.md`, "Valid Graph Assumptions" |
| 4 | "Terrible code: imports inside the body." | **Done** | the integration (`6ae2e43a9`) moved every import to module scope through `_contracts.py`; `test_import_structure.py` fails the suite if a function-local import returns |
| 5 | "Has Astra not heard of type hints? Without them go-to-definition and find-references do not work; what is `cancellation`?" | **Done** | every definition typed; `mypy --strict` and `ruff` clean on the package; `CancellationToken` typed on `StagingRun` |
| 6 | "Fix the contract: the graph is assumed valid, the arguments are assumed valid; a check that needs an operation over the data must not run by default." | **Done** | `AGENTS.md`, "Valid Graph Assumptions", now states the rule in his words; argument checks are the free Pydantic models at the call boundary, never queries |
| 7 | "`crates/sail-function/src/aggregate/compact_struct_min.rs`: what is this and why?" | Answered | same map, "Why `compact_struct_min.rs` exists": DataFusion 55.1's grouped `min(struct(...))` kept about 2 KB per group; the fork's accumulator keeps 48.8 times less at 100,000 groups. It exists because Pecan's traversal rounds take a `min` over a `struct(distance, hops, parent)` |
| 8 | "33.05 GiB for scale-24 SSSP is insane; even Spark GraphFrames asks for less." | **Answered; native accounting scoped, historical peak cause open** | same map, "What the 33.05 GiB number measures": the whole-container lifetime cgroup peak, three Sail processes, not an algorithm allocation. The causes under test: per-process pools that do not sum to the limit (section 3, F6), the struct-min accumulator (item 7), and the reference variant joining every reached vertex. C3 now observes real host/native reservation counters and explicit refusal/release; it does not reclassify the old whole-container peak or qualify an OS-32-GiB envelope. [C3](reviews/sem-completion-2026-10-03/C3/README.md). |
| 9 | "Which DataFusion pool does the harness use? Sail's default is unbounded; benchmarking on an unbounded pool would explain the insane memory." | **Answered; actual native quota control qualified** | not unbounded: the harness sets `SAIL_RUNTIME__MEMORY_POOL__TYPE=greedy` with an explicit size per process (`benchmarks/runtime.py`). The real defect is his point in another form: three processes each had a 96 GiB pool inside a 100 GiB container, so the sum was unbounded in effect (section 3, F6). Native C3 proves admission/refusal/final lease release. Transport, nonpool headroom, spill and OS/PSS still need separate evidence; a pool sum alone is not a resource-envelope verdict. [C3](reviews/sem-completion-2026-10-03/C3/README.md). |
| 10 | "Sail uses mimalloc, I use snmalloc-rs; that affects sampled peak RSS more than wall time." | Recorded | `crates/sail-cli` enables `mimalloc` by default; Stage A records the allocator with each run and compares RSS only within one allocator |
| 11 | "Test what is faster on Sail: `array(struct(src as id, ...), struct(dst as id, ...))` + explode, or `unionByName` as now. Not obvious: on vanilla DataFusion union is faster, on vanilla Spark explode is; union is two full scans, and two plans if the input carries transformations." | **Done:** B8 protocol, including retained OOMs and withheld graph500 shapes | same map, "UNION versus EXPLODE/UNNEST review targets" lists the sites; the paired measurement is Stage B item B8 below |
| 12 | "Do a proper scale test of writing Parquet sorted the right way so the merge join skips both the sort and the repartition; 16M is good, better to see how it scales." | **Done for D1; D2 qualified within its native scope** | Measured at 16M, 64M and 268M rows on Capitola: the sorted write is a constant 3.4 to 6.3 times a plain one at every size; the bucketed write a reader can declare is 12 to 16 times. The join it would remove is 45% of a round. Details and limits are in the D1 record. The native D2 follow-up measures unsorted keyed checkpoints with strict 2/1/0 exchange removal and complete answers; runtime sorts remain. [D2](reviews/sem-completion-2026-10-03/D2/README.md). |
| 13 | "Check Pecan against the LDBC `test-*` graphs: their archives carry ground-truth communities, PageRank ranks and SSSP, so Pecan matches LDBC semantics." | **Done:** A0, 16/16 supported reference cases | [Official-reference evidence](reviews/pecan-ldbc-semantics-2026-10-01/README.md); CDLP and LCC are explicitly unsupported |
| 14 | "`wcc_fused`: I do not like it. How is `min_by` implemented in Sail? I cannot imagine it without an array as state; at tens of millions of groups that is bad whether partial aggregation fires or not. Restoring original components is one O(V) aggregation at the end, and only if the user needs original ids. Why `min_by` and carrying original ids? The beauty of Bögeholz et al. is that ids are restored by reverse application of the transformation; no mapping to carry or compute. Ask Astra why she deviated from the paper." | **Done:** B9; original deviation and correction documented | The deviation is Fable's, from 2026-09-28, not Astra's: `wcc_fused.py` keeps original BIGINT ids as representatives (its docstring: to avoid mixing hashes across rounds and with isolated ids) and therefore needs `min_by` to carry the neighbor id beside its minimum priority, plus the reverse expansion joins over the round history. Sail's `min_by` is not an array: `crates/sail-function/src/aggregate/max_min_by.rs` holds a row-wise accumulator with two scalars, but the planner's simplify hook rewrites `min_by(neighbor, priority)` into DataFusion's ordered first/last value, which has grouped support (Astra's [WCC review](reviews/pecan-ldbc-semantics-2026-10-01/WCC-REVIEW.md) on branch `work/morrobay-pecan-typed-results`); the cost is an ordered aggregate over O(E) candidate rows with per-group state, plus the final canonical-minimum aggregate and join, which an arbitrary-label option could skip since LDBC validation accepts any partition labels. An earlier line here called it a per-group boxed fallback; that was a misreading corrected on 2026-10-01. The fix is to follow the paper: the affine priority is a permutation for nonzero `a`, so use it as the representative id, aggregate with plain `min`, and invert the affine maps in one O(V) pass at the end only when original ids are wanted. Stage B item B9 |
| 15 | "SSSP: why not Pregel? It expresses trivially, would be the common primitive for PageRank and SSSP (or multi-source), has fewer actions, and one join with the adjacency straight into groupBy+agg that DataFusion collapses, so no O(E) materialization; the active set for SSSP is tiny." | **Done:** E0 loop, weighted SSSP and landmark programs; native plans/full oracles | Our `frontier` method already joins only the active set; the `reference` method joins every reached vertex by design, as the reference baseline, and that is what his screenshot marks as O(E). What Pregel would add is one controller and one plan shape per superstep for PageRank, SSSP and label propagation, with the round's extra actions (two materializations and a count) gone. Recorded as Stage E's first candidate for the loop, beside the graphframes-rs embedding **2026-10-02: the abstraction exists**: `GraphAlgorithms.pregel()` (`9f0aa7d2a`), his builder's semantics with his unit tests as the specification; PageRank's delta form runs on it. Weighted SSSP and graphframes-rs landmark shortest paths now run on the primitive; [Oct 3 E0](reviews/sem-completion-2026-10-03/README.md#pregel-programs-and-plans-e0) records the exact source and 11 full native controls. Further algorithms remain candidates, not implementations claimed here |
| 17 | On a proposal in Codex's WCC review to replace `min_by` with plain `MIN(priority)` and decode the winner by the inverse map: "that is exactly what the paper proposes, what Spark GraphFrames implements, and what my graphframes-rs does." | **Done**: B9 | `work/wcc-affine` (`7475dfc03`): representatives are the hashed ids, one union, one grouped `min`, one `least`; the back pass composes the later affine maps; `canonical_labels=False` keeps hashed labels. Follows his `connected_components.rs` directly |
| 18 | "I do not like PageRank. Neither GraphX nor I redistribute dangling mass; it is almost enough to normalize at the end, and even that can be optional, because users need the order of ranks, not their values." | **Done**: B10 | `work/wcc-affine` (`f3b3ef8fc`): `method="pregel"`, the Pregel paper's and GraphX's static form, one job per step, no dangling term, no convergence test, `normalize=True` optional. The dangling term in `method="power"` is not an invention: it is the LDBC Graphalytics PageRank contract, and A0's 16 fixtures pass through it, so `power` stays for LDBC semantics and `pregel` is the GraphX-faithful form |
| 19 | "If we ask 'do it as in GraphX', do not invent that the ranks diverge by 1e-5; we understand that. Third algorithm, third time I see something 'improved' on the fly with a big trade-off. So hard to follow." | Recorded, rule adopted | The dangling redistribution, the L1 convergence test and the delta method's residual certificate are Fable's design from 2026-09-28, not Codex's. The rule now in `AGENTS.md`: an algorithm asked for "as in X" is implemented as in X, and any deviation is a separate, named method |
| 20 | On the delta method's per-step materialization of the active set and the second materialization of the state (two screenshots): "why?", "already materialized there, why another?"; on the activity aggregate: "it is essentially a stop condition, why?" | **Done**: B11 | The active set is written so the next step reads a stable frontier and the activity scalars come from it; the state write is the checkpoint; the aggregate feeds the frontier threshold and the dangling push. His point stands: GraphX's delta form needs none of this. B11 (`0d1ef2ca3`) is that method: `pregel_delta` writes the state once per step and nothing else; with a fixed budget it runs no aggregate at all, and the stop condition exists only under `vote_to_halt` |
| 21 | "The people from Google did not worry about 1e-5 (the Pregel paper); why was it decided necessary? In GraphX it is nicer still through delta, and the frontier shrinks." | **Done**: B10, B11 | B10 is the paper's form; B11 (`pregel_delta`) is the GraphX delta form, with the shrinking frontier, equal to graphframes-rs to 1e-15 on a 2M-edge test graph |
| 22 | "Same point as for SSSP: make a Pregel abstraction, then SSSP, PageRank, K-Core, ArticleRank and every other *Rank, label propagation, strongly connected components. One abstraction is easier to benchmark under different conditions." And: "I have looked at all three algorithms. If you want, I can write down for the agent what I would like checked." | **Done for the primitive and requested first programs; further algorithms deferred** | The Pregel loop, GraphX delta PageRank, weighted distance-only SSSP and graphframes-rs landmark shortest paths now have exact-source gates and eleven full native controls on the three requested graphs. His later [written checklist](SEM-QUESTIONS-2026-10-01.md) explicitly postpones CDLP, K-Core and friends; the broader list is a direction for the primitive, not an implementation claim. [E0](reviews/sem-completion-2026-10-03/E0/README.md). |
| 23 | His written checklist, "What I want to check" (pull request #31 on the fork, moved verbatim to [`SEM-QUESTIONS-2026-10-01.md`](SEM-QUESTIONS-2026-10-01.md)): (a) explode against `unionByName` on Sail, with numbers; (b) raise again the pre-sorted edge write that lets the merge join skip sort and repartition: vertices are always fewer than edges, so a 3x costlier state write can still win, 16M rows is too small to be more than planner and serde overhead, and vortex may be worth a look; (c) Pecan should be a proper Pregel, built from the best of GraphX, GraphFrames and graphframes-rs, with PageRank and SSSP first (shrinking and growing frontiers), checkpointing by Parquet or by persist, plans analysed and microbenchmarked, run on cit-Patents, kgs and wiki-Talk; even a Rust-level Pregel extension with a PySpark API; (d) WCC: re-implement graphframes-rs cleanly, reach the same single-node class or name the blocker, only then go distributed | **Requested controls delivered with explicit qualifications** | B8 retains all failures and withheld graph500 shapes; D1 measures all three write scales, D2 qualifies unsorted cluster checkpoints, and E0 supplies the two first programs and three-graph plan/oracle campaign. The Vortex reader passes but its writer is unavailable; persist is a native9f no-op. Rust-side Pregel remains his speculative option. [E0](reviews/sem-completion-2026-10-03/E0/README.md), [D2](reviews/sem-completion-2026-10-03/D2/README.md), [Vortex](reviews/sem-completion-2026-10-03/Vortex/README.md). |
| 24 | On Banda: his icebug numbers (in-memory CSR through icebug-format and a networkit fork, CSR built through DuckDB with a 12 GB memory limit, i64 indices), graph500-24 on an i3.xlarge, 4 cores, five runs: WCC 200 s, PageRank 10 iterations 209 s, CDLP 218 s, peak RSS about 19.5 GiB, 17 GiB of spill. "This is what I meant: algorithms on a CSR are mega fast, but building it every time is too expensive." The phase split in his receipts: CSR and graph build 186 s and 179 s; the WCC kernel 7 s; ten PageRank iterations 26 s | Recorded as Stage F's reference | `SemyonSinchenko/graphframes-rs` branch `ladybug`, `benches/results/ldbd/*/M/graph500-24/icebug_mem_12G_threads_4/benchmark.json` |
| 25 | "200 seconds on graph500-24 on 4 cores is what Banda should deliver, the more so since icebug has i64 indices. If Banda's numbers are an order of magnitude larger, go into icebug and icebug-disk and redo it, without adding things on the fly (like converting everything to strings and then a `HashMap<String, u32>`, what could go wrong)." | **Done: F0, released F1 and native F2/F2a** | Our scale-24 Banda BFS: 704 s on 32 cores, of which staging 48.5 s and a kernel of seconds, so the Utf8-id projection is the remaining 600-odd seconds (not separately timed in that receipt): the order of magnitude he predicts, on eight times the cores. The Utf8 staging and the string-keyed projection are exactly his example. F0 measures the native floor; F1 (S1 Int64 identity, S3 dense projection) removes the string-keyed projection. The native released int64 baseline and explicit four-phase profile now retain one/three-call outputs on both LDBC graphs. [F2](reviews/sem-completion-2026-10-03/F2/README.md). |
| 26 | "A parallel task. By my count a CSR pays for itself at three or more calls. And honestly, algorithms are easier to write on a CSR than on relations, so since Banda exists, finish it to a reasonable state: a CSR backend with clear limits, interactive when the CSR is cached; when it does not fit, the relational path and Pregel." | **Done for measured resident-CSR one/three-call controls; fit qualified by profile** | The native F2/F2a profiles stage once per series and compare one/three calls with complete outputs; C3 observes actual quota admission/refusal/release. This is not a universal edge-count fit limit or automatic relational fallback. [F2](reviews/sem-completion-2026-10-03/F2/README.md), [C3](reviews/sem-completion-2026-10-03/C3/README.md). |
| 27 | Alexy: "that is exactly the goal of all this: most people have small graphs that fit a u32 CSR; if they need more, distributed." Sem: "Broadly yes, except that if you run only one algorithm the conversion is not justified. So look at my icebug benchmark results in the form 'end to end: Parquet in, Parquet out'." | **Done for both native profiles and four-phase control** | The lazy baseline and explicit four-phase profile have separate disclosed transport boundaries; every output is retained and fully checked. [F2](reviews/sem-completion-2026-10-03/F2/README.md). |
| 16 | On the WCC pilot table (local against two workers, randomized against fused, 2.3 to 4.0 GiB): "this looks mega-strange; if it is single-source there should be a tiny frontier." | Answered | the table is WCC, not a traversal; the memory is container peak with three processes. The screenshot shows why the reading map was needed |

Two Stage B items follow from this review and are added here:

| # | Change | Where | Removes |
|---|---|---|---|
| B8 | measure `unionByName` of two projections against `array(struct, struct)` + explode on Sail, paired, on cit-Patents and scale 24, for the adjacency symmetrization, min-label's message union and the fused representatives | `algorithms.py`, `traversal.py`, `wcc_fused.py` | one of two full scans per round if explode wins |
| B9 | randomized WCC as in the paper: affine priority as representative id, plain `min`, inverse affine maps applied once at the end, original ids only on request | `wcc_randomized.py`, `wcc_fused.py` | `min_by`'s per-group accumulator and the reverse expansion joins over the round history |

## 9. Work division and status board (2026-10-01)

Fable keeps this board, the report and the plan current; Codex (the other
agent, working from Morrobay with the Linux gate) owns the items marked
Codex and appends status to `codex-to-codex.md` under the item ids below.
Status values: `open`, `running`, `done <commit or evidence path>`,
`blocked <reason>`. Nothing is `done` without a commit or an evidence path.

| Id | Item | Owner | Status | Evidence |
|---|---|---|---|---|
| A0 | LDBC Graphalytics `test-*` graphs with their reference outputs as Pecan's correctness oracle (BFS, PageRank, SSSP, WCC), before any timing (Sem, remark 13) | Codex | **done**: 16 of 16 supported cases pass against the official references (CDLP and LCC recorded unsupported) | `work/morrobay-pecan-typed-results`, `docs/reviews/pecan-ldbc-semantics-2026-10-01/README.md`, commit `cec260d6` |
| A1 | graphframes-rs at the benchmark branch built in the gate image; his settings read from `main.rs` | Codex | **done**: `b4da56d` built with `--release --locked` in the gate image, 16 CPUs, 32 GiB; settings audited: seed 42, 16 partitions, 30 GiB FairSpillPool, sort-merge preferred; his PageRank is thresholded delta Pregel and his shortest paths are per-landmark unweighted hops, so they are not LDBC's fixed-step power PR and weighted SSSP | `work/morrobay-sem-review`, `docs/reviews/sem-review-morrobay-2026-10-01/A1/` |
| A2 | Pecan in local mode on cit-Patents in the A1 container, against his binary there, two ABBA blocks, n = 4 per engine, full oracle on every cell | Codex | **done**: Pecan over graphframes-rs, launch to exit: randomized WCC (B9) **3.77**, frontier BFS against his directed hops **2.51**, min-label WCC against his randomized 9.49; engine PSS 2.2 against 1.5 GiB for WCC, equal for BFS; PageRank not compared (contracts differ until B11) | `docs/reviews/sem-review-morrobay-2026-10-01/A2/README.md` |
| A3 | the same in process-cluster mode: driver and two workers, 10 GiB pool each, 16 partitions | Codex | **done**: randomized WCC **4.74**, BFS **2.99**, min-label 12.1; so cluster mode costs 19 to 27% over local at this size | `.../A3/README.md` |
| A4 | the decision table of Stage A applied, written into section 4 | Fable | **done, then corrected on 2026-10-02**: the first reading (the controller's actions per round are the gap) does not hold. Repeated on Capitola with release builds, Pecan is 1.37 (WCC) and 1.28 (PageRank) times graphframes-rs, against 3.77 on the gate; the gate slows Sail 2.8 times more than his binary. A5 decides why | section 4, "Stage A result" and "Stage A repeated on Capitola"; `reviews/sem-review-capitola-2026-10-02/A2-local/README.md` |
| A5 | why Sail was slower on the gate than on Capitola relative to graphframes-rs | Codex (gate), Fable (reading) | **done: it was the VM.** The same Pecan cell (randomized WCC, cit-Patents, 16 partitions, snapshot on, oracle passing) takes 51.8 s launch to exit in the gate VM and **8.86 s natively on the same machine**; round 1 takes 23.2 s and 1.46 s. Not the build (release, LTO, confirmed by receipt and by ELF inspection) and not the hardware (plain C baseline: within 2 times of Capitola on one thread, equal on 16). The benchmark VM is retired; benchmarks run on bare macOS, a VM is for Linux build testing only (the user's instruction). Open as A6: the three matched contrasts natively on Morrobay, both engines, inputs in place | `reviews/sem-review-morrobay-2026-10-01/A5/NATIVE-COMPLETION.md`, `native-profile-receipt.json`; `reviews/sem-review-capitola-2026-10-02/host-baseline/README.md` |
| A6 | the matched contrasts natively on Morrobay: Pecan `9f0aa7d2a` against graphframes-rs `b4da56d`, randomized WCC, PageRank (`pregel_delta` against his `page-rank`, 10 steps, tolerance 0.01) and BFS (frontier against his `shortest-path`), cit-Patents and graph500-24, inputs in place and one snapshot-on WCC pair, ABBA, oracle on every pair; optionally with `-C target-cpu=native` for both | Codex | **done, natively on Morrobay** (bare macOS, release builds, 16 workers, inputs in place, two G/P/P/G blocks, every output audited against the full oracle; 48 of 48 calls qualified). Pecan over graphframes-rs, ratio of medians, with the same script as the Capitola run: cit-Patents WCC **1.42**, PageRank **1.16**, BFS **0.71**; graph500-24 WCC **0.80**, PageRank **0.86**, BFS **0.86**. Capitola gave 1.17, 1.14, 0.65 and 0.80, 0.95, 0.87, so the two hosts agree: Pecan is behind on the small sparse graph's WCC and ahead on the large graph and on BFS. A separate 70-call campaign on the earlier controller `d0e4e422a`, with a timer that also counts Pecan's Python imports, gives 1.94, 1.69, 1.67 and 0.89, 0.99, 1.09; snapshot-on WCC pairs 2.05 and 1.11. The `target-cpu=native` variant was not run. No VM was recreated; why the VM was slower stays unexplained by the user's choice | `reviews/sem-review-morrobay-2026-10-01/A5/FableExact/README.md`, `A5/NATIVE-MATCHED.md`, `PageRank/README.md` |
| B1 | keyless repartition toggle (`repartition_checkpoints`) | done | `6ae2e43a9` | integration |
| B2 | write receipt from the host's graph-utils service instead of read-back counts | Fable | **parked**: on Capitola what this removes (counts and schema round trips) is small: a count over a written stage returns in under 10 ms and all twelve tail rounds together take 0.26 s of a 4.1 s call. Reopen only if A5 shows round trips cost much more on the gate | `reviews/sem-review-capitola-2026-10-02/A2-local/README.md` |
| B3 | round scalars folded into the state write | Fable | **parked**: on Capitola what this removes (the per-round count) is small: a count over a written stage returns in under 10 ms and all twelve tail rounds together take 0.26 s of a 4.1 s call. Reopen only if A5 shows round trips cost much more on the gate | `reviews/sem-review-capitola-2026-10-02/A2-local/README.md` |
| B4 | fused contraction as the default | Fable | superseded by B9: `wcc_fused.py` removed, `randomized_fused` is an alias | |
| B5 | tail cutover for the contraction | Fable | **parked**: on Capitola what this removes (the twelve tail rounds) is small: a count over a written stage returns in under 10 ms and all twelve tail rounds together take 0.26 s of a 4.1 s call. Reopen only if A5 shows round trips cost much more on the gate | `reviews/sem-review-capitola-2026-10-02/A2-local/README.md` |
| B6 | checkpoint every k rounds | Fable | **parked**: on Capitola what this removes (per-round writes in the tail) is small: a count over a written stage returns in under 10 ms and all twelve tail rounds together take 0.26 s of a 4.1 s call. Reopen only if A5 shows round trips cost much more on the gate | `reviews/sem-review-capitola-2026-10-02/A2-local/README.md` |
| B7 | trusted immutable Parquet inputs: no snapshot rewrite (Sem, "why rewrite the inputs") | Fable; gate measurement Codex | **done; measured on Capitola, not on the gate**: reading the inputs in place takes the graph500-24 WCC from 30.4 to 20.3 s, the BFS from 14.2 to 8.5 s, and cit-Patents WCC from 5.0 to 4.05 s. Since graphframes-rs reads its inputs in place, a matched comparison uses `snapshot_inputs=False`. **Measured natively on Morrobay by Codex**: cit-Patents WCC, six cells, one ABBA block, full oracle: in place over snapshot 0.912 (8.8% less elapsed; pairs 0.906 and 0.918). `GraphAlgorithms(snapshot_inputs=False)` reads the caller's vertex and edge frames in place and writes nothing for the inputs; the default keeps the snapshot, because a caller's frame is not known to be immutable. The benchmark cells take `--no-snapshot-inputs` and record `pecan_snapshot_inputs` in the receipt. A test asserts no staging write for the inputs and identical components either way. Stage A put the snapshot at about 5 s of the 48 s public algorithm on cit-Patents; the paired in-place cell is Codex's to run | `querygraph/sail` `pecan` `b522bf3a9`; `reviews/sem-review-morrobay-2026-10-01/B7/README.md` |
| B12 | traversal: no second copy of the edges before the first round | Fable | **done**: BFS and SSSP wrote the snapshotted edge table again as their adjacency (with a constant weight column for BFS). A directed traversal now uses the snapshot, or the in-place input, as its adjacency. graph500-24 BFS on Capitola: 19.7 to 14.2 s with the snapshot, 8.5 s in place, against 9.7 s for graphframes-rs; 191 Pecan and 443 harness tests pass | `querygraph/sail` `pecan` `d0e4e422a` |
| B8 | `unionByName` against `array(struct, struct)` + explode, paired, on Sail (Sem, remarks 11, 23a); he wants numbers | Codex | **done (protocol completed with failures)**: array and explode over union, median elapsed, in the gate VM. cit-Patents: adjacency 1.02, representatives 1.12, min-label round 1.12. graph500-24: representatives 1.00 (blocks 1.02 and 0.99); adjacency and min-label round withheld, because four warmups ran out of the 32 GiB container. 40 of 60 cells qualified, 44 attempted, 16 skipped by policy. So explode is never faster than union on Sail in these shapes, and the answer to Sem's remark is: keep the union | `reviews/sem-review-morrobay-2026-10-01/B8/README.md` |
| B10 | PageRank in the Pregel paper's and GraphX's static form (`method="pregel"`), optional normalization (Sem, remarks 18, 21) | Fable | **done**: tests equal to `power` without dangling vertices, same order with them | `work/wcc-affine` `f3b3ef8fc` |
| B11 | PageRank delta as GraphX's vertex program: no certificates, no extra relation (Sem, remarks 20, 21) | Fable; gate measurement Codex | **done and measured natively under the matched contract (A6)**: `method="pregel_delta"`, read from graphframes-rs `pagerank.rs` and `pregel.rs` at `ba2fdd8`: rank and delta start at the reset probability, a vertex whose delta exceeds the tolerance sends delta/out_degree, a vertex adds (1 - reset) times what it received and takes that gain as its delta; all vertices send in step 1. No dangling term, no residual, no certificate, no vertex count; the state is the only relation a step writes, so a step is one job. A fixed budget counts nothing (his `max_iter > 0`); `vote_to_halt=True` counts the active vertices after each step and stops at zero (GraphX, and his `max_iter = 0`). `normalize=True` divides by the total, as he always does. **Parity against his binary** on Capitola, 200,000 vertices and 2,000,000 edges with sinks, isolates, parallel edges and loops, tolerance 0.01: largest relative difference in any rank 1.0e-15 after 10 fixed steps, 9.1e-16 run to the halt, and both halt after 16 steps. One deliberate difference in execution, not in the result: he checkpoints the aggregated messages and then the state, two writes a step; Pecan writes the state once. The certified `method="delta"` is unchanged and remains the LDBC-contract form with an error bound; whether to retire it is a decision for the review, not made here | `querygraph/sail` `pecan` `0d1ef2ca3`; 191 Pecan tests |
| B9 | randomized WCC as in the paper: affine ids, plain `min`, inverse maps once at the end (Sem, remarks 14 and 17) | Fable; gate measurement Codex, inside A2 | **measured in A2 and A3; the correctness defect Codex found is fixed in `b522bf3a9`**: a hashed component label could equal an isolated vertex's original id (three-vertex counterexample in `A2/RUN04-PREFLIGHT.md`), merging two components. An isolated vertex now takes its own image under the composition of all rounds' maps, a bijection, so every label lives in one id space and distinct components keep distinct labels. The gate's counterexample is a regression test, with and without canonical labels. cit-Patents has no isolates, so A2 and A3 stand; Codex reran the signed-isolate witness natively on `b522bf3a9`: it passes with and without canonical labels, and the `known_mismatch` is lifted (`reviews/sem-review-morrobay-2026-10-01/B9/README.md`). On Capitola against a native debug host: 183 Pecan and 443 harness tests pass. Earlier note: 176 Pecan and 337 harness tests pass; paired debug-build control on Capitola (2M vertices, 4M edges, identical labels): new 24.2 and 23.8 s against old fused 29.5 and 27.8 s and old randomized 39.3 and 31.0 s, about 30% less per round | `querygraph/sail` `pecan` `b522bf3a9` (first form `7475dfc03`) |
| C1 | local mode on one host: guide and harness | Fable | **done for the guide**: `WHICH-PATH.md` has a section "One host: local mode, not a local cluster" with A2 and A3's ratios (a local cluster costs 19 to 27% more on cit-Patents and adds no capacity) and its limit (one graph). The harness default is left alone on purpose: every measured cell passes `--mode` explicitly, and a changed default would silently change older scripts | `docs/WHICH-PATH.md` |
| C2 | fixed cost of one distributed job at P = 4, 16, 32 | Codex | **qualified native cold/warm campaign; phase attribution pending**: 60 fresh two-worker servers, 20 pairs per P, 120 complete 4,096-group answers. Actual two-stage workload task counts are 8/24/40 at P4/16/32, and both workers execute each action. Paired cold/warm p50 ratios are 0.445/0.529/0.593; setup, AnalyzePlan bootstrap and worker readiness are separate. The 30 GiB software pool sum is not an OS-32-GiB envelope. Operator telemetry is empty; numeric spill, PSS and full planning/serialization/scheduling/stream/teardown attribution remain unqualified. The fresh observer source still needs its exact gates and executed controls | [C2 evidence](reviews/sem-completion-2026-10-03/C2/README.md); [completion report](reviews/sem-completion-2026-10-03/README.md) |
| C3 | host pool reservations, native quotas and measured nonpool headroom inside the resource profile | Codex | **qualified native admission/refusal/release control; whole-process envelope open**: actual server ledger admits a 128 MiB native lease into a 192 MiB greedy pool, refuses a second lease with the typed allocation cause, returns the first reservation to zero, then admits and releases a distinct replacement lease. All three degree rows pass. Participating native used/peak/staged counters are distinct from the prepaid host reservation. Transport buffers, operator spill, measured nonpool headroom, unique physical memory and OS-32-GiB/PSS accounting remain unqualified; configured pool sums cannot close them | [C3 evidence](reviews/sem-completion-2026-10-03/C3/README.md); [portable counters](reviews/sem-completion-2026-10-03/C3/portable-accounting.json) |
| C4 | compact tuple MIN and min_by, with the actual aggregate factories and full answers | Codex | **qualified native plan probe and full-Struct factory allocation controls**: the original two fresh ordered cells retain four complete 4,096-group answers, both workers, Partial/FinalPartitioned aggregates and P4 exchanges. Separate six fresh single-thread controls at 4,096/100,000 groups use the same nonnull three-field Struct as payload and complete key. At 100,000 groups compact MIN requests 5 allocations versus ordered min_by 6,500,283; additional live requested bytes are 4,194,304/155,815,680 and cumulative requested bytes 8,126,464/622,458,304. Complete evaluate/state/merge checks pass. Exact standalone source ef5fc415 passes the actual committed native run04 Rust gates with unchanged binary and reused six controls. Failed run01 forced cleanup/unknown exit and pre-command run03 GIT_PAGER refusal remain retained. Requested System counters and clocks including size sampling do not qualify original WCC Long/Long min_by, MiMalloc, native pools, physical memory or whole-graph speed | [C4 plan evidence](reviews/sem-completion-2026-10-03/C4/README.md); [C4 factory controls](reviews/sem-completion-2026-10-03/C4-allocation/README.md); historical compact/generic Struct MIN evidence remains distinct |
| D1 | sorted-Parquet write cost at 16M, 64M, 268M rows, paired (Sem, remarks 12, 23b); Vortex capability as an alternative format | Fable; Vortex control Codex | **done for the paired write study; Vortex capability qualified**: Capitola release/local measurements at all three sizes retain sorted-write/plain-write ratios 3.4 to 6.3 and the costlier declarable bucketed writer. The current Vortex native format is unregistered; the separately registered Python reader passes all six full typed comparisons, while its writer returns NOT_IMPLEMENTED. No Vortex checkpoint writer or format performance comparison is claimed. The unsorted declared-checkpoint cluster control is D2; sort followed by checkpoint is excluded because upstream #2722 returns wrong results | [D1 study](reviews/sem-review-capitola-2026-10-02/D1/README.md); [Vortex evidence](reviews/sem-completion-2026-10-03/Vortex/README.md) |
| D2 | declared layout measured in process-cluster mode, natively under the benchmark policy | Codex | **qualified native unsorted checkpoint control**: P4/16/32 times 20 repetitions, 180 strict SortMergeJoin rounds and 420 full answer actions, with both workers. Path/path, checkpoint/path and checkpoint/checkpoint retain exactly 2/1/0 hash exchanges below the join, while two runtime sorts remain in every join. Median checkpoint/path ratios are 0.973/0.979/0.948 and both-checkpoints/path ratios 0.905/0.808/0.717; high-percentile regressions are retained. This measures repartition(P,key).checkpoint() on native9f, not sort preservation, the legacy sorted Nutmeg17 reader or a whole graph algorithm speedup. | [D2 evidence](reviews/sem-completion-2026-10-03/D2/README.md) |
| E0 | a proper Pregel (Sem, remarks 15, 22, 23c): PageRank and SSSP first, plans and microbenchmarks on cit-Patents, kgs and wiki-Talk; checkpoint alternatives and a Rust extension as an exploratory option | Fable (loop), both (programs and controls) | **done for the requested first programs and three-dataset native controls**: the existing loop carries GraphX dynamic PageRank, new distance-only weighted SSSP and graphframes-rs-style landmark shortest paths, with fixed-budget and vote-to-halt modes. Actual client source f2b297fc passes all 227 Pecan tests on the pinned native9f release runtime. Eleven full native controls pass, including two meaningful cit-Patents traversal cells from source 5795784; kgs weighted SSSP also matches every official reference row. All 104 pre-write plans are retained. PageRank uses normalized ten-round GraphX delta semantics, not the official fixed-step LDBC power contract. Parquet checkpoint execution is measured; native9f persist/unpersist are no-ops and checkpoint StorageLevel is unsupported. CDLP, K-Core and further programs were explicitly postponed by Sem’s written checklist; Rust-side Pregel remains the speculative option, not a delivered feature | [E0 evidence](reviews/sem-completion-2026-10-03/E0/README.md); [Sem’s checklist](SEM-QUESTIONS-2026-10-01.md); Sail source f2b297fc, runtime 9f0aa7d2a |
| F0 | native-only CSR build from `edges.parquet` as the ingest floor (Sem, remark 9 of his first review) | Fable; native rerun Codex | **done on Capitola; rerun natively on Morrobay by Codex** (four cells, counts and checksum guards pass; `reviews/sem-review-morrobay-2026-10-01/F0/README.md`, which withholds timing prose and keeps the raw clocks). Capitola: a 200-line Rust program (Parquet in, i64 ids kept, dense u32 targets under a checked bound, u64 arc offsets, parallel count and fill, a checksum against the edge list). Median of five, 4 threads, undirected adjacency: cit-Patents **0.42 s**; graph500-24 (260M edges, 521M arcs) **7.7 s**, of which read 1.8, id mapping 1.4, build 4.4; 4.7 s on 10 threads; peak RSS 8 GiB. With sparse ids (binary search instead of a direct table) graph500-24 takes 19 s on 4 threads. Beside Banda's about 28 s and 650 s and icebug's 186 s on 4 cores: the conversion is seconds, so Banda's ingest time is our conversion (Utf8 ids and the string map, the canonical sort, the projection's passes, the FFI crossing), which is F1. Limits: an M1 Max laptop with a warm cache, not the gate; in-memory, not out of core; no neighbour sort | `docs/reviews/sem-review-capitola-2026-10-02/F0/README.md` |
| F1 | S1, S2/`asStaged`, S3 toward the ingest budget, i64 contract kept; Sem's reference (remarks 24, 25): icebug builds the CSR for graph500-24 in 186 s on 4 cores with i64 indices | Fable | **done and released**: Grust 0.24.0 "Tanaid" is on crates.io (20 crates, tag `v0.24.0` at `d2668ec7`, `main`). Int64 identity on `from_arrow_batches` (direct table or sorted lookup, parallel fill, same first error at every width), an 8-byte-an-edge columnar edge table (breaking: `edges()` returns a view), 4-byte edge slots, the id map built on first use, work totals pinned to 0.23.0's. Projection of graph500-24 on Capitola: **119 s and 13.4 GiB (0.23.0, text ids) to 3.1 s with 8 workers, 14.8 s with none, and 4.65 GiB**. Gates on the release source `1cfd03be` with Rust 1.99.0: every gate passed on macOS arm64 and on arm64 Linux (container on Capitola); the exact released tag `d2668ec7` also passed the x86-64 Linux confirmation on Morrobay: `ci-local: PASSED every gate at d2668ec on Linux x86_64 in 3904s` ([receipt](reviews/sem-review-morrobay-2026-10-01/F1/Linux-v024/README.md)). The controller cleanup return code is recorded separately. The first Linux run failed at Clippy on toolchain drift (Rust 1.99 against `async-trait` 0.1.89), fixed in the lockfile. Extension side committed on the fork: staging option `ids` = `int64` (off by default: it changes the order of integer ids from text to numeric) and `NUTMEG_WORKERS`, pins at `=0.24.0`. Open: the book's live publish on FirstPair, which waits for the user | `grust` `v0.24.0`; `querygraph/sail` `work/nutmeg-int64-identity` `4b88c8fb4` (not yet on `pecan`); `benchmarks/projection-ingest/README.md`; `reviews/sem-review-capitola-2026-10-02/F1/README.md` |
| F2a | the baseline for F2 in Sem's format: current Banda (`asStaged`) on graph500-24 and cit-Patents in the A1 container, end to end with Parquet in and Parquet out, his four phases, one call and three calls on the same staged graph; beside his icebug receipts | Codex, after B8 | **done natively with explicit profiles**: released 0.24.0 lazy baseline (8 series, 16 full outputs), plus the bounded client-Arrow/chunk-checkpoint four-phase profile (4 series, 8 full outputs), one and three calls on both LDBC graphs. The profiles have different phase/transport boundaries; no fabricated exclusive split of the lazy baseline | [Native baseline](reviews/sem-review-morrobay-2026-10-01/F2a/Native024/README.md); [completion report](reviews/sem-completion-2026-10-03/README.md) |
| F2 | Banda as the resident CSR with explicit limits; one and three calls on the same staged graph, Parquet in/out and four phases (Sem, remarks 26, 27) | Fable; native controls Codex | **done for native measured amortization and explicit phase profiles**: released 0.24.0 lazy baseline has eight series and 16 full outputs on cit-Patents and graph500-24; the bounded client-Arrow/chunk-checkpoint four-phase profile has four series and eight full outputs. One and three calls share the staged graph within each series. The two profiles have different transport and phase boundaries, so no exclusive four-phase split is invented for the lazy baseline. Native quota admission/refusal is separately qualified by C3. A universal graph-size fit threshold, automatic fallback and a whole-process 32 GiB memory envelope are not implied by these two inputs | [F2 evidence](reviews/sem-completion-2026-10-03/F2/README.md); [released lazy baseline](reviews/sem-review-morrobay-2026-10-01/F2a/Native024/README.md); [C3](reviews/sem-completion-2026-10-03/C3/README.md) |
| R1 | typed Pecan, no validation, contract in `AGENTS.md` and README (Sem, remarks 3 to 6) | done | `7145d107c`, `6ae2e43a9`, `5aa755b9`, `71fc8c90` | |
| R2 | reading map for Sem (remarks 1, 2, 7, 8) | done | `5513e29c` | `pecan-code-and-harness.md` |
| R3 | every Sem remark recorded with status | done | `71fc8c90` | section 8 |
| X1 | Argentea two-host scale-24 failure: first cause with worker-side logging, then one rerun | Codex | **native two-host admission in progress; SSH restored**: source preparation and one-host controls do not qualify the requested two-host reproduction, cause or rerun. No remote execution is claimed | [completion limits](reviews/sem-completion-2026-10-03/README.md); [historical stream evidence](reviews/sail-stream-experiments-2026-09-30/RESULTS.md) |
| X2 | the original relational stream loss; preserve its cause separately from later failures | Codex | **native diagnostics controls qualified; twelve historical causes unexplained**: native reference BFS passes every one of 4,096 rows; a distinct explicit 1 MiB pool control has ten typed task-execution allocation records preceding matching worker task reports inside pre-shutdown byte windows. Both workers execute both controls; actual waits, source closure and lock release pass. These are not the historical scale-24/25 replay, and there is no global first-fault ordering proof. The original twelve zero-memory-event h2 cases still have no typed initiating cause: three logs have no ERROR, nine first ERROR records follow session removal. Failed native admission/directory/capacity attempts01–03 and uncertain write state are retained | [X2 review](reviews/sem-completion-2026-10-03/X2/README.md); [historical cases](reviews/sem-completion-2026-10-03/X2/historical-cases.json); [retained failures](reviews/sem-completion-2026-10-03/X2/retained-failures.json) |

Where Sem's contributions go, corrected 2026-10-01 after his first pull
request: **documents, questions and checklists go to `querygraph/grust`**,
under `docs/`, on `work/proposal-v5`, because the review's documents live in
grust and nothing of the kind may sit in a Sail tree, upstream or fork. Only
a change to Pecan's code itself goes to the fork, as a pull request against
`pecan` on `querygraph/sail` (kept at the current Pecan tip, today
`9f0aa7d2a`), because that is where `examples/extensions/graph-algorithms`
lives; that directory is fork-only and is not part of any upstream merge.

Order: A0 first, because no timing is reported on an unverified answer;
then A1 to A3, which decide between B and E; B9, B7, D1 and F0 run on
Capitola meanwhile because they need no gate time. The shared host rules
of `AGENTS.md` apply: one heavy job on the gate at a time, Codex's.

## 7. Limits

The initial document contained no paired run. The later C4 traversal control
and large compact replay are now recorded above; they do not establish WCC
speed or a general safe memory envelope. Section 2 preserves observations with
different contracts and hosts; it deliberately supplies no cross-system ratio.
Stage A can narrow mechanisms only with additional component controls. Local
qualification does not establish multi-host scaling. The earlier no-OOM stream
loss remains separate from the confirmed OOM replay and later diagnostic work
in [RESULTS.md](reviews/sail-stream-experiments-2026-09-30/RESULTS.md).
