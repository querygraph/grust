# Sem review progress and remaining work

Recorded UTC: 2026-10-01T05:17:30.889000+00:00

This accounts for the September 30 work against every stage of
[Sem's second review](../../SEM-REVIEW-2.md). **We have not yet demonstrated
fast end-to-end WCC on cit-Patents or Graph500.** The successful compact-runtime
SSSP experiments remove a real implementation cost, but do not answer that
WCC question. Sem's concern remains an engineering problem to resolve.

The recorded cit-Patents WCC cells were Pecan randomized 312 s, Pecan min-label
500 s, and Grenada 397/566 s. The 729 s entry was power PageRank. Sem reported
4.71 s for WCC. These historical cells differ in host, input and execution
boundary, so they do not supply a matched ratio. Those differences are reasons
to run the control, not a demonstrated explanation of the large gap. There is
no evidence that hundreds of seconds are an unavoidable Sail or Connect cost.

## What the day established

| Result | Evidence and practical limit |
|---|---|
| A costly grouped traversal accumulator was replaced. | At 100,000 groups, retained requested heap fell from about 204.8 MB to 4.19 MB, a 48.8-fold component reduction. This is grouped `min(struct(...))`, not every aggregate or WCC's `min_by`. |
| The change works in real worker execution. | The small Pecan SSSP frontier comparison passed all six trials and their physical-output scans. Across the four measured cells, compact/original median time was 0.6078 and sampled execution PSS was 0.8389. These are descriptive ratios on shared Morrobay, with host paging present. |
| A large SSSP cell now completes within the existing limit. | Pecan scale 24 DeltaStar passed its certificate and physical-output scan at a 33.05 GiB container peak, with zero OOM events. The original replay OOMed at 100 GiB; its failed run is not a completed timing or uncapped-memory denominator. |
| Several native allocations and lifetime costs were reduced. | CSR scratch/lookup, unused BFS/WCC inboxes, raw-input lifetimes, Done propagation, and SSSP candidate-buffer reuse have focused source gates and allocation controls. The later native changes were not loaded by the large compact replay. Their combined Linux and multi-host benefit remains unmeasured. |
| A proposed controller change did not improve its tested workload. | The SSSP overflow-action fusion had a 1.0894 median elapsed ratio for Pecan and 1.1359 in one Grenada pair. Those slower outcomes are retained. They are not measurements of randomized-fused WCC. |
| Four matched-input WCC pilot cells passed. | The official cit-Patents pair was hashed; vertex uniqueness/nulls and endpoint validity were checked for 3,774,768 vertices and 16,518,947 edges. Duplicate edges were not counted. All four local/two-worker original/fused cells passed every vertex label against the 3,627-component reference. Fused/original elapsed ratios were 0.7816 locally and 0.7795 in cluster mode; peak-memory ratios were 1.1984 and 1.1104. These are single samples on shared Morrobay, with instrumentation and no external CLI control; the existing large-graph certificate remains partial. |

Sources: [accumulator control](STRUCT-MIN-ALLOCATION.md),
[six-cell worker comparison](host-pair-publication/README.md),
[large replay and buffer reuse](COMPACT-REPLAY-AND-SSSP.md),
[all delivered fixes and slower cells](RESULTS.md),
[official inputs](sem-review2/cit-patents-input-verification/receipt.json),
[full WCC reference](sem-review2/cit-patents-wcc-reference/README.md),
[four-cell WCC results](../sem-wcc-pilot-2026-10-01/RESULTS.md).

## Every proposed change and its status

“Implemented” below does not imply a measured performance improvement.

| Review item | What is done | What remains |
|---|---|---|
| A — common inputs, output contract and timer | Audited Sem's CLI/settings/timer; pinned official cit-Patents bytes; built a complete WCC oracle; identified incompatible PageRank and shortest-path contracts. | Repeat the completed four-cell diagnostic pilot in controlled order and run the external CLI control. Report preparation, algorithm, export and verification separately; preserve the complete public-call boundary. |
| B1 — omit keyless checkpoint repartition | Opt-in `repartition_checkpoints=False` is committed and tested with unit and local SQL controls; default unchanged. | Real GraphUtils local/worker qualification and paired WCC measurements, including skew, file counts and actual exchanges. |
| B2 — writer receipt replaces redundant counts | Defined the required committed immutable generation and uncertain-write ownership boundary. | Implement bounded host receipts and fault tests. Footer existence alone cannot confirm that all writers finished. |
| B3 — carry required round scalars with state | Checked recurrence and commit requirements. | Implement state/scalar output consistently. Dangling mass must be available for the next recurrence; ordinary Parquet footers do not contain its sum. |
| B4 — explicitly measure randomized-fused WCC | All four original/fused local/worker WCC cells passed the full reference; fused elapsed ratios were lower and peak memory higher in both modes. Component and small worker controls also exist. | Repeat the full WCC comparison, isolating instrumentation and ordering effects before changing any default. |
| B5 — contract the small tail with fewer checkpoints | Identified the long nearly-empty tail in old receipts. | Implement a bounded experiment retaining seeded representatives, reverse expansion, isolates and iteration/cancellation semantics. The tail is not proved removable. |
| B6 — checkpoint less often | Documented source-generation lifetimes and plan-growth risks. | Implement bounded intervals with retained ancestors, a fallback, and measured recomputation, memory and plan size. |
| B7 — use already validated immutable inputs | The official input is available and independently validated. | Add a borrowed immutable-input entry point with file identity and ownership. The current public call still rewrites and validates input; an unchecked trust flag is insufficient. |
| C1 — local versus process-cluster | The four-cell pilot used common input, CPU/container limits and nominal total pools. Cluster/local elapsed ratios were 1.4463 original and 1.4423 fused in these single shared-host samples. | Repeat and isolate components: pool division, logging volume, scheduling, transport and host activity remain confounded. |
| C2 — quantify distributed job overhead | Worker plan/status controls exist for correctness. | Force real exchanges at P=4/16/32; measure planning, jobs/stages/tasks, stream setup/teardown and cold/warm latency. No 100 ms result exists. |
| C3 — enforce the resource envelope | Identified pool overcommit and confirmed OOM replays; the capacity runs have hard container caps and admission checks. | Repeat the four passing cells under the 32 GiB WCC profile, support separate driver/worker budgets, and measure pool, native, transport, spill and total memory together. Pool sums are not an RSS cap. |
| C4 — compact tuple MIN, then `min_by` | Tuple MIN has component and real traversal qualification. The `min_by` probe exposes separate accounting and per-batch work. | Optimize and measure `min_by` separately; preserve exact signed-i64 priority/tie semantics. The tuple-MIN success cannot be assigned to WCC. |
| D — preserve useful checkpoint layout | The earlier declared-layout read-side work exists, with scoped plan checks. | Measure cluster-mode benefit and the write/read tradeoff at 16M, 64M and 268M rows. No new large write-cost curve was produced today. |
| E — put an iterative controller on the server | Identified the library entry and the missing explicit Sail job-submission boundary. | Decide from the component measurements whether to prototype it. A library call inside an extension does not automatically distribute its internal actions. Prove submission, remote placement, cancellation and ownership. |
| F — make Banda ingestion economical | Argentea lifetime/allocation fixes landed; Banda representation bounds were reviewed. These fixes establish no Banda ingest improvement. | Run native-only cit-Patents read/decode/map/CSR construction, then compare complete cold and reused calls. The proposed one-second CSR and five-second ingestion budgets are unqualified. |

The [detailed response](SEM-REVIEW-2-RESPONSE.md) contains the source checks.
[B1's qualification record](pecan-checkpoint-repartition/README.md) states its
remaining controls; [the `min_by` probe](min-by-probe/README.md) and
[worker control](wcc-fused-worker-plan/README.md) establish their narrower scope.

## Corrections and answers that remain important

Sem supplied the input catalog, CLI/library entry, settings and timer; another
round of questions to him is unnecessary before the WCC pilot. The official
Parquet edges use `source`/`target`, while our controller expects `src`/`dst`.
A lazy column alias preserves the original bytes and IDs. Rewriting a different
graph or assuming dense IDs would invalidate that input control.

The full-domain generated Graph500 and LDBC Graphalytics inputs are distinct.
Dividing our reached count by LDBC's vertex count does not measure our own
isolates, and the different edge counts cannot be attributed solely to removed
duplicates without counting them on the same input. The earlier review's
stronger inference is corrected in its source section. This does not alter the
recorded traversal result.

Keep signed-i64 IDs at every public boundary. A checked dense internal index
does not permit truncating an external ID. Arc offsets require independent
wide bounds: symmetrization can exceed a narrow arc range while vertex indices
still fit. Banda's current narrow-offset path lacks a wide fallback; Argentea
already has i64 targets and usize offsets.

The 16 CPU / 32 GiB profile passed these cit-Patents cells; that does not
establish large-graph capacity. Sem's spill pool is FairSpillPool; our existing harness uses a
greedy pool. Effective settings and physical plans must accompany the result.
Native reservations and queued transport memory need their own accounting.

## Plan for the next working day

1. Repeat the completed original/fused, local/two-worker cit-Patents WCC pilot
   in controlled order and run the matched external CLI control. Separate plan
   capture from timing; test sampling/logging overhead and record host paging
   deltas. Retain full oracle checks, setup/round/export breakdown and memory.
   The first four cells diagnose where to look; they do not establish parity.
2. From that profile, qualify B1 and the existing fused variant separately.
   Attack measured setup and round costs with B7 and committed writer receipts;
   keep their ownership/failure semantics. Measure aggregation and scheduling
   independently where the profile points. Do not assume fewer Python calls
   means fewer physical jobs or a faster completed query.
3. Requalify WCC on scale 24, then 25 and 26, retaining failures and exact
   answers. The separate prepared Pecan/Grenada SSSP capacity cells remain
   useful, but are not a substitute for this WCC progression.
4. Qualify distributed placement, then fixed-input strong scaling and
   proportional-input weak scaling. Record the busiest worker's arcs/work,
   queued bytes, network, driver load and checkpoint-store throughput. A single
   fast node does not demonstrate distributed scaling.

## Current preparation and storage handoff

The [four-cell WCC pilot](../sem-wcc-pilot-2026-10-01/RESULTS.md) is complete.
Every cell checked all 3,774,768 vertex labels, converged in 19 rounds and exited
cleanly with no OOM. Peak container memory ranged from 2.293 to 4.010 GiB.
Contraction consumed 60–75% of the public timer, while setup and final expansion
also remained substantial. High system CPU is unexplained; the unequal debug
log volume and memory sampling require controls before assigning a cause.
Eleven offline controls and independent source review preceded execution.
The initial host-wrapper attempt stopped before container creation because the
default macOS Python lacked required hashing/tar APIs; all actual cells used
explicit `/usr/local/bin/python3.12`. The failed attempt remains recorded.

[Disk cleanup is complete](../morrobay-disk-cleanup-2026-10-01/README.md).
Selected disposable Cargo intermediates and five exited build containers were
removed after inventory and log preservation. Benchmark-volume free space rose
by 56.46 GiB to 91.02 GiB; host free space rose by 13.89 GiB around its separate
cache prune. Those boundaries must not be added together. Dataset manifests,
runtime, native library and WCC helper hashes matched; 1,199 other files and
artifacts passed metadata checks. Results and source were outside the deletion
scope; cleanup did not perform a full content audit of those trees.

The user offered `/Volumes/Apo` with 6 TB free. The morning check found it
mounted but with only 60.90 GiB free; it is not admitted as the expected extra
working capacity. When that space is available,
verify the mounted filesystem and free space, expose it to the Linux VM,
measure the resulting read/write path, and place new dataset/checkpoint/spill
namespaces there. Record that storage change as a new profile; do not silently
compare its I/O timings with the current volume. Existing input identities and
results remain pinned.

The four complete WCC cells and phase breakdown are linked above. The next
delivery should isolate one measured optimization at a time. The guarded
[Pecan scale-25 / Grenada scale-24/25 SSSP capacity supervisor](../graph500-next-scale-2026-10-01/README.md)
was launched after the pilot and fresh admission. Pecan scale 25 passed its
distributed certificate and clean closure at a 73.73 GiB peak, with 62
iterations and no OOM. Its independent physical-output audit is pending.
Grenada scale 24 is running; scale 25 remains conditional. Scale 26 and larger remain
conditional on exact answers and measured memory/storage admission. The plan
above is ordered work, not a promise that all B–F implementations finish in one
day.

## What scale 26 and above require

Scale 26 of our generated edge-factor-16 graph has 67,108,864 declared vertices
and 1,073,741,824 input tuples, or 2,147,483,648 arcs when expanded undirected.
It is a legitimate engineering target. Sem's reported scale-26 WCC result
used about 20.5 GiB RSS with a 28.8 GiB work-directory peak; that shows why
bounded, spill-capable relational execution merits testing. It is an external
observation on another input/profile, not our measured capacity requirement.

Pecan's 33.05 GiB scale-24 SSSP peak extrapolates to 66.1 GiB at scale 25 and
132.2 GiB at scale 26 **only if it scales linearly**. Those estimates are neither
measurements nor WCC estimates. Scale 25 is worth trying under the existing
100 GiB cap, and its new observed peak was 73.73 GiB. The earlier linear
planning estimate was low. Scale 26 needs fresh memory and disk admission from actual phase
peaks; adding memory alone would leave redundant jobs and traffic unresolved.

The completed [disk cleanup](../morrobay-disk-cleanup-2026-10-01/README.md)
increased free benchmark-volume space from 34.57 to 91.02 GiB. A new large
dataset plus checkpoints/spill and output still needs fresh admission; that
volume cannot admit a 120 GiB work-directory footprint. The planned external
volume may supply working storage once mounted and measured. Existing evidence
is retained.
For multi-host runs, also remove or bound full-state copies, unbounded shuffle
queues, owner skew, quadratic completion traffic and the 64-partition client
ceiling. [The cluster review](CLUSTER-PREPARATION.md) identifies those tasks.

The current pilot budgets—two data jobs per round, a one-second round floor,
five-second setup, and 30-second cit-Patents WCC on a qualified host—remain
unachieved. The next report should add controlled repeats and isolated
component experiments to the four-cell breakdown, retaining regressions and
unexplained outcomes.

Status updated UTC: 2026-10-01T14:03:21.436919+00:00
