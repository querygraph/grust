#!/usr/bin/env bash
# Run from a clean detached Grust checkout. Output and target must be external.
set -euo pipefail
: "${CARGO_TARGET_DIR:?set an owned external target directory}"
: "${GATE_OUTPUT:?set an absolute external output directory}"
: "${SAIL_BINARY:?set the qualified native release Sail binary}"
: "${GATE_PYTHON:?set the Python interpreter with PySpark}"
export CARGO_INCREMENTAL=0
source_commit=$(git rev-parse HEAD)
if git symbolic-ref -q HEAD >/dev/null || test -n "$(git status --porcelain)"; then
  echo 'gate requires a clean detached checkout' >&2
  exit 1
fi
mkdir -p "$GATE_OUTPUT"
df -h "$GATE_OUTPUT"
manifest=docs/reviews/grust-v2/wave-3/sketch/Cargo.toml
cargo fmt --manifest-path "$manifest" --all -- --check
cargo clippy --locked --manifest-path "$manifest" --workspace --all-targets -- -D warnings
cargo test --locked --manifest-path "$manifest" --workspace --all-targets
cargo clippy --locked --manifest-path "$manifest" --workspace --all-targets --all-features -- -D warnings
cargo test --locked --manifest-path "$manifest" --workspace --all-targets --all-features
cargo test --locked --release --manifest-path "$manifest" --workspace --all-targets
for mode in relational iterative cypher; do
  mkdir -p "$GATE_OUTPUT/$mode"
  if test "$mode" = relational; then
    cargo run --locked --release --manifest-path "$manifest" -p grust-query-qualification > "$GATE_OUTPUT/$mode/queries.json"
  else
    cargo run --locked --release --manifest-path "$manifest" -p grust-query-qualification -- "--$mode" > "$GATE_OUTPUT/$mode/queries.json"
  fi
  "$GATE_PYTHON" docs/reviews/grust-v2/wave-3/live/qualify.py --sail "$SAIL_BINARY" --manifest "$GATE_OUTPUT/$mode/queries.json" --output "$GATE_OUTPUT/$mode"
done
cargo run --locked --release --manifest-path "$manifest" -p grust-query-qualification -- --cypher-refusals > "$GATE_OUTPUT/refusals.json"
mkdir -p "$GATE_OUTPUT/memory"
printf '[]\n' > "$GATE_OUTPUT/memory/queries.json"
"$GATE_PYTHON" docs/reviews/grust-v2/wave-3/live/qualify.py --sail "$SAIL_BINARY" --manifest "$GATE_OUTPUT/memory/queries.json" --output "$GATE_OUTPUT/memory" --memory-probe
test "$(git rev-parse HEAD)" = "$source_commit"
test -z "$(git status --porcelain)"
printf 'PASSED Cypher frontend source %s: Rust default/all-features/release, native result bags and refusal controls\n' "$source_commit"
