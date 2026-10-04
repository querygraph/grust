# Native matched PageRank

## Findings

All 21 outcomes qualified: one separate GraphFrames reference, four warmups, and two ABBA blocks per mode. Warmups and the reference are excluded from pairs; each mode has four measured calls per engine.

| Mode | Four adjacent Pecan / GraphFrames ratios | Geometric mean | Maximum absolute error |
| --- | --- | ---: | ---: |
| local | 1.669233, 1.703381, 1.691158, 1.700073 | 1.690909 | 5.42101e-20 |
| process-cluster | 1.966085, 1.997109, 1.952226, 2.053012 | 1.991734 | 2.1684e-19 |

These are ratios on shared Morrobay. A ratio above one means the Pecan launch through exit interval was longer in that adjacent pair.

## Contract and timing

Both engines use the original directed edges with multiplicity; initial rank and delta 0.15, damping 0.85, send on the first step and thereafter only when the previous delta exceeds 0.01, ten fixed steps, no dangling redistribution, and final normalization. Pecan uses `pregel_delta`, `vote_to_halt=False`, and `snapshot_inputs=False`.

The independent physical oracle checks every original vertex exactly once in raw `id: int64, pagerank: float64` outputs and compares each score with the separate GraphFrames reference at absolute tolerance `1e-12`. Reference preparation checks domain and finite physical values; it has no numerical self-comparison. All candidate outputs passed with zero mismatches.

The primary timer starts immediately before child Popen and ends after its waited exit. It includes startup, reads, algorithm actions, full raw Parquet export, and cleanup. The oracle and retention checks run afterward.

## Sources and resources

Pecan controller `0d1ef2ca3`; optimized native Sail `9f0aa7d2a`; GraphFrames `b4da56dabe`; frozen Python runtime and measurement helpers `6ae2e43a9`. The controller and compiled Sail have an observed empty diff over `crates/`, `Cargo.toml`, `Cargo.lock`, and `rust-toolchain.toml`. Both native binaries were built with `cargo build --locked --release`, Rust 1.97.1, optimization level 3, full LTO, one codegen unit, debug information disabled and stripping enabled. The build receipts, client admission and exact input preservation are retained.

Local settings are 16 threads and 16 partitions with 30 GiB per engine's configured pool. GraphFrames uses FairSpillPool; Pecan uses greedy pools. Pecan process cluster has a driver and two workers, each configured with 16 threads and 10 GiB: 48 possible threads and 30 GiB total pools. GraphFrames remains local with 16 threads and a 30 GiB pool. This is a disclosed resource asymmetry. These are software settings on a physical 128 GiB macOS host. There is no OS CPU, memory or swap cap and no PSS, cgroup or steal measurement. Retained periodic RSS observations may include shared pages and are sampled maxima.

## Evidence

[report.json](report.json) retains all 21 outcomes and raw timer fields. [evidence.tar.gz](evidence.tar.gz) contains exact small original metadata, complete logs, source helpers and source archives. [INPUTS.json](INPUTS.json) maps every portable name to its original path and byte identity. [archive-verification.json](archive-verification.json) binds every physical archive member. The full raw Parquet results are retained on Apo under `PageRank-native-pair01/cells/*/raw-output`, with 156 files and 673,206,357 bytes independently verified against the SSD files. The scope is Sem’s fixed-budget dynamic PageRank contract on cit-Patents.
