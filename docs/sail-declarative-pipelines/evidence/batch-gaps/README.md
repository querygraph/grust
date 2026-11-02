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

## `5e905ecce` to `a4dfce84a`: audit, Iggy sources, final state

`5e905ecce` merges the audit of the non-AutoCDC suites: `batch-audit.json`, 435 entries, 349 ported, 72 partial, 14 internal, 0 missing. 32 of the partial entries are Hive profiles run on Sail's default catalog, and most others are AutoCDC cases of PythonPipelineSuite, or internals with a partial client-visible form. The `ported` calls of four clusters were reviewed for failures and notes, not each against its Scala body. It also adds SHOW CREATE TABLE. Three frozen sources changed, recorded as `audit_alignment` in the harness `preparation.json`: `sql.feature` now expects Spark's "Invalid partitioning transform" (SqlGraphRegistrationContext.scala:573, SqlPipelineSuite.scala:326), and two test files gained cleanup fixtures with no assertion changed.

`ad5c11711` reports a missing cluster column and a changed source set as Spark does.

`1d9fb676a` reads a BoundedSource from append flows, Iggy first. `test_iggy_append.py` 9 on a real broker, control 9 failed on `ad5c11711`, `append_bounded_tests.rs` 6 with a fake source. Spark has no Iggy source, so these state Sail's contract. Gates now set `SAIL_IGGY_SERVER_BINARY`, and all 15 Iggy tests ran.

`a4dfce84a`: a session released while its workers start could hang ReleaseSession for good. The pipelines suite found it in local-cluster mode, intermittently. A worker can stick in its own shutdown while its heartbeat task runs on, and the driver joined it forever. The driver now gives up after 30 seconds, which aborts what is left. Stop retries for an unreachable worker were added too. Repeating the racy tests 12 rounds in local-cluster mode: fixed binary 12 clean, with the bound firing once; prior binary 1 failed round. What holds the worker inside its shutdown was not found, so such a release takes 30 seconds.

Final gate at `a4dfce84a`: 15 crates, frozen 300 + 67, pipelines 1227 passed, 9 skipped, 5 strict expected failures, CLI 4 passed with `catalog.shared_memory`, Delta suite unchanged. Local-cluster pipelines plus ORC: 1227 passed. Whole tree against upstream `0ba425c03`: 47 failed or errored, all 47 also on upstream, 0 regressed, 0 new.

The 5 strict expected failures:

- Interrupting a run: Spark cancels the operation and the flows finish, Sail stops the flows. Deliberate: nothing could stop such a run, and session shutdown needs them stopped.
- Releasing a session during a run: the same.
- Spark refuses a union of streaming and batch views at query start, Sail runs it.
- Added columns: Spark's order comes from a Scala Map past four fields, Sail uses target order.
- `writeStream` to `memory` outside a pipeline.

Spark run file by file on the pre-merge audit tree: batch files failing there are mostly `LOCATION_ALREADY_EXISTS` from leftovers in the shared `default` schema (72 lines), since these fixtures rely on a fresh Sail catalog per session, and `NO_ACTIVE_SESSION` in the `direct` variants of `test_dataset_parse_errors.py`. The rest are Sail differences: Sail accepts dotted and hyphenated table names where Spark's catalog refuses them, and `test_direct_execution_policy.py` is a stated Sail policy. AutoCDC files fail on plain Spark, because it needs the row-level test catalog in `evidence/autocdc-spark-oracle`. The whole directory was not rerun on Spark after the final merges.

## `67a6931ba`: the whole-tree comparison, corrected

The peer reported 52 failures that the earlier comparisons did not show. They were right. `test_tpch.py`, `test_tpcds.py` and two utility tests never collected here, because duckdb and jedi were missing, and other tests failed for harness reasons: the server could not import pysail, and it did not share the tests' working directory. So "0 regressed" in the sections above covers only what ran.

`run-full.py` is the corrected harness, with the optional test dependencies pinned as in `pyproject.toml`, installed outside the shared venv. Under it, upstream `0ba425c03` has 0 failures and 12 JVM fixture errors, so most earlier "fails upstream too" were harness failures on both sides.

On `9d6646c92` 38 snapshots differed, 35 in TPC-DS and 3 in TPC-H, all plan text. Join, aggregate, filter, scan and repartition operators kept their counts, with 8 fewer projections that held a shared guard. Division guards became `spark_divisor_ansi_divide`, and a CASE ends in `ELSE NULL`. `67a6931ba` refreshes them.

## `609a6c251` and the second catalog

`609a6c251` refuses a union of streaming and batch inputs, as Spark does, so 4 strict expected failures remain. The merge after it adds `test_second_catalog.py`, which needs a server with two memory catalogs: `scripts/spark-pipelines-tests/run-second-catalog.sh`. Both SqlPipelineSuite catalog-crossing cases are now ported, on Sail only.

The 32 Hive profile cases stay partial. Spark's Hive suites add no test bodies, so rerunning the same modules against a metastore would settle them. Docker Desktop is down, with its engine failing since 2026-10-27 on a full disk. A standalone Hive 4.0.1 metastore was downloaded and checksummed, but running downloaded jars was denied by the permission system, so no test has run against a metastore. `scripts/spark-pipelines-tests/run-hive-metastore.sh` has never been run.
