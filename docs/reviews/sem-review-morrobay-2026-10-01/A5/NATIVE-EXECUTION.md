# Native benchmark execution on Morrobay

Observed UTC: 2026-10-02T09:29:54.620199+00:00.

Alexy instructed: stop VM benchmark execution; use bare macOS for benchmarks, and VMs for Linux build testing. This supersedes the A1-container benchmark queue for future measurements. Historical A2/A3/B8 records remain evidence for their original VM/container execution class.

## Work underway

- Optimized native binaries: Sail source `9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3` and graphframes-rs `b4da56dabe20bba8e29563e06acc5179b2113ce3`, exact detached workspaces. Both use `cargo build --locked --release`, rustc1.97.1, opt3, LTO, codegen1, debug0, striptrue, incremental0. Native build artifacts are on Apo. Owner PID97527, started2026-10-02T09:00:55Z, evidence `/Volumes/Apo/graph-tests/results/sem-review-20261001/native-optimized-build01/`. Compilation is in progress; no completed binary or native timing is claimed.
- Retire the graph VM: preserve portable experiment inputs, final results, logs and source on Apo, excluding compiled targets, venv/dependency caches and transient staging. No VM disk image is preserved. Owner PID23661, started2026-10-02T09:22:10Z; full archive/member audit precedes explicit deletion of profile `sail-gate`. Evidence `/Volumes/Apo/graph-tests/results/sem-review-20261001/graph-vm-retirement01/`. The production Eigen profile `default` is a separate publishing service and is outside this retirement.
- Native A5 diagnostic: frozen typed WCC write/count profiler at `/Volumes/Apo/graph-tests/results/sem-review-20261001/A5-native-preparation01/`, exact9f controller and6ae Python runtime-helper source. Snapshot-on16 partitions/16 software threads/30GiB greedy pool. This is one diagnostic cell, with nested method timers and an extra named component count, followed by a raw Parquet export and a separate full reference oracle. It has not launched.

## Native measurement contract

Morrobay is an Intel Xeon W-2191B Mac,18 physical/36 logical CPUs,128GiB RAM. Record actual host memory/RSS and process identity. Software thread counts and configured pool sizes do not impose a16CPU/32GiB Linux cgroup or establish a32GiB capacity bound. Linux cgroup/PSS/guest-steal fields are unavailable on the native path. Separate build and cleanup I/O from benchmark execution.

Benchmark inputs and active staging/output use the Mac SSD; retained artifacts and build targets use Apo. Every compared engine reads the same admitted input bytes. The relocated cit-Patents files at `/Users/alexy/src/grust-benchmark-data/cit-Patents/` were checked against the original A2 reference receipt SHA`fa8300ed3a92ea7874dc6612707feef189eda273dc73150b5cc25e64c68d56a0`, with complete before/after hashes. No retained guest-path receipt was rewritten.

Native shared-host measurements will be reported as paired ratios with settings/boundaries and all outcomes. The requested native run will measure the platform difference; no fivefold or tenfold factor is inferred from changing the runtime platform. The exact prior VM binary was already an optimized release, as established in [BUILD-PROVENANCE.md](BUILD-PROVENANCE.md).
