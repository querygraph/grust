#!/bin/sh
# All mutations are conditional on the reviewed candidate and successful gate.
cd /private/tmp/grust-sail-review-closed2-docs &&
PYTHONDONTWRITEBYTECODE=1 python3 /private/tmp/grust-sail-review-closed2-publication/guard.py candidate-before &&
PYTHONDONTWRITEBYTECODE=1 python3 docs/reviews/sail-stream-experiments-2026-09-30/verify_documentation_snapshot.py --expected-head 7387b985f242164281c7d94a1560bbfcfa8d8fe5 > /private/tmp/grust-sail-review-closed2-publication/candidate-gate.log 2>&1 &&
PYTHONDONTWRITEBYTECODE=1 python3 /private/tmp/grust-sail-review-closed2-publication/guard.py candidate-after &&
PYTHONDONTWRITEBYTECODE=1 python3 docs/reviews/sail-stream-experiments-2026-09-30/closed-cell-audit/test_audit_cell.py > /private/tmp/grust-sail-review-closed2-publication/closed-helper-gate.log 2>&1 &&
PYTHONDONTWRITEBYTECODE=1 python3 docs/reviews/sail-stream-experiments-2026-09-30/host-closure-collector-review/test_collector_portable.py > /private/tmp/grust-sail-review-closed2-publication/closure-helper-gate.log 2>&1 &&
git commit -F /private/tmp/grust-sail-review-closed2-publication/commit-message.txt &&
snapshot_commit=$(git rev-parse HEAD) &&
PYTHONDONTWRITEBYTECODE=1 python3 /private/tmp/grust-sail-review-closed2-publication/guard.py exact-before "$snapshot_commit" &&
PYTHONDONTWRITEBYTECODE=1 python3 docs/reviews/sail-stream-experiments-2026-09-30/verify_documentation_snapshot.py --expected-head "$snapshot_commit" > /private/tmp/grust-sail-review-closed2-publication/exact-gate.log 2>&1 &&
PYTHONDONTWRITEBYTECODE=1 python3 /private/tmp/grust-sail-review-closed2-publication/guard.py exact-after "$snapshot_commit"
