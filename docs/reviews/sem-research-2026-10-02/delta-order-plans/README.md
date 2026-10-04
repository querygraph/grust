# Delta, Parquet and checkpoint layouts on Sail: what the physical plan keeps

Written 2026-10-02 for the reviewer's request: try Delta with liquid
clustering (`CLUSTER BY`) or Z-order, write a harness that analyzes plans,
say how good Sail's Delta read path is at carrying sort order and
co-partitioning through the DataFusion plan, and assess range partitioning
the same way. Sail upstream `main` at `99ee46f69`, DataFusion 55.1.0, release
build, Apple M1 Max, macOS.

## Summary

1. **Liquid clustering and Z-order cannot be tried: Sail rejects them.**
   `CLUSTER BY` parses and is refused at planning. `OPTIMIZE ... ZORDER BY`
   does not parse. `bucketBy` and `sortBy` are refused. A sort placed before
   a Delta write is removed by the optimizer, so the files come out unsorted.
2. **The Delta read path carries neither sort order nor co-partitioning.**
   The scan declares no ordering and no partitioning. Every query over every
   Delta layout plans exactly as over plain Parquet. File pruning on Delta
   min/max statistics does work, on a control table whose files are clustered.
3. **Parquet read by path is the same.** A catalog table with `SORTED BY`
   does declare an order, but as `NULLS LAST`, so `ORDER BY k` and joins do
   not use it, and in cluster mode a `GROUP BY` over it fails.
4. **One route carries layout today: `DataFrame.checkpoint()`.** After
   `repartition(T, key)`, with T the session's partition count, the next join
   and `GROUP BY` plan no shuffle, in local and in local-cluster mode, with
   correct results. It is unsafe for sort order: a checkpoint taken after
   `sortWithinPartitions` declares an order its files do not have, and
   queries return wrong results (14 join rows instead of 4,000,000).
   In time the safe route is worth about 15% of a round at 260M edges
   (section 9).
5. **Range partitioning exists in DataFusion 55.1.0 as a plan property with
   fixed split points. Sail forwards it but never creates it.**
   `repartitionByRange` plans a hash repartition. There is no sampling.

## How this was checked

```sh
~/src/sail-pecan-integrated/.venv/bin/python order_plans.py \
    ~/src/sail-upstream-main/target/release/sail --label upstream
```

One command, about two minutes. [`order_plans.py`](order_plans.py) starts a
Sail server four times, one at a time, and stops each:

| Run | Mode | Join setting | How the plan is obtained |
|---|---|---|---|
| `local-hash` | `SAIL_MODE=local` | default | `EXPLAIN`, `EXPLAIN ANALYZE` |
| `local-smj` | `SAIL_MODE=local` | `SAIL_OPTIMIZER__PREFER_HASH_JOIN=false` | `EXPLAIN`, `EXPLAIN ANALYZE` |
| `cluster-hash` | `SAIL_MODE=local-cluster` | default | executed into the `noop` sink, plan and job graph read from the driver's debug log |
| `cluster-smj` | `SAIL_MODE=local-cluster` | `SAIL_OPTIMIZER__PREFER_HASH_JOIN=false` | same |

The two local-cluster runs exist for three reasons. They are the fallback
where `EXPLAIN` fails (section 7). They show stages and shuffles (section 6).
They log the plan of every write, which `EXPLAIN` cannot show.

Data: `v(id BIGINT, val DOUBLE)`, 2,000,000 rows, ids 0..N-1 in scrambled
order. `e(src BIGINT, dst BIGINT)`, 4,000,000 rows, hashed endpoints. The
session has 10 target partitions (the default, one per core). 21 layouts, 9
queries, 588 cells per binary. Every run also executes four check queries on
every layout and compares the rows with the plain layout.

Queries, all SQL over the layout's `v` and `e`, plus `e0` = plain Parquet edges:

| Name | Query |
|---|---|
| `join_same` | `v JOIN e ON v.id = e.src`, both tables in the layout |
| `join_mixed` | `v JOIN e0 ON v.id = e0.src`, edges plain |
| `round` | the join, then `GROUP BY e.dst` with `sum(v.val)`: one Pregel round |
| `group_by` | `SELECT src, count(*) FROM e GROUP BY src` |
| `order_by`, `order_by_nulls_last` | `SELECT id, val FROM v ORDER BY id [ASC NULLS LAST]` |
| `window` | `count(*) OVER (PARTITION BY src)` over `e` |
| `point`, `range` | `WHERE id = 1234567`, `WHERE id BETWEEN 1000000 AND 1000999` |

Evidence tags used below:

- **[run]** verified by running. The saved output is named.
- **[code]** read from code. `crates/...` is Sail upstream at `99ee46f69`.
  `datafusion-<crate>/...` is `datafusion-<crate>-55.1.0/src/...` in the cargo registry.
- **[inferred]** my reading, not run.

Full tables: [`results-upstream.md`](results-upstream.md). Raw plan text for
every cell: `raw/upstream/<run>/<layout>__<query>.txt`. Write plans:
`raw/upstream/cluster-hash/_write__<layout>.txt`. The raw plans are packed:
every `raw/upstream/...` path below is a member of
[`raw-upstream.tar.gz`](raw-upstream.tar.gz) (709 files), and the harness
writes them unpacked when it is run.

