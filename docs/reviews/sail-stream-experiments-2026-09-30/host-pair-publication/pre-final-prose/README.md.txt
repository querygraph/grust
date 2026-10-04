# Six-cell shared-host runtime comparison

Recorded UTC: 2026-10-01T02:12:07.401119+00:00. All six planned trials are closed. Each producer passed its recorded reference comparison and parent-tree check; all six later physical-output scans passed. This folder is a local publication package, not another benchmark run. The outcomes and raw samples below are retained for **descriptive ratios on shared Morrobay**, not dedicated-host absolute performance results.

## Fixed experiment

A is Sail runtime `2894a962076d3cc404dd72ec736ebeb9239901f6` (binary SHA-256 `40a78182a420152e8e3651f9cdb38a4196eaf8bc7aead092d10e258a17ac3497`). B is compact-accumulator runtime `56194b170155301ba91077f0ba3df31fe2c78b6b` (binary `5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec`). Both use the original controller `3a9028057c6c6c5034492845926fc4bc18f9626f` and installed native package from `ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73`. Runtime/binary and unique output identifiers change; the dataset, protocol and configured resources match. These runs do not load the later Argentea lifetime/buffer changes or the later Parquet-reader mitigation.

The immutable bounded traversal fixture has 16,384 vertices, 529,723 directed edge records, degree parameter 32, seed 42, source 0, and integer weights 0–15 stored as Float64. This is Pecan SSSP `frontier`, not Graph500 or DeltaStar. Every cell converged in 24 iterations. The producer compared all 16,384 unique rows with its independent BFS/heap-Dijkstra reference and checked the parent tree. The supplemental physical scans found 16,384 unique valid IDs, one valid source, one unreachable row and zero invalid distance/null/parent/hop/domain counters in every cell. The collected diagnostic archives omit the result Parquet payloads; the later reader receipts bind those payload hashes and before/after identities. No second Dijkstra computation was performed during this audit or packaging.

The hard envelope was 8 CPUs at VM cpuset 16–23, 12 GiB container memory without additional swap, 1024 PIDs, two worker processes, four logical partitions, four threads, and 16 task slots **per worker** (32 total). A greedy 3 GiB Sail pool is configured per process; it is not a shared RSS cap. Native quota is configured at 256 MiB. Server/worker counts, protocol, logging and 120-second HTTP/2 keepalive setting are pinned in the [original plan](../host-pair-16k/pair16k-20260930201356-plan.json) and [six configurations](../host-pair-16k/HANDOFF.json).

The order is unmeasured warmup A, warmup B, then measured A–B–B–A, each in fresh processes. Checksum reads warm the OS page cache; no cache flush occurs. Preflight checks source/binary/native/dataset identities, same VM boot, no current Docker container and at least 12 GiB free in the target volume. Those are observations, not a host lock or continuing capacity reservation. During each trial, the runner samples Docker siblings every 2 seconds; no sibling or inventory error was recorded. Processes outside that Docker context and activity between observations remain possible. The [launch preparation](launch-preparation/receipt.json) and [recorded sequence](study/sequence.json) preserve exact commands, admission, settings and outcomes.

## All six retained samples

The timer below is the producer's `end_to_end_seconds`: input DataFrame handles through the completed full result-Parquet write. It excludes server startup, later correctness validation, hashing and cleanup. These raw shared-host timer observations support the ratio arithmetic; they are not standalone speed ratings. Warmups are shown and excluded from all comparisons.

| Cell | Role | Runtime | Retained timer (s) | VM steal | Producer / physical |
| --- | --- | --- | --- | --- | --- |
| 1 | warmup | A | 17.821729663 | 0.0% | pass / pass |
| 2 | warmup | B | 11.092783022 | 0.0% | pass / pass |
| 3 | measurement | A | 17.973570568 | 0.0% | pass / pass |
| 4 | measurement | B | 11.187822541 | 0.0% | pass / pass |
| 5 | measurement | B | 11.078957127 | 0.0% | pass / pass |
| 6 | measurement | A | 18.661242065 | 0.0% | pass / pass |

