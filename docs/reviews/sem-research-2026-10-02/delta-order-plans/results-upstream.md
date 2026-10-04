# Plan tables: upstream

Binary `/Users/alexy/src/sail-upstream-main/target/release/sail` (modified 2026-10-02 02:06:28 PDT; its source tree is at `99ee46f69`, which the binary may predate), 2,000,000 vertices, 4,000,000 edges, pyspark 4.0.1, 10 CPUs, 2026-10-02 08:42:50 PDT. Written by `order_plans.py`; do not edit.

## Summary

Operator counts in the physical plan. `ORDER BY k` and `GROUP BY k` are from the default run. `h` = hash `RepartitionExec`. † = EXPLAIN failed in local mode and the plan is the one the local-cluster run executed. Results = whether every result check in every run equals the plain layout.

| Layout | ORDER BY k: SortExec | ORDER BY k NULLS LAST: SortExec | GROUP BY k: h | Hash join, both sides in layout: h | Sort-merge join, both sides: SortExec, h | Sort-merge join, edges plain: SortExec, h | Round (join, GROUP BY dst), sort-merge: SortExec, h | Results |
|---|---|---|---|---|---|---|---|---|
| parquet-plain | 1 | 1 | 1 | 2 | 2, 2 † | 2, 2 † | 2, 3 † | equal |
| parquet-hash-sorted | 1 | 1 | 1 | 2 | 2, 2 † | 2, 2 † | 2, 3 † | equal |
| parquet-range-sorted | 1 | 1 | 1 | 2 | 2, 2 † | 2, 2 † | 2, 3 † | equal |
| parquet-global-sorted | 1 | 1 | 1 | 2 | 2, 2 † | 2, 2 † | 2, 3 † | equal |
| parquet-catalog-sorted | 1 | 0 | 1 | 2 | 2, 2 † | 2, 2 † | 2, 3 † | equal. Query FAILED: cluster-hash group_by; cluster-smj group_by |
| parquet-bucket-dirs | 1 | 1 | 1 | 2 | 2, 2 † | 2, 2 † | 2, 3 † | equal |
| parquet-footer-sorted | 1 | 1 | 1 | 2 | 2, 2 † | 2, 2 † | 2, 3 † | equal |
| delta-plain | 1 | 1 | 1 | 2 | 2, 2 | 2, 2 † | 2, 3 | equal |
| delta-hash-sorted | 1 | 1 | 1 | 2 | 2, 2 | 2, 2 † | 2, 3 | equal |
| delta-catalog-sorted | 1 | 1 | 1 | 2 | 2, 2 | 2, 2 † | 2, 3 | equal |
| delta-global-sorted | 1 | 1 | 1 | 2 | 2, 2 | 2, 2 † | 2, 3 | equal |
| delta-bucket-dirs | 1 | 1 | 1 | 2 | 2, 2 † | 2, 2 † | 2, 3 † | equal |
| delta-clustered-input | 1 | 1 | 1 | 2 | 2, 2 | 2, 2 † | 2, 3 | equal |
| checkpoint-hash | 1 | 1 | 0 | 0 | 2, 0 | 2, 1 † | 2, 1 | equal |
| checkpoint-hash-fewer | 1 | 1 | 1 | 2 | 2, 2 | 2, 2 † | 2, 3 | equal |
| checkpoint-hash-more | 1 | 1 | 0 | 0 | 2, 0 | 2, 2 † | 2, 1 | equal |
| checkpoint-hash-sorted | 0 | 1 | 0 | 0 | 0, 0 | 1, 1 † | 0, 1 | **WRONG**: local-hash group_by; local-hash window; local-smj join_same; local-smj join_mixed; local-smj group_by; local-smj window; cluster-hash group_by; cluster-hash window; cluster-smj join_same; cluster-smj join_mixed; cluster-smj group_by; cluster-smj window |
| checkpoint-range-sorted | 0 | 1 | 0 | 0 | 0, 0 | 1, 1 † | 0, 1 | **WRONG**: local-hash group_by; local-hash window; local-smj join_same; local-smj join_mixed; local-smj group_by; local-smj window; cluster-hash group_by; cluster-hash window; cluster-smj join_same; cluster-smj join_mixed; cluster-smj group_by; cluster-smj window |
| checkpoint-hash-sorted-pinned | 0 | 1 | 0 | 0 | 0, 0 | 1, 1 † | 0, 1 | equal |
| checkpoint-aggregate | 1 | 1 | 0 | 1 | 2, 1 † | 2, 2 † | 2, 2 † | equal |
| checkpoint-aggregate-repartition | 1 | 1 | 0 | 0 | 2, 0 | 2, 1 † | 2, 1 | equal |

## What Sail accepts

| Attempt | Outcome | Error |
|---|---|---|
| parquet: write.partitionBy(col) | accepted |  |
| parquet: write.sortBy(col) | rejected | attribute ObjectName([Identifier("id")]) is missing from the schema: cannot resolve attribute |
| parquet: write.bucketBy(n, col).sortBy(col).saveAsTable | rejected | attribute ObjectName([Identifier("id")]) is missing from the schema: cannot resolve attribute |
| parquet: write.bucketBy(n, col).saveAsTable | rejected | bucketing for writing listing data source |
| parquet: CREATE TABLE ... WITH ORDER (col) | rejected | invalid argument: found end of input expected 'AS', or '(' |
| parquet: repartition(n, col).sortWithinPartitions(col).write | accepted |  |
| parquet: CREATE TABLE ... CLUSTERED BY (col) SORTED BY (col) INTO n BUCKETS | accepted |  |
| parquet: INSERT INTO that bucketed table | rejected | bucketing for writing listing data source |
| delta: write.partitionBy(col) | accepted |  |
| delta: write.sortBy(col) | rejected | attribute ObjectName([Identifier("id")]) is missing from the schema: cannot resolve attribute |
| delta: write.bucketBy(n, col) | rejected | bucketing for Delta format |
| delta: write.clusterBy(col) | rejected | CLUSTER BY for write |
| delta: writeTo(t).using('delta').clusterBy(col).create() | rejected | CLUSTER BY for write |
| delta: repartition(n, col).sortWithinPartitions(col).write | accepted |  |
| delta: CREATE TABLE ... CLUSTER BY (col) | rejected | CLUSTER BY in CREATE TABLE statement |
| delta: CREATE TABLE ... CLUSTER BY (col) AS SELECT | rejected | CLUSTER BY in CREATE TABLE AS SELECT statement |
| delta: CREATE TABLE ... CLUSTERED BY (col) SORTED BY (col) INTO n BUCKETS | accepted |  |
| delta: CREATE TABLE (plain) | accepted |  |
| delta: INSERT INTO (plain) | accepted |  |
| delta: ALTER TABLE ... CLUSTER BY (col) | rejected | invalid argument: found CLUSTER at 22:29 expected '.', 'RENAME', 'PARTITION', 'ADD', 'DROP', 'ALTER', 'CHANGE', 'REPLACE', 'SET', 'UNSET', or 'RECOVER' |
| delta: OPTIMIZE t | rejected | invalid argument: found OPTIMIZE at 0:8 expected something else, ';', statement, or end of input |
| delta: OPTIMIZE t ZORDER BY (col) | rejected | invalid argument: found OPTIMIZE at 0:8 expected something else, ';', statement, or end of input |
| sql: SELECT ... DISTRIBUTE BY col | rejected | DISTRIBUTE BY |
| sql: SELECT ... CLUSTER BY col | rejected | CLUSTER BY |
| sql: SELECT ... SORT BY col | accepted |  |
| dataframe: repartitionByRange(n, col) | accepted |  |
| dataframe: checkpoint() | accepted |  |
| dataframe: localCheckpoint() | accepted |  |
| dataframe: checkpoint(eager=False) | rejected | lazy DataFrame checkpoint |

## `repartitionByRange` in local mode

```
ProjectionExec: expr=[#0@0 as id, #1@1 as val]
  RepartitionExec: partitioning=Hash([#0@0], 10), input_partitions=4
    DataSourceExec: file_groups={4 groups: [[private/tmp/claude-501/-Users-alexy-src-grust/508c82ce-25d0-4e06-bb41-a1907715a911/scratchpad/sail-order-plans-ayjj9i8w/base/v/Olvjw27Km3mHOyIw_1.zst.parquet:4..5329703], [private/tmp/claude-501/-Users-alexy-src-grust/508c82ce-25d0-4e06-bb41-a1907715a911/scratchpad/sail-order-plans-ayjj9i8w/base/v/Olvjw27Km3mHOyIw_0.zst.parquet:4..5326649], [private/tmp/claude-501/-Users-alexy-src-grust/508c82ce-25d0-4e06-bb41-a1907715a911/scratchpad/sail-order-plans-ayjj9i8w/base/v/Olvjw27Km3mHOyIw_3.zst.parquet:4..5305062], [private/tmp/claude-501/-Users-alexy-src-grust/508c82ce-25d0-4e06-bb41-a1907715a911/scratchpad/sail-order-plans-ayjj9i8w/base/v/Olvjw27Km3mHOyIw_2.zst.parquet:4..5295565]]}, projection=[id@0 as #0, val@1 as #1], file_type=parquet
```

## Layouts: what is on disk

`Sorted` = every data file of `v` is sorted by the key. `Disjoint` = the files' key ranges do not overlap. `Footer` = a Parquet footer carries `sorting_columns`. `Write plan` = the operators of the job that wrote `v`, top down, from the driver log of the `cluster-hash` run.

