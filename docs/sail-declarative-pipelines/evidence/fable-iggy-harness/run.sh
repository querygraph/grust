#!/bin/zsh
# Builds and runs the Fable Iggy scenarios against the pinned broker binary, reusing the pin's target dir.
set -u
export PKG_CONFIG_PATH=/opt/homebrew/lib/pkgconfig
export CARGO_INCREMENTAL=0
export CARGO_TARGET_DIR=/Users/alexy/src/iggy-fable-pin-target
cd "$(dirname "$0")"
cargo test --release -- --test-threads=1 --nocapture "$@"
