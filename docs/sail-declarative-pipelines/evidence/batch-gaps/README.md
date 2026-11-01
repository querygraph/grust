# Batch gaps

## `ee193842f`

Closes 12 of the 13 strict expected failures, measured on Spark 4.2.1 first. The 13th, the closed session, is the session shutdown unit.

- Column constraints: Spark's `_LEGACY_ERROR_TEMP_0035`, checked before the other dataset restrictions, as Spark does.
- Bare `t OUTER JOIN d`: OUTER is an alias of `t`, an inner join. Only for the first join of a table without an alias.
- Partition columns move last in a file table. A generic change, measured by the whole tree below. One Delta-suite test inserted positionally under the old order and was corrected.
- Read options on a batch read of a graph table go to the table.
- A missing partition column: the table is created, each flow attempt fails with COLUMN_NOT_DEFINED_IN_TABLE, independent flows run.
- Repeated columns pass analysis and a dry run, and the flow fails with AMBIGUOUS_REFERENCE. A view that repeats a column is still refused during analysis, where Spark accepts `SELECT *` over it and refuses a reference to the column. That is a difference.
- `catalog.shared_memory`, default false. Sharing by default broke 104 tests, because Sail's fixtures rely on a fresh catalog per session, so this is opt-in. The three CLI tests skip without it and run in the gate with it: 4 passed.
- REFRESH TABLE and `spark.catalog.refreshTable` clear the file listing and statistics caches, all entries, since they do not key by table.
- `spark.sql()` of a write has no rows. It recognizes the write by its single UInt64 `count` column.
- Cluster: a refused retry reports the failure that caused it.

`test_batch_parity.py`: 9 passed on Sail, 9 on Spark.

Gate at `ee193842f`: 15 crates, frozen 300 + 67, pipelines 924 passed, 20 skipped, 1 strict expected failure, CLI 4 passed with sharing on, Delta suite 875 outcomes unchanged, local-cluster pipelines 924 passed. Whole tree against `d4c7a45eb`: 12,388 outcomes, 73 changed, all to passing, none worse.

## `43e4626aa`

Merges `work/sdp-orc-types` (`f481b5a4d`). TIMESTAMP, TIMESTAMP_NTZ, DECIMAL, ARRAY, MAP and STRUCT are written, and native encoder memory is reserved per slice. `test_orc_write.py` 74 passed on Sail and on Spark, negative control 45 failed.

Deliberate differences from Spark: TIMESTAMP is stored as TIMESTAMP_INSTANT, because Spark's kind depends on the writer's JVM zone, which a Sail worker cannot know. Instants in ORC-763's window before the epoch fail the write, where Spark succeeds and reads back a value one second later.

Limits: Spark on a non-UTC JVM reads Sail's instants before 1883-11-19 with its local-mean-time drift. Sail's reader does not rebase Spark's hybrid calendar for values before the cutover. Memory reservation sizes are estimates and do not bound the heap. Not run on real object stores.

Gate at `43e4626aa`: 15 crates, frozen 300 + 67, pipelines 974 passed, 20 skipped, 1 strict expected failure, CLI 4 passed, Delta suite unchanged.
