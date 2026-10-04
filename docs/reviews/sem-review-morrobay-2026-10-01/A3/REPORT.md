# A3 completed receipt comparison

Status: **complete_item_receipt_evidence**. Observed UTC: 2026-10-02T00:01:46.668214+00:00.

Ratios on Morrobay, a shared host. Raw seconds are diagnostics; no absolute-performance, multihost, generic signed-ID WCC, rebuilt-runtime, PageRank or larger-scale claim.

Retained host, bootstrap, container and cell JSON only; no Parquet/input reads, no independent rehash of payloads, no raw-sampler recomputation, no Docker or engine execution. Correctness is retained full-oracle receipt evidence, not a new physical-output audit.

## Shared-host ratios

Pecan / graphframes; values have three significant digits. All raw seconds below are diagnostics. graphframes is always a single CLI process with 16 workers; A3 changes Pecan to driver + two workers on one host.

| Execution class | Algorithm | Median ratio | ABBA block 1 | ABBA block 2 | Qualification |
| --- | --- | ---: | ---: | ---: | --- |
| process-cluster | wcc-randomized | 4.74 | 4.73 | 4.77 | 4 measured samples/engine; both ABBA blocks |
| process-cluster | wcc-min-label | 12.1 | 12.2 | 12.0 | 4 measured samples/engine; both ABBA blocks |
| process-cluster | bfs | 2.99 | 2.92 | 2.99 | 4 measured samples/engine; both ABBA blocks |

n=4 per engine and two ordered blocks limit inference. Warmups are retained and excluded from statistics; failed and known-mismatch cells cannot qualify. Input cache warming is retained in the boundary. No phases are subtracted.

## Every planned cell

| Run ID | Role / block | Host / cell | Diagnostic launch→exit seconds | Engine sampled PSS GiB | Final container lifetime peak GiB | Guest steal | Qualified |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| a3-wcc-randomized-01-graphframes | warmup / — | passed / passed | 14.0209 | 1.5114 | 1.76956 | 0 | True |
| a3-wcc-randomized-02-pecan | warmup / — | passed / passed | 63.609 | 2.41148 | 2.99494 | 0 | True |
| a3-wcc-randomized-03-graphframes | measured / 1 | passed / passed | 13.3149 | 1.48157 | 1.74119 | 0 | True |
| a3-wcc-randomized-04-pecan | measured / 1 | passed / passed | 66.7914 | 2.39443 | 2.95218 | 0 | True |
| a3-wcc-randomized-05-pecan | measured / 1 | passed / passed | 61.9199 | 2.47855 | 3.04531 | 0 | True |
| a3-wcc-randomized-06-graphframes | measured / 1 | passed / passed | 13.8605 | 1.46164 | 1.71587 | 0 | True |
| a3-wcc-randomized-07-graphframes | measured / 2 | passed / passed | 13.1083 | 1.52375 | 1.7812 | 0 | True |
| a3-wcc-randomized-08-pecan | measured / 2 | passed / passed | 60.9996 | 2.44853 | 3.02315 | 0 | True |
| a3-wcc-randomized-09-pecan | measured / 2 | passed / passed | 67.5952 | 2.3439 | 2.90543 | 0 | True |
| a3-wcc-randomized-10-graphframes | measured / 2 | passed / passed | 13.8174 | 1.44732 | 1.70431 | 0 | True |
| a3-wcc-min-label-01-graphframes | warmup / — | passed / passed | 13.2627 | 1.4974 | 1.75289 | 0 | True |
| a3-wcc-min-label-02-pecan | warmup / — | passed / passed | 164.17 | 3.36299 | 3.97539 | 0 | True |
| a3-wcc-min-label-03-graphframes | measured / 1 | passed / passed | 13.3077 | 1.45669 | 1.71538 | 0 | True |
| a3-wcc-min-label-04-pecan | measured / 1 | passed / passed | 163.363 | 3.66425 | 4.16745 | 0 | True |
| a3-wcc-min-label-05-pecan | measured / 1 | passed / passed | 164.068 | 3.47403 | 4.02282 | 0 | True |
| a3-wcc-min-label-06-graphframes | measured / 1 | passed / passed | 13.5461 | 1.42664 | 1.68249 | 0 | True |
| a3-wcc-min-label-07-graphframes | measured / 2 | passed / passed | 13.1632 | 1.445 | 1.70371 | 0 | True |
| a3-wcc-min-label-08-pecan | measured / 2 | passed / passed | 160.216 | 3.24526 | 3.87771 | 0 | True |
| a3-wcc-min-label-09-pecan | measured / 2 | passed / passed | 162.335 | 3.70345 | 4.22034 | 0 | True |
| a3-wcc-min-label-10-graphframes | measured / 2 | passed / passed | 13.6829 | 1.49501 | 1.75187 | 0 | True |
| a3-bfs-01-graphframes | warmup / — | passed / passed | 8.31688 | 0.949787 | 1.2001 | 0 | True |
| a3-bfs-02-pecan | warmup / — | passed / passed | 25.8442 | 1.83849 | 2.42024 | 0 | True |
| a3-bfs-03-graphframes | measured / 1 | passed / passed | 8.63935 | 0.959162 | 1.21016 | 0 | True |
| a3-bfs-04-pecan | measured / 1 | passed / passed | 26.3504 | 1.91285 | 2.4506 | 0 | True |
| a3-bfs-05-pecan | measured / 1 | passed / passed | 25.7964 | 1.98557 | 2.41884 | 0 | True |
| a3-bfs-06-graphframes | measured / 1 | passed / passed | 9.25914 | 0.987242 | 1.23763 | 0 | True |
| a3-bfs-07-graphframes | measured / 2 | passed / passed | 8.66831 | 0.984293 | 1.23451 | 0 | True |
| a3-bfs-08-pecan | measured / 2 | passed / passed | 26.0643 | 1.93606 | 2.44841 | 0 | True |
| a3-bfs-09-pecan | measured / 2 | passed / passed | 26.0299 | 1.94642 | 2.43399 | 0 | True |
| a3-bfs-10-graphframes | measured / 2 | passed / passed | 8.77982 | 0.975416 | 1.22681 | 0 | True |