| Layout | How | Files | Sorted | Disjoint | Footer | Write plan |
|---|---|---|---|---|---|---|
| parquet-plain | write.parquet | 4 | False | False | False |  |
| parquet-hash-sorted | repartition(10, k).sortWithinPartitions(k).write.parquet | 4 | True | False | False | DataSink > SortPreservingMerge > Projection > Sort > Repartition > DataSource |
| parquet-range-sorted | repartitionByRange(10, k).sortWithinPartitions(k).write.parquet | 4 | True | False | False | DataSink > SortPreservingMerge > Projection > Sort > Repartition > DataSource |
| parquet-global-sorted | orderBy(k).write.parquet | 4 | True | False | False | DataSink > Projection > SortPreservingMerge > Projection > Sort > DataSource |
| parquet-catalog-sorted | the parquet-hash-sorted files behind CREATE TABLE ... CLUSTERED BY (k) SORTED BY (k) INTO 10 BUCKETS | 4 | True | False | False |  |
| parquet-bucket-dirs | bucket = pmod(xxhash64(k), 10); repartition(10, bucket).sortWithinPartitions(k).write.partitionBy(bucket) | 10 | True | False | False | DataSink > SortPreservingMerge > Projection > Sort > Repartition > DataSource |
| parquet-footer-sorted | control, not written by Sail: the bucket files rewritten by pyarrow with footer sorting_columns | 10 | True | False | True |  |
| delta-plain | write.format('delta') | 4 | False | False | False | DeltaCommit > CoalescePartitions > DeltaWriter > DataSource |
| delta-hash-sorted | repartition(10, k).sortWithinPartitions(k).write.format('delta') | 10 | False | False | False | DeltaCommit > CoalescePartitions > DeltaWriter > Projection > Repartition > DataSource |
| delta-catalog-sorted | the delta-hash-sorted table behind CREATE TABLE ... CLUSTERED BY (k) SORTED BY (k) INTO 10 BUCKETS | 10 | False | False | False |  |
| delta-global-sorted | orderBy(k).write.format('delta') | 1 | False | one file | False | DeltaCommit > DeltaWriter > Projection > CoalescePartitions > DataSource |
| delta-bucket-dirs | as parquet-bucket-dirs, write.format('delta').partitionBy(bucket) | 10 | False | False | False | DeltaCommit > CoalescePartitions > DeltaWriter > Projection > Sort > Repartition > DataSource |
| delta-clustered-input | control: the same rows generated in key order in 10 contiguous ranges, then write.format('delta') | 10 | True | True | False | DeltaCommit > CoalescePartitions > DeltaWriter > Projection > Range |
| checkpoint-hash | repartition(10, k).checkpoint() | 10 | False | False | False | RemoteCheckpointCommit > CoalescePartitions > RemoteCheckpointWrite > Repartition > DataSource |
| checkpoint-hash-fewer | repartition(8, k).checkpoint() | 8 | False | False | False | RemoteCheckpointCommit > CoalescePartitions > RemoteCheckpointWrite > Repartition > DataSource |
| checkpoint-hash-more | repartition(16, k).checkpoint() | 16 | False | False | False | RemoteCheckpointCommit > CoalescePartitions > RemoteCheckpointWrite > Repartition > DataSource |
| checkpoint-hash-sorted | repartition(10, k).sortWithinPartitions(k).checkpoint() | 10 | False | False | False | RemoteCheckpointCommit > CoalescePartitions > RemoteCheckpointWrite > Repartition > DataSource |
| checkpoint-range-sorted | repartitionByRange(10, k).sortWithinPartitions(k).checkpoint() | 10 | False | False | False | RemoteCheckpointCommit > CoalescePartitions > RemoteCheckpointWrite > Repartition > DataSource |
| checkpoint-hash-sorted-pinned | control: repartition(10, k), a row_number() window over k that pins a sort, sortWithinPartitions(k), checkpoint() | 10 | True | False | False | RemoteCheckpointCommit > CoalescePartitions > RemoteCheckpointWrite > Projection > BoundedWindowAgg > Sort > Repartition > DataSource |
| checkpoint-aggregate | v = groupBy(id).agg(max(val)).checkpoint(); e as checkpoint-hash | 10 | False | False | False | RemoteCheckpointCommit > CoalescePartitions > RemoteCheckpointWrite > Projection > Aggregate > Repartition > Aggregate > DataSource |
| checkpoint-aggregate-repartition | v = groupBy(id).agg(max(val)).repartition(10, id).checkpoint(); e as checkpoint-hash | 10 | False | False | False | RemoteCheckpointCommit > CoalescePartitions > RemoteCheckpointWrite > Repartition > Projection > Aggregate > Repartition > Aggregate > DataSource |

## Result checks

Each cell is the row a check query returned: `join_same` = count, sum(id + dst), sum(val); `join_mixed` = count, sum(id + dst); `group_by` = groups, rows; `window` = rows, sum(deg). **WRONG** = differs from the plain layout in the same run.

| Layout | Run | join_same | join_mixed | group_by | window |
|---|---|---|---|---|---|
| parquet-plain | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-plain | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-plain | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-plain | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-hash-sorted | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-hash-sorted | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-hash-sorted | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-hash-sorted | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-range-sorted | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-range-sorted | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-range-sorted | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-range-sorted | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-global-sorted | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-global-sorted | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-global-sorted | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-global-sorted | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-catalog-sorted | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-catalog-sorted | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-catalog-sorted | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | error: internal error: repartition is order-preserving and would result in incorrect results in distributed execution | 4000000, 11999520 |
| parquet-catalog-sorted | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | error: internal error: repartition is order-preserving and would result in incorrect results in distributed execution | 4000000, 11999520 |
| parquet-bucket-dirs | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-bucket-dirs | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-bucket-dirs | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-bucket-dirs | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-footer-sorted | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-footer-sorted | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-footer-sorted | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| parquet-footer-sorted | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-plain | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-plain | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-plain | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-plain | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-hash-sorted | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-hash-sorted | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-hash-sorted | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-hash-sorted | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-catalog-sorted | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-catalog-sorted | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-catalog-sorted | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-catalog-sorted | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-global-sorted | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-global-sorted | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-global-sorted | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-global-sorted | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-bucket-dirs | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-bucket-dirs | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-bucket-dirs | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-bucket-dirs | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-clustered-input | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-clustered-input | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-clustered-input | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| delta-clustered-input | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-hash | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-hash | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-hash | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-hash | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-hash-fewer | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-hash-fewer | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-hash-fewer | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-hash-fewer | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-hash-more | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-hash-more | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-hash-more | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-hash-more | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-hash-sorted | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 3919455, 4000000 **WRONG** | 4000000, 4000032 **WRONG** |
| checkpoint-hash-sorted | local-smj | 14, 45726889, -11131117 **WRONG** | 321, 916102305 **WRONG** | 3919490, 4000000 **WRONG** | 4000000, 4000032 **WRONG** |
| checkpoint-hash-sorted | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 3919399, 4000000 **WRONG** | 4000000, 4000032 **WRONG** |
| checkpoint-hash-sorted | cluster-smj | 16, 52622140, -18810754 **WRONG** | 268, 782326809 **WRONG** | 3919728, 4000000 **WRONG** | 4000000, 4000032 **WRONG** |
| checkpoint-range-sorted | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 3919114, 4000000 **WRONG** | 4000000, 4000032 **WRONG** |
| checkpoint-range-sorted | local-smj | 15, 50530991, -15084193 **WRONG** | 275, 786871592 **WRONG** | 3919586, 4000000 **WRONG** | 4000000, 4000032 **WRONG** |
| checkpoint-range-sorted | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 3919443, 4000000 **WRONG** | 4000000, 4000032 **WRONG** |
| checkpoint-range-sorted | cluster-smj | 12, 38126140, -23834153 **WRONG** | 262, 766441968 **WRONG** | 3919148, 4000000 **WRONG** | 4000000, 4000032 **WRONG** |
| checkpoint-hash-sorted-pinned | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-hash-sorted-pinned | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-hash-sorted-pinned | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-hash-sorted-pinned | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-aggregate | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-aggregate | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-aggregate | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-aggregate | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-aggregate-repartition | local-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-aggregate-repartition | local-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-aggregate-repartition | cluster-hash | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |
| checkpoint-aggregate-repartition | cluster-smj | 4000000, 8000666076093, 110412032 | 4000000, 8000666076093 | 1729019, 4000000 | 4000000, 11999520 |

## Plans: local-hash

Server environment: `{"SAIL_MODE": "local", "SAIL_EXECUTION__CHECKPOINT__PATH": "file:///private/tmp/claude-501/-Users-alexy-src-grust/508c82ce-25d0-4e06-bb41-a1907715a911/scratchpad/sail-order-plans-ayjj9i8w/checkpoints-local-hash", "RUST_LOG": "warn"}`. Target partitions: 10.

