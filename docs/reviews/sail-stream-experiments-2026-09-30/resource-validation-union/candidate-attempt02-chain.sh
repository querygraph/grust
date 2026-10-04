#!/bin/sh
# Every mutation is conditional on the full frozen union gate and source guard.
/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/bin/python -B \
  /Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30/resource-validation-union/run_gate.py \
  --repo /private/tmp/sail-resource-validation-union-gate \
  --output /Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30/resource-validation-union/candidate-gate02 \
  --target-root /private/tmp/sail-resource-validation-union-target \
  --head 200d1cf8eb1db5e9057e09e071ebd57391f4b376 \
  --tree d43293b4e5de64878c85c1d3d756077e2b7b749b \
  --sql-helper /Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30/resource-validation-union/sql_gate.py \
  --sql-helper-sha256 0aca81a5819f29095d2592804aea836250d7640de917ce7d959a264ec80f124e &&
python3 -B /Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30/resource-validation-union/guard_commit.py &&
git -C /private/tmp/sail-stream-review-followup commit -F \
  /Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30/resource-validation-union/commit-message.txt
