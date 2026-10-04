# A1: exact graphframes-rs gate build

**Passed build and CLI-help checks**, with independent source/binary/closure audit retained in [independent-audit.json](independent-audit.json). This is A1 preparation for matched experiments. No algorithm was run for A1, no runtime memory admission for an algorithm is established, and no performance comparison is made.

## Frozen identities

| Property | Observed value |
| --- | --- |
| Source | `b4da56dabe20bba8e29563e06acc5179b2113ce3`, clean and detached |
| Image | `sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e` |
| Rust / Cargo | 1.97.1 / 1.97.1 |
| CMake / C++ | 3.31.6 / Debian GCC 14.2.0 |
| Locked dependencies | DataFusion 55.1.0, Arrow 59.3.0, SnMalloc 0.7.4 |
| Build | `cargo build --release --locked --bin graphframes --jobs 8`, default CLI feature |
| Target | fresh `/targets/sem-review-20261001/A1-run02/target`, incremental disabled |
| Executable | 162,805,992 bytes; SHA-256 `b2a7fc0f077fafc158aaa8a45ac32e5f2af5b3d96b8050c348421fa79442722f` |
| Build envelope | 16 CPUs, affinity 0–15, 32 GiB memory, zero swap; 8 compiler jobs |
| Build cgroup peak | 5,499,604,992 bytes (~5.12 GiB), build-container lifetime, including CLI help |
| Outcome | exit 0, CLI `--help` and `wcc --help` exit 0, zero cgroup oom/oom_kill |

All 333 tracked source files, the helper and source-manifest hashes agree before/after and in the final observation. No source change, Cargo.lock update or toolchain install was needed. The retained [build receipt](build-receipt.json), [host result](host-result.json), [orchestration](orchestration.json) and [preflight](preflight.json) bind the command, compiler, limits, executable, observations and certain stopped/removed container. The serial queue lock was released; no competing heavy job was started.

## Settings from main.rs

The [source/settings audit](SOURCE-SETTINGS.md) records exact CLI behavior and scoped historical source bridges. The proposed historical tuple is seed 42, 16 DataFusion target partitions and 30 GiB FairSpillPool, with sort-merge preference. `num_workers` is partition width in one process. The allocator is SnMalloc; the spill pool does not bound complete RSS. A future Sail contrast must state its allocator, pool strategy, per-process arithmetic and nonpool headroom explicitly.

WCC exports full `(id,component)` canonical minimum-ID labels including isolates. PR is thresholded delta Pregel, distinct from fixed-step LDBC power PR. Shortest paths is per-landmark unweighted Int32 hops, distinct from weighted DOUBLE SSSP. Matching iteration caps does not make those numerical contracts equal. The external timer includes startup/input setup/output/cleanup through process exit; validation and input/result oracles belong in separate phases.

## Retained first attempt

Run01 failed in cheap staging before cloning or compilation because the new namespace's parent directory was absent. Original failed host/stage receipts and helpers remain in the archive. [Closure audit](first-attempt-closure.json) independently confirms owner process dead, zero running containers, both stage/build names absent and no build launch. The owned closed lock was preserved under `gate.lock.closed-A1-run01`, not discarded. A fresh run02 namespace fixed parent creation and received a read-only review of source/ownership, final verdict ordering and failure observations. No failed ID was reused.

The original short-shell background launch was observed to leave no process, run directory or engine; the actual supervisor used nohup in a separate process session. Both launch observations are retained.

## Storage and reproduction boundary

[Portable evidence](evidence.tar.gz) and [manifest](evidence-manifest.json) retain build logs, commands, both attempts, original/corrected helpers, hashes and failure/closure records. The large source bundle and executable are stored separately on Apo; their exact paths/sizes/hashes are indexed. Full material: `/Volumes/Apo/graph-tests/results/sem-review-20261001/A1/`. Source, target and executable remain in the guest named volume too.

Guest executable for future cells: `/targets/sem-review-20261001/A1-run02/target/release/graphframes`. Verify its hash before use. Historical binary bytes/compiler flags are unknown; this fresh build is not asserted byte-identical to Sem's historical executable.

A2/A3 have not launched. The referenced status-board commit `557a7565` is not yet on origin; currently proposal-v5 is `d7991b23` without sections 8/9. Await the board to bind the remaining item scopes and paired profiles. This report does not change shared-host timing rules or imply multi-host qualification.