Adjacent measured A/B timer ratios are **1.606529823** (cell 3 / cell 4) and **1.684386161** (cell 6 / cell 5); their geometric mean is **1.644997447**. The separate ratio of median B time to median A time is 0.607803837. These are different summaries of two measured samples per runtime, not confidence bounds, an isolated runtime effect or a general speedup guarantee. [Unrounded metrics and boundaries](metrics.json), [original summary](study/summary.json).

Memory values below use MiB=2^20 bytes. PSS/RSS are maxima of sampled sums across visible container processes during `execute`; RSS counts shared pages per process. The cgroup columns are cumulative high-water marks through execution and through container completion, including charged cache. They are neither per-worker RSS nor exact unsampled execution peaks. Cgroup values need not match summed process PSS/RSS because their accounting boundaries differ.

| Cell | Execute PSS (MiB) | Execute RSS (MiB) | Cgroup through execute (MiB) | Cgroup lifetime (MiB) |
| --- | --- | --- | --- | --- |
| 1 | 970.546 | 1111.215 | 958.484 | 958.484 |
| 2 | 820.456 | 960.242 | 754.848 | 760.121 |
| 3 | 1012.358 | 1150.898 | 1024.422 | 1024.422 |
| 4 | 836.952 | 974.371 | 728.379 | 730.547 |
| 5 | 848.826 | 989.617 | 777.680 | 777.680 |
| 6 | 997.120 | 1135.934 | 994.773 | 994.773 |

For the four measured cells, median B/A is 0.838913334 for execute PSS, 0.858824896 for execute RSS, 0.745870686 for the cgroup peak through execution, and 0.746944366 for the lifetime cgroup peak. No cell or metric is dropped: for example, B cell 5 uses more sampled PSS/RSS and higher cgroup peaks than B cell 4 despite its slightly smaller timer. The table preserves that variation. This fixture does not establish the effect at larger sizes or under different skew, partition counts or concurrency.

Execution-window cgroup CPU-counter deltas and sampler counts are retained for each cell. The configured 50 ms sampler interval is a sleep after a scan; observed median scan-start gaps are about 80 ms, with every per-cell range in `metrics.json`. The six full JSONL sampler streams are retained.

| Cell | CPU usage (µs) | User (µs) | System (µs) | Periods | Throttled periods / µs | Execute samples |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 76093249 | 20488393 | 55604856 | 179 | 0 / 0 | 215 |
| 2 | 45158057 | 5986462 | 39171595 | 111 | 0 / 0 | 134 |
| 3 | 76404563 | 20178601 | 56225962 | 179 | 0 / 0 | 217 |
| 4 | 46040607 | 5956600 | 40084007 | 112 | 0 / 0 | 136 |
| 5 | 45489809 | 6035854 | 39453954 | 110 | 0 / 0 | 134 |
| 6 | 75051655 | 20744810 | 54306844 | 187 | 0 / 0 | 228 |

All six cgroups record zero `max`, `oom` and `oom_kill` events, zero additional swap, and clean producer/container closure and removal. Whole-Linux-VM, full-trial steal is 0.0% in every cell. Steal is not measured over the execution timer alone, the container or its cpuset. Zero steal, zero observed Docker siblings and low dispersion cannot establish a dedicated or quiet physical host.

## Host pressure and interpretation

These are absolute whole-macOS-host counters from each cell's **before** snapshot, not cell-attributed increments:

| Before cell | Swapins | Swapouts | Compressions | Decompressions | Occupied compressor pages |
| --- | --- | --- | --- | --- | --- |
| 1 | 2491667224 | 2497847722 | 696449092 | 632630452 | 2048012 |
| 2 | 2491671316 | 2497847722 | 696449092 | 632636533 | 2051821 |
| 3 | 2491674320 | 2497847722 | 696449092 | 632640714 | 2054712 |
| 4 | 2491676620 | 2497847722 | 696449092 | 632645265 | 2056783 |
| 5 | 2491678727 | 2497847722 | 696449092 | 632649058 | 2058710 |
| 6 | 2491680510 | 2497847722 | 696449092 | 632652751 | 2060173 |

