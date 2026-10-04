#!/bin/sh
# All mutations are conditional on the reviewed candidate and successful gate.
cd /private/tmp/grust-sail-review-interim-docs &&
PYTHONDONTWRITEBYTECODE=1 python3 /private/tmp/grust-sail-review-interim-publication/guard.py candidate-before &&
PYTHONDONTWRITEBYTECODE=1 python3 docs/reviews/sail-stream-experiments-2026-09-30/verify_documentation_snapshot.py --expected-head b478e57cb34220c1f671dca7ce92b2b061867855 > /private/tmp/grust-sail-review-interim-publication/candidate-gate.log 2>&1 &&
PYTHONDONTWRITEBYTECODE=1 python3 /private/tmp/grust-sail-review-interim-publication/guard.py candidate-after &&
git commit -F /private/tmp/grust-sail-review-interim-publication/commit-message.txt &&
snapshot_commit=$(git rev-parse HEAD) &&
PYTHONDONTWRITEBYTECODE=1 python3 /private/tmp/grust-sail-review-interim-publication/guard.py exact-before "$snapshot_commit" &&
PYTHONDONTWRITEBYTECODE=1 python3 docs/reviews/sail-stream-experiments-2026-09-30/verify_documentation_snapshot.py --expected-head "$snapshot_commit" > /private/tmp/grust-sail-review-interim-publication/exact-gate.log 2>&1 &&
PYTHONDONTWRITEBYTECODE=1 python3 /private/tmp/grust-sail-review-interim-publication/guard.py exact-after "$snapshot_commit"
