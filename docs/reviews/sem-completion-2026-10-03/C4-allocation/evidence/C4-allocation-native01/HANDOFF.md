# Current-native C4 full-struct allocation control

Prepared source only. No Cargo, compilation, probe, native query, or allocation measurement was executed by the author. Root owns all actual gates and measurements. Historical probes under Grust's `min-struct-comparison` and `min-by-probe` remain unchanged.

The new standalone crate compares two grouped factories with the same nonnull full `(distance Float64,hops Int64,parent Int64)` value and complete ordering key. Parent values include negative signed IDs; keys are finite and total. Exact ties, nullable children, NaNs and arbitrary struct layouts are outside this paired contract. The copied native9f compact source and its sibling tests are byte-identical to the qualified runtime source. Ordered min_by uses the public DataFusion55.1 `last_value_udaf` grouped factory with complete-struct DESC NULLS FIRST, the actual rewrite observed in C4-native02/pair03. Both receive an all-true filter. The pair03 plans independently show Partial and FinalPartitioned modes with Hash4 and full4096-group answers on two workers.

This is a current compact MIN versus planner-ordered min_by factory control. It is **not** the historical generic DataFusion struct MIN baseline, and not a query execution or graph benchmark. The historical original-versus-compact probes remain separately named. Dynamic requested System allocator bytes/counts, reported accumulator size, Arrow output size and process-lifetime `getrusage` peak RSS have separate fields. No MiMalloc, usable-heap, transport, Sail software-pool, or deduplicated physical-memory equivalence is claimed.

## Gates and fresh process measurements

Root must use a fresh private target under this profile, bounded build jobs4, CARGO_INCREMENTAL=0, Rust1.97.1 and the exact frozen Cargo.lock. All commands below are prospective. Copy the source into a detached committed source gate when publishing; no root gate/commit is implied by the source-only freeze.

```sh
RUSTUP_TOOLCHAIN=1.97.1 CARGO_BUILD_JOBS=4 CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=/Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-allocation-native01/target CARGO_PROFILE_RELEASE_OPT_LEVEL=3 CARGO_PROFILE_RELEASE_LTO=fat CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1 CARGO_PROFILE_RELEASE_DEBUG=0 CARGO_PROFILE_RELEASE_STRIP=true cargo fmt --manifest-path /Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-allocation-native01/probe/Cargo.toml --all -- --check &&
RUSTUP_TOOLCHAIN=1.97.1 CARGO_BUILD_JOBS=4 CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=/Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-allocation-native01/target cargo clippy --offline --locked --manifest-path /Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-allocation-native01/probe/Cargo.toml --all-targets -- -D warnings &&
RUSTUP_TOOLCHAIN=1.97.1 CARGO_BUILD_JOBS=4 CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=/Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-allocation-native01/target cargo test --offline --locked --manifest-path /Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-allocation-native01/probe/Cargo.toml --all-targets &&
RUSTUP_TOOLCHAIN=1.97.1 CARGO_BUILD_JOBS=4 CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=/Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-allocation-native01/target CARGO_PROFILE_RELEASE_OPT_LEVEL=3 CARGO_PROFILE_RELEASE_LTO=fat CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1 CARGO_PROFILE_RELEASE_DEBUG=0 CARGO_PROFILE_RELEASE_STRIP=true cargo build --offline --locked --release --manifest-path /Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-allocation-native01/probe/Cargo.toml
```

Root retains real PIDs/groups, waited exits, compiler/architecture, source before/after, binary pin and every stdout/stderr. Only after all gates pass, use fresh native processes for `4096 tuple-min`, `4096 min-by`, then100000-group controls. For paired100000 measurements use UAAU order, where U=tuple-min and A=min-by, each a separate process:

```sh
/Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-allocation-native01/target/release/current-struct-aggregate-allocation-probe 100000 tuple-min
/Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-allocation-native01/target/release/current-struct-aggregate-allocation-probe 100000 min-by
/Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-allocation-native01/target/release/current-struct-aggregate-allocation-probe 100000 min-by
/Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-allocation-native01/target/release/current-struct-aggregate-allocation-probe 100000 tuple-min
```

Gate and measurement owners must check both shared locks, obtain only fresh owned locks, stop on failure, retain failed IDs/logs and never signal completed historical PIDs. Root may use its existing bounded native build owner; no new supervision framework is supplied. Nominal inputs are a fewMiB for100000groups, but runtime RSS must be measured and reported. There is no OS32GiB cap on native macOS. Compilation may use more memory/disk than the probe, and must occur separately from timings.

## Output acceptance

Every process must reach final `checks=passed` with the expected method/groups and no missing phase. Input construction is its own allocator control. Prepared batches, filters and JSON metadata lie outside accumulator phase counters. First update, identical update, improving update, sparse update, full evaluate, full/prefix state emissions and merges are measured. Every evaluated field and cardinality is checked, including retained prefix tails. The sibling tests additionally exercise reversed input order, signed extreme tie breaking, a filtered dangerous candidate and independent partial-state merging. They are authored and still need actual Cargo execution.

`preparation.json` binds copied-source, lowerer/registry and dependency sources. `source-gate01.json` records Rustfmt only. Build/ELF/macOS ABI and allocation qualification remain false until root runs the prospective gates and probes.
