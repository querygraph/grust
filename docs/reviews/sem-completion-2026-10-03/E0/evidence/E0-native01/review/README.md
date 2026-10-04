# E0 native Pregel programs: closed artifact review

Reviewed at 2026-10-03T19:01:43.343236+00:00; source `f2b297fc8443221891ce5f4afe88f955ed125b38` (tree `3395c493c98edebc4ca137ea81d7fa25dadd8979`), native runtime `9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3`.

All nine original cells completed, wrote all original vertex IDs, passed independent full physical-output oracles, and closed every owned process group. The supervisor actually waited the owner; source/binary/input hashes remained unchanged and the heavy-job lock was released. The two cit-Patents traversal cells from source 1 are **correctness controls with trivial reachability**, not representative traversal speed. Two fresh source-5795784 cells also passed the same full oracles and lifecycle checks; their representative measurements are below.

## Measurements

Each value is one fresh local native cell, in seconds. These are unpaired measurements; no engine speed ratio or variance claim follows from this table.

| Dataset / program | Parquet in → complete Parquet export | Client launch → actual wait | Rounds | Reachable / vertices | Max hops | Full oracle |
|---|---:|---:|---:|---:|---:|---|
| cit-Patents / pagerank | 3.672817 | 5.199536 | 10 | — | — | independent |
| cit-Patents / sssp | 0.447945 | 2.000393 | 1 | 1 / 3,774,768 | — | independent |
| cit-Patents / landmarks | 0.435764 | 1.996530 | 1 | 1 / 3,774,768 | 0 | independent |
| kgs / pagerank | 4.179019 | 5.730146 | 10 | — | — | independent |
| kgs / sssp | 5.031130 | 6.560525 | 20 | 819,249 / 832,247 | — | independent + official SSSP |
| kgs / landmarks | 1.947280 | 3.472015 | 10 | 819,249 / 832,247 | 9 | independent |
| wiki-Talk / pagerank | 2.339292 | 3.980935 | 10 | — | — | independent |
| wiki-Talk / sssp | 1.274699 | 2.788670 | 7 | 2,354,316 / 2,394,385 | — | independent |
| wiki-Talk / landmarks | 1.292756 | 2.845038 | 7 | 2,354,316 / 2,394,385 | 6 | independent |

The original input sizes are cit-Patents 3,774,768 vertices / 16,518,947 edges; Kgs 832,247 / 17,891,698; wiki-Talk 2,394,385 / 5,021,410. Kgs is undirected, so all three programs see 35,783,396 directed adjacency rows after mirroring. Parallel edges and self-loops retain their original multiplicity. Each cell exported four Parquet files; footer totals agree with the full oracle for every original vertex.

## Sources, orientation and output contracts

- **cit-Patents:** directed, unit-weight SSSP, root-selected source 1; explicitly neither an official source nor the prior A2/A5 source. Only that vertex is reachable. Both programs stop after one superstep and final zero frontier. The separate representative campaign uses source 5795784, matching the existing A2/A5 BFS default.
- **Kgs:** undirected, source 239044 from its official properties. Weighted SSSP uses the original DOUBLE `weight`; landmark hops ignore weight. Both reach 819,249 vertices; 12,998 are unreachable. The hop program has maximum distance 9 and stops after 10 supersteps, including its terminal zero-frontier step. Weighted SSSP takes 20 improving-frontier rounds; this is not a hop-depth measurement.
- **wiki-Talk:** directed, source 2 from its official BFS properties; unit-weight SSSP is an explicit adaptation. Both traversal programs reach 2,354,316 vertices, leave 40,069 unreachable, and have maximum hop distance 6. Seven supersteps include the terminal zero-frontier step.

SSSP returns `id: BIGINT, distance: DOUBLE?`: zero at the source and NULL for unreachable vertices. It is explicitly distance-only; parent/hops are not this method’s contract. Landmark output is `id: BIGINT, dist_<source>: INT`, with INT32 MAX (2147483647) for unreachable vertices. Distances are **from** the landmark (`to_landmarks=False`). The oracle checks the full domain and physical types, exact integer distances, reachability sentinels, original IDs and all output rows.

## PageRank contract

All PageRank cells run `pregel_delta`, reset probability 0.15, tolerance 0.01, normalized output, exactly ten supersteps, `vote_to_halt=False`. The program implements the graphframes-rs / GraphX dynamic delta recurrence: initial rank and delta are 0.15; all vertices send in the first step, then only vertices whose new delta exceeds 0.01 send; each receives 0.85 times the summed messages and adds that delta to its accumulated rank. There is no dangling redistribution. The final rank vector is divided by its total.

