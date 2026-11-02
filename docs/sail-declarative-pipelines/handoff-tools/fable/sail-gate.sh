#!/bin/zsh
# Detached exact-commit gate for the Fable Sail branch. Usage: sail-gate.sh <sha> [<sha>...]
# Own worktree, own target dir, own venv; verdict names the commit and refuses to print one if HEAD moved.
set -u
SRC=/Users/alexy/src/sail-sdp-fable
GATE=/Users/alexy/src/sail-sdp-fable-gate
TARGET=/Users/alexy/src/sail-sdp-fable-gate-target
VENV=/Users/alexy/src/sail-sdp-fable-gate-venv
export CARGO_INCREMENTAL=0 RUSTUP_TOOLCHAIN=1.98.1 CARGO_TARGET_DIR=$TARGET
unset SPARK_REMOTE
if [ ! -d "$GATE" ]; then git -C "$SRC" worktree add --detach "$GATE" "$1" || exit 2; fi
if [ ! -x "$VENV/bin/python" ]; then
  uv venv --python 3.12 "$VENV" || exit 2
  uv pip freeze --python "$SRC/.venvs/fable-spark-4.2.1/bin/python" | grep -v '^pysail' | grep -v '^-e' > "$VENV/requirements.txt"
  uv pip install --python "$VENV/bin/python" -r "$VENV/requirements.txt" maturin || exit 2
fi
for SHA in "$@"; do
  echo "=== gate $SHA start $(date -u +%Y-%m-%dT%H:%M:%SZ) host=$(hostname) rustc=$(rustc +1.98.1 --version)"
  git -C "$GATE" checkout --detach -q "$SHA" || { echo "checkout failed"; continue; }
  START=$(git -C "$GATE" rev-parse HEAD)
  cd "$GATE" || exit 2
  df -h "$TARGET" 2>/dev/null | tail -1 || df -h "$GATE" | tail -1
  cargo +nightly fmt --check -p sail-common -p sail-common-datafusion -p sail-spark-connect; FMT=$?
  cargo clippy -p sail-common -p sail-common-datafusion -p sail-spark-connect --all-targets --all-features -- -D warnings >/dev/null 2>&1; CLIPPY=$?
  cargo test -p sail-common --lib root_lowercase 2>&1 | grep "^test result"; COMMON=${pipestatus[1]}
  cargo test -p sail-common-datafusion --lib 2>&1 | grep "^test result"; COMMONDF=${pipestatus[1]}
  cargo test -p sail-spark-connect --lib pipelines:: 2>&1 | grep "^test result"; RUST=${pipestatus[1]}
  VIRTUAL_ENV=$VENV "$VENV/bin/maturin" develop --uv >/dev/null 2>&1; MATURIN=$?
  "$VENV/bin/python" -m pytest python/pysail/tests/spark/pipelines -q -p no:cacheprovider 2>&1 | tail -1; PYTEST=${pipestatus[1]}
  END=$(git -C "$GATE" rev-parse HEAD)
  if [ "$START" != "$END" ]; then echo "HEAD moved during gate: no verdict"; continue; fi
  echo "VERDICT commit=$END fmt=$FMT clippy=$CLIPPY rust_common=$COMMON rust_common_datafusion=$COMMONDF rust_pipelines=$RUST maturin=$MATURIN pytest_pipelines=$PYTEST at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
done
