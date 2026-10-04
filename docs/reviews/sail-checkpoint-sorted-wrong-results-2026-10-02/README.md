# Note for Sail upstream: a checkpoint taken after a sort returns wrong results

> **For filing upstream, use [`../sail-upstream-reports-2026-10-02/01-checkpoint-after-sort-wrong-results/`](../sail-upstream-reports-2026-10-02/01-checkpoint-after-sort-wrong-results/README.md).** That version is standalone. This note is kept because it carries the project's own context and links.

Written 2026-10-02 for the upstream Sail maintainers. It is self-contained:
a reproducer, what it prints, the code path, and what would fix it. Nothing
here depends on the graph extensions.

## Summary

`DataFrame.checkpoint()` taken after `sortWithinPartitions(k)` or
`orderBy(k)` gives a frame that answers later queries wrongly. On 4,000,000
rows with 1,000,003 distinct keys, `GROUP BY k` returns 4,000,000 groups and
`SELECT DISTINCT k` returns 4,000,000 keys. No error, no warning, default
settings.

The checkpoint records that its data is sorted by `k`. The files it writes
are not sorted: the optimizer removes the sort before the write. Every later
plan trusts the recorded order.

## Reproduce

```sh
python checkpoint_sorted_repro.py /path/to/release/sail
```

[`checkpoint_sorted_repro.py`](checkpoint_sorted_repro.py) starts a server in
local mode with `SAIL_EXECUTION__CHECKPOINT__PATH` set, builds one frame,
checkpoints it three ways, and asks each checkpoint the same questions. It
also reads the checkpoint's Parquet files with pyarrow and says whether each
is sorted. It needs `pyspark[connect]` 4.0 and `pyarrow`.

The frame:

```python
rows = spark.range(4_000_000).select(
    ((F.col("id") * 2654435761) % 1_000_003).alias("k"), F.col("id").alias("v"))
```

## Measured

Unmodified upstream `main` at `99ee46f69` (2026-10-02, Sail 0.7.2,
DataFusion 55.1.0), `cargo build --release --locked -p sail-cli`, Apple M1
Max, macOS, local mode, default settings. Output:
[`repro-upstream-99ee46f69.txt`](repro-upstream-99ee46f69.txt).

| Checkpoint taken after | Rows | `GROUP BY k`: groups | `DISTINCT k` | Hash join on `k`: rows | Files sorted by `k` | |
|---|---|---|---|---|---|---|
| (truth, no checkpoint) | 4,000,000 | 1,000,003 | 1,000,003 | 4,000,000 | | |
| `repartition(10, k)` | 4,000,000 | 1,000,003 | 1,000,003 | 4,000,000 | 0 of 10 | correct |
| `repartition(10, k).sortWithinPartitions(k)` | 4,000,000 | **4,000,000** | **4,000,000** | 4,000,000 | **0 of 10** | wrong |
| `orderBy(k)` | 4,000,000 | **3,963,113** | **3,963,113** | 4,000,000 | **0 of 1** | wrong |

The plan of the wrong aggregate has no sort and aggregates in sorted mode:

```
AggregateExec: mode=SinglePartitioned, gby=[#0@0 as #0], aggr=[count(Int64(1))], ordering_mode=Sorted
  ProjectionExec: expr=[#0@0 as #0]
    DataSourceExec: file_groups={10 groups: [[.../part-00000-....parquet], ...
```

A sorted-mode aggregate closes a group when the key changes. Over unsorted
input it emits a new group at every change, which is where the 4,000,000
comes from.

The hash join is right because it does not use the order. With
`SAIL_OPTIMIZER__PREFER_HASH_JOIN=false` the join is a sort-merge join with
no `SortExec`, and it is wrong too: a wider run of the same case returned 14
rows for 4,000,000
([`../sem-research-2026-10-02/delta-order-plans/README.md`](../sem-research-2026-10-02/delta-order-plans/README.md),
section 4). Window functions partitioned by the key are wrong in the same
way. The wrong counts vary a little from run to run; that they are wrong
does not.

## Where it goes wrong

1. **The order is recorded before the optimizer runs.**
   `crates/sail-session/src/planner.rs:195-200` builds the checkpoint
   command during physical planning and takes `input.output_ordering()` and
   `input.output_partitioning()` from the unoptimized physical input. At
   that point the user's `SortExec` is still there, so the order is recorded.
2. **The writer does not ask for that order.**
   `RemoteCheckpointWriteExec`
   (`crates/sail-physical-plan/src/remote_checkpoint.rs:478`) implements
   neither `required_input_ordering` nor `maintains_input_order`. To
   DataFusion's sort enforcement a `SortExec` under such a node is
   unnecessary, and it is removed
   (`datafusion-physical-optimizer` 55.1.0,
   `ensure_requirements/enforce_sorting`). The executed write plan is
   `RemoteCheckpointCommit > CoalescePartitions > RemoteCheckpointWrite > Repartition > source`,
   with no sort.
