# Prepared degree kernel qualification

Capitola, aarch64 macOS, Rust 1.98.0. Clean source and preserved executable
hashes are in the adjacent status files. The raw archive retains both complete
Criterion trees and test/Clippy/benchmark logs, including outliers.

Baseline `184b5a4` charges each scalar; `5d28f02` precharges bounded chunks.
Both execute the same closed-form fixture oracle before timing. The latter
passed 38 focused tests, zero failures or ignored tests, and all-targets,
all-features Clippy with warnings denied for the two algorithm crates.

| Mode | Nodes | Baseline slope (µs) | Batched slope (µs) |
| --- | ---: | ---: | ---: |
| unweighted | 4,096 | 47.289 | 10.086 |
| unweighted | 65,536 | 756.875 | 162.799 |
| weighted | 4,096 | 387.667 | 26.684 |
| weighted | 65,536 | 6229.291 | 427.792 |

These are prepared-projection kernel measurements, including result allocation
and disposal. Capture, projection construction, backend access and Arrow output
are excluded. Throughput counts output nodes, not traversed arcs. Each fixture
has `nodes - nodes / 10` active nodes, eight outgoing edges per active node
(including a self-loop), and trailing isolates. Weighted edges carry 0 through 7.

Criterion uses 20 samples per case with its default warmup and measurement
windows; these are sampling windows, not query deadlines. The context admits
256 MiB, unlimited practical work (`usize::MAX`), and no deadline. This is not
a total process-memory bound. Runs are sequential before/after on the same host;
no cross-engine or end-to-end performance claim follows from these results.

Successful kernel work remains exactly V (unweighted) or V+A (weighted).
Tests cover chunk boundaries, finite work exhaustion, retained memory release,
weighted overflow, cancellation, Arrow nullability and Cypher output, plus 486
small multigraph/orientation/weight combinations against an independent oracle.