## Result in one table

Operator counts from the physical plan. `h` = hash `RepartitionExec`.
† = `EXPLAIN` failed in local mode, the plan is the one the local-cluster run
executed. Source: the Summary table of `results-upstream.md` **[run]**.

| Layout | `ORDER BY k`: SortExec | `GROUP BY k`: h | Hash join, both sides: h | Sort-merge join, both sides: SortExec, h | Round, sort-merge: SortExec, h | Results |
|---|---|---|---|---|---|---|
| parquet-plain | 1 | 1 | 2 | 2, 2 † | 2, 3 † | equal |
| parquet-hash-sorted | 1 | 1 | 2 | 2, 2 † | 2, 3 † | equal |
| parquet-range-sorted | 1 | 1 | 2 | 2, 2 † | 2, 3 † | equal |
| parquet-global-sorted | 1 | 1 | 2 | 2, 2 † | 2, 3 † | equal |
| parquet-catalog-sorted | 1 (0 with `NULLS LAST`) | 1, order-preserving | 2 | 2, 2 † | 2, 3 † | equal in local mode. `GROUP BY` fails in local-cluster |
| parquet-bucket-dirs | 1 | 1 | 2 | 2, 2 † | 2, 3 † | equal |
| parquet-footer-sorted (control) | 1 | 1 | 2 | 2, 2 † | 2, 3 † | equal |
| delta-plain | 1 | 1 | 2 | 2, 2 | 2, 3 | equal |
| delta-hash-sorted | 1 | 1 | 2 | 2, 2 | 2, 3 | equal |
| delta-catalog-sorted | 1 | 1 | 2 | 2, 2 | 2, 3 | equal |
| delta-global-sorted | 1 | 1 | 2 | 2, 2 | 2, 3 | equal |
| delta-bucket-dirs | 1 | 1 | 2 | 2, 2 † | 2, 3 † | equal |
| delta-clustered-input (control) | 1 | 1 | 2 | 2, 2 | 2, 3 | equal |
| **checkpoint-hash** | 1 | **0** | **0** | 2, **0** | 2, **1** | equal |
| checkpoint-hash-fewer (8 < 10) | 1 | 1 | 2 | 2, 2 | 2, 3 | equal |
| checkpoint-hash-more (16 > 10) | 1 | 0 | 0 | 2, 0 | 2, 1 | equal |
| **checkpoint-hash-sorted** | 0 | 0 | 0 | **0, 0** | 0, 1 | **WRONG** in all four runs |
| checkpoint-range-sorted | 0 | 0 | 0 | 0, 0 | 0, 1 | **WRONG** in all four runs |
| checkpoint-hash-sorted-pinned (control) | 0 | 0 | 0 | 0, 0 | 0, 1 | equal |
| checkpoint-aggregate | 1 | 0 | 1 | 2, 1 † | 2, 2 † | equal |
| checkpoint-aggregate-repartition | 1 | 0 | 0 | 2, 0 | 2, 1 | equal |

Reading:

- All thirteen Parquet and Delta layouts plan like plain Parquet. I compared
  all nine queries in both local runs: the only layout that differs is
  `parquet-catalog-sorted`, in `group_by` and `order_by_nulls_last` **[run]**.
- Only checkpoints change join plans.
- `GROUP BY k` is over `e`. In the two `checkpoint-aggregate` rows `e` is a
  plain hash checkpoint, so that column says nothing about `v` there.

## 1. Write side: what Sail accepts

Outcome and error text are from the "What Sail accepts" table of
`results-upstream.md` **[run]**. File state is from the "Layouts" table
**[run]**: the harness reads every data file of `v` with pyarrow.

| Request | Parsed | Planned | Executed | What happens |
|---|---|---|---|---|
| `CREATE TABLE ... USING delta CLUSTER BY (k)` | yes, `crates/sail-sql-analyzer/src/statement.rs:1922` | no | no | `CLUSTER BY in CREATE TABLE statement`, `crates/sail-plan/src/resolver/command/catalog/table.rs:47` |
| `CREATE TABLE ... CLUSTER BY (k) AS SELECT` | yes | no | no | `CLUSTER BY in CREATE TABLE AS SELECT statement`, same file, line 128 |
| `ALTER TABLE t CLUSTER BY (k)` | no | | | parse error `found CLUSTER at 22:29` |
| `OPTIMIZE t`, `OPTIMIZE t ZORDER BY (k)` | no | | | parse error `found OPTIMIZE at 0:8` |
| `df.write.clusterBy(k)`, `df.writeTo(t).clusterBy(k)` | n/a | no | no | `CLUSTER BY for write`, `crates/sail-plan/src/resolver/command/write.rs:231` |
| `df.write.bucketBy(n, k)` | n/a | no | no | Delta: `bucketing for Delta format`, `crates/sail-delta-lake/src/lake_source.rs:135`. Parquet: `bucketing for writing listing data source`, `crates/sail-data-source/src/listing/source.rs:293` |
| `df.write.sortBy(k)` | n/a | no | no | `attribute ObjectName([Identifier("id")]) is missing from the schema`, both formats |
| `df.write.partitionBy(c)` | n/a | yes | yes | both formats. This is the slow write of the earlier note |
| `repartition(n, k).sortWithinPartitions(k)` then write | n/a | yes | yes | Parquet: sort kept, see below. Delta: **sort removed** |
| `orderBy(k)` then write | n/a | yes | yes | Parquet: sort kept. Delta: **sort removed** |
| `CREATE TABLE ... CLUSTERED BY (k) SORTED BY (k) INTO n BUCKETS` | yes | yes | yes | stored in the catalog for both formats. `INSERT` into it is refused (`bucketing for writing listing data source`) |
| `CREATE TABLE ... WITH ORDER (k)` (DataFusion syntax) | no | | | parse error |
| `SELECT ... DISTRIBUTE BY k`, `SELECT ... CLUSTER BY k` | yes | no | no | `crates/sail-sql-analyzer/src/query.rs:151-157`. `SORT BY k` is accepted |

