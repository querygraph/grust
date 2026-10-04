#!/bin/sh
set -C
export PYTHONDONTWRITEBYTECODE=1 GIT_OPTIONAL_LOCKS=0
out=/Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30/sssp-candidate-buffer-reuse
repo=/private/tmp/sail-sssp-candidate-buffer-reuse
gate=/private/tmp/sail-sssp-candidate-buffer-gate
target=/private/tmp/sail-sssp-candidate-target
python3 "$out/run_gate.py" --repo "$gate" --output "$out/candidate-gate" --head 33adfce1d2ab77c3e108aa542f7eda80dd5f5cf9 --tree 5abc3e30eadb878402b3a90bcbeb0a48ac8c4b25 --target-root "$target" &&
python3 "$out/verify_precommit.py" &&
git -C "$repo" commit -F "$out/commit-message.txt" &&
commit=$(git -C "$repo" rev-parse HEAD) &&
git -C "$gate" checkout --detach "$commit" &&
python3 "$out/run_gate.py" --repo "$gate" --output "$out/exact-gate" --head "$commit" --tree 5abc3e30eadb878402b3a90bcbeb0a48ac8c4b25 --target-root "$target" --exact
