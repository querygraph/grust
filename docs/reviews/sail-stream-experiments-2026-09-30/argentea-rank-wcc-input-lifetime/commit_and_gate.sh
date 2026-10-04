#!/bin/sh
# Candidate gate and precommit guard must both succeed before the named commit.
set -C
export PYTHONDONTWRITEBYTECODE=1 GIT_OPTIONAL_LOCKS=0
base=a3462345a6764096024c055dc4d105a3c634e5a4
tree=27816af17601af202307268bc79633130d458b36
out=/Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30/argentea-rank-wcc-input-lifetime
repo=/private/tmp/sail-argentea-rank-wcc-input-lifetime
gate=/private/tmp/sail-rank-wcc-lifetime-gate
target=/private/tmp/sail-rank-wcc-lifetime-target
python3 "$out/run_gate.py" --repo "$gate" --output "$out/candidate-gate" --head "$base" --tree "$tree" --target-root "$target" &&
python3 "$out/verify_precommit.py" &&
git -C "$repo" commit -F "$out/commit-message.txt" &&
commit=$(git -C "$repo" rev-parse HEAD) &&
git -C "$gate" checkout --detach "$commit" &&
python3 "$out/run_gate.py" --repo "$gate" --output "$out/exact-gate" --head "$commit" --tree "$tree" --target-root "$target" --exact
