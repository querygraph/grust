# A sort before `monotonically_increasing_id()` is removed: the ids do not follow the sort

**Kind:** wrong values, silently.

## Summary

`df.orderBy(k).withColumn("i", monotonically_increasing_id())` is the usual way to number rows in sorted order. When the consumer of that frame does not itself need the order (an aggregate, a join), the optimizer removes the sort under the id operator, and the ids no longer follow `k`. On 2,000,000 rows whose keys are 0 to 1,999,999 in scrambled order, the id should equal the key for every row. Read by an aggregate, it equals the key for 1 row.

When the same frame is written to Parquet instead, the sort is kept and all 2,000,000 ids are right. `row_number() over (order by k)` is right in both cases.

## Environment

- Sail `main` at `99ee46f69a97342e91bf7d4eaedb4509f1d8a9c2` (2026-10-02, version 0.7.2), unmodified, built with `cargo build --release --locked -p sail-cli`.
- DataFusion 55.1.0, as pinned by that commit.
- Client: PySpark 4.0.1 (Spark Connect), Python 3.12.8, pyarrow 25.0.1.
- macOS 26.2 on an Apple M1 Max. Local mode, default settings.

## Reproduce

```sh
python repro.py /path/to/release/sail
```

[`repro.py`](repro.py) starts its own server, runs the case, and stops the server. It needs `pyspark[connect]` 4.0 and `pyarrow`. The output of the run reported here is [`output.txt`](output.txt).

```python
n = 2_000_000
rows = spark.range(n).select(((F.col("id") * 7919) % n).alias("k"))   # every k once, scrambled
indexed = rows.orderBy("k").select("k", F.monotonically_increasing_id().alias("i"))
indexed.agg(F.sum(F.when(F.col("i") == F.col("k"), 1).otherwise(0)))  # expected: 2,000,000
```

## Observed

| Consumer of `orderBy(k)` + `monotonically_increasing_id()` | Rows where the id equals the key |
|---|---|
| an aggregate | **1** of 2,000,000 |
| a Parquet write, then read | 2,000,000 of 2,000,000 |
| (for comparison) `row_number() over (order by k) - 1`, read by an aggregate | 2,000,000 of 2,000,000 |

The plan of the aggregate has no `SortExec`:

```
CoalescePartitionsExec
MonotonicIdExec: col=#2
RepartitionExec: partitioning=RoundRobinBatch(10), input_partitions=1
```

## Expected

The ids are assigned in the sorted order whatever consumes the frame, as when it is written.

## Cause

`MonotonicIdExec` numbers the rows of each partition stream as they pass (`crates/sail-physical-plan/src/monotonic_id.rs`). It reports `maintains_input_order` (line 100) but does not implement `required_input_ordering`, so the default, no requirement, applies. DataFusion's sort enforcement removes a `SortExec` when nothing above it needs the order. An aggregate does not, so the sort under the id operator goes, and a round-robin repartition is put in its place.

Sail already has a way to pin a sort for order-sensitive windows and aggregates: `RequiredSortNode`, planned as a sort under an output requirement (`crates/sail-session/src/planner.rs:428`). The id function does not use it.

## Possible fix

When the input of the id operator has a sort that the user wrote, keep it: either have `MonotonicIdExec` require the ordering its input declares at planning time, or plan the user's sort through `RequiredSortNode` when an id function sits above it.

## Related upstream items

Searched in `lakehq/sail` issues and pull requests on 2026-10-02. No existing issue or pull request found. Pull request #1936 ("fix: correct monotonic_id partitioning", merged 2026-05-20) is about the operator's partitioning, not its input order. The same mechanism, an operator that depends on input order without requiring it, is behind issue #2722 (`checkpoint()` after a sort) and #2726 (a sort before a Delta write).

## Notes

- The fix is from reading the code. It was not built or tested.
- `spark_partition_id()` is not affected: it does not depend on row order.
- Workarounds: write the frame before using the id, or use `row_number() over (order by k)`.
- Separately from the dropped sort, an id taken directly over a Parquet scan differs between executions in local mode, because the scan's partition streams share files. That is within the function's documented non-determinism, but it differs from cluster mode, where a scan is repeatable.
