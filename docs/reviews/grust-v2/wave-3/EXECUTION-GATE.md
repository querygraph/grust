# Wave 3 executable-query gate

Run in a detached checkout with its own target on Apo. This gates the unpublished compiler workspace and native Sail query boundary, not the released Grust workspace. No VM is started.

```sh
export CARGO_INCREMENTAL=0
export CARGO_TARGET_DIR=/Volumes/Apo/graph-tests/workspaces/grust-v2-wave3-20261007/execution-gate-target
manifest=docs/reviews/grust-v2/wave-3/sketch/Cargo.toml
cargo fmt --all --manifest-path "$manifest" -- --check &&
cargo clippy --workspace --all-targets --all-features --release --locked --manifest-path "$manifest" -- -D warnings &&
cargo test --workspace --all-targets --all-features --release --locked --manifest-path "$manifest" &&
cargo test --workspace --all-targets --release --locked --manifest-path "$manifest" &&
cargo run --release --locked --manifest-path "$manifest" -p grust-query-qualification > queries.json
```

Use a Python environment with PySpark 4.0.1 Connect and its dependencies, plus Ruff and mypy for the client gate:

```sh
ruff check docs/reviews/grust-v2/wave-3/live/qualify.py &&
ruff format --check docs/reviews/grust-v2/wave-3/live/qualify.py &&
mypy --strict --follow-imports=silent docs/reviews/grust-v2/wave-3/live/qualify.py &&
python docs/reviews/grust-v2/wave-3/live/qualify.py \
  --sail /path/to/qualified/native/release/sail \
  --manifest queries.json --output /absolute/path/to/cell
```

The client compares both SQL variants with independently authored expected rows, preserving multiplicity, requested order and output data types. Every failure remains in its receipt. It starts and closes only its own Sail server. Generate detailed plan explanations with `cargo run ... -p grust-query-qualification -- --explain` when needed; the default manifest retains SQL, result types, answers and every rewrite trace.

Exact tested source, verdict, runtime versions and retained attempts are appended after qualification. The original nine-test sketch gate is historical evidence in [GATE.md](GATE.md).
