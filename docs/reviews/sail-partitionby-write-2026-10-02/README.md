# Note for Sail upstream: `partitionBy` writes are 5 to 45 times slower than plain writes

> **For filing upstream, use [`../sail-upstream-reports-2026-10-02/10-partitionby-write-slow/`](../sail-upstream-reports-2026-10-02/10-partitionby-write-slow/README.md).** That version is standalone. This note is kept because it carries the project's own context and links.

Written 2026-10-02 for the upstream Sail maintainers. It is self-contained:
a reproducer, numbers, the code path, and what would fix it. Nothing here
depends on the graph extensions.

## Summary

`DataFrameWriter.partitionBy(col).parquet(path)` costs about 60 ns a row on
a 10-core laptop, against 11 ns a row for the same frame written without
`partitionBy`. It keeps two cores busy where the plain write keeps six. With
many partition values in each batch it is far worse: 512 ns a row for 1,000
values, 45 times the plain write.

The time is spent in DataFusion's Hive-style demultiplexer, which Sail's
Parquet writer calls unchanged. One task handles every batch of the write,
and for every row it formats the partition value as a string and allocates a
`Vec<String>` key for a hash map.

## Reproduce

[`partitionby_probe.py`](partitionby_probe.py) starts a Sail server in local
mode, writes one frame four ways three times each, and prints wall seconds
and the server's CPU seconds for every write.

```sh
python partitionby_probe.py /path/to/release/sail 16000000 10
```

It needs `pyspark[connect]` 4.0 and a release build of `sail`. The frame has
three columns: a BIGINT, a DOUBLE and an INT bucket in `[0, buckets)`. The
first two are incompressible by construction.

## Measured

Unmodified upstream `main` at `99ee46f69` (2026-10-02, Sail 0.7.2,
DataFusion 55.1.0), `cargo build --release --locked -p sail-cli`, Apple M1
Max (10 cores), macOS 26.2, local mode with default settings. Median of
three; the three span at most 16% of the median.

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

Raw records: `probe-upstream-*.jsonl`. The same script on a fork build based
on `a85d912d7` gave the same picture (`probe-16m.jsonl`, `probe-64m.jsonl`,
`probe-16m-1000-buckets.jsonl`).

What the table shows:

- The cost is linear in rows: 64 ns a row at 16M and at 64M.
- The partitioned write is close to serial. Its CPU time doubles while its
  wall time grows fivefold.
- Arranging the input so each batch holds one partition value
  (`repartition` on the same column first) removes the 1,000-bucket blow-up
  but not the base cost.
- The plain write is fast and parallel, so the gap is in the partitioning
  step, not in Parquet encoding.

## Where the time goes

`sail-data-source/src/formats/parquet/write.rs` hands the write to
DataFusion's `ParquetFormat::create_writer_physical_plan`. With partition
columns set, `datafusion-datasource` 55.1.0 runs
`hive_style_partitions_demuxer` in `src/write/demux.rs`:

1. **One task for the whole write.** `start_demuxer_task` spawns a single
   task over one input stream. Every batch of every input partition passes
   through it in turn.
2. **A string per row.** `compute_partition_keys_by_row` formats each
   partition value to text for every row, even for an integer column.
3. **A heap-allocated key per row.** `compute_take_arrays` builds a
   `Vec<String>` for each row and looks it up in a
   `HashMap<Vec<String>, UInt64Builder>`.
4. **A `take` per distinct value per batch.** The batch is converted to a
   `StructArray` and gathered once for each key it holds. With 1,000 values
   in every batch that is 1,000 gathers of a few rows each, and 1,000 tiny
   batches sent downstream.

Items 2 and 3 explain the base cost of about 50 ns a row. Item 4 explains
the 1,000-bucket case. Item 1 explains why none of it runs in parallel.

## What would fix it

In rough order of gain for the work involved:

1. **Skip the demultiplexer when the input is already partitioned by the
   partition columns.** After `repartition(n, cols)` or an aggregation on
   those columns, each input partition holds whole partition values. Sail
   knows the input partitioning at plan time. Each input partition could then
   write its own files directly, in parallel, with a run-length scan for
   value changes instead of a hash per row.
2. **Compute keys per batch, not per row.** Dictionary-encode or
   row-format the partition columns once per batch (`arrow-row`), group row
   indices by the encoded key, and format the directory name once per
   distinct key. No per-row string, no per-row allocation.
3. **Fast path for a batch with a single partition value.** Compare first
   and last after a sort check, or use the column's min and max, and forward
   the batch whole.
4. **Run the demultiplexer per input partition.** Several tasks feeding the
   same set of per-value writers.

Items 2 to 4 belong in DataFusion and would help every engine on it. Item 1
can be done in Sail's planner or sink without waiting for that.

## Why it matters to us

Iterative graph algorithms checkpoint their vertex state every round. Writing
that state bucketed and sorted by vertex id lets the next round's join skip
its shuffle and its sort. On Sail today the bucketed write costs 8 to 11
times the plain one, which is more than the join it would save
([`../sem-review-capitola-2026-10-02/D1/README.md`](../sem-review-capitola-2026-10-02/D1/README.md)).

## Limits of this note

- One machine, a laptop with a fast internal SSD and a warm page cache.
- Local mode only. In cluster mode the single demultiplexer task is per
  write task, so the picture may differ.
- The code reading is of DataFusion 55.1.0 as pinned by Sail. A later
  DataFusion may already have changed this function; I did not check.
- Server CPU seconds come from `ps`, to 10 ms.
