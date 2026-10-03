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
# The commit this run is about. If HEAD moves before the gates finish, because
# someone committed or pulled in this checkout, the gates tested a mixture and
# the line at the end would name a commit that was never tested. Both Linux hosts
# met this while appending to codex-to-codex.md from the checkout a gate was
# running in. Run gates in a worktree of their own:
#   git worktree add --detach ../grust-gate <commit> && cd ../grust-gate
tested=$(git rev-parse HEAD)
verdict() {
    local now
    now=$(git rev-parse HEAD)
    if [[ "$now" != "$tested" ]]; then
        echo
        echo "ci-local: NO VERDICT. HEAD was ${tested:0:7} when the gates began and is" \
            "${now:0:7} now, so they did not test one commit. Rerun in a worktree of its own." >&2
        exit 2
    fi
    local dirty=""
    [[ -n "$(git status --porcelain)" ]] && dirty=" (dirty tree)"
    echo
    echo "ci-local: PASSED $1 at ${tested:0:7}${dirty} on $(uname -sm) in $(( $(date +%s) - started ))s"
}
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
    verdict "(fast: package verification and attribution skipped)"
    exit 0
fi

gate "Release package verification" cargo package --locked --workspace --allow-dirty
gate "Third-party package attribution" bash scripts/verify-package-attribution.sh

verdict "every gate"