Notes:

- **`sortBy` looks like a bug, not a missing feature.** Both sinks accept a
  sort order: the Parquet sink at
  `crates/sail-data-source/src/formats/parquet/write.rs:36`, the Delta writer
  at `crates/sail-delta-lake/src/lake_source.rs:602`. The request dies
  earlier, in name resolution. **[inferred]** cause: `write.rs:240` resolves
  the sort columns against the input after `resolve_write_input`
  (`write.rs:550-558`) has renamed it to user-facing names, and the resolver
  state only knows the internal names.
- **What a sorted Parquet write produces.** Write plan
  `DataSink > SortPreservingMerge > Projection > Sort > Repartition`
  (`raw/upstream/cluster-hash/_write__parquet-hash-sorted.txt`) **[run]**.
  The sink merges the ten sorted partitions into one sorted stream and deals
  it into 4 files. Each file is sorted. The files are not the hash
  partitions, their key ranges overlap, and no footer carries
  `sorting_columns` **[run]**. DataFusion writes `sorting_columns` only when
  the sink is given a sort requirement
  (`datafusion-datasource-parquet/file_format.rs:536-556`), which only
  `sortBy` would supply **[code]**.
- **What a "sorted" Delta write produces.** Write plan
  `DeltaCommit > CoalescePartitions > DeltaWriter > Projection > Repartition`
  with no `SortExec` (`_write__delta-hash-sorted.txt`) **[run]**. Ten files,
  one per hash partition, none sorted. With `orderBy(k)` the plan is
  `DeltaWriter > Projection > CoalescePartitions`: one unsorted file
  (`_write__delta-global-sorted.txt`) **[run]**. Cause **[code]**:
  `DeltaWriterExec` asks for an input order only on partition columns
  (`crates/sail-delta-lake/src/physical_plan/writer_exec.rs:566-594`) and
  does not say it maintains input order. DataFusion then treats the user's
  sort as unnecessary and removes it
  (`datafusion-physical-optimizer/ensure_requirements/enforce_sorting/mod.rs:447-451`).
  The Parquet sink keeps the sort because `DataSinkExec` declares
  `maintains_input_order` (`datafusion-datasource/sink.rs:296-302`).
- **So Sail cannot write a Delta table clustered by a key at all today**,
  by any route I found. With `partitionBy(bucket)` the writer sorts by
  `bucket` only (`_write__delta-bucket-dirs.txt`), and the files are not
  sorted by `k` **[run]**.
- **No declared sort order in Delta metadata.** `clusteringProvider` is a
  field Sail carries through Add actions
  (`crates/sail-delta-lake/src/spec/actions.rs:284`). The only place that
  sets it is a test (`checkpoint/mod.rs:1932`, test module from line 1547)
  **[code]**.

## 2. Delta read path

| Property | What the scan declares | Evidence |
|---|---|---|
| Output ordering | none | `FileScanParams.sort_order` (`crates/sail-delta-lake/src/datasource/scan.rs:61`) is `None` at both call sites (`physical/scan_planner.rs:314`, `physical_plan/scan_by_adds_exec.rs:380`). Even when set it only regroups files by statistics (`scan.rs:500-509`). The scan config is built without `with_output_ordering` (`scan.rs:511-525`) **[code]** |
| Output partitioning | none | no `with_output_partitioning` in `scan.rs:511-525` **[code]** |
| Catalog `SORTED BY`, `CLUSTERED BY` | ignored | `create_source` discards `sort_order`, `bucket_by`, `partition_by` (`lake_source.rs:83-101`) **[code]**. `delta-catalog-sorted` plans like `delta-plain` **[run]** |
| File grouping | one group per distinct partition-value tuple, so one group for an unpartitioned table (`scan.rs:258-316`). DataFusion then splits it by byte range into 10 groups, across file boundaries | `raw/upstream/local-hash/delta-hash-sorted__join_same.txt` shows groups like `[fileA:0..2941534, fileB:0..6237], [fileB:6237..2949611], ...` **[run]** |

Consequences, all **[run]**:

- A file is not a partition on read. Even though the Delta writer makes one
  file per hash partition, the reader regroups by bytes.
- Sort-merge join between two Delta tables: 2 `SortExec`, 2 hash
  `RepartitionExec`. Same with one plain side. `GROUP BY k`: 1 repartition.
  `ORDER BY k`: 1 `SortExec`. Window by key: 1 sort, 1 repartition. Identical
  to plain Parquet for every Delta layout, including the bucketed one.
