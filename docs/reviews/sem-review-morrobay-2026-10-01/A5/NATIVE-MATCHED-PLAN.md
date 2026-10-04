# A5 native matched contrasts

Observed UTC: 2026-10-02T12:55:15.038504+00:00.

Status: preparation; no engine cell has launched.

## Source and build

Exact Pecan controller: `d0e4e422afdea967126ae7b9506e04c9f1812b97`, detached tree `3378fb720ef23d357d7a92ad280e63dce7605edf`. Compiled native Sail: `9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3`; its compiled Rust paths and Cargo lock have an observed empty diff against the controller. It remains labeled compiled9f. GraphFrames: `b4da56dabe20bba8e29563e06acc5179b2113ce3`.

Both optimized native builds used Rust 1.97.1, optimization 3, full LTO, one codegen unit, debug 0 and stripping enabled. See [build evidence](NATIVE-COMPLETION.md) and the [historical gate answer](BUILD-ANSWER.md). Benchmarks use bare macOS under Alexy's instruction; no VM benchmark is requested or planned.

## Protocol

Two original LDBC Parquet inputs: cit-Patents (3,774,768 vertices, 16,518,947 edges) and graph500-24 (8,870,942 vertices, 260,379,520 edges). Input/staging/output are on the internal SSD; binaries, Python client and retained evidence are on Apo. Full input hashes match retained originals. A separate outside-timer preparation checked the complete original Int64 vertex domain, uniqueness and BFS source membership.

Local mode only, 16 software threads/partitions and 30 GiB configured pool per engine; greedy for Pecan, FairSpillPool for GraphFrames. These settings do not impose macOS CPU or memory caps.

For each dataset and algorithm: one separate GraphFrames reference, one warmup per engine, and two ABBA blocks (GraphFrames/Pecan/Pecan/GraphFrames). WCC additionally has one measured GraphFrames/Pecan pair with Pecan snapshots enabled. Planned cells: 13 WCC, 11 PageRank and 11 BFS per dataset, 70 total. Each output receives an independent full physical oracle after waited engine exit. Reference preparation checks the original domain and valid physical values; it performs no numerical self-comparison.

- WCC: randomized contraction, seed 42, minimum-original-ID canonical labels, Pecan cap 100 rounds, inputs in place for the main contrast.
- PageRank: matched dynamic GraphX/Pregel delta contract, reset 0.15, tolerance 0.01, ten fixed steps, normalized result, no vote-to-halt or dangling redistribution; inputs in place.
- BFS: directed stored source-to-target edges, Pecan frontier method, cap 1000 rounds, Cit source 5795784 and Graph500 source 798169 (Fable's paired control). Export only `id,hops`, consistent with original A2 and GraphFrames' two-column hop output. This differs from Fable's four-field Pecan BFS export. Matching this stored direction does not claim the official undirected Graph500 BFS/PageRank ground-truth contract.

The main timer runs from immediately before child launch through waited exit, including startup, reads, algorithm, selected full Parquet export and cleanup. Output oracles and retention follow that boundary. Results will be ratios on shared Morrobay; raw clocks and every attempted, failed or skipped outcome remain in evidence. No historical VM cell or previous native campaign is relabeled.

## Evidence destination

Full campaign: `/Volumes/Apo/graph-tests/results/sem-review-20261001/A5-native-matched-run01/`. Root-owned serial execution only. Source preparation, input admissions, exact source archive and helper controls are retained in separately named adjacent directories. Results are pending.
