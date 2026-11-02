# Four Spark suites ported

Sail `0643d6477` (parent `19d7137eb`) adds client-level ports of ConnectInvalidPipelineSuite, ConnectValidPipelineSuite, TriggeredGraphExecutionSuite and the rest of MaterializeTablesSuite, and closes the divergences they found. The ports were written by a delegated agent and checked here by running them.

Native 140 + 125 + 430, fmt, strict Clippy. Frozen 300 + 67, with the harness now in `harness/`: `cycle-migration.json` binds the one changed test hash. Sail pipelines directory: 732 passed, 8 skipped, 4 strict expected failures. Spark 4.2.1: 86 of 87 passed, 8 skipped. On the prior binary, 16 of the new tests fail.

**The one Spark failure** is `test_execution.py::test_cycle_does_not_read_old_catalog_output[False]`: `LOCATION_ALREADY_EXISTS` from the test's own `saveAsTable`, because the `[True]` parameter left a warehouse directory behind. It is a test setup limit on Spark, and `[True]` confirms the changed message. That test was not written for Spark.

**Strict expected failures on Sail** (each passes on Spark):
- `test_multi_hop_schema_merging`: Sail parses `... OUTER JOIN d` as a full join, where Spark reads `OUTER` as an alias. This returns different rows, in plain `spark.sql` too.
- `test_joining_on_a_column_with_different_names`: `UNRESOLVED_COLUMN`, where Spark has `UNRESOLVED_USING_COLUMN_FOR_JOIN`.
- `test_specifying_a_partition_column_with_an_existing_partitioned_table`: partition columns keep declared order in Sail's catalog.
- `test_consecutive_failures_are_each_reported`: a bad partition column fails during materialization, once, not as three flow failures.

**What the ports do not prove.** `MemoryStream` is replaced by parquet tables, so file discovery is part of these tests. Eight cases are skipped because they need Scala internals or a stop request. Some unions and multi-query cases are dry runs only. Event levels are not client-visible. Clustering is recorded in a `clusteringColumns` property: no writer lays out files by it, and only Sail's parts of the catalog read it. The inventory counts are unchanged.