- A Delta table partitioned by `bucket` gives 10 file groups, one per bucket,
  and still no declared partitioning.

Pruning for a filter on the key (`EXPLAIN ANALYZE`, "Pruning" tables in
`results-upstream.md`) **[run]**:

| Layout | Query | Rows out of the scan | Row groups considered | Bytes scanned |
|---|---|---|---|---|
| delta-plain | point | 2.00 M | 4 | 28.18 M |
| delta-hash-sorted (unsorted in fact) | point | 2.00 M | 10 | 31.38 M |
| delta-clustered-input (control) | point | 20.48 K | 1 | 1.66 M |
| delta-clustered-input (control) | range | 20.48 K | 1 | 1.65 M |
| parquet-plain | point | 2.00 M | 4 | 21.26 M |
| parquet-hash-sorted | point | 73.73 K | 4 | 4.44 M |
| parquet-hash-sorted | range | 49.15 K | 4 | 2.94 M |

- Delta prunes files at plan time from the min/max statistics in the log
  (`crates/sail-delta-lake/src/physical/scan_planner.rs:191-229`) **[code]**.
  On the control, whose ten files have disjoint key ranges, the scan reads
  one row group of one file **[run]**.
- On every Delta table Sail wrote, nothing is pruned, because no file is
  clustered or sorted (section 1) **[run]**.
- The control is not a Sail feature. Its rows were generated in key order in
  ten contiguous ranges, because a sort before a Delta write is dropped. It
  shows what the reader would do with a clustered table.
- Sorted Parquet files prune inside the file through the page index. File
  level statistics cannot prune, since every file spans the whole key range.

## 3. Parquet control

| Route | Declares order | Declares partitioning | Evidence |
|---|---|---|---|
| `spark.read.parquet(path)` over sorted files | no | no | `parquet-hash-sorted`, `parquet-global-sorted` plan like plain **[run]** |
| Files whose footers carry `sorting_columns` | no | no | `parquet-footer-sorted`: pyarrow rewrote the bucket files with `sorting_columns`. `ORDER BY` still sorts **[run]** |
| Hive directories `bucket=N` | no | no | `parquet-bucket-dirs`: one file group per directory, no partitioning **[run]** |
| Catalog table with `SORTED BY (k)` | yes, `ASC NULLS LAST` | no | `parquet-catalog-sorted` **[run]** |
| `bucketBy` + `sortBy` + `saveAsTable` | cannot be written | | section 1 **[run]** |

Details:

- **The footer path is dead code for path reads.** The listing planner would
  derive an order from Parquet footers
  (`crates/sail-data-source/src/listing/planner.rs:276`, using
  `ordering_from_parquet_metadata` at `formats/parquet/read.rs:206`). But
  `source.rs:268` always passes `file_sort_order: vec![sort_order]`, a list
  of length one even when `sort_order` is empty, and `planner.rs:269` returns
  early whenever that list is non-empty **[code]**. The control confirms it
  **[run]**. A one-line fix.
- **Catalog `SORTED BY` is honoured on read.** `read.rs:131` passes the
  table's `sort_by` to the source. The conversion hard-codes
  `nulls_first: false` (`crates/sail-common-datafusion/src/catalog/mod.rs:89`)
  **[code]**. So `ORDER BY id ASC NULLS LAST` has no `SortExec`, and the
  default `ORDER BY id`, which in Spark means `NULLS FIRST`, keeps it
  **[run]**. `GROUP BY` uses sorted aggregation with an order-preserving
  hash repartition. Sort-merge joins still plan 2 sorts and 2 repartitions.
- **The declaration is trusted, not checked.** The table here points at
  files that really are sorted, and results are equal. A wrong declaration
  would give wrong answers **[inferred]** from the checkpoint case below.
- **`CLUSTERED BY ... INTO n BUCKETS` is ignored on read**
  (`source.rs:170`, `bucket_by: _`) **[code]**.
- **Hive directories could declare partitioning but the switch is off.**
  The planner sets hash partitioning on the partition columns only when
  DataFusion's `preserve_file_partitions` is above zero
  (`planner.rs:171-179`, `411-423`). Its default is 0
  (`datafusion-common/config.rs:1597`) and Sail does not expose it
  (`crates/sail-session/src/session_factory/server.rs:186-199`) **[code]**.
  It would partition by `bucket`, not by `id`, so a join on `id` would not
  use it **[inferred]**.

## 4. Checkpoint: the route that carries layout

`DataFrame.checkpoint()` and `localCheckpoint()` are implemented upstream.
They need `SAIL_EXECUTION__CHECKPOINT__PATH`
(`crates/sail-common/src/config/application.yaml:488`). Only eager
checkpoints, no storage level
(`crates/sail-spark-connect/src/service/plan_executor.rs:508-545`).

How it works **[code]**:

- Write: one Parquet file per input partition, no merge
  (`crates/sail-physical-plan/src/remote_checkpoint.rs:528-552`).
- The planner records the input plan's partitioning and ordering
  (`crates/sail-session/src/planner.rs:195-200`).
