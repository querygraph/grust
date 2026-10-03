# C2: sixty fresh native process-cluster pairs

Independent artifact review passed all 60 closed cells and all 120 full, 4,096-row answers. There are 20 fresh servers at each P=4,16,32, ordered P4/P16/P32 within each repetition. Each server executes the same query twice after the session metadata bootstrap and both worker registrations. The query reads 32,768 edges in eight Parquet fragments, repartitions by the signed original source id, then computes per-source MIN(payload) and COUNT. Every complete answer and BIGINT schema matches the independently preserved fixture reference.

These are shared-host descriptive observations. The review publishes ratios; absolute p50/p95 clocks and raw memory measurements remain in `private-clocks.csv` and `private-quantiles.csv`. Quantiles interpolate at `(n-1)*q`; 20 observations per P do not establish a machine-independent tail guarantee.

## Timing findings

| Observation | P4 | P16 | P32 |
|---|---:|---:|---:|
| Paired cold/warm collect ratio, p50 | 0.445 | 0.529 | 0.593 |
| Paired cold/warm collect ratio, p95 | 0.482 | 0.571 | 0.642 |
| Cold collect p50 relative to P4 | 1.000 | 1.293 | 1.674 |
| Cold collect p95 relative to P4 | 1.000 | 1.298 | 1.676 |
| Warm collect p50 relative to P4 | 1.000 | 1.093 | 1.252 |
| Warm collect p95 relative to P4 | 1.000 | 1.094 | 1.256 |
| AnalyzePlan bootstrap p50 / p95 relative to P4 | 1 / 1 | 1.010 / 1.011 | 1.003 / 1.010 |
| Worker-readiness p50 / p95 relative to P4 | 1 / 1 | 0.970 / 1.002 | 1.007 / 0.982 |
| Pre-data setup p50 / p95 relative to P4 | 1 / 1 | 0.993 / 0.998 | 0.999 / 0.994 |
| Child launch through actual wait p50 / p95 relative to P4 | 1 / 1 | 1.003 / 1.007 | 1.016 / 1.022 |

The second collect was slower than the first in this experiment. Increasing P increases these small workload action clocks while leaving bootstrap and readiness broadly similar. This does not identify a scheduler or network cause: the helper records neither complete server phase intervals nor a cache-purged first read.

The cold action is the first **dataset data action**, after `spark.version` AnalyzePlan session bootstrap and explicit two-worker readiness. The collect clock spans RPC submission through return of all rows. The helper reads `frame.schema` before the clock and normalizes/compares rows afterward. Warm is a separate job on the same frame/server; no cache flush, result-cache assertion, or OS cold-read assertion is made. Pre-data setup is an aggregate receipt interval covering admission, startup and readiness. Launch-through-wait additionally includes Python imports, evidence queries and shutdown; it is not an algorithm clock.

## Actual execution topology

| P | Workload jobs per action | Stages per action | Scan tasks | Shuffle aggregate tasks | Total tasks per action | Worker slots each |
|---|---:|---:|---:|---:|---:|---:|
| 4 | 1 | 2 | 4 | 4 | 8 | 2 |
| 16 | 1 | 2 | 8 | 16 | 24 | 8 |
| 32 | 1 | 2 | 8 | 32 | 40 | 16 |

Every workload job and task succeeds. Executed worker logs show the shuffle and aggregate on both registered workers; system job/stage/task snapshots agree with the independently counted task attempts. The scan stage uses `min(8,P)` partitions and the downstream keyed aggregate uses P. Evidence queries create additional metadata jobs; those are excluded from this table using each action's server-log byte interval and corresponding job ids. The execution stages' shuffle input links and observed worker plan show a real exchange.

## Resource scope

The native process cluster has one driver and two workers. Each process is configured with a greedy 10-GiB software pool, 16 Tokio threads and 16 Rayon threads. Thus the three software pools sum to 30 GiB, but this is neither a 32-GiB OS limit nor a 16-thread total host budget. The Python client and native processes use OMP/OpenBLAS/MKL thread setting 1.

The 500-ms sampler preserves per-PID `ps` RSS, `proc_pid_rusage` resident size and physical footprint, including the producer/client, driver and workers. The private CSV stores maxima for each role and the largest simultaneous sampled sum. These are sampled process observations, not PSS, unique system memory, a hard peak or complete per-phase attribution. Shared memory can be counted more than once. Fifteen P32 physical calls failed with `errno=3: No such process` (nine driver observations and six worker observations); those absent physical values are retained explicitly and cannot be treated as measured zero. P4/P16 had no such observer errors. The independently sampled `ps` RSS remains available for those sample rows.

Relative simultaneous sampled-sum p50/p95 against P4 are: RSS P16 1.004/1.040, P32 1.085/1.552; resident P16 0.997/0.933, P32 1.047/1.124; footprint P16 1.005/0.929, P32 1.009/0.943. Physical-call omissions and the sampling interval limit interpretation.

All 60 telemetry snapshots are empty. The retained server/worker logs expose configuration thresholds but no observed numeric `peak_mem_used`, `mem_used`, `spilled_bytes` or `spill_count` values. Therefore no operator memory/spill measurement or zero-spill claim is justified. `full_server_phase_attribution=False` and `physical_memory_accounting_qualified=False` remain explicit.

## Provenance and closure

Runtime/Python graph source is `9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3`, tree `950e3ebed76a37c454ed50c950b9b74087fcc60d`. Native release binary SHA256 is `ee80ac3cf9d028639561f3cf32435985192719d629807fcf6a368324fa84946e` (150,472,188 bytes); v04 helpers are frozen in `../freeze01.json`. Every cell's before/after source and input pins are equal. Each server and oracle process has an actual completed wait, owned process groups are absent, no forced cleanup is needed, and the serial owner releases its locks. The detached supervisor actually waits for the owner and observes its group absent.

`review.json` binds all 60 producer/oracle receipts and preserved log byte identities. `ratios.csv` contains all published p50/p95 relative metrics. Raw evidence is under `/Users/alexy/src/grust-benchmark-runs/sem-completion-20261003/c2-main01`; owner, oracle and supervisor evidence is under `../c2-main01`.
