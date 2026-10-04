#!/bin/sh
# Candidate gate and precommit guard must both succeed before the named commit.
set -C
export PYTHONDONTWRITEBYTECODE=1 GIT_OPTIONAL_LOCKS=0
base=a41cbd8dd5cbd6eb9f8c09c7019391999efae6d4
tree=3f4399056199b49708340abf0b4d1205fca860dd
out=/Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30/argentea-rank-wcc-input-lifetime
repo=/private/tmp/sail-argentea-rank-wcc-input-lifetime
gate=/private/tmp/sail-rank-wcc-lifetime-gate
target=/private/tmp/sail-rank-wcc-lifetime-target
python3 "$out/run_extended_gate.py" --repo "$gate" --output "$out/extended-candidate-gate" --head "$base" --tree "$tree" --target-root "$target" &&
python3 "$out/verify_extended_precommit.py" &&
git -C "$repo" commit -F "$out/extended-commit-message.txt" &&
commit=$(git -C "$repo" rev-parse HEAD) &&
git -C "$gate" checkout --detach "$commit" &&
python3 "$out/run_extended_gate.py" --repo "$gate" --output "$out/extended-exact-gate" --head "$commit" --tree "$tree" --target-root "$target" --exact