| Layout | Query | Sort | Repartition | SPM | Coalesce | Join; aggregate; window | Scans (file groups, printed properties) | Job graph | Note |
|---|---|---|---|---|---|---|---|---|---|
| parquet-plain | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 4g, 4g |  |  |
| parquet-plain | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 4g, 4g |  |  |
| parquet-plain | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 4g, 4g |  |  |
| parquet-plain | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 4g |  |  |
| parquet-plain | order_by | 1 | 0h | 1 | 0 | - | 4g |  |  |
| parquet-plain | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 4g |  |  |
| parquet-plain | window | 1 | 1h | 0 | 0 | WindowAgg | 4g |  |  |
| parquet-plain | point | 0 | 0h | 0 | 0 | - | 4g |  |  |
| parquet-plain | range | 0 | 0h | 0 | 0 | - | 4g |  |  |
| parquet-hash-sorted | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 4g, 4g |  |  |
| parquet-hash-sorted | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 4g, 4g |  |  |
| parquet-hash-sorted | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 4g, 4g |  |  |
| parquet-hash-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 4g |  |  |
| parquet-hash-sorted | order_by | 1 | 0h | 1 | 0 | - | 4g |  |  |
| parquet-hash-sorted | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 4g |  |  |
| parquet-hash-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 4g |  |  |
| parquet-hash-sorted | point | 0 | 0h | 0 | 0 | - | 4g |  |  |
| parquet-hash-sorted | range | 0 | 0h | 0 | 0 | - | 4g |  |  |
| parquet-range-sorted | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 4g, 4g |  |  |
| parquet-range-sorted | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 4g, 4g |  |  |
| parquet-range-sorted | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 4g, 4g |  |  |
| parquet-range-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 4g |  |  |
| parquet-range-sorted | order_by | 1 | 0h | 1 | 0 | - | 4g |  |  |
| parquet-range-sorted | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 4g |  |  |
| parquet-range-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 4g |  |  |
| parquet-range-sorted | point | 0 | 0h | 0 | 0 | - | 4g |  |  |
| parquet-range-sorted | range | 0 | 0h | 0 | 0 | - | 4g |  |  |
| parquet-global-sorted | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 4g, 4g |  |  |
| parquet-global-sorted | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 4g, 4g |  |  |
| parquet-global-sorted | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 4g, 4g |  |  |
| parquet-global-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 4g |  |  |
| parquet-global-sorted | order_by | 1 | 0h | 1 | 0 | - | 4g |  |  |
| parquet-global-sorted | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 4g |  |  |
| parquet-global-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 4g |  |  |
| parquet-global-sorted | point | 0 | 0h | 0 | 0 | - | 4g |  |  |
| parquet-global-sorted | range | 0 | 0h | 0 | 0 | - | 4g |  |  |
| parquet-catalog-sorted | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 10g |  |  |
| parquet-catalog-sorted | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g |  |  |
| parquet-catalog-sorted | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g |  |  |
| parquet-catalog-sorted | group_by | 0 | 1h (1 order-preserving) | 0 | 0 | Partial[Sorted]+FinalPartitioned[Sorted] | 10g |  |  |
| parquet-catalog-sorted | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| parquet-catalog-sorted | order_by_nulls_last | 0 | 0h | 1 | 0 | - | 10g |  |  |
| parquet-catalog-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g |  |  |
| parquet-catalog-sorted | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| parquet-catalog-sorted | range | 0 | 0h | 0 | 0 | - | 10g order=[id@0 ASC NULLS LAST] |  |  |
| parquet-bucket-dirs | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 10g |  |  |
| parquet-bucket-dirs | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g |  |  |
| parquet-bucket-dirs | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g |  |  |
| parquet-bucket-dirs | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g |  |  |
| parquet-bucket-dirs | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| parquet-bucket-dirs | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| parquet-bucket-dirs | window | 1 | 1h | 0 | 0 | WindowAgg | 10g |  |  |
| parquet-bucket-dirs | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| parquet-bucket-dirs | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| parquet-footer-sorted | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 10g |  |  |
| parquet-footer-sorted | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g |  |  |
| parquet-footer-sorted | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g |  |  |
| parquet-footer-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g |  |  |
| parquet-footer-sorted | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| parquet-footer-sorted | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| parquet-footer-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g |  |  |
| parquet-footer-sorted | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| parquet-footer-sorted | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-plain | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 10g |  |  |
| delta-plain | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g |  |  |
| delta-plain | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g |  |  |
| delta-plain | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g |  |  |
| delta-plain | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-plain | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-plain | window | 1 | 1h | 0 | 0 | WindowAgg | 10g |  |  |
| delta-plain | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-plain | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-hash-sorted | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 10g |  |  |
| delta-hash-sorted | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g |  |  |
| delta-hash-sorted | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g |  |  |
| delta-hash-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g |  |  |
| delta-hash-sorted | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-hash-sorted | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-hash-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g |  |  |
| delta-hash-sorted | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-hash-sorted | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-catalog-sorted | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 10g |  |  |
| delta-catalog-sorted | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g |  |  |
| delta-catalog-sorted | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g |  |  |
| delta-catalog-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g |  |  |
| delta-catalog-sorted | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-catalog-sorted | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-catalog-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g |  |  |
| delta-catalog-sorted | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-catalog-sorted | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-global-sorted | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 10g |  |  |
| delta-global-sorted | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g |  |  |
| delta-global-sorted | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g |  |  |
| delta-global-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g |  |  |
| delta-global-sorted | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-global-sorted | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-global-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g |  |  |
| delta-global-sorted | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-global-sorted | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-bucket-dirs | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 10g |  |  |
| delta-bucket-dirs | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g |  |  |
| delta-bucket-dirs | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g |  |  |
| delta-bucket-dirs | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g |  |  |
| delta-bucket-dirs | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-bucket-dirs | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-bucket-dirs | window | 1 | 1h | 0 | 0 | WindowAgg | 10g |  |  |
| delta-bucket-dirs | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-bucket-dirs | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-clustered-input | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 10g |  |  |
| delta-clustered-input | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g |  |  |
| delta-clustered-input | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g |  |  |
| delta-clustered-input | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g |  |  |
| delta-clustered-input | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-clustered-input | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-clustered-input | window | 1 | 1h | 0 | 0 | WindowAgg | 10g |  |  |
| delta-clustered-input | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-clustered-input | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-hash | join_same | 0 | 0h | 0 | 0 | Hash(Partitioned) | 10g, 10g |  |  |
| checkpoint-hash | join_mixed | 0 | 1h | 0 | 0 | Hash(Partitioned) | 10g, 4g |  |  |
| checkpoint-hash | round | 0 | 1h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g |  |  |
| checkpoint-hash | group_by | 0 | 0h | 0 | 0 | SinglePartitioned | 10g |  |  |
| checkpoint-hash | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-hash | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-hash | window | 1 | 0h | 0 | 0 | WindowAgg | 10g |  |  |
| checkpoint-hash | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-hash | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-hash-fewer | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 8g, 8g |  |  |
| checkpoint-hash-fewer | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 8g, 4g |  |  |
| checkpoint-hash-fewer | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 8g, 8g |  |  |
| checkpoint-hash-fewer | group_by | 0 | 1h+1rr | 0 | 0 | Partial+FinalPartitioned | 8g |  |  |
| checkpoint-hash-fewer | order_by | 1 | 0h | 1 | 0 | - | 8g |  |  |
| checkpoint-hash-fewer | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 8g |  |  |
| checkpoint-hash-fewer | window | 1 | 0h | 0 | 0 | WindowAgg | 8g |  |  |
| checkpoint-hash-fewer | point | 0 | 0h+1rr | 0 | 0 | - | 8g |  |  |
| checkpoint-hash-fewer | range | 0 | 0h+1rr | 0 | 0 | - | 8g |  |  |
| checkpoint-hash-more | join_same | 0 | 0h | 0 | 0 | Hash(Partitioned) | 16g, 16g |  |  |
| checkpoint-hash-more | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 16g, 4g |  |  |
| checkpoint-hash-more | round | 0 | 1h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 16g, 16g |  |  |
| checkpoint-hash-more | group_by | 0 | 0h | 0 | 0 | SinglePartitioned | 16g |  |  |
| checkpoint-hash-more | order_by | 1 | 0h | 1 | 0 | - | 16g |  |  |
| checkpoint-hash-more | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 16g |  |  |
| checkpoint-hash-more | window | 1 | 0h | 0 | 0 | WindowAgg | 16g |  |  |
| checkpoint-hash-more | point | 0 | 0h | 0 | 0 | - | 16g |  |  |
| checkpoint-hash-more | range | 0 | 0h | 0 | 0 | - | 16g |  |  |
| checkpoint-hash-sorted | join_same | 0 | 0h | 0 | 0 | Hash(Partitioned) | 10g, 10g |  |  |
| checkpoint-hash-sorted | join_mixed | 0 | 1h | 0 | 0 | Hash(Partitioned) | 10g, 4g |  |  |
| checkpoint-hash-sorted | round | 0 | 1h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g |  |  |
| checkpoint-hash-sorted | group_by | 0 | 0h | 0 | 0 | SinglePartitioned[Sorted] | 10g |  |  |
| checkpoint-hash-sorted | order_by | 0 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-hash-sorted | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-hash-sorted | window | 0 | 0h | 0 | 0 | WindowAgg | 10g |  |  |
| checkpoint-hash-sorted | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-hash-sorted | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-range-sorted | join_same | 0 | 0h | 0 | 0 | Hash(Partitioned) | 10g, 10g |  |  |
| checkpoint-range-sorted | join_mixed | 0 | 1h | 0 | 0 | Hash(Partitioned) | 10g, 4g |  |  |
| checkpoint-range-sorted | round | 0 | 1h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g |  |  |
| checkpoint-range-sorted | group_by | 0 | 0h | 0 | 0 | SinglePartitioned[Sorted] | 10g |  |  |
| checkpoint-range-sorted | order_by | 0 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-range-sorted | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-range-sorted | window | 0 | 0h | 0 | 0 | WindowAgg | 10g |  |  |
| checkpoint-range-sorted | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-range-sorted | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-hash-sorted-pinned | join_same | 0 | 0h | 0 | 0 | Hash(Partitioned) | 10g, 10g |  |  |
| checkpoint-hash-sorted-pinned | join_mixed | 0 | 1h | 0 | 0 | Hash(Partitioned) | 10g, 4g |  |  |
| checkpoint-hash-sorted-pinned | round | 0 | 1h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g |  |  |
| checkpoint-hash-sorted-pinned | group_by | 0 | 0h | 0 | 0 | SinglePartitioned[Sorted] | 10g |  |  |
| checkpoint-hash-sorted-pinned | order_by | 0 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-hash-sorted-pinned | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-hash-sorted-pinned | window | 0 | 0h | 0 | 0 | WindowAgg | 10g |  |  |
| checkpoint-hash-sorted-pinned | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-hash-sorted-pinned | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-aggregate | join_same | 0 | 1h | 0 | 0 | Hash(Partitioned) | 10g, 10g |  |  |
| checkpoint-aggregate | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g |  |  |
| checkpoint-aggregate | round | 0 | 2h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g |  |  |
| checkpoint-aggregate | group_by | 0 | 0h | 0 | 0 | SinglePartitioned | 10g |  |  |
| checkpoint-aggregate | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-aggregate | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-aggregate | window | 1 | 0h | 0 | 0 | WindowAgg | 10g |  |  |
| checkpoint-aggregate | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-aggregate | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-aggregate-repartition | join_same | 0 | 0h | 0 | 0 | Hash(Partitioned) | 10g, 10g |  |  |
| checkpoint-aggregate-repartition | join_mixed | 0 | 1h | 0 | 0 | Hash(Partitioned) | 10g, 4g |  |  |
| checkpoint-aggregate-repartition | round | 0 | 1h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g |  |  |
| checkpoint-aggregate-repartition | group_by | 0 | 0h | 0 | 0 | SinglePartitioned | 10g |  |  |
| checkpoint-aggregate-repartition | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-aggregate-repartition | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-aggregate-repartition | window | 1 | 0h | 0 | 0 | WindowAgg | 10g |  |  |
| checkpoint-aggregate-repartition | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-aggregate-repartition | range | 0 | 0h | 0 | 0 | - | 10g |  |  |

### Every EXPLAIN variant on `parquet-plain` / `join_same`: local-hash