- Read: a scan with one file group per partition that reports the recorded
  partitioning (`remote_checkpoint.rs:90-92`) and ordering
  (`planner.rs:335-336`).
- The registry is per session and is not reloaded after a restart
  (`crates/sail-cache/src/remote_checkpoint.rs:42-43`). Files are removed at
  session shutdown.

### What works **[run]**

`repartition(10, key).checkpoint()` on both tables, no sort:

| Query | Plain Parquet | checkpoint-hash |
|---|---|---|
| Hash join, both sides | 2 hash repartitions | 0 |
| Hash join, edges plain | 2 | 1 (the plain side) |
| Round: join then `GROUP BY dst` | 3 | 1 (the aggregation) |
| `GROUP BY k` | 1, two-phase | 0, `SinglePartitioned` |
| Window by key | 1 sort, 1 repartition | 1 sort, 0 |
| Results | | equal in all four runs |

Plans: `raw/upstream/local-hash/checkpoint-hash__join_same.txt`,
`...__round.txt`.

Three conditions, each shown by a layout:

- **The partition count must match.** With 8 partitions against a target of
  10 everything is repartitioned again (`checkpoint-hash-fewer`). With 16,
  joins between two checkpoints and single-input operators keep the layout,
  but a join with a plain table repartitions both sides
  (`checkpoint-hash-more`). The rule is DataFusion's
  (`datafusion-physical-optimizer/ensure_requirements/enforce_distribution.rs:1357-1363`
  and `1054-1124`) **[code]**. Use exactly the session's partition count.
- **The partitioning must be visible before optimization.** A checkpoint
  taken straight after `groupBy(id)` records nothing, although its rows are
  hash-partitioned by `id`: the join repartitions that side
  (`checkpoint-aggregate`). Adding `repartition(10, id)` fixes the read and
  costs a second hash repartition of the state in the write
  (`_write__checkpoint-aggregate-repartition.txt`:
  `Repartition > Projection > Aggregate > Repartition > Aggregate`).
- **Never sort before a checkpoint.** Next section.

### What is broken: a sorted checkpoint returns wrong results **[run]**

`repartition(10, k).sortWithinPartitions(k).checkpoint()`:

| Check | Plain | checkpoint-hash-sorted, `local-hash` | checkpoint-hash-sorted, `local-smj` |
|---|---|---|---|
| Join, both sides: rows | 4,000,000 | 4,000,000 | **14** |
| Join, edges plain: rows | 4,000,000 | 4,000,000 | **321** |
| `GROUP BY src`: groups | 1,729,019 | **3,919,455** | **3,919,490** |
| Window: sum of degrees | 11,999,520 | **4,000,032** | **4,000,032** |

("Result checks" table of `results-upstream.md`. The wrong numbers vary from
run to run. The local-cluster runs are wrong in the same way.)

It needs no special setting: the aggregate and the window are wrong with
default settings.

Mechanism:

- The files are not sorted. pyarrow reads all ten: none is sorted **[run]**
  ("Layouts" table).
- The write plan has no `SortExec`:
  `RemoteCheckpointCommit > CoalescePartitions > RemoteCheckpointWrite > Repartition > DataSource`
  (`raw/upstream/cluster-hash/_write__checkpoint-hash-sorted.txt`) **[run]**.
- The ordering is recorded at physical planning, before the optimizer runs
  (`planner.rs:195-200`), and copied unchanged afterwards
  (`remote_checkpoint.rs:334-353`). `RemoteCheckpointWriteExec` neither
  requires an input order nor maintains one (`remote_checkpoint.rs:478-552`),
  so DataFusion removes the sort, as for Delta **[code]**.
- The scan then declares the order. The plans trust it: sort-merge join with
  0 `SortExec`, aggregation in `Sorted` mode **[run]**.
- Upstream's test of this feature compares plans only
  (`python/pysail/tests/spark/dataframe/test_checkpoint.py:147-160`) **[code]**.

The same early recording also misses an order the optimizer adds later, and
the partitioning of an aggregation, as above.

### The reader is sound when the files are honest **[run]**

Control `checkpoint-hash-sorted-pinned`: a `row_number()` window over the key
forces a sort the optimizer cannot drop, and a `sortWithinPartitions` after
it makes the order visible at planning time. The files are sorted (pyarrow).
Then:

- Sort-merge join of two such checkpoints: 0 `SortExec`, 0 `RepartitionExec`
  (`raw/upstream/local-smj/checkpoint-hash-sorted-pinned__join_same.txt`).
- `ORDER BY k`: no `SortExec`. `GROUP BY k`: `SinglePartitioned[Sorted]`,
  no repartition. Window: no sort, no repartition.
- All checks equal the plain layout in all four runs.

This is a demonstration, not a recommendation: it stores an extra column and
runs a window. It shows the gap is on the write side only.

## 5. Range partitioning

DataFusion 55.1.0 **[code]**:

- `Partitioning::Range(RangePartitioning { ordering, split_points })` exists
  (`datafusion-physical-expr/partitioning.rs:121-131`, `203-209`).
- It satisfies a key-partitioning requirement on the same keys
  (`partitioning.rs:430-442`). Two sides are co-partitioned only with equal
  split points (`datafusion-physical-plan/distribution_requirements.rs:346-357`).