3. **The recorded order is copied to the committed checkpoint unchanged**
   and declared by every later scan of it
   (`remote_checkpoint.rs:334-353`, `planner.rs:335-336`).

The existing test of this behaviour,
`test_checkpoint_preserves_partitioning_and_ordering`
(`python/pysail/tests/spark/dataframe/test_checkpoint.py:145-160`), compares
plan snapshots, not results, so it passes.

The same early recording has a second, harmless effect: a partitioning the
optimizer establishes later is not recorded. A checkpoint taken straight
after `groupBy(k)` is hash-partitioned by `k` on disk and declares nothing.

## What would fix it

Either of these, in rough order of preference:

1. **Make the writer require what the commit records.** Give
   `RemoteCheckpointWriteExec` the recorded ordering as its
   `required_input_ordering`, and have it report `maintains_input_order`.
   The sort then stays, the files are sorted, and the declaration is true.
   This also keeps the feature's benefit: a sort-merge join over two such
   checkpoints then needs no sort and no shuffle.
2. **Record the properties after optimization.** Take ordering and
   partitioning from the writer's optimized input when the write executes,
   not from the unoptimized plan. A dropped sort is then simply not
   recorded. This also records partitioning the optimizer adds.
3. **As a stopgap, record no ordering at all.** Correct at once, at the
   cost of the order-based plans.

A regression test should compare query results over the checkpoint with the
same queries over the source frame, for `sortWithinPartitions` and for
`orderBy`.

That the reader side is sound when the files are honest was checked: with a
sort the optimizer cannot remove, the files are sorted, the same plans have
no `SortExec`, and every result is correct (the `checkpoint-hash-sorted-pinned`
control in the wider study).

## Smaller observations from the same study

Each reproduces on the same upstream commit with the harness in
[`../sem-research-2026-10-02/delta-order-plans/`](../sem-research-2026-10-02/delta-order-plans/README.md),
which has the evidence for every line.

| # | Observation | Where |
|---|---|---|
| 1 | A `sortWithinPartitions` or `orderBy` before a Delta write is removed silently, for the same reason: `DeltaWriterExec` asks for an input order on partition columns only and does not report that it maintains input order. Sail cannot write a Delta table sorted by a key today. | `crates/sail-delta-lake/src/physical_plan/writer_exec.rs:566-594` |
| 2 | `DataFrameWriter.sortBy` fails name resolution for every format: `attribute ... is missing from the schema`. Both sinks accept a sort order; the request dies before reaching them. | `crates/sail-plan/src/resolver/command/write.rs:240` |
| 3 | Ordering from Parquet footers (`sorting_columns`) is unreachable for path reads: the listing source always passes a one-element `file_sort_order`, and the planner returns early when that list is not empty. | `crates/sail-data-source/src/listing/source.rs:268`, `listing/planner.rs:269` |
| 4 | `EXPLAIN` fails for sort-merge joins that execute correctly, under `prefer_hash_join=false`: the explain path plans with an empty physical optimizer list and then hits DataFusion's invariant that a sort-merge join's inputs are co-partitioned. | `crates/sail-plan/src/explain.rs:215-222` |
| 5 | In cluster mode a `GROUP BY` over a catalog table with a declared `SORTED BY` fails: `repartition is order-preserving and would result in incorrect results in distributed execution`. The same query runs in local mode. | `crates/sail-execution/src/job_graph/planner.rs:464-471` |
| 6 | `repartitionByRange` plans a hash repartition, with no warning. DataFusion 55.1.0 carries a range partitioning and Sail forwards one, but nothing creates it. | `crates/sail-plan/src/resolver/query/repartition.rs:52-58` |
| 7 | A catalog table's `SORTED BY (k)` is declared as `NULLS LAST`, so Spark's default `ORDER BY k` (nulls first) still sorts. | `crates/sail-common-datafusion/src/catalog/mod.rs:89` |

The earlier note on slow `partitionBy` writes is
[`../sail-partitionby-write-2026-10-02/README.md`](../sail-partitionby-write-2026-10-02/README.md).

## Limits of this note

- One machine, local mode for the reproducer. The wider study saw the same
  wrong results in `local-cluster` mode. No multi-process cluster was run.
- `localCheckpoint()` was not run. It goes through the same planner code.
- The fixes are from reading the code. None was built or tested.
- I did not search the upstream issue tracker for an existing report.
- The cause of observation 2 is inferred from the code; the failure itself
  is observed.
- DataFusion was read at 55.1.0, the version Sail pins.
