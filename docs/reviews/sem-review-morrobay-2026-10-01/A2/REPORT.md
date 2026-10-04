# A2 completed receipt comparison

Status: **complete_item_receipt_evidence**. Observed UTC: 2026-10-01T23:29:41.609706+00:00.

Ratios on Morrobay, a shared host. Raw seconds are diagnostics; no absolute-performance, multihost, generic signed-ID WCC, rebuilt-runtime, PageRank or larger-scale claim.

Retained host, bootstrap, container and cell JSON only; no Parquet/input reads, no independent rehash of payloads, no raw-sampler recomputation, no Docker or engine execution. Correctness is retained full-oracle receipt evidence, not a new physical-output audit.

## Shared-host ratios

Pecan / graphframes; values have three significant digits. All raw seconds below are diagnostics. graphframes is always a single CLI process with 16 workers; A3 changes Pecan to driver + two workers on one host.

| Execution class | Algorithm | Median ratio | ABBA block 1 | ABBA block 2 | Qualification |
| --- | --- | ---: | ---: | ---: | --- |
| local | wcc-randomized | 3.77 | 3.79 | 3.84 | 4 measured samples/engine; both ABBA blocks |
| local | wcc-min-label | 9.49 | 9.16 | 9.53 | 4 measured samples/engine; both ABBA blocks |
| local | bfs | 2.51 | 2.59 | 2.49 | 4 measured samples/engine; both ABBA blocks |

n=4 per engine and two ordered blocks limit inference. Warmups are retained and excluded from statistics; failed and known-mismatch cells cannot qualify. Input cache warming is retained in the boundary. No phases are subtracted.

## Every planned cell

