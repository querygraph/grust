# B9: signed-isolate WCC regression

Both canonical label modes passed the original logical three-vertex witness on native macOS. The finalized [root receipt](root-receipt.json) records successful execution; the [root audit](root-audit.json) qualifies full output retention and absence of the owned process groups. Qualification is limited to this witness. The historical `f3` mismatch and A2/A3 results remain unchanged; they were not rerun. Generic signed-ID qualification is false.

## Exact results

Vertices are `1`, `2`, and `-7694170072594669674`, with edge `(1, 2)`. Each mode returned all three vertices in the correct two components, converged in one iteration, and passed full coverage and partition checks. Inputs were fresh Spark Connect local relations with the same logical rows; the historical Parquet originals were preserved separately.

| Mode | Vertex | Observed component |
| --- | ---: | ---: |
| Canonical | -7694170072594669674 | -7694170072594669674 |
| Canonical | 1 | 1 |
| Canonical | 2 | 1 |
| Noncanonical | -7694170072594669674 | 6030022625275584585 |
| Noncanonical | 1 | -7694170072594669674 |
| Noncanonical | 2 | -7694170072594669674 |

Canonical labels match the expected minimum IDs exactly. Noncanonical values above are observed labels; their partition and complete vertex coverage were checked without requiring predeclared numeric labels. Full decoded rows and physical schema metadata are in the unchanged [control receipt](native-control-receipt.json).

## Source and execution scope

Controller `b522bf3a9c38d3861a114bf672abe7f7d6c7c491` used the optimized native runtime compiled from `9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3` and harness `6ae2e43a903c2cee02da170465c922c72b76198e`. The [source admission](source-admission.json) records unchanged `crates/`, `Cargo.toml`, `Cargo.lock`, and `rust-toolchain.toml` between those controller/runtime revisions. This is scoped Rust parity, not identity of the Python controllers.

Both calls used randomized contraction, seed 42, a 100-iteration cap, snapshot inputs enabled, and 16 threads/partitions. The host has 128GiB of physical memory; the actual child receipt records a 30GiB software pool and a 256MiB configured native quota. These are not an enforced 32GiB container envelope. This correctness control supplies no performance comparison or A2/A3 execution-class parity.

## Retained evidence

Root verified all nine retained files (39,508 bytes), including six raw Parquet files, and closed the child, server, and outer owner groups with locks released. The child's independent-closure and outer-retention fields remain false; the separate root audit supplies those qualifications. Payloads remain at `/Volumes/Apo/graph-tests/results/sem-review-20261001/B9-native-regression02/retained` with their inventory in [report.json](report.json). The [control source archive](evidence/control-source.tar.gz) preserves the frozen runner. The [complete raw output archive](evidence/retained-output.tar.gz) preserves all nine physical files; its [verification](evidence/retained-output-verification.json) binds every member to the retained inventory.

The [initial preflight error](initial-preflight-error.json) is retained: the root interpreter lacked `hashlib.file_digest` while pinning the configuration, before any helper/server PID was recorded. Fresh run `B9-native-regression02` completed successfully; the initial failure is not an algorithm result.


Status: **DONE**; the current witness `known_mismatch` is lifted on the pinned native source/runtime. See the [B7 snapshot comparison](../B7/README.md).