## Phase and memory boundaries

The comparison timer spans engine launch through completed exit, including input, snapshots, algorithm, export and engine cleanup. Parent identity hashing, full oracle and final ownership checks are outside. JSON retains each cell's exact recorded boundary, supervisor phases, Pecan phases/rounds, coverage, steal and host admission observations. Pecan input_snapshot is nested inside public_algorithm: these durations are not additive. External phase breakdown and rounds are unavailable when the CLI emits no structured receipt; they are never inferred.

Sampled engine PSS excludes supervisor/PID 1. Whole-container execute PSS includes them. Cgroup peaks include page cache and prior identity reads; the final lifetime peak also includes parent oracle/final observation. Peaks and sampling coverage remain separate.

## Retained attempts and prerequisite phases

- compatibility04: compatibility; host passed_with_known_mismatch, producer passed_with_known_mismatch; accepted closure True; known mismatches ['b9-signed-isolate'].
- stage04: stage; host passed, producer passed; accepted closure True; known mismatches [].
- validation04: validation; host passed, producer passed; accepted closure True; known mismatches [].
- Prior archive: /Volumes/Apo/graph-tests/results/sem-review-20261001/A2-run01
  - stage01: stage; host error, producer passed. Phase failures are distinct from engine-cell failures.
  - validation01: validation; host error, producer error. Phase failures are distinct from engine-cell failures.
- Prior archive: /Volumes/Apo/graph-tests/results/sem-review-20261001/A2-run02
  - stage02: stage; host passed, producer passed. Phase failures are distinct from engine-cell failures.
  - validation02: validation; host error, producer None. Phase failures are distinct from engine-cell failures.
- Prior archive: /Volumes/Apo/graph-tests/results/sem-review-20261001/A2-run03
  - compatibility03: compatibility; host error, producer error. Phase failures are distinct from engine-cell failures.
  - stage03: stage; host passed, producer passed. Phase failures are distinct from engine-cell failures.
  - validation03: validation; host passed, producer passed. Phase failures are distinct from engine-cell failures.

## Withheld cells


## Explicit method labels and phase observations



Pecan / graphframes, three significant digits; four measured samples per engine per contrast, in two ABBA blocks.

| Comparison | Median ratio | Paired geometric mean, block 1 | Block 2 |
| --- | ---: | ---: | ---: |
| Pecan randomized WCC / graphframes randomized contraction WCC | 4.74 | 4.73 | 4.77 |
| Pecan min_label WCC / graphframes randomized contraction WCC | 12.1 | 12.2 | 12.0 |
| Pecan frontier BFS / graphframes directed unweighted shortest-path hops | 2.99 | 2.92 | 2.99 |