- `RepartitionExec` routes rows by the split points
  (`datafusion-physical-plan/repartition/mod.rs:622-645`).
- Split points are an input. Nothing in DataFusion samples to choose them.
  The type's own note says optimizer and execution behaviour is being added
  step by step (`partitioning.rs:200-202`).
- No rule in `datafusion-physical-optimizer` mentions `Range`. So the
  optimizer does not know, for example, that range partitions sorted inside
  are globally sorted **[inferred]** from that absence.

Sail **[code]**, **[run]**:

- `repartitionByRange` arrives as `RepartitionByExpression`
  (`crates/sail-spark-connect/src/proto/plan.rs:843`) and is always planned
  as `ExplicitRepartitionKind::Hash`
  (`crates/sail-plan/src/resolver/query/repartition.rs:52-58`). The kinds
  are `Coalesce`, `RoundRobin`, `Hash`
  (`crates/sail-logical-plan/src/repartition.rs:9-13`). The sort direction
  is dropped (`crates/sail-plan/src/resolver/expression/sort.rs:11-19`).
- The plan in local mode
  (`raw/upstream/local-hash/repartitionByRange.txt`):

  ```
  ProjectionExec: expr=[#0@0 as id, #1@1 as val]
    RepartitionExec: partitioning=Hash([#0@0], 10), input_partitions=4
      DataSourceExec: file_groups={4 groups: ...}
  ```

  No sampling, no bounds, no warning.
- Sail forwards a `Range` partitioning if it meets one: the repartition
  rewrite (`crates/sail-physical-optimizer/src/explicit_repartition.rs:43`),
  the shuffle writer (`crates/sail-execution/src/plan/shuffle_write.rs:169`,
  `232`), the job graph (`crates/sail-execution/src/job_graph/planner.rs:484-489`,
  `810`), the checkpoint (`crates/sail-session/src/planner.rs:563`). No
  non-test code constructs one (grep for `RangePartitioning::` and
  `Partitioning::Range`).
- `repartitionByRange(...).sortWithinPartitions(k)`, then write and read:
  row for row the same as the hash variant in every table.
  `parquet-range-sorted` equals `parquet-hash-sorted`. The files' key ranges
  overlap. `checkpoint-range-sorted` equals `checkpoint-hash-sorted`,
  wrong results included. Nothing range-like is remembered.

Assessment: for an equi-join, range partitioning gives nothing hash does not.
Both sides would have to share split points. Its value would be file pruning
(disjoint ranges) and global order. Sail would need a new repartition kind
and a sampling pass to pick split points.

## 6. Local mode versus cluster mode

From code **[code]**:

- The job graph is built from the already optimized physical plan. It cuts
  stages at `RepartitionExec`, `CoalescePartitionsExec` and
  `SortPreservingMergeExec`
  (`crates/sail-execution/src/job_graph/planner.rs:463-530`).
- A shuffle read carries the partitioning of the repartition it replaces
  (`planner.rs:796-824`). Hash partitioning survives a stage boundary.
- Ordering does not survive a shuffle. An order-preserving repartition is
  refused outright (`planner.rs:464-471`).
- Join dynamic filters are off in cluster modes
  (`crates/sail-session/src/session_factory/server.rs:190-197`).

From the local-cluster runs **[run]** (`raw/upstream/cluster-hash/`):

| Query | Plain Parquet | checkpoint-hash |
|---|---|---|
| Join, both sides | 3 stages, 2 shuffles | 1 stage, 0 shuffles |
| Join, edges plain | 3, 2 | 2, 1 |
| Round | 4, 3 | 2, 1 |
| `GROUP BY k` | 2, 1 | 1, 0 |

- A scan that declares partitioning needs no exchange, so the join and both
  scans run in one stage, task *i* reading partition *i* of each checkpoint.
  Results equal the plain layout.
- **A declared order can make a query fail in cluster mode.**
  `GROUP BY src` over `parquet-catalog-sorted` plans an order-preserving
  repartition and fails with `internal error: repartition is
  order-preserving and would result in incorrect results in distributed
  execution` (`raw/upstream/cluster-hash/parquet-catalog-sorted__group_by.txt`).
  The same query runs in local mode.

## 7. `EXPLAIN` under `prefer_hash_join=false`

Reproduced **[run]**. In `local-smj`, 39 of 189 cells fail, all joins:

```
Physical plan error: error in DataFusion: Invariant for ExecutionPlan node 'SortMergeJoinExec' failed
caused by
Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned.
```

- Every variant fails the same way: `EXPLAIN`, `EXTENDED`, `FORMATTED`,
  `CODEGEN`, `COST`, `ANALYZE`, `VERBOSE`
  (`raw/upstream/local-smj/_explain_variants__parquet-plain__join_same.txt`).
- The queries execute and return the right rows (result checks).
- It does not fail when both join inputs already have one partition, or the
  same hash layout, before optimization: two unpartitioned Delta tables, two
  matched checkpoints.
- Cause **[code]**: `crates/sail-plan/src/explain.rs:215-222` builds the
  initial plan with a session whose physical optimizer list is empty.
  DataFusion's planner still ends with its "executable" invariant check
  (`datafusion/physical_planner.rs:2904`). A sort-merge join needs
  co-partitioned inputs, which only the optimizer establishes. Execution
  uses the full optimizer and passes.
