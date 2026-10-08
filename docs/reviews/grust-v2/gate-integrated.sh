#!/usr/bin/env bash
# Run from a clean detached checkout; all outputs/targets must be external.
set -euo pipefail
: "${CARGO_TARGET_DIR:?set owned external target}"
: "${GATE_OUTPUT:?set owned external evidence directory}"
source_commit=$(git rev-parse HEAD)
base_commit=f568c534378676e48b37f7c9ac868a44e40d22b7
if git symbolic-ref -q HEAD >/dev/null || test -n "$(git status --porcelain)"; then
  echo 'integration gate requires a clean detached checkout' >&2
  exit 1
fi
export CARGO_INCREMENTAL=0
mkdir -p "$GATE_OUTPUT"
df -h "$GATE_OUTPUT"
# Released library source/manifests match base; the legacy benchmark fixture is corrected.
git diff --exit-code "$base_commit" HEAD -- Cargo.toml Cargo.lock crates \
  ':(exclude)crates/grust-cypher/benches/cypher_pipeline.rs'
cargo fmt --all -- --check
cargo clippy --locked -p grust-cypher --all-targets -- -D warnings
cargo test --locked -p grust-cypher --all-targets
wave2=docs/reviews/grust-v2/wave-2/sketch/Cargo.toml
cargo fmt --manifest-path "$wave2" --all -- --check
cargo clippy --locked --manifest-path "$wave2" --workspace --all-targets --all-features -- -D warnings
cargo test --locked --release --manifest-path "$wave2" --workspace --all-features
cargo test --locked --release --manifest-path "$wave2" --workspace
cargo run --locked --release --manifest-path "$wave2" -p grust-programmatic --example people
bash docs/reviews/grust-v2/wave-3/live/gate-semantics.sh
test "$(git rev-parse HEAD)" = "$source_commit"
test -z "$(git status --porcelain)"
printf 'PASSED integrated Wave 2/3 source %s on main base %s: production parser, both draft workspaces and native semantics/SNB oracle; HEAD unchanged and clean\n' "$source_commit" "$base_commit"
