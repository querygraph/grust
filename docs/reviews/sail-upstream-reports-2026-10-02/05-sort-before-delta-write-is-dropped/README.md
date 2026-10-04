# A sort before a Delta write is removed; the same write to Parquet keeps it

**Kind:** silent behaviour difference between sinks. No wrong query results.

## Summary

`df.orderBy(k).write.format("delta")` and `df.repartition(n, k).sortWithinPartitions(k).write.format("delta")` write unsorted files. The same two writes with `format("parquet")` write sorted files. There is no way found to write a Delta table whose files are sorted by a non-partition column, so Delta's min/max statistics cannot prune on it.

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

The reproducer writes 1,000,000 rows with a scrambled key four ways and reads every data file back with pyarrow.

## Observed

| Sink | Write | Files sorted by `k` |
|---|---|---|
| Parquet | `orderBy(k).write` | 4 of 4 |
| Parquet | `repartition(4, k).sortWithinPartitions(k).write` | 4 of 4 |
| Delta | `orderBy(k).write` | **0 of 1** |
| Delta | `repartition(4, k).sortWithinPartitions(k).write` | **0 of 4** |

## Expected

The Delta sink keeps a sort the user asked for, as the Parquet sink does.

## Cause

`DeltaWriterExec` asks for an input order only on partition columns (`crates/sail-delta-lake/src/physical_plan/writer_exec.rs:566-594`) and does not report that it maintains input order. DataFusion's sort enforcement then removes the user's `SortExec` as unnecessary. The Parquet path keeps it because DataFusion's `DataSinkExec` reports `maintains_input_order`.

## Possible fix

Have `DeltaWriterExec` report that it maintains input order, so an explicit sort below it is kept.

## Related upstream items

Searched in `lakehq/sail` issues and pull requests on 2026-10-02.

No issue found for Delta. Open pull request #1862 ("fix: preserve global sort order in CTAS ORDER BY", opened 2026-05-06) reports the same symptom for a different path: `CREATE TABLE ... AS SELECT ... ORDER BY` wrote unordered Parquet files.

## Notes

- Whether Delta's file statistics would then prune on the sorted column was checked only with a table whose files were clustered by construction: there the scan read one row group of one file for a point filter.
- The same mechanism, a writer that neither requires nor maintains input order, also affects `DataFrame.checkpoint()` after a sort, where it leads to wrong results. That is a separate report.