- The other way to see the plan: in `local-cluster` mode with
  `RUST_LOG=warn,sail_execution::driver::job_scheduler::core=debug` the
  driver logs every executed plan and job graph
  (`crates/sail-execution/src/driver/job_scheduler/core.rs:55-65`). The
  harness does this. Local mode has no such log line **[code]**.
- One caveat of that fallback: the `noop` sink lets the optimizer drop a
  top-level `ORDER BY`, so the cluster runs skip the two `ORDER BY` queries
  and the filters.

## 8. Verdict

**Is there a route today by which a per-round checkpoint written by Sail is
read back with ordering and co-partitioning that the join uses?**

- **Co-partitioning: yes.** `repartition(T, key).checkpoint()`, T equal to
  the session's partition count, no sort. The next hash join plans no
  shuffle on a checkpointed side, the results are correct, and it holds in
  local-cluster mode. Verified.
- **Ordering: no safe route.** The checkpoint is the only route that makes a
  join use a declared order, and it returns wrong results. The catalog
  `SORTED BY` route declares an order that joins do not use.
- **Delta: no route.** Nothing is declared on read, and nothing sorted or
  clustered can be written.

Options, ranked by gain for the work:

| # | Change | Where | Size | Gain | Status |
|---|---|---|---|---|---|
| 1 | Checkpoint the edges once and the state each round with `repartition(T, key).checkpoint()`; hash join; no sort | Pecan client (`examples/extensions/graph-algorithms/src/pyspark_pecan/staging.py:58-66` in the fork writes Parquet and reads it by path today) plus one server variable | small, no Sail change | the round goes from 3 hash repartitions to 1, from 4 stages to 2. The edge shuffle, the large one, disappears | works today **[run]**. Time not measured |
| 2 | Make the checkpoint honest: require the recorded order of the writer's input, or record order and partitioning after optimization | `crates/sail-physical-plan/src/remote_checkpoint.rs`, `crates/sail-session/src/planner.rs:195-216` | tens of lines | fixes wrong results. Then sort-merge join with no sort and no shuffle, as the pinned control shows. Recording after optimization also removes the extra repartition after an aggregation | fix shape is **[inferred]**, not built |
| 3 | Parquet footers: pass an empty `file_sort_order` when there is none (`source.rs:268`), and fix `sortBy` name resolution (`write.rs:240`) | Sail | one line plus a small fix | durable tables that declare order. Order only, files are not buckets, joins still shuffle | **[inferred]** |
| 4 | Range repartition with sampled split points | Sail planner; DataFusion already carries the property | medium | file pruning and global order. Nothing for equi-joins over hash | **[inferred]** |
| 5 | Delta: keep the sort in the writer, store a layout in table metadata, declare it in the scan; or `CLUSTER BY` / `OPTIMIZE` proper | Sail Delta crate | large | pruning for stored tables. A weak fit for per-round state: Delta has no standard field for "files are sorted" or "file is hash bucket i" | **[inferred]** |
| 6 | Expose `preserve_file_partitions` | Sail config | small | hash partitioning on Hive partition columns only. Does not match a join on `id`, and needs the slow `partitionBy` write | **[inferred]** |

Caveats on option 1:

- A checkpoint lives in one session. It cannot be resumed by another
  process. If Pecan relies on re-reading staged Parquet after a restart,
  that is lost.
- The state must be repartitioned explicitly before each checkpoint. That is
  one hash repartition of V rows, the same rows the join shuffles today.
- T must be the session's partition count, so set
  `SAIL_EXECUTION__DEFAULT_PARALLELISM` rather than depend on the core count.
- The earlier measurement put the join at 45 to 48% of a round. Removing its
  shuffles is some part of that. This note measured no time.

## 9. Checked independently, and what the route is worth in time

Added by the reviewer of this study, with two scripts written apart from
the harness. Both ran on unmodified upstream `99ee46f69`, release build,
local mode, default settings.

**The two central claims hold** ([`checkpoint_repro.py`](checkpoint_repro.py),
output in [`checkpoint-repro-upstream.txt`](checkpoint-repro-upstream.txt)):

| Check | Expected | Got |
|---|---|---|
| `GROUP BY src` over `repartition(10, src).checkpoint()`: groups | 1,000,003 | 1,000,003 |
| `GROUP BY src` over `repartition(10, src).sortWithinPartitions(src).checkpoint()`: groups | 1,000,003 | **4,000,000** |
| Join of two hash checkpoints: rows, `sum(val)` | as without checkpoints | equal |
| The same join: hash repartitions in the plan | 2 without checkpoints | 0 |

So the wrong result is real, needs no special setting, and is one aggregate
away from any user who sorts before a checkpoint.

**Time** ([`checkpoint_round_cost.py`](checkpoint_round_cost.py),
`checkpoint-round-cost-*.jsonl`). One Pregel-shaped round on the LDBC files:
the state joined with the edges on the source, summed by destination. Three
runs each, seconds, median with the range. The answers are identical in
every variant.