The median ratio compares the four-sample medians. Each block pairs adjacent runs (Pecan position 2 / graphframes position 1, Pecan position 3 / graphframes position 4). n=4, ordered blocks, filesystem cache warming and shared-host activity limit inference. No absolute-performance or multihost claim follows.

## Contract and resources

Each fresh engine container has 16 CPUs, cpuset 0–15, 32 GiB memory and no swap. graphframes has a 30 GiB FairSpillPool with SnMalloc. Pecan local has a 30 GiB greedy pool with mimalloc; in A3, driver and two workers each have 10 GiB, summing to 30 GiB. Each Pecan process prepays its 256 MiB native quota from its pool. Pool sums do not guarantee a physical memory bound.

The timer spans engine process launch through completed exit, including startup, input reads, Pecan snapshots, algorithm, full Parquet export, cleanup and shutdown. Hashing, input/reference construction, full physical oracle and parent final observations are outside. Pecan input_snapshot is nested in public_algorithm: raw phase medians below overlap and must not be added or subtracted from the launch-to-exit ratio. graphframes has no corresponding structured phase breakdown.

Sampled engine PSS excludes the supervisor and PID 1; sampled container PSS includes them. Cgroup lifetime peaks include page cache and earlier identity reads, and final peaks also include the parent oracle. Per-cell observations, sampling coverage and guest steal are preserved in [report.json](report.json).

Original cit-Patents inputs remain pinned. Validation observed zero isolated vertices. The former source 750000 was absent; its failed validation is retained. The explicit common BFS source is **5795784**, chosen before timing by maximum outgoing edge-row count (770), ties by minimum raw vertex ID. This does not reproduce the historical landmark.

The signed/isolate B9 control remains **known_mismatch**, with exact observed and expected rows retained. Dataset qualification is restricted to zero-isolate cit-Patents with a full oracle in every cell; generic signed-ID WCC is not qualified. PageRank remains **not comparable pending B11**; no PR timing is included.

Controller source is f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a, on retained runtime 56194b170155301ba91077f0ba3df31fe2c78b6b and native source ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73; this does not claim a runtime rebuilt from the controller pin. graphframes source is b4da56dabe20bba8e29563e06acc5179b2113ce3. Exact byte pins are retained in the plan and JSON report.

## Phase diagnostics

Pecan measured phase medians in seconds, for explanation only; input_snapshot overlaps public_algorithm. Each named phase sums its own completed occurrences within a cell before taking its median.

| Pecan method | Input snapshot | Public algorithm (includes snapshot) | Result export | Server startup | Server shutdown |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pecan randomized WCC | 2.29 | 59.33 | 0.2995 | 0.06675 | 0.5365 |
| Pecan min_label WCC | 2.325 | 157.6 | 0.2824 | 0.0667 | 0.5399 |
| Pecan frontier BFS | 2.476 | 21.17 | 0.2565 | 0.06919 | 0.3846 |

## Memory and steal diagnostics

Ranges cover the four measured cells per engine and contrast. Peaks are observations within their labelled boundaries, not future capacity guarantees.

| Contrast / engine | Sampled engine PSS GiB range | Final container lifetime peak GiB range | Guest steal % range |
| --- | ---: | ---: | ---: |
| wcc-randomized / graphframes | 1.45–1.52 | 1.7–1.78 | 0–0 (4/4 observed) |
| wcc-randomized / pecan | 2.34–2.48 | 2.91–3.05 | 0–0 (4/4 observed) |
| wcc-min-label / graphframes | 1.43–1.5 | 1.68–1.75 | 0–0 (4/4 observed) |
| wcc-min-label / pecan | 3.25–3.7 | 3.88–4.22 | 0–0 (4/4 observed) |
| bfs / graphframes | 0.959–0.987 | 1.21–1.24 | 0–0 (4/4 observed) |
| bfs / pecan | 1.91–1.99 | 2.42–2.45 | 0–0 (4/4 observed) |

## Retained evidence

[evidence.tar.gz](evidence.tar.gz) contains finalized JSON/JSONL, logs, plans, helpers and offline controls. [evidence-index.json](evidence-index.json) records every archive member's exact name, byte count, SHA-256 and original path. Historical run01–03 failed preflights and phase attempts remain distinct; they are not counted as algorithm results.

Full Parquet outputs, binary references and other physical payloads remain on Apo. Their unchanged collected manifests are linked by `physical_payloads` in [report.json](report.json), with copies indexed in the archive. This generator does not read or rehash those payloads.
