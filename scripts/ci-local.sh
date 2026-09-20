#!/usr/bin/env bash
# The `workspace` GitHub workflow, run on this machine. Use it on Linux (hosts
# grust and quegee) while the hosted workflows are paused, and paste its last
# line into the pull request. Keep it in step with
# .github/workflows/workspace.yml: same gates, same order.
#
#   scripts/ci-local.sh            every gate
#   scripts/ci-local.sh --fast     stop before package verification, the slowest
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$repo"
fast=${1:-}

# As in the workflow: line tables keep file and line in a backtrace and cut the
# build from 64 GB to 29 GB.
export CARGO_PROFILE_DEV_DEBUG=line-tables-only
export CARGO_PROFILE_TEST_DEBUG=line-tables-only
export CARGO_TERM_COLOR=${CARGO_TERM_COLOR:-always}

started=$(date +%s)
gate() {
    printf '\n==> %s\n' "$1"
    shift
    "$@"
}

if [[ "$(uname -s)" != Linux ]]; then
    echo "ci-local.sh: this is $(uname -s). Two defects this month showed only on" \
        "Linux; a pass here is not the workflow's verdict." >&2
fi

gate "Formatting" cargo fmt --all -- --check
gate "Graph benchmark formatting" cargo fmt --manifest-path benchmarks/lsqb/Cargo.toml -- --check
gate "Workspace build" cargo build --locked --workspace --all-features
gate "Workspace Clippy" cargo clippy --locked --workspace --all-features --all-targets -- -D warnings
gate "Graph benchmark Clippy" cargo clippy --locked --manifest-path benchmarks/lsqb/Cargo.toml --all-targets -- -D warnings
# LadybugDB bundles zstd; tested with the workspace it links zstd twice on Linux.
gate "Workspace tests" cargo test --locked --workspace --all-features --exclude grust-ladybug
gate "Ladybug tests" cargo test --locked -p grust-ladybug
gate "Pinned LSQB sources" benchmarks/lsqb/fetch-upstream.sh
# One attempt, not the workflow's three: on a machine you control, a timing
# failure is worth seeing. See docs/LSQB_RUNNER_TIMING_FLAKES.md.
gate "Graph benchmark tests" cargo test --locked --manifest-path benchmarks/lsqb/Cargo.toml

if [[ "$fast" == --fast ]]; then
    echo
    echo "ci-local: PASSED (fast: package verification and attribution skipped)" \
        "at $(git rev-parse --short HEAD) on $(uname -sm) in $(( $(date +%s) - started ))s"
    exit 0
fi

gate "Release package verification" cargo package --locked --workspace --allow-dirty
gate "Third-party package attribution" bash scripts/verify-package-attribution.sh

dirty=$([[ -n "$(git status --porcelain)" ]] && echo " (dirty tree)" || true)
echo
echo "ci-local: PASSED every gate at $(git rev-parse --short HEAD)${dirty}" \
    "on $(uname -sm) in $(( $(date +%s) - started ))s"
