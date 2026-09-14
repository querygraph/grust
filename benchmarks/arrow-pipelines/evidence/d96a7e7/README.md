# Empty-SUM correction qualification

Clean source d96a7e7 on Capitola, 2026-09-14. Exact source, binary hash,
commands, environment and resource boundary are recorded in `status.json`.

- All 54 engine checks passed across five optimized profiles. Both previously
  mismatching empty-SUM fixtures now produce integer zero in Cypher and SQL.
- Cypher package tests: 868 passed, zero failed, two ignored.
- Cypher all-feature/all-target Clippy passed with warnings denied.
- Optimized standalone harness build passed.

Raw before-fix evidence remains in the sibling `09fa41e` and `c3bd9fb`
directories. This qualifies the correction on these fixtures, not general
Cypher/DataFusion equivalence. Timings retain all trials and the same distinct
execution-class and memory-accounting boundaries as the baseline. This is a
semantic correction, not a claimed performance improvement.

Workspace/package qualification and the named crate/book release remain pending.