| Statement | Outcome |
|---|---|
| EXPLAIN | physical plan shown |
| EXPLAIN EXTENDED | physical plan shown |
| EXPLAIN FORMATTED | physical plan shown |
| EXPLAIN CODEGEN | physical plan shown |
| EXPLAIN COST | physical plan shown |
| EXPLAIN ANALYZE | physical plan shown |
| EXPLAIN VERBOSE | physical plan shown |

### Pruning (EXPLAIN ANALYZE, first file scan): local-hash

| Layout | Query | file_groups | output_rows | files_ranges_pruned_statistics | row_groups_pruned_statistics | row_groups_pruned_bloom_filter | page_index_rows_pruned | bytes_scanned |
|---|---|---|---|---|---|---|---|---|
| parquet-plain | point | 4 | 2.00 M | 4 total → 4 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 2.00 M matched | 21.25 M |
| parquet-plain | range | 4 | 2.00 M | 4 total → 4 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 2.00 M matched | 21.25 M |
| parquet-hash-sorted | point | 4 | 73.73 K | 4 total → 4 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 73.73 K matched | 4.44 M |
| parquet-hash-sorted | range | 4 | 49.15 K | 4 total → 4 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 49.15 K matched | 2.94 M |
| parquet-range-sorted | point | 4 | 73.73 K | 4 total → 4 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 73.73 K matched | 4.44 M |
| parquet-range-sorted | range | 4 | 49.15 K | 4 total → 4 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 49.15 K matched | 2.94 M |
| parquet-global-sorted | point | 4 | 73.73 K | 4 total → 4 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 73.73 K matched | 4.44 M |
| parquet-global-sorted | range | 4 | 49.15 K | 4 total → 4 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 49.15 K matched | 2.94 M |
| parquet-catalog-sorted | point | 10 | 73.73 K | 13 total → 13 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 73.73 K matched | 4.44 M |
| parquet-catalog-sorted | range | 10 | 49.15 K | 10 total → 10 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 49.15 K matched | 2.94 M |
| parquet-bucket-dirs | point | 10 | 86.79 K | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 86.79 K matched | 11.84 M |
| parquet-bucket-dirs | range | 10 | 204.8 K | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 204.8 K matched | 12.33 M |
| parquet-footer-sorted | point | 10 | 2.00 M | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 0 total → 0 matched | 22.60 M |
| parquet-footer-sorted | range | 10 | 2.00 M | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 0 total → 0 matched | 22.60 M |
| delta-plain | point | 10 | 2.00 M | 13 total → 13 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 2.00 M matched | 28.18 M |
| delta-plain | range | 10 | 2.00 M | 13 total → 13 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 2.00 M matched | 28.18 M |
| delta-hash-sorted | point | 10 | 2.00 M | 19 total → 19 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 31.38 M |
| delta-hash-sorted | range | 10 | 2.00 M | 19 total → 19 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 31.38 M |
| delta-catalog-sorted | point | 10 | 2.00 M | 19 total → 19 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 31.38 M |
| delta-catalog-sorted | range | 10 | 2.00 M | 19 total → 19 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 31.38 M |
| delta-global-sorted | point | 10 | 2.00 M | 10 total → 10 matched | 2 total → 2 matched | 2 total → 2 matched | 2.00 M total → 2.00 M matched | 27.11 M |
| delta-global-sorted | range | 10 | 2.00 M | 10 total → 10 matched | 2 total → 2 matched | 2 total → 2 matched | 2.00 M total → 2.00 M matched | 27.11 M |
| delta-bucket-dirs | point | 10 | 2.00 M | 19 total → 19 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 31.39 M |
| delta-bucket-dirs | range | 10 | 2.00 M | 19 total → 19 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 31.39 M |
| delta-clustered-input | point | 10 | 20.48 K | 10 total → 10 matched | 1 total → 1 matched | 1 total → 1 matched | 200.0 K total → 20.48 K matched | 1.66 M |
| delta-clustered-input | range | 10 | 20.48 K | 10 total → 10 matched | 1 total → 1 matched | 1 total → 1 matched | 200.0 K total → 20.48 K matched | 1.65 M |
| checkpoint-hash | point | 10 | 200.3 K | 10 total → 10 matched | 10 total → 10 matched | 10 total → 1 matched | 200.3 K total → 200.3 K matched | 5.35 M |
| checkpoint-hash | range | 10 | 2.00 M | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 27.17 M |
| checkpoint-hash-fewer | point | 8 | 250.0 K | 8 total → 8 matched | 8 total → 8 matched | 8 total → 1 matched | 250.0 K total → 250.0 K matched | 5.35 M |
| checkpoint-hash-fewer | range | 8 | 2.00 M | 8 total → 8 matched | 8 total → 8 matched | 8 total → 8 matched | 2.00 M total → 2.00 M matched | 25.90 M |
| checkpoint-hash-more | point | 16 | 125.0 K | 16 total → 16 matched | 16 total → 16 matched | 16 total → 1 matched | 125.0 K total → 125.0 K matched | 3.96 M |
| checkpoint-hash-more | range | 16 | 2.00 M | 16 total → 16 matched | 16 total → 16 matched | 16 total → 16 matched | 2.00 M total → 2.00 M matched | 29.72 M |
| checkpoint-hash-sorted | point | 10 | 200.3 K | 10 total → 10 matched | 10 total → 10 matched | 10 total → 1 matched | 200.3 K total → 200.3 K matched | 5.35 M |
| checkpoint-hash-sorted | range | 10 | 2.00 M | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 27.17 M |
| checkpoint-range-sorted | point | 10 | 200.3 K | 10 total → 10 matched | 10 total → 10 matched | 10 total → 1 matched | 200.3 K total → 200.3 K matched | 5.35 M |
| checkpoint-range-sorted | range | 10 | 2.00 M | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 27.17 M |
| checkpoint-hash-sorted-pinned | point | 10 | 8.19 K | 10 total → 10 matched | 10 total → 10 matched | 10 total → 1 matched | 200.3 K total → 8.19 K matched | 3.81 M |
| checkpoint-hash-sorted-pinned | range | 10 | 245.8 K | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 245.8 K matched | 12.80 M |
| checkpoint-aggregate | point | 10 | 200.3 K | 10 total → 10 matched | 10 total → 10 matched | 10 total → 1 matched | 200.3 K total → 200.3 K matched | 5.35 M |
| checkpoint-aggregate | range | 10 | 2.00 M | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 27.19 M |
| checkpoint-aggregate-repartition | point | 10 | 200.3 K | 10 total → 10 matched | 10 total → 10 matched | 10 total → 1 matched | 200.3 K total → 200.3 K matched | 5.35 M |
| checkpoint-aggregate-repartition | range | 10 | 2.00 M | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 27.19 M |

## Plans: local-smj

Server environment: `{"SAIL_MODE": "local", "SAIL_EXECUTION__CHECKPOINT__PATH": "file:///private/tmp/claude-501/-Users-alexy-src-grust/508c82ce-25d0-4e06-bb41-a1907715a911/scratchpad/sail-order-plans-ayjj9i8w/checkpoints-local-smj", "RUST_LOG": "warn", "SAIL_OPTIMIZER__PREFER_HASH_JOIN": "false"}`. Target partitions: 10.

