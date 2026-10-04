#!/usr/bin/env bash
# Run scripts/ci-local.sh on x86-64 Linux inside a container, from a Mac.
#
# Written 2026-09-23, when the Linux gate hosts were shut down. On an Intel Mac
# this is real x86-64 Linux — glibc, Linux threads, /proc, the same architecture
# the retired hosts ran — so it catches the class of defect ci-local.sh warns
# about when run on macOS. On an Apple Silicon Mac it is arm64 Linux instead:
# still Linux, no longer the same codegen, and the script says which it was.
#
# What it is not: a dedicated host. The machine is shared with a desktop, the
# container's CPU and memory are a slice of it, and a laptop or an iMac may
# throttle under sustained load. No timing from this script is publishable;
# AGENTS.md publishes absolutes from a dedicated host only. It produces a
# verdict about correctness, not about speed.
#
#   scripts/gate-linux-container.sh <commit>            every gate
#   scripts/gate-linux-container.sh <commit> --fast     stop before packaging
#
# Environment:
#   GATE_DIR    where clones and target directories live (default ~/gates-local)
#   GATE_IMAGE  container image (default rust:1-bookworm)
#   GATE_CPUS   container CPUs (default: half the machine's, min 4)
#   GATE_MEM    container memory (default 32g; the workspace build peaks near 29g
#               with line-tables-only debug info, which ci-local.sh sets)
set -euo pipefail

commit=${1:?usage: gate-linux-container.sh <commit> [--fast]}
fast=${2:-}
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
dir=${GATE_DIR:-$HOME/gates-local}
image=${GATE_IMAGE:-rust:1-bookworm}
mem=${GATE_MEM:-32g}
if [[ -z ${GATE_CPUS:-} ]]; then
    total=$(sysctl -n hw.ncpu 2>/dev/null || nproc)
    GATE_CPUS=$(( total / 2 )); (( GATE_CPUS < 4 )) && GATE_CPUS=4
fi

command -v docker >/dev/null || { echo "gate-linux-container.sh: docker is not on PATH" >&2; exit 2; }
sha=$(git -C "$repo" rev-parse "$commit")

# A clone of its own, never the working checkout: a gate whose HEAD moves under
# it tests a mixture, and ci-local.sh refuses to print a verdict when it does.
# Clone rather than `git worktree add` because a worktree's .git is a pointer
# into this repository, which the container cannot follow.
work=$dir/$sha
if [[ ! -d $work/.git ]]; then
    mkdir -p "$dir"
    git clone --quiet --no-hardlinks "$repo" "$work"
fi
git -C "$work" fetch --quiet "$repo" "$sha"
git -C "$work" checkout --quiet --detach "$sha"
mkdir -p "$dir/target-$sha" "$dir/cargo-registry"

echo "gate-linux-container.sh: $sha at ${sha:0:7}, image $image, ${GATE_CPUS} cpus, $mem," \
     "started $(date -u +%H:%MZ)"

# CARGO_INCREMENTAL=0: a gate never reuses incremental state, and it cost 39 GB
# on the retired hosts. The registry is shared between runs so a gate does not
# re-download the index; the target directory is per commit so one gate's
# artefacts cannot be mistaken for another's.
docker run --rm \
    --platform linux/amd64 \
    --cpus "$GATE_CPUS" --memory "$mem" --memory-swap "$mem" \
    -v "$work":/repo \
    -v "$dir/target-$sha":/target \
    -v "$dir/cargo-registry":/usr/local/cargo/registry \
    -e CARGO_TARGET_DIR=/target \
    -e CARGO_INCREMENTAL=0 \
    -e CARGO_TERM_COLOR=always \
    -w /repo \
    "$image" \
    bash -c 'git config --global --add safe.directory /repo && exec bash scripts/ci-local.sh '"$fast"
