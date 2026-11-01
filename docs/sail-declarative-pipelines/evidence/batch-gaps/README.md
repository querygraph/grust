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

## `ae41beee0`: regressions against the upstream base

Until this point the whole tree had only been compared with earlier roots of this branch, so "no new failures" meant no new failures since the last root. Run against the merge base with main, `0ba425c03`, 75 tests passed upstream and failed here. That had been reported as pre-existing, which was wrong.

Causes:

- `87a7c941d`, found by bisect: under ANSI a string cast lowers to `spark_ansi_string_cast`. A correlated scalar subquery over such a key failed to decorrelate (56 tests), and VALUES lost its NaN detection, so a double and a decimal in one column fell to decimal.
- A CASE coerced during resolution used the non-ANSI policy for an integer and a float.
- Unresolved column reporting failed on internal columns, with an internal error (8 tests).
- The partition column check refused nested sources and did not fold case as Spark does.
- CTAS has no rows, deliberately, and Spark with Delta agrees, so that scenario was outdated. Merge error text and four plan snapshots moved on purpose.

Eight tests marked as known bugs now pass and lost their markers.

## `ea8f37edd`: final state of this run

Merges `work/sdp-session-shutdown`. Gate: 15 crates, frozen 300 + 67, pipelines 978 passed, 20 skipped, 0 expected failures, CLI 4 passed with `catalog.shared_memory`, Delta suite unchanged from `ae41beee0`. Local-cluster pipelines: 978 passed.

Whole tree against upstream `0ba425c03`: 47 failures and errors, all 47 also failing upstream, 0 regressed, 0 new. By signature: 13 `ModuleNotFoundError` in a Python data source on an external server, 12 JVM gateway setup, 8 Delta maintenance commit lookups, 7 missing connectorx, 5 collection failures from missing modules, 2 others. Not fixed and not all diagnosed, since they fail the same way upstream under this harness.

Session limits, from the branch: fallible actor and gateway results are not done, since they need the common actor framework. Non-checkpoint table writers are not routed through the effect owner. Cluster worker effects are not qualified, and a cluster session that used checkpoints now fails release and leaves the server exiting 1.