| Layout | Query | Sort | Repartition | SPM | Coalesce | Join; aggregate; window | Scans (file groups, printed properties) | Job graph | Note |
|---|---|---|---|---|---|---|---|---|---|
| parquet-plain | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 4g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-plain | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 4g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-plain | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 4g, 4g | 4 stages, 3 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-plain | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 4g |  |  |
| parquet-plain | order_by | 1 | 0h | 1 | 0 | - | 4g |  |  |
| parquet-plain | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 4g |  |  |
| parquet-plain | window | 1 | 1h | 0 | 0 | WindowAgg | 4g |  |  |
| parquet-plain | point | 0 | 0h | 0 | 0 | - | 4g |  |  |
| parquet-plain | range | 0 | 0h | 0 | 0 | - | 4g |  |  |
| parquet-hash-sorted | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 4g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-hash-sorted | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 4g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-hash-sorted | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 4g, 4g | 4 stages, 3 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-hash-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 4g |  |  |
| parquet-hash-sorted | order_by | 1 | 0h | 1 | 0 | - | 4g |  |  |
| parquet-hash-sorted | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 4g |  |  |
| parquet-hash-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 4g |  |  |
| parquet-hash-sorted | point | 0 | 0h | 0 | 0 | - | 4g |  |  |
| parquet-hash-sorted | range | 0 | 0h | 0 | 0 | - | 4g |  |  |
| parquet-range-sorted | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 4g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-range-sorted | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 4g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-range-sorted | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 4g, 4g | 4 stages, 3 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-range-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 4g |  |  |
| parquet-range-sorted | order_by | 1 | 0h | 1 | 0 | - | 4g |  |  |
| parquet-range-sorted | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 4g |  |  |
| parquet-range-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 4g |  |  |
| parquet-range-sorted | point | 0 | 0h | 0 | 0 | - | 4g |  |  |
| parquet-range-sorted | range | 0 | 0h | 0 | 0 | - | 4g |  |  |
| parquet-global-sorted | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 4g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-global-sorted | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 4g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-global-sorted | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 4g, 4g | 4 stages, 3 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-global-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 4g |  |  |
| parquet-global-sorted | order_by | 1 | 0h | 1 | 0 | - | 4g |  |  |
| parquet-global-sorted | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 4g |  |  |
| parquet-global-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 4g |  |  |
| parquet-global-sorted | point | 0 | 0h | 0 | 0 | - | 4g |  |  |
| parquet-global-sorted | range | 0 | 0h | 0 | 0 | - | 4g |  |  |
| parquet-catalog-sorted | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 10g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-catalog-sorted | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-catalog-sorted | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-catalog-sorted | group_by | 0 | 1h (1 order-preserving) | 0 | 0 | Partial[Sorted]+FinalPartitioned[Sorted] | 10g |  |  |
| parquet-catalog-sorted | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| parquet-catalog-sorted | order_by_nulls_last | 0 | 0h | 1 | 0 | - | 10g |  |  |
| parquet-catalog-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g |  |  |
| parquet-catalog-sorted | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| parquet-catalog-sorted | range | 0 | 0h | 0 | 0 | - | 10g order=[id@0 ASC NULLS LAST] |  |  |
| parquet-bucket-dirs | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 10g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-bucket-dirs | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-bucket-dirs | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-bucket-dirs | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g |  |  |
| parquet-bucket-dirs | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| parquet-bucket-dirs | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| parquet-bucket-dirs | window | 1 | 1h | 0 | 0 | WindowAgg | 10g |  |  |
| parquet-bucket-dirs | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| parquet-bucket-dirs | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| parquet-footer-sorted | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 10g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-footer-sorted | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-footer-sorted | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| parquet-footer-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g |  |  |
| parquet-footer-sorted | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| parquet-footer-sorted | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| parquet-footer-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g |  |  |
| parquet-footer-sorted | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| parquet-footer-sorted | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-plain | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 10g |  |  |
| delta-plain | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| delta-plain | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g |  |  |
| delta-plain | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g |  |  |
| delta-plain | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-plain | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-plain | window | 1 | 1h | 0 | 0 | WindowAgg | 10g |  |  |
| delta-plain | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-plain | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-hash-sorted | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 10g |  |  |
| delta-hash-sorted | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| delta-hash-sorted | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g |  |  |
| delta-hash-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g |  |  |
| delta-hash-sorted | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-hash-sorted | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-hash-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g |  |  |
| delta-hash-sorted | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-hash-sorted | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-catalog-sorted | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 10g |  |  |
| delta-catalog-sorted | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| delta-catalog-sorted | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g |  |  |
| delta-catalog-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g |  |  |
| delta-catalog-sorted | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-catalog-sorted | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-catalog-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g |  |  |
| delta-catalog-sorted | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-catalog-sorted | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-global-sorted | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 10g |  |  |
| delta-global-sorted | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| delta-global-sorted | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g |  |  |
| delta-global-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g |  |  |
| delta-global-sorted | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-global-sorted | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-global-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g |  |  |
| delta-global-sorted | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-global-sorted | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-bucket-dirs | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 10g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| delta-bucket-dirs | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| delta-bucket-dirs | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| delta-bucket-dirs | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g |  |  |
| delta-bucket-dirs | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-bucket-dirs | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-bucket-dirs | window | 1 | 1h | 0 | 0 | WindowAgg | 10g |  |  |
| delta-bucket-dirs | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-bucket-dirs | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-clustered-input | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 10g |  |  |
| delta-clustered-input | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| delta-clustered-input | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g |  |  |
| delta-clustered-input | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g |  |  |
| delta-clustered-input | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-clustered-input | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| delta-clustered-input | window | 1 | 1h | 0 | 0 | WindowAgg | 10g |  |  |
| delta-clustered-input | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| delta-clustered-input | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-hash | join_same | 2 | 0h | 0 | 0 | SortMergeJoin | 10g, 10g |  |  |
| checkpoint-hash | join_mixed | 2 | 1h | 0 | 0 | SortMergeJoin | 10g, 4g | 2 stages, 1 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| checkpoint-hash | round | 2 | 1h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g |  |  |
| checkpoint-hash | group_by | 0 | 0h | 0 | 0 | SinglePartitioned | 10g |  |  |
| checkpoint-hash | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-hash | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-hash | window | 1 | 0h | 0 | 0 | WindowAgg | 10g |  |  |
| checkpoint-hash | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-hash | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-hash-fewer | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 8g, 8g |  |  |
| checkpoint-hash-fewer | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 8g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| checkpoint-hash-fewer | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 8g, 8g |  |  |
| checkpoint-hash-fewer | group_by | 0 | 1h+1rr | 0 | 0 | Partial+FinalPartitioned | 8g |  |  |
| checkpoint-hash-fewer | order_by | 1 | 0h | 1 | 0 | - | 8g |  |  |
| checkpoint-hash-fewer | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 8g |  |  |
| checkpoint-hash-fewer | window | 1 | 0h | 0 | 0 | WindowAgg | 8g |  |  |
| checkpoint-hash-fewer | point | 0 | 0h+1rr | 0 | 0 | - | 8g |  |  |
| checkpoint-hash-fewer | range | 0 | 0h+1rr | 0 | 0 | - | 8g |  |  |
| checkpoint-hash-more | join_same | 2 | 0h | 0 | 0 | SortMergeJoin | 16g, 16g |  |  |
| checkpoint-hash-more | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 16g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| checkpoint-hash-more | round | 2 | 1h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 16g, 16g |  |  |
| checkpoint-hash-more | group_by | 0 | 0h | 0 | 0 | SinglePartitioned | 16g |  |  |
| checkpoint-hash-more | order_by | 1 | 0h | 1 | 0 | - | 16g |  |  |
| checkpoint-hash-more | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 16g |  |  |
| checkpoint-hash-more | window | 1 | 0h | 0 | 0 | WindowAgg | 16g |  |  |
| checkpoint-hash-more | point | 0 | 0h | 0 | 0 | - | 16g |  |  |
| checkpoint-hash-more | range | 0 | 0h | 0 | 0 | - | 16g |  |  |
| checkpoint-hash-sorted | join_same | 0 | 0h | 0 | 0 | SortMergeJoin | 10g, 10g |  |  |
| checkpoint-hash-sorted | join_mixed | 1 | 1h | 0 | 0 | SortMergeJoin | 10g, 4g | 2 stages, 1 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| checkpoint-hash-sorted | round | 0 | 1h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g |  |  |
| checkpoint-hash-sorted | group_by | 0 | 0h | 0 | 0 | SinglePartitioned[Sorted] | 10g |  |  |
| checkpoint-hash-sorted | order_by | 0 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-hash-sorted | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-hash-sorted | window | 0 | 0h | 0 | 0 | WindowAgg | 10g |  |  |
| checkpoint-hash-sorted | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-hash-sorted | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-range-sorted | join_same | 0 | 0h | 0 | 0 | SortMergeJoin | 10g, 10g |  |  |
| checkpoint-range-sorted | join_mixed | 1 | 1h | 0 | 0 | SortMergeJoin | 10g, 4g | 2 stages, 1 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| checkpoint-range-sorted | round | 0 | 1h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g |  |  |
| checkpoint-range-sorted | group_by | 0 | 0h | 0 | 0 | SinglePartitioned[Sorted] | 10g |  |  |
| checkpoint-range-sorted | order_by | 0 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-range-sorted | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-range-sorted | window | 0 | 0h | 0 | 0 | WindowAgg | 10g |  |  |
| checkpoint-range-sorted | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-range-sorted | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-hash-sorted-pinned | join_same | 0 | 0h | 0 | 0 | SortMergeJoin | 10g, 10g |  |  |
| checkpoint-hash-sorted-pinned | join_mixed | 1 | 1h | 0 | 0 | SortMergeJoin | 10g, 4g | 2 stages, 1 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| checkpoint-hash-sorted-pinned | round | 0 | 1h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g |  |  |
| checkpoint-hash-sorted-pinned | group_by | 0 | 0h | 0 | 0 | SinglePartitioned[Sorted] | 10g |  |  |
| checkpoint-hash-sorted-pinned | order_by | 0 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-hash-sorted-pinned | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-hash-sorted-pinned | window | 0 | 0h | 0 | 0 | WindowAgg | 10g |  |  |
| checkpoint-hash-sorted-pinned | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-hash-sorted-pinned | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-aggregate | join_same | 2 | 1h | 0 | 0 | SortMergeJoin | 10g, 10g | 2 stages, 1 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| checkpoint-aggregate | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| checkpoint-aggregate | round | 2 | 2h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 3 stages, 2 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| checkpoint-aggregate | group_by | 0 | 0h | 0 | 0 | SinglePartitioned | 10g |  |  |
| checkpoint-aggregate | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-aggregate | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-aggregate | window | 1 | 0h | 0 | 0 | WindowAgg | 10g |  |  |
| checkpoint-aggregate | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-aggregate | range | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-aggregate-repartition | join_same | 2 | 0h | 0 | 0 | SortMergeJoin | 10g, 10g |  |  |
| checkpoint-aggregate-repartition | join_mixed | 2 | 1h | 0 | 0 | SortMergeJoin | 10g, 4g | 2 stages, 1 shuffles | EXPLAIN failed: Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. Plan taken from the local-cluster run. |
| checkpoint-aggregate-repartition | round | 2 | 1h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g |  |  |
| checkpoint-aggregate-repartition | group_by | 0 | 0h | 0 | 0 | SinglePartitioned | 10g |  |  |
| checkpoint-aggregate-repartition | order_by | 1 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-aggregate-repartition | order_by_nulls_last | 1 | 0h | 1 | 0 | - | 10g |  |  |
| checkpoint-aggregate-repartition | window | 1 | 0h | 0 | 0 | WindowAgg | 10g |  |  |
| checkpoint-aggregate-repartition | point | 0 | 0h | 0 | 0 | - | 10g |  |  |
| checkpoint-aggregate-repartition | range | 0 | 0h | 0 | 0 | - | 10g |  |  |

### Every EXPLAIN variant on `parquet-plain` / `join_same`: local-smj

| Statement | Outcome |
|---|---|
| EXPLAIN | Physical plan error: error in DataFusion: Invariant for ExecutionPlan node 'SortMergeJoinExec' failed caused by Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. This issue was likely caused by a bug in DataFu |
| EXPLAIN EXTENDED | Physical plan error: error in DataFusion: Invariant for ExecutionPlan node 'SortMergeJoinExec' failed caused by Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. This issue was likely caused by a bug in DataFu |
| EXPLAIN FORMATTED | Physical plan error: error in DataFusion: Invariant for ExecutionPlan node 'SortMergeJoinExec' failed caused by Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. This issue was likely caused by a bug in DataFu |
| EXPLAIN CODEGEN | Physical plan error: error in DataFusion: Invariant for ExecutionPlan node 'SortMergeJoinExec' failed caused by Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. This issue was likely caused by a bug in DataFu |
| EXPLAIN COST | Physical plan error: error in DataFusion: Invariant for ExecutionPlan node 'SortMergeJoinExec' failed caused by Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. This issue was likely caused by a bug in DataFu |
| EXPLAIN ANALYZE | Physical plan error: error in DataFusion: Invariant for ExecutionPlan node 'SortMergeJoinExec' failed caused by Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. This issue was likely caused by a bug in DataFu |
| EXPLAIN VERBOSE | Physical plan error: error in DataFusion: Invariant for ExecutionPlan node 'SortMergeJoinExec' failed caused by Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. This issue was likely caused by a bug in DataFu |

