# Native draft workspace gate

This gate covers only the unpublished Wave 3 standalone workspace, not the production Grust workspace or a live Sail query. Use a detached checkout and its own target directory on Apo; disable incremental compilation.

```sh
export CARGO_INCREMENTAL=0
export CARGO_TARGET_DIR=/Volumes/Apo/graph-tests/workspaces/grust-v2-wave3-20261007/gate-target
manifest=docs/reviews/grust-v2/wave-3/sketch/Cargo.toml
cargo fmt --all --manifest-path "$manifest" -- --check &&
cargo clippy --workspace --all-targets --all-features --release --locked --manifest-path "$manifest" -- -D warnings &&
cargo test --workspace --all-targets --all-features --release --locked --manifest-path "$manifest" &&
cargo test --workspace --all-targets --release --locked --manifest-path "$manifest"
```

The gate log and exact source tree/commit receipt are recorded during qualification. The intended controls cover metadata semantics, not runtime execution, concurrency or benchmark speed.

## Observed verdict

UTC: 2026-10-07T18:23:39.115979+00:00

`PASSED Wave 3 draft gate at 3d9691c47b8b637e1bb96d675482a320189258e0 on Darwin x86_64`: fmt, release Clippy (all targets/features), nine release tests with all features and nine with default features. Exact detached HEAD unchanged and clean after the gate. No live Sail execution was tested.

[Native log](evidence/native-source-gate.log). Toolchain: `rustc 1.98.1 (48a229cea 2026-09-01)`.
