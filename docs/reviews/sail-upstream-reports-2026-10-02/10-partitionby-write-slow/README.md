# `partitionBy` writes are 5 to 45 times slower than plain writes

**Kind:** performance. The time is in DataFusion's Hive-style demultiplexer, which Sail calls unchanged.

## Summary

`DataFrameWriter.partitionBy(col).parquet(path)` costs about 60 ns a row on a 10-core laptop, against 12 ns a row for the same frame written without `partitionBy`. It keeps two cores busy where the plain write keeps six. With many partition values in each batch it is far worse: 512 ns a row for 1,000 values, 45 times the plain write.

One task handles every batch of the write, and for every row it formats the partition value as a string and allocates a `Vec<String>` key for a hash map.

## Environment

- Sail `main` at `99ee46f69a97342e91bf7d4eaedb4509f1d8a9c2` (2026-10-02, version 0.7.2), unmodified, built with `cargo build --release --locked -p sail-cli`.
- DataFusion 55.1.0, as pinned by that commit.
- Client: PySpark 4.0.1 (Spark Connect), Python 3.12.8, pyarrow 25.0.1.
- macOS 26.2 on an Apple M1 Max. Local mode, default settings.

## Reproduce

```sh
python repro.py /path/to/release/sail 16000000 10
```

[`repro.py`](repro.py) starts a server, writes one frame four ways three times each, and prints wall seconds and the server's CPU seconds for every write as JSON lines. The frame has three columns: a BIGINT, a DOUBLE and an INT bucket in `[0, buckets)`. The first two are incompressible by construction. The outputs of the runs reported here are the `output-*.jsonl` files.

## Observed

Median of three; the three span at most 16% of the median.

| Rows | Buckets | Write | Wall | Times plain | Server CPU | Cores busy | Files | ns per row |
|---|---|---|---|---|---|---|---|---|
| 16M | 10 | plain | 0.19 s | 1.0 | 1.05 s | 5.4 | 4 | 12 |
| 16M | 10 | `repartition(10, bucket)` | 0.20 s | 1.0 | 1.22 s | 6.2 | 4 | 12 |
| 16M | 10 | `partitionBy(bucket)` | 1.03 s | 5.3 | 2.21 s | 2.1 | 10 | 64 |
| 16M | 10 | `repartition(10, bucket)` then `partitionBy(bucket)` | 0.93 s | 4.8 | 2.04 s | 2.2 | 10 | 58 |
| 64M | 10 | plain | 0.74 s | 1.0 | 4.23 s | 5.7 | 4 | 12 |
| 64M | 10 | `partitionBy(bucket)` | 4.07 s | 5.5 | 8.42 s | 2.1 | 10 | 64 |
| 64M | 10 | `repartition(10, bucket)` then `partitionBy(bucket)` | 3.68 s | 5.0 | 8.03 s | 2.2 | 10 | 58 |
| 16M | 1,000 | plain | 0.18 s | 1.0 | 1.09 s | 6.1 | 4 | 11 |
| 16M | 1,000 | `partitionBy(bucket)` | 8.19 s | 45.5 | 33.40 s | 4.1 | 1,000 | 512 |
| 16M | 1,000 | `repartition(1000, bucket)` then `partitionBy(bucket)` | 1.25 s | 7.0 | 4.18 s | 3.3 | 1,000 | 78 |

- The cost is linear in rows: 64 ns a row at 16M and at 64M.
- The partitioned write is close to serial. Its CPU time doubles while its wall time grows fivefold.
- Arranging the input so each batch holds one partition value removes the 1,000-bucket blow-up but not the base cost.
- The plain write is fast and parallel, so the gap is in the partitioning step, not in Parquet encoding.

## Expected

A partitioned write within a small factor of the plain write, and parallel.

## Cause

`crates/sail-data-source/src/formats/parquet/write.rs` hands the write to DataFusion's `ParquetFormat::create_writer_physical_plan`. With partition columns set, `datafusion-datasource` 55.1.0 runs `hive_style_partitions_demuxer` in `src/write/demux.rs`:

1. **One task for the whole write.** `start_demuxer_task` spawns a single task over one input stream. Every batch of every input partition passes through it in turn.
2. **A string per row.** `compute_partition_keys_by_row` formats each partition value to text for every row, even for an integer column.
3. **A heap-allocated key per row.** `compute_take_arrays` builds a `Vec<String>` for each row and looks it up in a `HashMap<Vec<String>, UInt64Builder>`.
4. **A `take` per distinct value per batch.** With 1,000 values in every batch that is 1,000 gathers of a few rows each, and 1,000 tiny batches sent downstream.

Items 2 and 3 explain the base cost of about 50 ns a row. Item 4 explains the 1,000-bucket case. Item 1 explains why none of it runs in parallel.

## Possible fix

In rough order of gain for the work:

1. **Skip the demultiplexer when the input is already partitioned by the partition columns.** After `repartition(n, cols)` or an aggregation on those columns, each input partition holds whole partition values. Each input partition could write its own files directly, in parallel, with a scan for value changes instead of a hash per row. This can be done in Sail's planner or sink.
2. **Compute keys per batch, not per row.** Encode the partition columns once per batch (for example with the Arrow row format), group row indices by the encoded key, and format the directory name once per distinct key.
3. **A fast path for a batch with a single partition value.**
4. **Run the demultiplexer per input partition.**

Items 2 to 4 belong in DataFusion and would help every engine built on it.

## Related upstream items

Searched in `lakehq/sail` issues and pull requests on 2026-10-02.

No issue found in Sail. Open pull request #1360 ("feat: introduce partitioned concurrent write orchestration and adaptive demux for Delta Lake", 2026-02-12) addresses partitioned writes for Delta and says it lacks benchmarks. In DataFusion's tracker no issue about the per-row cost of `hive_style_partitions_demuxer` was found; two of the searches there timed out, so that search is incomplete.

## Notes

- One machine, a laptop with a fast internal SSD and a warm page cache.
- Local mode only. In cluster mode the single demultiplexer task is per write task, so the picture may differ.
- DataFusion was read at 55.1.0. A later version may have changed this function.
- Server CPU seconds come from `ps`, to 10 ms.