This is distinct from the official LDBC fixed power-iteration PageRank contract, including Kgs’s official ten-iteration reference. We did not compare these outputs to the official power PageRank files. The independent NumPy recurrence compares every vertex under the actual delta contract. The largest absolute difference is 2.03e-19 on cit-Patents, 1.49e-16 on Kgs and 2.47e-18 on wiki-Talk; all normalized sums are within 1.8e-15 of one. Fixed-budget outputs declare `converged=None`; the vote-to-halt traversal outputs declare `converged=True`.

## Full official weighted Kgs SSSP

The official reference SHA256 is `a4b9a0b03760ed45786ef3d676b16f26526fbe580fdf20538081731fcd714933`. A separate reviewer audit aligned all 832,247 unique physical output IDs with the full reference, checked source 239044 at distance zero, and matched all 12,998 official +Infinity entries to physical NULL. All 819,249 finite distances match at rtol=atol=1e-12. Maximum absolute error against the official file alone is 8.881784197001252e-16; 739,464 finite rows are numerically identical and 79,785 differ only within that roundoff bound. This supplements the separate independent heap-Dijkstra oracle.

The timed pipeline is 5.031130 seconds; client launch through actual exit wait is 6.560525 seconds. The independent plus official oracle process then takes 30.767894 seconds, **after** the engine and client have exited. Verification time is separate from the reported pipeline and client times.

## Setup and clock boundaries

Each cell has a fresh native macOS Sail server and Python client. Declared local execution parallelism, Tokio workers and Rayon threads are all 16. `snapshot_inputs=False` and `repartition_checkpoints=False`: source Parquet is read in place and state writes do not add a keyless repartition. The runtime is the preserved native release binary, 150,472,188 bytes, SHA256 `ee80ac3cf9d028639561f3cf32435985192719d629807fcf6a368324fa84946e`. Python 3.12.6 / PySpark 4.0.1 run the exact committed E0 package and helper source. The server’s greedy pool is configured at 30 GiB. There is no OS CPU or RAM cap and no cache purge between cells.

The inner clock starts before constructing the source Parquet relations, includes algorithm setup, all iterative state materialization/read-back, plan generation, normalization or convergence checks and the complete final Parquet export. It stops immediately after the export returns; result-lease cleanup and session stop follow outside that inner clock. Creating the Spark session and GraphAlgorithms’ lease/ping setup occurs before this clock. The outer clock includes Python startup/imports, connection/setup, cleanup, session stop and actual client wait; it excludes separate server startup/readiness. SHA inventory and all correctness oracles are outside both clocks. Source selection is lazy, so `algorithm_and_export_seconds` excludes only the cheap relation construction, not the ensuing input reads.

## Write, checkpoint and count actions

The following counts are derived from the exact executed program’s call sites and the recorded superstep count. They count primary synchronous DataFrame actions; they are not observed engine scheduler job IDs. No `DataFrame.checkpoint()` call occurs. Each staging checkpoint is instead a full Parquet write followed by a read-back relation/schema check. Control/lease, metadata, schema and explain RPCs are not counted as data jobs.

| Dataset / program | State/public staging writes | Final export writes | Vote counts | Normalization aggregate | Snapshot writes | Pre-write plans |
|---|---:|---:|---:|---:|---:|---:|
| cit-Patents / pagerank | 12 | 1 | 0 | 1 | 0 | 10 |
| cit-Patents / sssp | 3 | 1 | 1 | 0 | 0 | 1 |
| cit-Patents / landmarks | 3 | 1 | 1 | 0 | 0 | 1 |
| kgs / pagerank | 12 | 1 | 0 | 1 | 0 | 10 |
| kgs / sssp | 22 | 1 | 20 | 0 | 0 | 20 |
| kgs / landmarks | 12 | 1 | 10 | 0 | 0 | 10 |
| wiki-Talk / pagerank | 12 | 1 | 0 | 1 | 0 | 10 |
| wiki-Talk / sssp | 9 | 1 | 7 | 0 | 0 | 7 |
| wiki-Talk / landmarks | 9 | 1 | 7 | 0 | 0 | 7 |

For T supersteps the staging writes are: one initial vertex-state write + T updated-state writes + one public-output projection/normalization write. There is then one independent export write. PageRank has one normalization scalar aggregate, no eager vertex count and no per-round halt count. SSSP and landmark programs have one active-row count after each updated state write. This makes Kgs weighted SSSP 23 writes plus 20 halt counts; its ten-step landmark program 13 writes plus ten halt counts; ten-step PageRank 13 writes plus one normalization aggregate. All programs record one pre-write plan per superstep.

## Observed physical plans

All 76 original supersteps have their actual pre-write updated-relation physical plans preserved. Every one contains:

