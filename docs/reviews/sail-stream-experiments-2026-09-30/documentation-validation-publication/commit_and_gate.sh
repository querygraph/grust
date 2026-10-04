#!/bin/sh
# Root executes only after frozen-input authorization and independent review.
# No command may follow a failed gate; candidate/exact outputs are kept separate.
set -C
cd /private/tmp/grust-sail-review-validation-docs &&
export GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 &&
python3 /private/tmp/grust-sail-review-validation-publication/guard.py candidate-before &&
python3 docs/reviews/sail-stream-experiments-2026-09-30/verify_documentation_snapshot.py --expected-head d9df4b0e89b1e4a1838b1b536d05f47ba4f12808 > /private/tmp/grust-sail-review-validation-publication/candidate-gate.log 2>&1 &&
python3 /private/tmp/grust-sail-review-validation-publication/guard.py candidate-after &&
git commit -F /private/tmp/grust-sail-review-validation-publication/commit-message.txt &&
snapshot_commit=$(git rev-parse HEAD) &&
python3 /private/tmp/grust-sail-review-validation-publication/guard.py exact-before "$snapshot_commit" &&
python3 docs/reviews/sail-stream-experiments-2026-09-30/verify_documentation_snapshot.py --expected-head "$snapshot_commit" > /private/tmp/grust-sail-review-validation-publication/exact-gate.log 2>&1 &&
python3 /private/tmp/grust-sail-review-validation-publication/guard.py exact-after "$snapshot_commit"
