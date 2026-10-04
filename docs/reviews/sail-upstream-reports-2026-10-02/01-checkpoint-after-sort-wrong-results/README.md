# `checkpoint()` after a sort returns wrong results

**Kind:** wrong results, silently.

## Summary

`DataFrame.checkpoint()` taken after `sortWithinPartitions(k)` or `orderBy(k)` gives a frame that answers later queries wrongly. On 4,000,000 rows with 1,000,003 distinct keys, `GROUP BY k` over the checkpoint returns 4,000,000 groups and `SELECT DISTINCT k` returns 4,000,000 keys. There is no error and no warning, and the settings are the defaults.

The checkpoint records that its data is sorted by `k`. The files it writes are not sorted, because the optimizer removes the sort before the write. Every later plan trusts the recorded order.

## Environment

- Sail `main` at `99ee46f69a97342e91bf7d4eaedb4509f1d8a9c2` (2026-10-02, version 0.7.2), unmodified, built with `cargo build --release --locked -p sail-cli`.
- DataFusion 55.1.0, as pinned by that commit.
- Client: PySpark 4.0.1 (Spark Connect), Python 3.12.8, pyarrow 25.0.1.
- macOS 26.2 on an Apple M1 Max. Local mode, with `SAIL_EXECUTION__CHECKPOINT__PATH` set to a local directory.

## Reproduce

```sh
python repro.py /path/to/release/sail
```

[`repro.py`](repro.py) starts its own server, runs the case, and stops the server. It needs `pyspark[connect]` 4.0 and `pyarrow`. The output of the run reported here is [`output.txt`](output.txt).

The frame:

```python
rows = spark.range(4_000_000).select(
    ((F.col("id") * 2654435761) % 1_000_003).alias("k"), F.col("id").alias("v"))
```

## Observed

| Checkpoint taken after | Rows | `GROUP BY k`: groups | `DISTINCT k` | |
|---|---|---|---|---|
| (no checkpoint) | 4,000,000 | 1,000,003 | 1,000,003 | |
| `repartition(10, k)` | 4,000,000 | 1,000,003 | 1,000,003 | correct |
| `repartition(10, k).sortWithinPartitions(k)` | 4,000,000 | **4,000,000** | **4,000,000** | wrong |
| `orderBy(k)` | 4,000,000 | **3,960,618** | **3,960,618** | wrong |

The wrong aggregate's plan has no sort and aggregates in sorted mode:

```
AggregateExec: mode=SinglePartitioned, gby=[#0@0 as #0], aggr=[count(Int64(1))], ordering_mode=Sorted
```

A sorted-mode aggregate closes a group when the key changes. Over unsorted input it emits a new group at each change.

Reading the checkpoint's Parquet files directly shows that none is sorted by `k`. The `orderBy` count varies a little between runs; that it is wrong does not.

With `SAIL_OPTIMIZER__PREFER_HASH_JOIN=false` a join on `k` between the sorted checkpoint and a sorted checkpoint of the 1,000,003 keys becomes a sort-merge join with no `SortExec`, and returns **139 rows instead of 4,000,000** (the reproducer's last line). The same join over the unsorted checkpoint returns 4,000,000. With the default hash join the join is correct, because it does not use the order.

## Expected

The same answers as over the frame before the checkpoint.

## Cause

1. **The order is recorded before the optimizer runs.** `crates/sail-session/src/planner.rs:195-200` builds the checkpoint command during physical planning and takes `input.output_ordering()` and `input.output_partitioning()` from the unoptimized physical input. The user's `SortExec` is still there, so the order is recorded.
2. **The writer does not ask for that order.** `RemoteCheckpointWriteExec` (`crates/sail-physical-plan/src/remote_checkpoint.rs:478`) implements neither `required_input_ordering` nor `maintains_input_order`. DataFusion's sort enforcement treats a `SortExec` under such a node as unnecessary and removes it.
3. **The recorded order is carried to the committed checkpoint unchanged** (`remote_checkpoint.rs:334-353`) and declared by every later scan of it (`planner.rs:335-336`).

The existing test of this behaviour, `test_checkpoint_preserves_partitioning_and_ordering` (`python/pysail/tests/spark/dataframe/test_checkpoint.py:145-160`), compares plan snapshots, not results, so it passes.

## Possible fix

Any one of these:

1. Give `RemoteCheckpointWriteExec` the recorded ordering as its `required_input_ordering`, and have it report `maintains_input_order`. The sort then stays, the files are sorted, and the declaration is true.
2. Record ordering and partitioning from the writer's optimized input when the write runs, not from the unoptimized plan. A dropped sort is then not recorded.
3. As a stopgap, record no ordering.

A regression test should compare query results over the checkpoint with the same queries over the source frame, for `sortWithinPartitions` and for `orderBy`.

## Related upstream items

Searched in `lakehq/sail` issues and pull requests on 2026-10-02.

No existing issue or pull request found. The feature was added by pull request #2270 (merged 2026-07-29); its review thread does not discuss the recorded order.

## Notes

- The fixes are from reading the code. None was built or tested.
- `localCheckpoint()` was not run. It goes through the same planner code.
- The same wrong results were seen in `local-cluster` mode. No multi-process cluster was run.
