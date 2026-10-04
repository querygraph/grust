# `EXPLAIN` fails for a sort-merge join that executes correctly

**Kind:** `EXPLAIN` failure; execution is unaffected.

## Summary

With `optimizer.prefer_hash_join` set to false, `EXPLAIN` of a join between two multi-partition inputs fails:

```
Physical plan error: error in DataFusion: Invariant for ExecutionPlan node 'SortMergeJoinExec' failed
caused by
Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned.
```

The same query executes and returns the right rows. Every variant fails: `DataFrame.explain`, `EXPLAIN`, `EXPLAIN EXTENDED`, `EXPLAIN FORMATTED`, `EXPLAIN ANALYZE`.

## Environment

- Sail `main` at `99ee46f69a97342e91bf7d4eaedb4509f1d8a9c2` (2026-10-02, version 0.7.2), unmodified, built with `cargo build --release --locked -p sail-cli`.
- DataFusion 55.1.0, as pinned by that commit.
- Client: PySpark 4.0.1 (Spark Connect), Python 3.12.8, pyarrow 25.0.1.
- macOS 26.2 on an Apple M1 Max. Local mode, with `SAIL_OPTIMIZER__PREFER_HASH_JOIN=false`.

## Reproduce

```sh
python repro.py /path/to/release/sail
```

[`repro.py`](repro.py) starts its own server, runs the case, and stops the server. It needs `pyspark[connect]` 4.0 and `pyarrow`. The output of the run reported here is [`output.txt`](output.txt).

Two Parquet directories of 1,000,000 rows each, joined on an equality.

## Observed

| Step | Result |
|---|---|
| `a.join(b, a.a == b.b).count()` | 1,000,000 |
| `DataFrame.explain()` | the error above |
| `EXPLAIN`, `EXTENDED`, `FORMATTED`, `ANALYZE` | the error above |

It does not fail when both inputs already have a single partition, or the same hash partitioning, before optimization.

## Expected

`EXPLAIN` prints the plan that would execute.

## Cause

`crates/sail-plan/src/explain.rs:215-222` builds the initial physical plan with a session state whose physical optimizer rule list is empty. DataFusion's planner still ends with its invariant check for an executable plan, and a sort-merge join needs co-partitioned inputs, which only the optimizer's distribution enforcement establishes. Execution uses the full optimizer and passes.

## Possible fix

Do not run the executable-plan invariant on the unoptimized plan that `EXPLAIN` builds for display, or build that plan with the distribution and sorting enforcement rules kept.

## Related upstream items

Searched in `lakehq/sail` issues and pull requests on 2026-10-02.

No existing issue or pull request found. The option was exposed by pull request #2451 (merged 2026-08-20).

## Notes

- A workaround to see the plan: in `local-cluster` mode with `RUST_LOG=warn,sail_execution::driver::job_scheduler::core=debug` the driver logs each executed plan.
