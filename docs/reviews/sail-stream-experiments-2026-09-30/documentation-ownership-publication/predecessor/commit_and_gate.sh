#!/bin/sh
# Root executes only after frozen-input authorization and independent review.
# No command may follow a failed gate; candidate/exact outputs are kept separate.
set -C
cd /private/tmp/grust-sail-review-ownership-docs &&
export GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 &&
python3 /private/tmp/grust-sail-review-ownership-publication/guard.py candidate-before &&
python3 docs/reviews/sail-stream-experiments-2026-09-30/verify_documentation_snapshot.py --expected-head 980da04151cd5860017a06580a658bdf7e133c40 > /private/tmp/grust-sail-review-ownership-publication/candidate-gate.log 2>&1 &&
python3 /private/tmp/grust-sail-review-ownership-publication/guard.py candidate-after &&
git commit -F /private/tmp/grust-sail-review-ownership-publication/commit-message.txt &&
snapshot_commit=$(git rev-parse HEAD) &&
python3 /private/tmp/grust-sail-review-ownership-publication/guard.py exact-before "$snapshot_commit" &&
python3 docs/reviews/sail-stream-experiments-2026-09-30/verify_documentation_snapshot.py --expected-head "$snapshot_commit" > /private/tmp/grust-sail-review-ownership-publication/exact-gate.log 2>&1 &&
python3 /private/tmp/grust-sail-review-ownership-publication/guard.py exact-after "$snapshot_commit"