From the first warmup's before-snapshot to the post-sequence closure snapshot, Swapins increased 21,965, Swapouts 0, Compressions 50,908 and Decompressions 119,580; occupied compressor pages increased 20,761. Pageins increased 5,826,495 and Pageouts 3,012. These are counter/page counts, **not physical bytes transferred**. They include all six trials, gaps and the collection interval. The [host-after capture](outer/host-after.json) was taken after the sequence and before physical scans; its [attribution record](outer/host-after-attribution.json) expressly does not supply per-cell closure deltas. Existing host swap use and changing paging/compression counters remain a confound even though the VM reports zero steal and container swap.

The comparison can report these matched outcomes and descriptive shared-host ratios. It cannot attribute every difference solely to the runtime change, establish dedicated-host timings, extrapolate to scale 24 or explain historical stream failures. It is one-host execution with two worker processes, not multi-host strong/weak scaling. The large compact replay and its physical check have their own evidence boundary, and their timings are not a denominator for this experiment. Earlier unfavorable controller experiments also retain their own outcomes; they are not replaced by this runtime comparison.

## Later physical checks and portable evidence

All six physical scans began only after the complete original sequence and collection. They ran serially, with one CPU, 2 GiB memory without additional swap, no network, read-only graph/bundle mounts and a separate evidence output. The retained Python 3.12.14 / PyArrow 21.0.0 / NumPy 2.5.3 reader ran as UID/GID 0:20 with all capabilities dropped; its new host-owned 501:20 evidence directories use 0770. Every checker exited 0, recorded no OOM, and was removed after state capture. The [serial receipt](physical-execution/evidence/serial-receipt.json) keeps original benchmark outcomes/ratios separate from supplemental physical qualification. Physical checking establishes finite/nonnegative/null/domain metadata properties, not independent shortest paths or parent-edge chains.

The complete [sealed request bundle](sealed-physical-bundle/pair-requests.json) is copied byte-identically, including every producer receipt, full per-cell integrity audit, exact configurations, code and all-six closure context. Its operational absolute paths remain historical; publication does not authorize relaunch. [Original helper/verifier controls](../physical-output-audit/README.md) and [collection-verifier boundary](../host-pair-collection-audit/README.md) are already tracked. V4 preparation sources, controls and root review are copied here; the prior 18-control pair preparation and paused, ungated v3 draft remain distinct. The exact sources and 26-control v4 receipt are under [physical-preparation-v4](physical-preparation-v4/preparation.json). No failure was relabelled a pass: the independent closure auditor's first timestamp-equality assumption failure and its exact source/log are retained alongside the corrected audit.

The [independent closed review](independent-review/receipt.json) verifies all producer archives/member bytes, configs/runtime/native/dataset/protocol identities, sampler-derived metrics and actual checker lifecycle/payload-identity receipts. The [copy receipt](copy-receipt.json) lists every original source, copied hash and omission. Six diagnostic tar files are omitted with all four member payloads retained. The outer transfer tar repeats the collected study, including those six redundant tars; the copied study and omission inventory replace it. Each omitted archive's exact hash and source location remain recorded. Original tar bytes are still available at those local source paths. This package does not claim to reconstruct tar headers byte for byte. The original result Parquet files remain on the retained remote volume and were neither copied nor read for packaging.

[manifest.json](manifest.json), `self-audit.json` and `FREEZE.json` bind the public set and its checks. Run `python3 -B verify.py --root /path/to/host-pair-publication` for local hash/JSON/link/bundle checks; it performs no remote action or workload. Historical receipts retain their original absolute source paths as provenance, while the copied evidence and current links are local. Packaging preserves originals, does not alter the frozen compact snapshot, and makes no commit or publication claim.