- One partitioned inner hash join between participating source state and adjacency, then a message aggregation with Partial and FinalPartitioned `AggregateExec`.
- One partitioned left hash join that merges the aggregated messages back into the full vertex state.
- Four `RepartitionExec` nodes, all hash partitioning to 16, and a participation `FilterExec` on the source state scan.
- Three Parquet `DataSourceExec` nodes for directed datasets, or four plus a `UnionExec` for Kgs’s mirrored adjacency.

There is no SortExec in these step plans and no separate edge/message Parquet materialization call in the program. The edge-side join and aggregation are within the same state-write relation. The plans still contain an edge join and intermediate messages; the evidence does not establish that O(E) intermediate work or hash repartitioning disappears. A small active frontier is not universal: Kgs weighted SSSP reaches a peak improving frontier of 687,955 vertices and wiki-Talk reaches 1,423,197. The later frontiers shrink to zero, and their entire sequences are retained in the JSON review.

An explain of a relation does not include the final writer sink, execution metrics, successful row counters or engine job IDs. The receipt has no scheduler/job telemetry, so this report does not equate a physical RepartitionExec with an observed distributed shuffle job, or claim one engine job per round as a measured fact. It does establish one state write call per round and the physical adjacency-join/aggregate/update topology.

## RSS and lifecycle

Owned server/client/oracle RSS is sampled every 500 ms. The largest simultaneous sampled server+client sum among these nine cells is 1.899 GiB (Kgs SSSP); its server alone reaches 1.788 GiB. Oracle processes are sampled separately after engine exit. These are sampled observations, not hard peaks or proof that an arbitrary graph fits the configured pool. Every cell has actual server/client/oracle waits, absence of all their process groups, no forced kill and no lifecycle errors. The server’s expected SIGTERM exit is recorded as -15. The campaign supervisor’s actual owner wait returns zero.

## Preserved evidence

- `../receipt.json`, `../wait.json`: campaign process identity, closure, qualified-cell count and complete source/input/output inventory.
- `../support/source-admission01.json`: native binary/source pins, all nine exact commands, selected environment and source gates.
- `../raw/<dataset>-<program>/cell/receipt.json`, `events.json`, `pre-write-relation-step-*.txt`, `result/*.parquet`: producer clocks, full frontier trace, physical plans and physical outputs.
- `../raw/<dataset>-<program>/oracle.json`, `oracle.log`, `rss-500ms.jsonl`: separate full oracle and process RSS.
- `closed-cells.json`, `closed-cells.csv`: portable review index containing all nine clocks, output/schema totals, action counts, plan nodes, per-plan hashes, frontiers, reachability and sampled RSS.
- `official-sssp-audit.json`: independent official-only Kgs SSSP precision/reachability audit.

The native engine integration test of the committed core previously passed all 227 tests; root schedules the complete engine test again on the actual final helper/source commit before publication. This review does not substitute for that final source gate.

## Representative cit-Patents source 5795784

The independent follow-up campaign `../../E0-native-cit-active02` uses the existing A2/A5 BFS source 5795784, explicitly nonofficial, with the same native binary, exact source, in-place inputs, sixteen workers, full plans and post-exit independent oracles. All 3,774,768 vertex rows are exported, including 3,648,470 unreachable vertices. Both programs reach 126,298 vertices, with maximum hop distance 13. Fourteen supersteps include the terminal zero-frontier step.

| Program | Parquet in → complete export (s) | Client launch → actual wait (s) | Reachable | Max hops | Rounds | Oracle error |
|---|---:|---:|---:|---:|---:|---:|
| Unit-weight SSSP | 2.875913 | 4.406529 | 126,298 | 13 | 14 | 0 |
| One landmark | 2.941558 | 4.549221 | 126,298 | 13 | 14 | 0 |

The active frontiers are identical: `770, 3542, 9506, 17854, 26095, 27836, 21460, 11834, 5014, 1782, 482, 112, 10, 0`. Each program has sixteen staging writes, one final export write, fourteen halt counts, no snapshot write and fourteen preserved pre-write plans. Each plan has two hash joins, four hash repartitions to sixteen, Partial/FinalPartitioned aggregation, one participation filter and three source scans, matching the original directed cells. The largest sampled server+client sum is 1.353 GiB for SSSP and 1.222 GiB for landmarks.

The follow-up campaign closes all groups with actual waits, unchanged source/input/output hashes and a released lock. Its review index and full physical-output summary are in `../../E0-native-cit-active02/review/closed-cells.{json,csv}`. The original source-1 receipts remain preserved and are not replaced. `representative-cells.csv` combines the three PageRank rows with the six meaningful traversal rows; `all-cells.csv` retains all eleven rows with campaign and source identity.
