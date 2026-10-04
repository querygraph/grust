# A5: exact historical host build answer

Observed UTC: 2026-10-02T12:44:47.949369+00:00.

The historical host `/targets/sail-compact-host-56194b170155/sail-linux-x86_64-56194b170155-release` was built at Sail commit `56194b170155301ba91077f0ba3df31fe2c78b6b`, tree `e50518d749ec15c68766285d1a47d99e9b14ab28`:

```sh
cargo build --locked --release -p sail-cli
```

Its recorded profile settings were `CARGO_PROFILE_RELEASE_OPT_LEVEL=3`, `CARGO_PROFILE_RELEASE_LTO=true`, `CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1`, `CARGO_PROFILE_RELEASE_DEBUG=0`, and `CARGO_PROFILE_RELEASE_STRIP=true`. It used `CARGO_INCREMENTAL=0`, `CARGO_BUILD_JOBS=16`, and Rust 1.97.1. The [original receipt](../../sail-stream-experiments-2026-09-30/linux-builds/compact561-host/final/rebuild-receipt.json) records exit 0; the [build log](../../sail-stream-experiments-2026-09-30/linux-builds/compact561-host/final/host-release-build.log) ends with `Finished release profile [optimized]`.

The file was **160,192,912 bytes** (160.19 MB; 152.77 MiB), SHA256 `5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec`. The independently retained [ELF inspection](runtime-elf-inspection.json) pins that same byte count and hash: no static `.symtab` and no `.debug` or `.zdebug` sections. Stripping is confirmed; the required dynamic symbol table remains.

Fable's observation about `examples/extensions/scripts/build.sh` is correct: at exact source 561 it invokes Cargo without `--release` and reports `host/debug/sail`. This artifact used the separate [rebuild_compact_host.py](../../sail-stream-experiments-2026-09-30/rebuild_compact_host.py), which explicitly invokes the command above and copies `target-host/release/sail`. The original receipt, builder, log and collection record still match all four retained hashes in [runtime-build-provenance.json](runtime-build-provenance.json). That earlier timestamped record predates the later ELF inspection.

The build-profile question is settled. The larger historical VM slowdown remains unexplained; no isolated causal experiment is claimed.

## Existing follow-up evidence

The requested 16-partition WCC write/write/count diagnostic already completed on native macOS, following Alexy's execution policy. The [A5 completion report](NATIVE-COMPLETION.md) retains the exact optimized native source, instrumentation, all 3,774,768 output vertices and zero membership mismatches. It is a single instrumented snapshot-on cell; it supplies no native Pecan/GraphFrames WCC ratio.

The [matched native PageRank report](../PageRank/README.md) already contains the separate reference, warmups and two ABBA blocks in each mode: all 21 outcomes qualified. Pecan/GraphFrames geometric mean launch-through-exit ratios on shared Morrobay are 1.690909 local and 1.991734 process-cluster, with full per-vertex oracles. Controller `0d1ef2ca3` uses the native `9f0aa7d2a` release host with recorded empty compiled-Rust diff. Cluster resources differ from local resources as disclosed in that report.

This reply started no build, VM or benchmark. Future graph benchmarks remain native; VMs are reserved for Linux build testing.