### Pruning (EXPLAIN ANALYZE, first file scan): local-smj

| Layout | Query | file_groups | output_rows | files_ranges_pruned_statistics | row_groups_pruned_statistics | row_groups_pruned_bloom_filter | page_index_rows_pruned | bytes_scanned |
|---|---|---|---|---|---|---|---|---|
| parquet-plain | point | 4 | 2.00 M | 4 total → 4 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 2.00 M matched | 21.25 M |
| parquet-plain | range | 4 | 2.00 M | 4 total → 4 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 2.00 M matched | 21.25 M |
| parquet-hash-sorted | point | 4 | 73.73 K | 4 total → 4 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 73.73 K matched | 4.44 M |
| parquet-hash-sorted | range | 4 | 49.15 K | 4 total → 4 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 49.15 K matched | 2.94 M |
| parquet-range-sorted | point | 4 | 73.73 K | 4 total → 4 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 73.73 K matched | 4.44 M |
| parquet-range-sorted | range | 4 | 49.15 K | 4 total → 4 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 49.15 K matched | 2.94 M |
| parquet-global-sorted | point | 4 | 73.73 K | 4 total → 4 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 73.73 K matched | 4.44 M |
| parquet-global-sorted | range | 4 | 49.15 K | 4 total → 4 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 49.15 K matched | 2.94 M |
| parquet-catalog-sorted | point | 10 | 73.73 K | 13 total → 13 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 73.73 K matched | 4.44 M |
| parquet-catalog-sorted | range | 10 | 49.15 K | 10 total → 10 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 49.15 K matched | 2.94 M |
| parquet-bucket-dirs | point | 10 | 86.79 K | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 86.79 K matched | 11.84 M |
| parquet-bucket-dirs | range | 10 | 204.8 K | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 204.8 K matched | 12.33 M |
| parquet-footer-sorted | point | 10 | 2.00 M | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 0 total → 0 matched | 22.60 M |
| parquet-footer-sorted | range | 10 | 2.00 M | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 0 total → 0 matched | 22.60 M |
| delta-plain | point | 10 | 2.00 M | 13 total → 13 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 2.00 M matched | 28.18 M |
| delta-plain | range | 10 | 2.00 M | 13 total → 13 matched | 4 total → 4 matched | 4 total → 4 matched | 2.00 M total → 2.00 M matched | 28.18 M |
| delta-hash-sorted | point | 10 | 2.00 M | 19 total → 19 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 31.38 M |
| delta-hash-sorted | range | 10 | 2.00 M | 19 total → 19 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 31.38 M |
| delta-catalog-sorted | point | 10 | 2.00 M | 19 total → 19 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 31.38 M |
| delta-catalog-sorted | range | 10 | 2.00 M | 19 total → 19 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 31.38 M |
| delta-global-sorted | point | 10 | 2.00 M | 10 total → 10 matched | 2 total → 2 matched | 2 total → 2 matched | 2.00 M total → 2.00 M matched | 27.11 M |
| delta-global-sorted | range | 10 | 2.00 M | 10 total → 10 matched | 2 total → 2 matched | 2 total → 2 matched | 2.00 M total → 2.00 M matched | 27.11 M |
| delta-bucket-dirs | point | 10 | 2.00 M | 19 total → 19 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 31.39 M |
| delta-bucket-dirs | range | 10 | 2.00 M | 19 total → 19 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 31.39 M |
| delta-clustered-input | point | 10 | 20.48 K | 10 total → 10 matched | 1 total → 1 matched | 1 total → 1 matched | 200.0 K total → 20.48 K matched | 1.66 M |
| delta-clustered-input | range | 10 | 20.48 K | 10 total → 10 matched | 1 total → 1 matched | 1 total → 1 matched | 200.0 K total → 20.48 K matched | 1.65 M |
| checkpoint-hash | point | 10 | 200.3 K | 10 total → 10 matched | 10 total → 10 matched | 10 total → 1 matched | 200.3 K total → 200.3 K matched | 5.35 M |
| checkpoint-hash | range | 10 | 2.00 M | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 27.17 M |
| checkpoint-hash-fewer | point | 8 | 250.0 K | 8 total → 8 matched | 8 total → 8 matched | 8 total → 1 matched | 250.0 K total → 250.0 K matched | 5.35 M |
| checkpoint-hash-fewer | range | 8 | 2.00 M | 8 total → 8 matched | 8 total → 8 matched | 8 total → 8 matched | 2.00 M total → 2.00 M matched | 25.92 M |
| checkpoint-hash-more | point | 16 | 125.0 K | 16 total → 16 matched | 16 total → 16 matched | 16 total → 1 matched | 125.0 K total → 125.0 K matched | 3.96 M |
| checkpoint-hash-more | range | 16 | 2.00 M | 16 total → 16 matched | 16 total → 16 matched | 16 total → 16 matched | 2.00 M total → 2.00 M matched | 29.70 M |
| checkpoint-hash-sorted | point | 10 | 200.3 K | 10 total → 10 matched | 10 total → 10 matched | 10 total → 1 matched | 200.3 K total → 200.3 K matched | 5.35 M |
| checkpoint-hash-sorted | range | 10 | 2.00 M | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 27.17 M |
| checkpoint-range-sorted | point | 10 | 200.3 K | 10 total → 10 matched | 10 total → 10 matched | 10 total → 1 matched | 200.3 K total → 200.3 K matched | 5.35 M |
| checkpoint-range-sorted | range | 10 | 2.00 M | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 27.17 M |
| checkpoint-hash-sorted-pinned | point | 10 | 8.19 K | 10 total → 10 matched | 10 total → 10 matched | 10 total → 1 matched | 200.3 K total → 8.19 K matched | 3.81 M |
| checkpoint-hash-sorted-pinned | range | 10 | 245.8 K | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 245.8 K matched | 12.80 M |
| checkpoint-aggregate | point | 10 | 200.3 K | 10 total → 10 matched | 10 total → 10 matched | 10 total → 1 matched | 200.3 K total → 200.3 K matched | 5.35 M |
| checkpoint-aggregate | range | 10 | 2.00 M | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 27.19 M |
| checkpoint-aggregate-repartition | point | 10 | 200.3 K | 10 total → 10 matched | 10 total → 10 matched | 10 total → 1 matched | 200.3 K total → 200.3 K matched | 5.35 M |
| checkpoint-aggregate-repartition | range | 10 | 2.00 M | 10 total → 10 matched | 10 total → 10 matched | 10 total → 10 matched | 2.00 M total → 2.00 M matched | 27.19 M |

## Plans: cluster-hash

Server environment: `{"SAIL_MODE": "local-cluster", "SAIL_EXECUTION__CHECKPOINT__PATH": "file:///private/tmp/claude-501/-Users-alexy-src-grust/508c82ce-25d0-4e06-bb41-a1907715a911/scratchpad/sail-order-plans-ayjj9i8w/checkpoints-cluster-hash", "RUST_LOG": "warn,sail_execution::driver::job_scheduler::core=debug"}`. Target partitions: 10.

