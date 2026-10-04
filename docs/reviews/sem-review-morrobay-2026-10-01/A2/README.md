# A2: cit-Patents shared-host comparison

All 30 A2 cells qualified by retained host/producer/full-oracle receipts: 24 measured cells and six warmups. Warmups remain in the evidence and are excluded from ratios. This is a receipt audit, not a new physical payload comparison.

Execution: Pecan local runtime; graphframes remains one CLI process with 16 workers. Morrobay is a shared host. Only within-class ratios are reported; raw seconds in the [detailed report](REPORT.md) are diagnostics.

## Ratios

Pecan / graphframes, three significant digits; four measured samples per engine per contrast, in two ABBA blocks.

| Comparison | Median ratio | Paired geometric mean, block 1 | Block 2 |
| --- | ---: | ---: | ---: |
| Pecan randomized WCC / graphframes randomized contraction WCC | 3.77 | 3.79 | 3.84 |
| Pecan min_label WCC / graphframes randomized contraction WCC | 9.49 | 9.16 | 9.53 |
| Pecan frontier BFS / graphframes directed unweighted shortest-path hops | 2.51 | 2.59 | 2.49 |

The median ratio compares the four-sample medians. Each block pairs adjacent runs (Pecan position 2 / graphframes position 1, Pecan position 3 / graphframes position 4). n=4, ordered blocks, filesystem cache warming and shared-host activity limit inference. No absolute-performance or multihost claim follows.

## Contract and resources

Each fresh engine container has 16 CPUs, cpuset 0–15, 32 GiB memory and no swap. graphframes has a 30 GiB FairSpillPool with SnMalloc. Pecan local has a 30 GiB greedy pool with mimalloc; in A3, driver and two workers each have 10 GiB, summing to 30 GiB. The harness configures 256 MiB native quota settings for Nutmeg and Argentea. Native quotas are admitted from the ordinary process pool when the corresponding extension owner is bound; actual per-process reservations were not measured. See the [source correction and C3 accounting audit](../C3-NATIVE-QUOTA-CORRECTION.md). Pool sums do not guarantee a physical memory bound.

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

## B9 current status — 2026-10-02T11:09:14.526577+00:00

The current signed-isolate witness **passes** on controller b522bf3a9 with the optimized native runtime 9f0aa7d2a, in both canonical-label modes; its current `known_mismatch` is lifted. The [separate B9 report](../B9/README.md) preserves exact rows, source identities and independent retention/process closure. The paragraph above records the historical f3 outcome, whose machine receipts remain unchanged. A2/A3 were not rerun; their original cit-Patents scope and PageRank contract stay as recorded. This focused regression does not qualify every signed-ID graph.


## Native matched PageRank follow-up — 2026-10-02T12:29:05.907556+00:00

The [PageRank report](../PageRank/README.md) adds the local contrast on original cit-Patents Parquet with controller `0d1ef2ca3` and optimized native runtime `9f0aa7d2a` (compiled Rust paths identical). Each engine has one warmup and four measured calls across two ABBA blocks. Every score is compared against a separate, immutable graphframes-rs reference after engine exit. Resource settings, full export and cleanup boundaries, shared-host ratios and complete retention are documented there. The original A2/A3 receipts retain their recorded source and execution class.
