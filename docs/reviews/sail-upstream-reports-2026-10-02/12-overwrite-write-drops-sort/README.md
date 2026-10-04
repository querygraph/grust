# A sort before a Parquet write is dropped with `mode("overwrite")`

**Kind:** silent behaviour difference between save modes. No wrong query results.

## Summary

`df.orderBy(k).write.parquet(path)` writes files sorted by `k`. The same write with `.mode("overwrite")` writes unsorted files. The same holds for `repartition(n, k).sortWithinPartitions(k)`. Nothing reports that the sort was dropped. Anyone who sorts to get clustered files for min/max pruning, and overwrites the output, as any re-run does, silently loses the clustering.

## Environment

- Sail `main` at `99ee46f69a97342e91bf7d4eaedb4509f1d8a9c2` (2026-10-02, version 0.7.2), unmodified, built with `cargo build --release --locked -p sail-cli`.
- DataFusion 55.1.0, as pinned by that commit.
- Client: PySpark 4.0.1 (Spark Connect), Python 3.12.8, pyarrow 25.0.1.
- macOS 26.2 on an Apple M1 Max. Local mode, default settings.

## Reproduce

```sh
python repro.py /path/to/release/sail
```

[`repro.py`](repro.py) starts its own server, writes 1,000,000 rows with a scrambled key four ways, and reads every data file back with pyarrow. It needs `pyspark[connect]` 4.0 and `pyarrow`. The output of the run reported here is [`output.txt`](output.txt).

## Observed

| Write | Files sorted by `k` |
|---|---|
| `orderBy(k).write.parquet(path)` | 4 of 4 |
| `orderBy(k).write.mode("overwrite").parquet(path)` | **0 of 4** |
| `repartition(4, k).sortWithinPartitions(k).write.parquet(path)` | 4 of 4 |
| `repartition(4, k).sortWithinPartitions(k).write.mode("overwrite").parquet(path)` | **0 of 4** |

## Expected

The save mode does not change what is written inside the files. Both modes keep the sort.

## Cause

From reading the code; the write plan was not inspected. With overwrite, the listing planner wraps the sink in a `BarrierExec` whose precondition deletes the old files (`crates/sail-data-source/src/listing/planner.rs:253-258`). `BarrierExec` (`crates/sail-physical-plan/src/barrier.rs`) does not report that it maintains its input order. DataFusion's sort enforcement then treats the user's `SortExec` below it as unnecessary and removes it. In the default mode the sink is the top node, and DataFusion's `DataSinkExec` reports `maintains_input_order`, so the sort stays.

## Possible fix

Have `BarrierExec` report `maintains_input_order` for its main plan child (not for the preconditions), and pass the child's ordering through its plan properties.

## Related upstream items

Searched in `lakehq/sail` issues and pull requests on 2026-10-03. No existing issue or pull request found. #1862 reports a dropped sort for `CREATE TABLE ... AS SELECT ... ORDER BY`. #2722, #2726 and #2732 come from the same family: an operator that depends on input order, or sits above a sort, without declaring it, so the optimizer removes the sort.

## Notes

- The fix is from reading the code. It was not built or tested.
- Only Parquet and local mode were run. Other file formats share the listing planner and were not checked.