| Layout | Query | Sort | Repartition | SPM | Coalesce | Join; aggregate; window | Scans (file groups, printed properties) | Job graph | Note |
|---|---|---|---|---|---|---|---|---|---|
| parquet-plain | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 4g, 4g | 3 stages, 2 shuffles |  |
| parquet-plain | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 4g, 4g | 3 stages, 2 shuffles |  |
| parquet-plain | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 4g, 4g | 4 stages, 3 shuffles |  |
| parquet-plain | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 4g | 2 stages, 1 shuffles |  |
| parquet-plain | window | 1 | 1h | 0 | 0 | WindowAgg | 4g | 2 stages, 1 shuffles |  |
| parquet-hash-sorted | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 4g, 4g | 3 stages, 2 shuffles |  |
| parquet-hash-sorted | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 4g, 4g | 3 stages, 2 shuffles |  |
| parquet-hash-sorted | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 4g, 4g | 4 stages, 3 shuffles |  |
| parquet-hash-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 4g | 2 stages, 1 shuffles |  |
| parquet-hash-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 4g | 2 stages, 1 shuffles |  |
| parquet-range-sorted | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 4g, 4g | 3 stages, 2 shuffles |  |
| parquet-range-sorted | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 4g, 4g | 3 stages, 2 shuffles |  |
| parquet-range-sorted | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 4g, 4g | 4 stages, 3 shuffles |  |
| parquet-range-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 4g | 2 stages, 1 shuffles |  |
| parquet-range-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 4g | 2 stages, 1 shuffles |  |
| parquet-global-sorted | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 4g, 4g | 3 stages, 2 shuffles |  |
| parquet-global-sorted | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 4g, 4g | 3 stages, 2 shuffles |  |
| parquet-global-sorted | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 4g, 4g | 4 stages, 3 shuffles |  |
| parquet-global-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 4g | 2 stages, 1 shuffles |  |
| parquet-global-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 4g | 2 stages, 1 shuffles |  |
| parquet-catalog-sorted | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 10g | 3 stages, 2 shuffles |  |
| parquet-catalog-sorted | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g | 3 stages, 2 shuffles |  |
| parquet-catalog-sorted | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles |  |
| parquet-catalog-sorted | group_by | 0 | 1h (1 order-preserving) | 0 | 0 | Partial[Sorted]+FinalPartitioned[Sorted] | 10g |  | execution FAILED: internal error: repartition is order-preserving and would result in incorrect results in distributed execution |
| parquet-catalog-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g | 2 stages, 1 shuffles |  |
| parquet-bucket-dirs | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 10g | 3 stages, 2 shuffles |  |
| parquet-bucket-dirs | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g | 3 stages, 2 shuffles |  |
| parquet-bucket-dirs | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles |  |
| parquet-bucket-dirs | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g | 2 stages, 1 shuffles |  |
| parquet-bucket-dirs | window | 1 | 1h | 0 | 0 | WindowAgg | 10g | 2 stages, 1 shuffles |  |
| parquet-footer-sorted | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 10g | 3 stages, 2 shuffles |  |
| parquet-footer-sorted | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g | 3 stages, 2 shuffles |  |
| parquet-footer-sorted | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles |  |
| parquet-footer-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g | 2 stages, 1 shuffles |  |
| parquet-footer-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g | 2 stages, 1 shuffles |  |
| delta-plain | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 10g | 3 stages, 2 shuffles |  |
| delta-plain | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g | 3 stages, 2 shuffles |  |
| delta-plain | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles |  |
| delta-plain | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g | 2 stages, 1 shuffles |  |
| delta-plain | window | 1 | 1h | 0 | 0 | WindowAgg | 10g | 2 stages, 1 shuffles |  |
| delta-hash-sorted | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 10g | 3 stages, 2 shuffles |  |
| delta-hash-sorted | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g | 3 stages, 2 shuffles |  |
| delta-hash-sorted | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles |  |
| delta-hash-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g | 2 stages, 1 shuffles |  |
| delta-hash-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g | 2 stages, 1 shuffles |  |
| delta-catalog-sorted | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 10g | 3 stages, 2 shuffles |  |
| delta-catalog-sorted | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g | 3 stages, 2 shuffles |  |
| delta-catalog-sorted | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles |  |
| delta-catalog-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g | 2 stages, 1 shuffles |  |
| delta-catalog-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g | 2 stages, 1 shuffles |  |
| delta-global-sorted | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 10g | 3 stages, 2 shuffles |  |
| delta-global-sorted | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g | 3 stages, 2 shuffles |  |
| delta-global-sorted | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles |  |
| delta-global-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g | 2 stages, 1 shuffles |  |
| delta-global-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g | 2 stages, 1 shuffles |  |
| delta-bucket-dirs | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 10g | 3 stages, 2 shuffles |  |
| delta-bucket-dirs | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g | 3 stages, 2 shuffles |  |
| delta-bucket-dirs | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles |  |
| delta-bucket-dirs | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g | 2 stages, 1 shuffles |  |
| delta-bucket-dirs | window | 1 | 1h | 0 | 0 | WindowAgg | 10g | 2 stages, 1 shuffles |  |
| delta-clustered-input | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 10g | 3 stages, 2 shuffles |  |
| delta-clustered-input | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g | 3 stages, 2 shuffles |  |
| delta-clustered-input | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles |  |
| delta-clustered-input | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g | 2 stages, 1 shuffles |  |
| delta-clustered-input | window | 1 | 1h | 0 | 0 | WindowAgg | 10g | 2 stages, 1 shuffles |  |
| checkpoint-hash | join_same | 0 | 0h | 0 | 0 | Hash(Partitioned) | 10g, 10g | 1 stages, 0 shuffles |  |
| checkpoint-hash | join_mixed | 0 | 1h | 0 | 0 | Hash(Partitioned) | 10g, 4g | 2 stages, 1 shuffles |  |
| checkpoint-hash | round | 0 | 1h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g | 2 stages, 1 shuffles |  |
| checkpoint-hash | group_by | 0 | 0h | 0 | 0 | SinglePartitioned | 10g | 1 stages, 0 shuffles |  |
| checkpoint-hash | window | 1 | 0h | 0 | 0 | WindowAgg | 10g | 1 stages, 0 shuffles |  |
| checkpoint-hash-fewer | join_same | 0 | 2h | 0 | 0 | Hash(Partitioned) | 8g, 8g | 3 stages, 2 shuffles |  |
| checkpoint-hash-fewer | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 8g, 4g | 3 stages, 2 shuffles |  |
| checkpoint-hash-fewer | round | 0 | 3h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 8g, 8g | 4 stages, 3 shuffles |  |
| checkpoint-hash-fewer | group_by | 0 | 1h+1rr | 0 | 0 | Partial+FinalPartitioned | 8g | 3 stages, 2 shuffles |  |
| checkpoint-hash-fewer | window | 1 | 0h+1rr | 0 | 0 | WindowAgg | 8g | 2 stages, 1 shuffles |  |
| checkpoint-hash-more | join_same | 0 | 0h | 0 | 0 | Hash(Partitioned) | 16g, 16g | 1 stages, 0 shuffles |  |
| checkpoint-hash-more | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 16g, 4g | 3 stages, 2 shuffles |  |
| checkpoint-hash-more | round | 0 | 1h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 16g, 16g | 2 stages, 1 shuffles |  |
| checkpoint-hash-more | group_by | 0 | 0h | 0 | 0 | SinglePartitioned | 16g | 1 stages, 0 shuffles |  |
| checkpoint-hash-more | window | 1 | 0h | 0 | 0 | WindowAgg | 16g | 1 stages, 0 shuffles |  |
| checkpoint-hash-sorted | join_same | 0 | 0h | 0 | 0 | Hash(Partitioned) | 10g, 10g | 1 stages, 0 shuffles |  |
| checkpoint-hash-sorted | join_mixed | 0 | 1h | 0 | 0 | Hash(Partitioned) | 10g, 4g | 2 stages, 1 shuffles |  |
| checkpoint-hash-sorted | round | 0 | 1h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g | 2 stages, 1 shuffles |  |
| checkpoint-hash-sorted | group_by | 0 | 0h | 0 | 0 | SinglePartitioned[Sorted] | 10g | 1 stages, 0 shuffles |  |
| checkpoint-hash-sorted | window | 0 | 0h | 0 | 0 | WindowAgg | 10g | 1 stages, 0 shuffles |  |
| checkpoint-range-sorted | join_same | 0 | 0h | 0 | 0 | Hash(Partitioned) | 10g, 10g | 1 stages, 0 shuffles |  |
| checkpoint-range-sorted | join_mixed | 0 | 1h | 0 | 0 | Hash(Partitioned) | 10g, 4g | 2 stages, 1 shuffles |  |
| checkpoint-range-sorted | round | 0 | 1h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g | 2 stages, 1 shuffles |  |
| checkpoint-range-sorted | group_by | 0 | 0h | 0 | 0 | SinglePartitioned[Sorted] | 10g | 1 stages, 0 shuffles |  |
| checkpoint-range-sorted | window | 0 | 0h | 0 | 0 | WindowAgg | 10g | 1 stages, 0 shuffles |  |
| checkpoint-hash-sorted-pinned | join_same | 0 | 0h | 0 | 0 | Hash(Partitioned) | 10g, 10g | 1 stages, 0 shuffles |  |
| checkpoint-hash-sorted-pinned | join_mixed | 0 | 1h | 0 | 0 | Hash(Partitioned) | 10g, 4g | 2 stages, 1 shuffles |  |
| checkpoint-hash-sorted-pinned | round | 0 | 1h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g | 2 stages, 1 shuffles |  |
| checkpoint-hash-sorted-pinned | group_by | 0 | 0h | 0 | 0 | SinglePartitioned[Sorted] | 10g | 1 stages, 0 shuffles |  |
| checkpoint-hash-sorted-pinned | window | 0 | 0h | 0 | 0 | WindowAgg | 10g | 1 stages, 0 shuffles |  |
| checkpoint-aggregate | join_same | 0 | 1h | 0 | 0 | Hash(Partitioned) | 10g, 10g | 2 stages, 1 shuffles |  |
| checkpoint-aggregate | join_mixed | 0 | 2h | 0 | 0 | Hash(Partitioned) | 10g, 4g | 3 stages, 2 shuffles |  |
| checkpoint-aggregate | round | 0 | 2h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g | 3 stages, 2 shuffles |  |
| checkpoint-aggregate | group_by | 0 | 0h | 0 | 0 | SinglePartitioned | 10g | 1 stages, 0 shuffles |  |
| checkpoint-aggregate | window | 1 | 0h | 0 | 0 | WindowAgg | 10g | 1 stages, 0 shuffles |  |
| checkpoint-aggregate-repartition | join_same | 0 | 0h | 0 | 0 | Hash(Partitioned) | 10g, 10g | 1 stages, 0 shuffles |  |
| checkpoint-aggregate-repartition | join_mixed | 0 | 1h | 0 | 0 | Hash(Partitioned) | 10g, 4g | 2 stages, 1 shuffles |  |
| checkpoint-aggregate-repartition | round | 0 | 1h | 0 | 0 | Hash(Partitioned); Partial+FinalPartitioned | 10g, 10g | 2 stages, 1 shuffles |  |
| checkpoint-aggregate-repartition | group_by | 0 | 0h | 0 | 0 | SinglePartitioned | 10g | 1 stages, 0 shuffles |  |
| checkpoint-aggregate-repartition | window | 1 | 0h | 0 | 0 | WindowAgg | 10g | 1 stages, 0 shuffles |  |

## Plans: cluster-smj

Server environment: `{"SAIL_MODE": "local-cluster", "SAIL_EXECUTION__CHECKPOINT__PATH": "file:///private/tmp/claude-501/-Users-alexy-src-grust/508c82ce-25d0-4e06-bb41-a1907715a911/scratchpad/sail-order-plans-ayjj9i8w/checkpoints-cluster-smj", "RUST_LOG": "warn,sail_execution::driver::job_scheduler::core=debug", "SAIL_OPTIMIZER__PREFER_HASH_JOIN": "false"}`. Target partitions: 10.