| | cit-Patents (16.5M edges) | graph500-24 (260M edges) |
|---|---|---|
| Round, state and edges read by path (today) | 0.24 (0.22 to 0.27) | 3.20 (3.06 to 3.26) |
| Round, state from a hash checkpoint, edges by path | 0.24 (0.23 to 0.26) | 3.08 (3.04 to 3.55) |
| Round, state and edges from hash checkpoints | 0.22 (0.22 to 0.23) | 2.72 (2.62 to 2.79) |
| State written plain | 0.04 | 0.10 |
| State written with `repartition(T, id).checkpoint()` | 0.06 | 0.11 |
| Edges written once with `repartition(T, src).checkpoint()` | 0.30 | 3.36 |

Reading:

- With both sides co-partitioned the round is 8% shorter on cit-Patents and
  15% shorter on graph500-24. Checkpointing the state alone changes nothing:
  the edge side is the shuffle that matters.
- The state's checkpoint costs what a plain write costs. So there is no
  per-round price, unlike the `partitionBy` write.
- The one-time edge checkpoint costs about one round. It is repaid after
  about seven rounds at this size.
- The earlier note put the join at 45% of a round. Removing its shuffles
  removes about a third of that. The hash join itself and the aggregation's
  own shuffle remain.
- This helps loops whose edges do not change: Pregel programs such as
  PageRank and the traversals. The WCC contraction rewrites its edges every
  round, so a one-time edge checkpoint does not apply there.

These are a laptop's numbers with other work running (load average above 25
at the time). They show the size of the effect, not a result to quote.

## Findings for upstream, at the user's decision

All reproduce with `order_plans.py` on unmodified upstream. I did not search
the upstream tracker for existing reports.

1. **Wrong results**: a checkpoint after `sortWithinPartitions` declares an
   order its files do not have (section 4).
2. `sortWithinPartitions` and `orderBy` before a Delta write are dropped
   silently (section 1).
3. `DataFrameWriter.sortBy` fails name resolution for every format (section 1).
4. Ordering from Parquet footers is unreachable for path reads (section 3).
5. `EXPLAIN` fails for sort-merge joins that execute correctly (section 7).
6. In cluster mode a `GROUP BY` over a table with a declared order fails
   (section 6).
7. `repartitionByRange` hash-partitions without saying so (section 5).

## Fork versus upstream

The same harness on the fork binary: [`results-fork.md`](results-fork.md).
All 588 cells agree with upstream in every operator count, join, aggregate
and window mode, failure and stage count. Write support, file state and
which results are wrong also agree. The only difference is scan file
grouping: upstream groups a plain Parquet scan into 4 file groups, the fork
into 10. Upstream has `crates/sail-physical-optimizer/src/scan_partitions.rs`
and the fork's tree does not.

## Limits

- **Plans, not time,** except section 9, which times one round shape on one
  laptop.
- Small tables (2M and 4M rows), one laptop, 10 target partitions. Plan
  shapes depend on statistics and sizes. Every join here was partitioned;
  small inputs plan `CollectLeft` joins instead.
- Cluster evidence is `local-cluster` mode: one process, workers as threads,
  local files. No multi-process cluster, no Kubernetes, no object store.
  A real cluster needs the checkpoint path on shared storage.
- Delta: only tables Sail wrote in this run, plus one control. No deletion
  vectors, no column mapping, no log-replay scan path. I did not test
  whether Sail reads a table that Spark or Databricks wrote with real liquid
  clustering or Z-order.
- Iceberg was not looked at.
- The fixes in section 8 come from code reading. None was built or tested.
- `orderBy(k).checkpoint()` was not tested. Only `sortWithinPartitions`.
- Pruning by a filter on a Hive partition column was not tested.
- The "no code constructs a range partitioning" and "no optimizer rule
  mentions `Range`" claims rest on grep.
- The fork binary (modified 00:19) is older than its tree's HEAD
  (`4b88c8fb4`, committed 05:43). The harness prints the tree's HEAD, not
  the commit the binary was built from. The upstream binary (02:06) is newer
  than its HEAD commit and the tree is clean.
- DataFusion was read at 55.1.0 only.
- The wrong-result numbers differ between runs. Only "not equal" is stable.
- Another process ran Sail benchmarks on the laptop during these runs. That
  does not affect plans.

## Files

| File | Contents |
|---|---|
| [`order_plans.py`](order_plans.py) | the harness. Typed, passes mypy. Needs pyspark[connect] 4.0 and pyarrow |
| [`results-upstream.md`](results-upstream.md), `results-upstream.json` | all tables for upstream `99ee46f69` |
| [`results-fork.md`](results-fork.md), `results-fork.json` | the same for the fork binary |
| `raw-upstream.tar.gz` | `upstream/local-hash/`, `upstream/local-smj/`: `EXPLAIN` text for every layout x query, `__analyze` for the filters, `_explain_variants__...`; `upstream/cluster-hash/`, `upstream/cluster-smj/`: executed plan and job graph per cell, and `_write__<layout>.txt` for each write |
| `raw-fork.tar.gz` | the same raw plans for the fork binary |
| `checkpoint_repro.py`, `checkpoint-repro-upstream.txt` | the independent check of section 9 |
| `checkpoint_round_cost.py`, `checkpoint-round-cost-*.jsonl` | the timing of section 9 |
