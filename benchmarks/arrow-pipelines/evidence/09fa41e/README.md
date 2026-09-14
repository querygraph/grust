# Optimized relational baseline

Clean source 09fa41e71d4c9797c6fbff68e0d81872348cfe96, Capitola,
2026-09-14. `status.json` records binary SHA-256, host, toolchain, commands and
exit statuses. `build.log` records successful optimized compilation; `runner.py`
records execution and attribution checks. The preserved binary is on Capitola
under `/tmp/grust-relational-baseline/20260914T164956Z/`.

All 36 answers across the two larger fixtures matched independent oracles.
The small fixtures retained two empty-SUM mismatches, now classified as
mismatches with actual null values. No timeout or resource cutoff was applied.

Median query seconds across three trials (first-use observations retained):

| Nodes | Workload | Indexed Cypher | Explicit DataFusion SQL |
| --- | --- | ---: | ---: |
| 2,000 | Node aggregate | 0.001531 | 0.000944 |
| 2,000 | One-hop aggregate | 0.032503 | 0.002312 |
| 2,000 | Two-hop trail aggregate | 0.303606 | 0.004967 |
| 20,000 | Node aggregate | 0.024527 | 0.001261 |
| 20,000 | One-hop aggregate | 0.319759 | 0.003801 |
| 20,000 | Two-hop trail aggregate | 4.422547 | 0.022803 |

These are **distinct execution classes**, including query parse/plan/execution
and complete result consumption. SQL is explicitly authored, not automatically
lowered from Cypher. Three observations are descriptive, not a confidence claim.

At 20,000 nodes, preparation took 58.25 ms for fixture creation, 15.01 ms for
typed indexing, 47.84 ms for graph-to-Arrow conversion and 0.44 ms for session
registration. Full-process maximum RSS was 10,449,272,832 bytes; at 2,000 nodes it
was 1,082,294,272 bytes. Both engines and all input representations coexist, so
these are not per-engine memory measurements. The 256 MiB DataFusion working
pool excludes retained input and does not cap Cypher or the entire process.

Source inspection shows ordinary MATCH materializes candidates before WHERE
and RETURN. The measurements motivate profiling this expansion and materialization
cost and testing generalized relational execution. They do not establish a
universal backend speedup, equivalent resource envelopes, or complete semantics.