| Layout | Query | Sort | Repartition | SPM | Coalesce | Join; aggregate; window | Scans (file groups, printed properties) | Job graph | Note |
|---|---|---|---|---|---|---|---|---|---|
| parquet-plain | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 4g, 4g | 3 stages, 2 shuffles |  |
| parquet-plain | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 4g, 4g | 3 stages, 2 shuffles |  |
| parquet-plain | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 4g, 4g | 4 stages, 3 shuffles |  |
| parquet-plain | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 4g | 2 stages, 1 shuffles |  |
| parquet-plain | window | 1 | 1h | 0 | 0 | WindowAgg | 4g | 2 stages, 1 shuffles |  |
| parquet-hash-sorted | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 4g, 4g | 3 stages, 2 shuffles |  |
| parquet-hash-sorted | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 4g, 4g | 3 stages, 2 shuffles |  |
| parquet-hash-sorted | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 4g, 4g | 4 stages, 3 shuffles |  |
| parquet-hash-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 4g | 2 stages, 1 shuffles |  |
| parquet-hash-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 4g | 2 stages, 1 shuffles |  |
| parquet-range-sorted | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 4g, 4g | 3 stages, 2 shuffles |  |
| parquet-range-sorted | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 4g, 4g | 3 stages, 2 shuffles |  |
| parquet-range-sorted | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 4g, 4g | 4 stages, 3 shuffles |  |
| parquet-range-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 4g | 2 stages, 1 shuffles |  |
| parquet-range-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 4g | 2 stages, 1 shuffles |  |
| parquet-global-sorted | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 4g, 4g | 3 stages, 2 shuffles |  |
| parquet-global-sorted | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 4g, 4g | 3 stages, 2 shuffles |  |
| parquet-global-sorted | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 4g, 4g | 4 stages, 3 shuffles |  |
| parquet-global-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 4g | 2 stages, 1 shuffles |  |
| parquet-global-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 4g | 2 stages, 1 shuffles |  |
| parquet-catalog-sorted | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 10g | 3 stages, 2 shuffles |  |
| parquet-catalog-sorted | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles |  |
| parquet-catalog-sorted | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles |  |
| parquet-catalog-sorted | group_by | 0 | 1h (1 order-preserving) | 0 | 0 | Partial[Sorted]+FinalPartitioned[Sorted] | 10g |  | execution FAILED: internal error: repartition is order-preserving and would result in incorrect results in distributed execution |
| parquet-catalog-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g | 2 stages, 1 shuffles |  |
| parquet-bucket-dirs | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 10g | 3 stages, 2 shuffles |  |
| parquet-bucket-dirs | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles |  |
| parquet-bucket-dirs | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles |  |
| parquet-bucket-dirs | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g | 2 stages, 1 shuffles |  |
| parquet-bucket-dirs | window | 1 | 1h | 0 | 0 | WindowAgg | 10g | 2 stages, 1 shuffles |  |
| parquet-footer-sorted | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 10g | 3 stages, 2 shuffles |  |
| parquet-footer-sorted | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles |  |
| parquet-footer-sorted | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles |  |
| parquet-footer-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g | 2 stages, 1 shuffles |  |
| parquet-footer-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g | 2 stages, 1 shuffles |  |
| delta-plain | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 10g | 3 stages, 2 shuffles |  |
| delta-plain | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles |  |
| delta-plain | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles |  |
| delta-plain | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g | 2 stages, 1 shuffles |  |
| delta-plain | window | 1 | 1h | 0 | 0 | WindowAgg | 10g | 2 stages, 1 shuffles |  |
| delta-hash-sorted | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 10g | 3 stages, 2 shuffles |  |
| delta-hash-sorted | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles |  |
| delta-hash-sorted | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles |  |
| delta-hash-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g | 2 stages, 1 shuffles |  |
| delta-hash-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g | 2 stages, 1 shuffles |  |
| delta-catalog-sorted | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 10g | 3 stages, 2 shuffles |  |
| delta-catalog-sorted | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles |  |
| delta-catalog-sorted | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles |  |
| delta-catalog-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g | 2 stages, 1 shuffles |  |
| delta-catalog-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g | 2 stages, 1 shuffles |  |
| delta-global-sorted | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 10g | 3 stages, 2 shuffles |  |
| delta-global-sorted | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles |  |
| delta-global-sorted | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles |  |
| delta-global-sorted | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g | 2 stages, 1 shuffles |  |
| delta-global-sorted | window | 1 | 1h | 0 | 0 | WindowAgg | 10g | 2 stages, 1 shuffles |  |
| delta-bucket-dirs | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 10g | 3 stages, 2 shuffles |  |
| delta-bucket-dirs | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles |  |
| delta-bucket-dirs | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles |  |
| delta-bucket-dirs | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g | 2 stages, 1 shuffles |  |
| delta-bucket-dirs | window | 1 | 1h | 0 | 0 | WindowAgg | 10g | 2 stages, 1 shuffles |  |
| delta-clustered-input | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 10g | 3 stages, 2 shuffles |  |
| delta-clustered-input | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles |  |
| delta-clustered-input | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 4 stages, 3 shuffles |  |
| delta-clustered-input | group_by | 0 | 1h | 0 | 0 | Partial+FinalPartitioned | 10g | 2 stages, 1 shuffles |  |
| delta-clustered-input | window | 1 | 1h | 0 | 0 | WindowAgg | 10g | 2 stages, 1 shuffles |  |
| checkpoint-hash | join_same | 2 | 0h | 0 | 0 | SortMergeJoin | 10g, 10g | 1 stages, 0 shuffles |  |
| checkpoint-hash | join_mixed | 2 | 1h | 0 | 0 | SortMergeJoin | 10g, 4g | 2 stages, 1 shuffles |  |
| checkpoint-hash | round | 2 | 1h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 2 stages, 1 shuffles |  |
| checkpoint-hash | group_by | 0 | 0h | 0 | 0 | SinglePartitioned | 10g | 1 stages, 0 shuffles |  |
| checkpoint-hash | window | 1 | 0h | 0 | 0 | WindowAgg | 10g | 1 stages, 0 shuffles |  |
| checkpoint-hash-fewer | join_same | 2 | 2h | 0 | 0 | SortMergeJoin | 8g, 8g | 3 stages, 2 shuffles |  |
| checkpoint-hash-fewer | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 8g, 4g | 3 stages, 2 shuffles |  |
| checkpoint-hash-fewer | round | 2 | 3h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 8g, 8g | 4 stages, 3 shuffles |  |
| checkpoint-hash-fewer | group_by | 0 | 1h+1rr | 0 | 0 | Partial+FinalPartitioned | 8g | 3 stages, 2 shuffles |  |
| checkpoint-hash-fewer | window | 1 | 0h+1rr | 0 | 0 | WindowAgg | 8g | 2 stages, 1 shuffles |  |
| checkpoint-hash-more | join_same | 2 | 0h | 0 | 0 | SortMergeJoin | 16g, 16g | 1 stages, 0 shuffles |  |
| checkpoint-hash-more | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 16g, 4g | 3 stages, 2 shuffles |  |
| checkpoint-hash-more | round | 2 | 1h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 16g, 16g | 2 stages, 1 shuffles |  |
| checkpoint-hash-more | group_by | 0 | 0h | 0 | 0 | SinglePartitioned | 16g | 1 stages, 0 shuffles |  |
| checkpoint-hash-more | window | 1 | 0h | 0 | 0 | WindowAgg | 16g | 1 stages, 0 shuffles |  |
| checkpoint-hash-sorted | join_same | 0 | 0h | 0 | 0 | SortMergeJoin | 10g, 10g | 1 stages, 0 shuffles |  |
| checkpoint-hash-sorted | join_mixed | 1 | 1h | 0 | 0 | SortMergeJoin | 10g, 4g | 2 stages, 1 shuffles |  |
| checkpoint-hash-sorted | round | 0 | 1h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 2 stages, 1 shuffles |  |
| checkpoint-hash-sorted | group_by | 0 | 0h | 0 | 0 | SinglePartitioned[Sorted] | 10g | 1 stages, 0 shuffles |  |
| checkpoint-hash-sorted | window | 0 | 0h | 0 | 0 | WindowAgg | 10g | 1 stages, 0 shuffles |  |
| checkpoint-range-sorted | join_same | 0 | 0h | 0 | 0 | SortMergeJoin | 10g, 10g | 1 stages, 0 shuffles |  |
| checkpoint-range-sorted | join_mixed | 1 | 1h | 0 | 0 | SortMergeJoin | 10g, 4g | 2 stages, 1 shuffles |  |
| checkpoint-range-sorted | round | 0 | 1h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 2 stages, 1 shuffles |  |
| checkpoint-range-sorted | group_by | 0 | 0h | 0 | 0 | SinglePartitioned[Sorted] | 10g | 1 stages, 0 shuffles |  |
| checkpoint-range-sorted | window | 0 | 0h | 0 | 0 | WindowAgg | 10g | 1 stages, 0 shuffles |  |
| checkpoint-hash-sorted-pinned | join_same | 0 | 0h | 0 | 0 | SortMergeJoin | 10g, 10g | 1 stages, 0 shuffles |  |
| checkpoint-hash-sorted-pinned | join_mixed | 1 | 1h | 0 | 0 | SortMergeJoin | 10g, 4g | 2 stages, 1 shuffles |  |
| checkpoint-hash-sorted-pinned | round | 0 | 1h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 2 stages, 1 shuffles |  |
| checkpoint-hash-sorted-pinned | group_by | 0 | 0h | 0 | 0 | SinglePartitioned[Sorted] | 10g | 1 stages, 0 shuffles |  |
| checkpoint-hash-sorted-pinned | window | 0 | 0h | 0 | 0 | WindowAgg | 10g | 1 stages, 0 shuffles |  |
| checkpoint-aggregate | join_same | 2 | 1h | 0 | 0 | SortMergeJoin | 10g, 10g | 2 stages, 1 shuffles |  |
| checkpoint-aggregate | join_mixed | 2 | 2h | 0 | 0 | SortMergeJoin | 10g, 4g | 3 stages, 2 shuffles |  |
| checkpoint-aggregate | round | 2 | 2h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 3 stages, 2 shuffles |  |
| checkpoint-aggregate | group_by | 0 | 0h | 0 | 0 | SinglePartitioned | 10g | 1 stages, 0 shuffles |  |
| checkpoint-aggregate | window | 1 | 0h | 0 | 0 | WindowAgg | 10g | 1 stages, 0 shuffles |  |
| checkpoint-aggregate-repartition | join_same | 2 | 0h | 0 | 0 | SortMergeJoin | 10g, 10g | 1 stages, 0 shuffles |  |
| checkpoint-aggregate-repartition | join_mixed | 2 | 1h | 0 | 0 | SortMergeJoin | 10g, 4g | 2 stages, 1 shuffles |  |
| checkpoint-aggregate-repartition | round | 2 | 1h | 0 | 0 | SortMergeJoin; Partial+FinalPartitioned | 10g, 10g | 2 stages, 1 shuffles |  |
| checkpoint-aggregate-repartition | group_by | 0 | 0h | 0 | 0 | SinglePartitioned | 10g | 1 stages, 0 shuffles |  |
| checkpoint-aggregate-repartition | window | 1 | 0h | 0 | 0 | WindowAgg | 10g | 1 stages, 0 shuffles |  |
