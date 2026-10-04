# A5 native matched contrasts: completed

Observed UTC: 2026-10-02T14:01:23.199165+00:00.

All 70 calls qualified, with independent final physical-output retention and process-closure audit. Six separate GraphFrames references, twelve warmups, two ABBA blocks for each dataset/algorithm (four measured calls per engine), and one additional snapshot-on WCC pair per dataset.

## Results

Pecan / GraphFrames geometric mean launch-through-exit ratios on shared native Morrobay; below one means a shorter Pecan interval. Main inputs are read in place.

| Dataset | WCC | PageRank | BFS |
| --- | ---: | ---: | ---: |
| cit-Patents | 1.936001 | 1.694032 | 1.670187 |
| graph500-24 | 0.886048 | 0.986203 | 1.094556 |

Separate single-pair snapshot-on WCC ratios: Cit 2.053981; Graph500 1.114015. These are not repeated snapshot measurements.

All original vertices are covered exactly once: 3,774,768 Cit and 8,870,942 Graph500. WCC full partition equivalence and canonical labels pass; BFS exact stored-directed hops pass; PageRank full vectors pass the declared absolute bound 1e-12. Maximum PageRank absolute differences are 1.36e-19 Cit and 2.39e-18 Graph500. Agreement is with separate GraphFrames references, not an independent topology ground truth.

## Boundaries and provenance

Exact Pecan controller d0e4e422afdea967126ae7b9506e04c9f1812b97 uses optimized native Sail 9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3; the compiled Rust paths and Cargo lock have an observed empty diff. GraphFrames source is b4da56dabe20bba8e29563e06acc5179b2113ce3. Both native binaries are release builds; no VM was used.

The parent timer includes Python bootstrap/imports, engine startup, reads, algorithm, complete selected Parquet export and cleanup. Fable starts after imports. BFS here exports two fields (`id,hops`), while his Pecan contrast exports four. These results do not reproduce those boundaries. Directed Graph500 BFS/PageRank do not qualify official undirected ground truth.

Both engines use 16 configured software threads and a 30 GiB pool (Pecan greedy, GraphFrames FairSpillPool), with 16 Pecan partitions. The shared macOS host has 128 GiB; software settings impose no OS CPU, memory or swap caps.

The [historical build answer](BUILD-ANSWER.md) confirms cargo build --locked --release -p sail-cli, opt3/full LTO/codegen1/debug0/stripped, 160,192,912 bytes. Its VM slowdown remains unexplained.

## Preserved evidence

[Full report and portable package](MatchedNative/README.md) includes every outcome, raw clocks, exact small logs/metadata/source archives, original path/hash index and archive verification. The [original planned protocol](NATIVE-MATCHED-PLAN.md) is preserved byte for byte. Full raw Parquet remains on Apo in `/Volumes/Apo/graph-tests/results/sem-review-20261001/A5-native-matched-run01/`; root verified 516 retained files totaling 2,029,219,632 bytes against both original SSD and retained copies.