| Run ID | Role / block | Host / cell | Diagnostic launch→exit seconds | Engine sampled PSS GiB | Final container lifetime peak GiB | Guest steal | Qualified |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| a2-wcc-randomized-01-graphframes | warmup / — | passed / passed | 16.6076 | 1.49864 | 1.75328 | 0 | True |
| a2-wcc-randomized-02-pecan | warmup / — | passed / passed | 51.9824 | 2.19628 | 2.5059 | 0 | True |
| a2-wcc-randomized-03-graphframes | measured / 1 | passed / passed | 13.3241 | 1.44763 | 1.70669 | 0 | True |
| a2-wcc-randomized-04-pecan | measured / 1 | passed / passed | 52.0008 | 2.24849 | 2.53343 | 0 | True |
| a2-wcc-randomized-05-pecan | measured / 1 | passed / passed | 50.4168 | 2.27433 | 2.61649 | 0 | True |
| a2-wcc-randomized-06-graphframes | measured / 1 | passed / passed | 13.6773 | 1.47566 | 1.73265 | 0 | True |
| a2-wcc-randomized-07-graphframes | measured / 2 | passed / passed | 13.9012 | 1.46794 | 1.72668 | 0 | True |
| a2-wcc-randomized-08-pecan | measured / 2 | passed / passed | 51.6794 | 2.2555 | 2.56068 | 0 | True |
| a2-wcc-randomized-09-pecan | measured / 2 | passed / passed | 54.7216 | 2.19326 | 2.54265 | 0 | True |
| a2-wcc-randomized-10-graphframes | measured / 2 | passed / passed | 13.8311 | 1.48879 | 1.74414 | 0 | True |
| a2-wcc-min-label-01-graphframes | warmup / — | passed / passed | 14.0603 | 1.48115 | 1.73931 | 0 | True |
| a2-wcc-min-label-02-pecan | warmup / — | passed / passed | 123.781 | 3.28611 | 3.46241 | 0 | True |
| a2-wcc-min-label-03-graphframes | measured / 1 | passed / passed | 14.152 | 1.48815 | 1.74599 | 0 | True |
| a2-wcc-min-label-04-pecan | measured / 1 | passed / passed | 122.975 | 3.41454 | 3.64478 | 0 | True |
| a2-wcc-min-label-05-pecan | measured / 1 | passed / passed | 128.882 | 3.33245 | 3.53957 | 0 | True |
| a2-wcc-min-label-06-graphframes | measured / 1 | passed / passed | 13.3524 | 1.48302 | 1.73648 | 0 | True |
| a2-wcc-min-label-07-graphframes | measured / 2 | passed / passed | 13.6589 | 1.49242 | 1.74702 | 0 | True |
| a2-wcc-min-label-08-pecan | measured / 2 | passed / passed | 127.411 | 2.94652 | 3.22822 | 0 | True |
| a2-wcc-min-label-09-pecan | measured / 2 | passed / passed | 129.421 | 3.18729 | 3.3642 | 0 | True |
| a2-wcc-min-label-10-graphframes | measured / 2 | passed / passed | 13.2975 | 1.46518 | 1.71891 | 0 | True |
| a2-bfs-01-graphframes | warmup / — | passed / passed | 8.69079 | 0.974318 | 1.22538 | 0 | True |
| a2-bfs-02-pecan | warmup / — | passed / passed | 22.1991 | 1.11136 | 1.34332 | 0 | True |
| a2-bfs-03-graphframes | measured / 1 | passed / passed | 8.70511 | 0.991308 | 1.24212 | 0 | True |
| a2-bfs-04-pecan | measured / 1 | passed / passed | 22.2311 | 1.1003 | 1.38624 | 0 | True |
| a2-bfs-05-pecan | measured / 1 | passed / passed | 22.8799 | 1.06516 | 1.33352 | 0 | True |
| a2-bfs-06-graphframes | measured / 1 | passed / passed | 8.72825 | 0.974142 | 1.22427 | 0 | True |
| a2-bfs-07-graphframes | measured / 2 | passed / passed | 8.22347 | 1.03159 | 1.28163 | 0 | True |
| a2-bfs-08-pecan | measured / 2 | passed / passed | 21.5168 | 1.06593 | 1.32551 | 0 | True |
| a2-bfs-09-pecan | measured / 2 | passed / passed | 21.5271 | 1.09696 | 1.36037 | 0 | True |
| a2-bfs-10-graphframes | measured / 2 | passed / passed | 9.11661 | 1.11754 | 1.36884 | 0 | True |

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
| Pecan randomized WCC / graphframes randomized contraction WCC | 3.77 | 3.79 | 3.84 |
| Pecan min_label WCC / graphframes randomized contraction WCC | 9.49 | 9.16 | 9.53 |
| Pecan frontier BFS / graphframes directed unweighted shortest-path hops | 2.51 | 2.59 | 2.49 |

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
| Pecan randomized WCC | 5.023 | 48.12 | 0.2284 | 0.06675 | 0.1696 |
| Pecan min_label WCC | 5.228 | 124.3 | 0.2302 | 0.06908 | 0.1954 |
| Pecan frontier BFS | 5.232 | 18.27 | 0.1686 | 0.0681 | 0.1695 |

## Memory and steal diagnostics

Ranges cover the four measured cells per engine and contrast. Peaks are observations within their labelled boundaries, not future capacity guarantees.

| Contrast / engine | Sampled engine PSS GiB range | Final container lifetime peak GiB range | Guest steal % range |
| --- | ---: | ---: | ---: |
| wcc-randomized / graphframes | 1.45–1.49 | 1.71–1.74 | 0–0 (4/4 observed) |
| wcc-randomized / pecan | 2.19–2.27 | 2.53–2.62 | 0–0 (4/4 observed) |
| wcc-min-label / graphframes | 1.47–1.49 | 1.72–1.75 | 0–0 (4/4 observed) |
| wcc-min-label / pecan | 2.95–3.41 | 3.23–3.64 | 0–0 (4/4 observed) |
| bfs / graphframes | 0.974–1.12 | 1.22–1.37 | 0–0 (4/4 observed) |
| bfs / pecan | 1.07–1.1 | 1.33–1.39 | 0–0 (4/4 observed) |

## Retained evidence

[evidence.tar.gz](evidence.tar.gz) contains finalized JSON/JSONL, logs, plans, helpers and offline controls. [evidence-index.json](evidence-index.json) records every archive member's exact name, byte count, SHA-256 and original path. Historical run01–03 failed preflights and phase attempts remain distinct; they are not counted as algorithm results.

Full Parquet outputs, binary references and other physical payloads remain on Apo. Their unchanged collected manifests are linked by `physical_payloads` in [report.json](report.json), with copies indexed in the archive. This generator does not read or rehash those payloads.
