#!/bin/sh
# All mutations are conditional on the reviewed candidate and successful gate.
cd /private/tmp/grust-sail-review-interim2-docs &&
PYTHONDONTWRITEBYTECODE=1 python3 /private/tmp/grust-sail-review-interim2-publication/guard.py candidate-before &&
PYTHONDONTWRITEBYTECODE=1 python3 docs/reviews/sail-stream-experiments-2026-09-30/verify_documentation_snapshot.py --expected-head 7bb00a299db9a24c35a47022614d6f572309b9a2 > /private/tmp/grust-sail-review-interim2-publication/candidate-gate.log 2>&1 &&
PYTHONDONTWRITEBYTECODE=1 python3 /private/tmp/grust-sail-review-interim2-publication/guard.py candidate-after &&
git commit -F /private/tmp/grust-sail-review-interim2-publication/commit-message.txt &&
snapshot_commit=$(git rev-parse HEAD) &&
PYTHONDONTWRITEBYTECODE=1 python3 /private/tmp/grust-sail-review-interim2-publication/guard.py exact-before "$snapshot_commit" &&
PYTHONDONTWRITEBYTECODE=1 python3 docs/reviews/sail-stream-experiments-2026-09-30/verify_documentation_snapshot.py --expected-head "$snapshot_commit" > /private/tmp/grust-sail-review-interim2-publication/exact-gate.log 2>&1 &&
PYTHONDONTWRITEBYTECODE=1 python3 /private/tmp/grust-sail-review-interim2-publication/guard.py exact-after "$snapshot_commit"
