# Spark 4.2.1 AutoCDC test equivalence in Sail, second pass

Read-only audit. Nothing was built or run. Proposed tests below have not been executed on either engine.

- Spark: `spark-sdp-4.2.1` at `61761839`. This checkout has no `common/`, so error templates were read from the 4.2.1 `error-conditions.json` in `scratchpad/ec.json`, which is byte-size identical to the copy in the `spark-common-utils` 4.2.1 jar.
- Sail: `sail-sdp-fable-iggy`, branch `work/sdp-initialization-intents`, commit `9da5a6ecb`. First audit was `f0bd5320a`.
- Oracle evidence used: `scratchpad/jvm-sem-4` (18 passed) and `scratchpad/jvm-suites-2` (35 test functions, 38 items, 3 skipped). Their `server.log` files give the real Spark error text quoted below. The three `sail_only` cases were not run on Spark. The logs do not record which commit of the test files ran.

## Counts

| Scope                                                       |    Rows | COVERED | PARTIAL, metadata only | PARTIAL, other | MISSING | NOT_APPLICABLE |
| ----------------------------------------------------------- | ------: | ------: | ---------------------: | -------------: | ------: | -------------: |
| Rows reclassified (first audit PARTIAL or MISSING)          |      32 |       2 |                      6 |             23 |       1 |              0 |
| New suites                                                  |      21 |       3 |                      3 |             15 |       0 |              0 |
| Rows not re-audited (first audit COVERED or NOT_APPLICABLE) |     137 |     130 |                      0 |              0 |       0 |              7 |
| **All rows**                                                | **190** | **135** |                  **9** |         **38** |   **1** |          **7** |

| Suite                                    |   Cases | COVERED | PARTIAL | MISSING | NOT_APPLICABLE |
| ---------------------------------------- | ------: | ------: | ------: | ------: | -------------: |
| AutoCdcAuxiliaryTableSuite               |       5 |       5 |       0 |       0 |              0 |
| AutoCdcScd1AuxiliaryTableDurabilitySuite |       6 |       3 |       3 |       0 |              0 |
| AutoCdcScd1FullRefreshSuite              |       3 |       2 |       1 |       0 |              0 |
| AutoCdcScd1KeyDriftSuite                 |      13 |      12 |       1 |       0 |              0 |
| AutoCdcScd1SinglePipelineSuite           |       4 |       3 |       1 |       0 |              0 |
| AutoCdcFlowSuite                         |      22 |      12 |       3 |       0 |              7 |
| ChangeArgsSuite                          |      22 |      21 |       1 |       0 |              0 |
| Scd1BatchProcessorMergeSuite             |      20 |      19 |       0 |       1 |              0 |
| Scd1BatchProcessorSuite                  |      36 |      34 |       2 |       0 |              0 |
| Scd1ForeachBatchHandlerSuite             |      18 |       6 |      12 |       0 |              0 |
| ConnectValidPipelineSuite                |       1 |       1 |       0 |       0 |              0 |
| ConnectInvalidPipelineSuite              |       4 |       2 |       2 |       0 |              0 |
| PythonPipelineSuite                      |      15 |      12 |       3 |       0 |              0 |
| AutoCdcScd1MultiPipelineSuite            |       5 |       0 |       5 |       0 |              0 |
| AutoCdcScd1SchemaEvolutionSuite          |      13 |       3 |      10 |       0 |              0 |
| AutoCdcScd1TargetTableDurabilitySuite    |       3 |       0 |       3 |       0 |              0 |
| **Total**                                | **190** | **135** |  **47** |   **1** |          **7** |

Upgrades from the first audit: KeyDrift:188 and :315 to COVERED. Handler:327 and Python:1186 from MISSING to PARTIAL.

## Rule applied

- COVERED means every Spark assertion in the case has a named test that asserts it. Sanity preconditions (table absent before a drop) are not counted.
- A family match does not pin a condition. `match="AUTOCDC_"` and a bare `pytest.raises(FAILURE)` are not the condition.
- An order-free check does not pin a parameter. Two `in` checks for `left` and `right` pass with the operands swapped.
- A Rust validator test is accepted for parameters only with the same values Spark expects on that input.
- "Metadata only" means the sole loss is `__spark_autocdc_metadata` contents (or one of its two fields). Those nine rows become COVERED if the owner waives metadata contents. `durable.rs::assert_exact` already pins both fields on the production path for an upsert and a delete, so the waiver risk is low, but no named test pins them for these cases.
- This rule is stricter than the first audit's. KeyDrift:45, :83, :119 and :158 remain COVERED from that audit at validator level, and the same strictness would make them PARTIAL. They were out of scope.

## What changed since the first audit

- `tests/durable.rs` changed by one assertion only: a reset now changes the auxiliary identity (`assert_ne!(guard.auxiliary, before.auxiliary)`). It upgrades no row here.
- The `broker` fixture in `test_autocdc_spark_suites.py` is now a local directory `Landing`, so that file no longer needs `SAIL_IGGY_SERVER_BINARY`. The first audit's skip caveat now applies only to `test_autocdc_iggy.py`.
- First audit's gaps, as now tested:
  - Gap 1: `test_a_full_refresh_changes_the_keys_and_the_types`. Full refresh as the remedy for the three corrupt-metadata conditions still has no test.
  - Gap 2: `test_a_dropped_auxiliary_table_is_recreated` (mutant `no_rebind` killed).
  - Gap 3: `test_a_full_refresh_creates_a_target_that_does_not_exist`.
  - Gap 4: `test_a_dry_run_reports_what_a_run_would`, family match only, and no reserved-prefix case.
  - Gap 5: `test_a_view_downstream_of_a_target_sees_what_the_flow_writes`, metadata half only. Selecting an excluded column is not tested.
- Stale comments still in the tree:
  - The comment on `target_key_comparison_respects_case_sensitivity` claims both grid arms.
  - `tests/graph.rs` says the persisted-view arm "reports the condition only", while `graph.rs:503` passes both identifiers to `flow_query_type_error`.
  - `test_auto_cdc_flow_targeting_a_persisted_view` is a skip stub.

## A constraint on any cross-engine failure assertion

`getCondition()` and `getMessageParameters()` are not a safe cross-engine assertion for a run failure.

- Spark's `server.log` shows the top-level exception is `StreamingQueryException` for microbatch failures and `DatasetManager$TableMaterializationException` for merge-type failures. Sail returns the structured error directly.
- The value `getCondition()` returns on Spark for those wrappers was not observed. `checkErrorInPipelineFailure` walks the cause chain, which a Connect client cannot do.
- `str(failure.value)` carries the inner text on both engines, because the existing `match=` tests pass on both.

So the tests below match rendered text. Each regex comes from the Spark log or from `error-conditions.json`. Every regex here should be treated as unconfirmed until its first oracle run. Use `(?s)` where text may wrap.

## test_autocdc_spark_suites.py: what it drops

Across the whole file:

| Dropped                                 | Effect                                                                                                                                                                    |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `cdcMeta(...)` on every row             | Metadata asserted only by name in `test_a_target_without_the_metadata_column_gains_it` and by one field in `test_a_view_downstream_of_a_target_sees_what_the_flow_writes` |
| Full-row `checkAnswer` on `spark.table` | `rows(...)` selects by name, so column position is never pinned, including Spark's rule that an evolved column lands after the metadata column                            |
| Intermediate `checkAnswer` after run 1  | Absent from every multi-run port                                                                                                                                          |
| `sqlState`                              | Not asserted anywhere in the file                                                                                                                                         |
| `CREATE TABLE` up front                 | Multi-1, Multi-2 and Evolution 1, 4, 5, 6, 7 and the nested cases let the first run create the target                                                                     |
| `NOT NULL` on the metadata column       | `METADATA` omits it, while `cdcMetadataDdl` has it                                                                                                                        |
| Separate streams per pipeline           | One `Landing` is shared, so a later flow with a new checkpoint replays earlier files. This changes what Multi-1, -3 and -4 test                                           |
| `PIPELINES_MAX_FLOW_RETRY_ATTEMPTS=0`   | Failure cases run with default retries. No assertion depends on it                                                                                                        |

Per test:

| Python test                                                                  | Spark assertions dropped                                                                                                                                                                                     |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `test_a_preloaded_row_outranks_a_lower_sequence`                             | Metadata `(None,5)` and `(None,10)`                                                                                                                                                                          |
| `test_preloaded_rows_merge_and_the_auxiliary_table_appears_on_the_first_run` | Metadata `(None,2)`                                                                                                                                                                                          |
| `test_a_target_without_the_metadata_column_gains_it`                         | Metadata `(None,1)`                                                                                                                                                                                          |
| `test_two_targets_keep_independent_state`                                    | Metadata. `t_b` sees `t_a`'s row through the shared landing, where Spark asserts exactly one row                                                                                                             |
| `test_a_later_pipeline_reads_a_target_without_its_metadata_column`           | Selects three columns out of `downstream`, so an extra metadata column there would pass. Spark's `checkAnswer` is on the whole table                                                                         |
| `test_two_pipelines_merge_into_a_shared_target`                              | Check after pipeline 1, metadata, auxiliary existence. "id=1 untouched" is lost: flow_two replays `(1, alice, 1)` from the shared landing, so id=1 is re-upserted on a tie                                   |
| `test_two_pipelines_with_other_columns_evolve_a_shared_target`               | The whole third stage (pipeline 1 re-runs on the old schema, `age` persists), check after pipeline 1, metadata, column position                                                                              |
| `test_a_second_pipeline_with_other_keys_is_refused`                          | `sqlState`, all four parameters. Note the oracle's values are `name STRING` and `id INT`; Spark's `id INT NOT NULL` comes from a Scala primitive                                                             |
| `test_a_nullable_column_merges_mixed_values`                                 | Run 1 row, metadata                                                                                                                                                                                          |
| `test_a_type_change_between_runs_is_refused` (3 cases)                       | `sqlState`, and the order of `left` and `right`                                                                                                                                                              |
| `test_a_new_source_column_is_added_to_the_target`                            | Run 1 row, `name`, `seq`, metadata, position of `email` after metadata                                                                                                                                       |
| `test_broadening_the_selection_adds_the_column`                              | Same as above                                                                                                                                                                                                |
| `test_narrowing_the_selection_keeps_the_column`                              | Run 1 row, `name`, `seq`, metadata                                                                                                                                                                           |
| `test_a_dropped_source_column_keeps_its_rows_and_is_null_on_new_ones`        | Run 1 row, `name`, `seq`, metadata, position                                                                                                                                                                 |
| `test_dropping_a_nested_struct_field_is_refused`                             | `colName` `` `value`.`b`.`c` ``, `tableName`                                                                                                                                                                 |
| `test_dropping_a_field_in_an_array_of_structs_is_refused`                    | `colName` `` `vals`.`element`.`b`.`d` ``, `tableName`                                                                                                                                                        |
| `test_a_column_differing_from_the_target_by_case_is_ambiguous`               | `queryContext` fragment. Spark's parameters are `.*`, so nothing else. Unasserted divergence: Spark reports ``[`...`.`Value`, `...`.`Value`]``, while `execute.rs` builds ``[`...`.`value`, `...`.`Value`]`` |
| `test_a_new_field_in_an_array_of_structs_is_added`                           | Nothing                                                                                                                                                                                                      |
| `test_extra_target_columns_survive_the_merge`                                | Nothing                                                                                                                                                                                                      |

The rest of the file (views, unions, Delta sources, full refresh, dry run) has no Spark suite counterpart and maps to no row here.

## Reclassified rows

"Closure" names a block in the next section.

| Suite          | Line | Spark test                           | Was     | Now               | Evidence and gap                                                                                                                                                                                                       | Closure |
| -------------- | ---: | ------------------------------------ | ------- | ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| AuxDurability  |  151 | aux preserves declared key order     | PARTIAL | PARTIAL           | `test_the_auxiliary_table_records_keys_in_declared_order` asserts the first two column names. Drops the third name and the `keyColumnNames` property                                                                   | C1      |
| AuxDurability  |  184 | dropped aux recreated                | PARTIAL | PARTIAL, metadata | `test_a_dropped_auxiliary_table_is_recreated` runs the production path and asserts recreation. Drops `seq` and metadata                                                                                                | M1      |
| AuxDurability  |  223 | key names survive special characters | PARTIAL | PARTIAL           | `test_special_characters_in_key_names_survive_two_runs` uses two of Spark's four names (no `a"b`, no `c\d`) and never reads the property                                                                               | C2      |
| FullRefresh    |  159 | selective refresh                    | PARTIAL | PARTIAL, metadata | `test_two_flows_in_one_pipeline_and_a_selective_full_refresh`, production path, same ids and sequences. Drops metadata                                                                                                 | M2      |
| KeyDrift       |  188 | composite reorder no drift           | PARTIAL | COVERED           | `test_reordering_composite_keys_is_not_drift`. Spark asserts only that the run completes; this asserts the row too                                                                                                     |         |
| KeyDrift       |  208 | nullability or metadata no drift     | PARTIAL | PARTIAL           | `reorder_nullability_and_backticks_are_not_drift` is validator only. No completing second run, no column metadata                                                                                                      | C3      |
| KeyDrift       |  315 | case-insensitive no drift            | PARTIAL | COVERED           | `test_keys_may_be_given_in_another_case`. Spark asserts only completion                                                                                                                                                |         |
| SinglePipeline |  118 | two flows, one pipeline              | PARTIAL | PARTIAL           | First half of `test_two_flows_in_one_pipeline_and_a_selective_full_refresh`. Drops auxiliary existence, metadata, and Spark's second row                                                                               | C4      |
| Flow           |  211 | schema, Include                      | PARTIAL | PARTIAL           | Names only in Rust; no type or metadata struct check                                                                                                                                                                   | C5      |
| Flow           |  234 | schema, Exclude                      | PARTIAL | PARTIAL           | Names only. `"seq" not in columns` is one fact                                                                                                                                                                         | C5      |
| Flow           |  255 | metadata uses resolved type          | PARTIAL | PARTIAL           | `test_a_sequence_expression_types_the_metadata` covers the cast over BIGINT but only `upsertSequence`. Spark compares the whole struct                                                                                 | C6      |
| ChangeArgs     |  254 | `quoted` safe for `col`              | PARTIAL | PARTIAL           | Rust test asserts a different condition (`AUTOCDC_MULTIPART_COLUMN_IDENTIFIER`). No DataFrame half                                                                                                                     | C7      |
| MergeSuite     |  476 | grid, caseSensitive=true             | MISSING | MISSING           | `test_a_mis_cased_key_fails_when_names_are_case_sensitive` fails at the flow check, before any merge (oracle: `AUTOCDC_KEY_NOT_IN_SELECTED_SCHEMA`), and has no condition. No merge runs under case sensitivity        | R1      |
| BatchProcessor |  390 | key collides with reserved name      | PARTIAL | PARTIAL           | Failure only, no `AMBIGUOUS_REFERENCE`. Unreachable from a client                                                                                                                                                      | R2      |
| BatchProcessor |  640 | incompatible sequencing type         | PARTIAL | PARTIAL           | Failure only, no `DATATYPE_MISMATCH.CAST_WITHOUT_SUGGESTION`. Unreachable from a client                                                                                                                                | R3      |
| Handler        |   84 | null sequencing before merge         | PARTIAL | PARTIAL           | `test_a_null_sequence_fails_before_any_merge` asserts no effect, but `match="AUTOCDC_"` and no metadata. Rust pins condition on the validator alone                                                                    | C8      |
| Handler        |  113 | null key before merge                | PARTIAL | PARTIAL           | `test_a_null_key_fails_before_any_merge`: one null row where Spark has two and a good row, family match, no aux assertion                                                                                              | C9      |
| Handler        |  145 | composite null key                   | PARTIAL | PARTIAL           | Rust validator only. No test with tables                                                                                                                                                                               | C10     |
| Handler        |  233 | sequencing must be orderable         | PARTIAL | PARTIAL           | Rust validator only. No test with tables                                                                                                                                                                               | C11     |
| Handler        |  270 | stale dropped, fresh written         | PARTIAL | PARTIAL, metadata | `test_a_tombstone_drops_a_stale_row_and_a_fresh_upsert_is_written`. Drops target metadata and aux `upsertSequence`                                                                                                     | M3      |
| Handler        |  308 | dedup before merge                   | PARTIAL | PARTIAL, metadata | `test_duplicate_keys_in_a_batch_merge_once_over_an_existing_row`. Drops only `deleteSequence`                                                                                                                          | M4      |
| Handler        |  327 | six out-of-order batches             | MISSING | PARTIAL           | `test_out_of_order_batches_converge_with_the_sequence_excluded` excludes `seq`, but a different sequence. Never sends an older delete below a live row, drops the check after batch 4, the final aux row, and metadata | C12     |
| Handler        |  438 | late delete, tombstone kept          | PARTIAL | PARTIAL, metadata | `test_a_late_delete_leaves_the_row_and_still_records_a_tombstone`                                                                                                                                                      | M5      |
| Handler        |  456 | within-batch delete then upsert      | PARTIAL | PARTIAL, metadata | `test_a_delete_losing_within_a_batch_leaves_no_tombstone`. One send is one batch (`MAX_FILES_PER_BATCH` is 100), so dedup is reached                                                                                   | M6      |
| Handler        |  480 | composite key isolates rows          | PARTIAL | PARTIAL           | `test_a_composite_key_merges_on_every_key` runs a real composite merge. Drops aux empty, metadata and the Exclude selection                                                                                            | C13     |
| Handler        |  599 | case-insensitive at every stage      | PARTIAL | PARTIAL           | `test_an_upper_case_flow_runs_when_names_are_case_insensitive` uses `except_column_list`, not Spark's uppercase Include, and asserts a delete, not an upsert over a row with aux empty                                 | C14     |
| Handler        |  621 | case-sensitive analysis              | PARTIAL | PARTIAL           | `test_a_mis_cased_key_fails_when_names_are_case_sensitive` has no exception type or condition, so an internal error passes. Only the key is uppercase                                                                  | C15     |
| ConnectInvalid |  608 | persisted view                       | PARTIAL | PARTIAL           | Debug-string match, no parameters. Python is a skip stub                                                                                                                                                               | R4      |
| ConnectInvalid |  658 | temporary view                       | PARTIAL | PARTIAL           | `test_auto_cdc_flow_targeting_a_temporary_view` asserts the condition with `` `target_view` ``. Spark's test expects a qualified name it builds by hand. No oracle run of this file was found                          | C16     |
| Python         | 1166 | source is the flow's input           | PARTIAL | PARTIAL           | `test_auto_cdc_flow_resolves` asserts resolution only                                                                                                                                                                  | C17     |
| Python         | 1186 | single-part source inherits defaults | MISSING | PARTIAL           | `test_auto_cdc_flow_resolves` runs with a non-session default database, so a mis-qualified `events` would fail. Default catalog never differs and inputs are not asserted                                              | C18     |
| Python         | 1218 | multi-part source resolves           | PARTIAL | PARTIAL           | `multi_part_source_is_kept_for_resolution_against_the_graph` asserts the parse. No test names a qualified `source`                                                                                                     | C17     |

## New suites

| Suite            |   # | Spark test                          | Class             | Evidence and gap                                                                                                                                            | Closure |
| ---------------- | --: | ----------------------------------- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| MultiPipeline    |   1 | separate tables, independent state  | PARTIAL           | `test_two_targets_keep_independent_state`, see drops                                                                                                        | C19     |
| MultiPipeline    |   2 | downstream pipeline reads target    | PARTIAL           | `test_a_later_pipeline_reads_a_target_without_its_metadata_column`                                                                                          | C20     |
| MultiPipeline    |   3 | same table, identical schemas       | PARTIAL           | `test_two_pipelines_merge_into_a_shared_target`                                                                                                             | C21     |
| MultiPipeline    |   4 | same key, different columns         | PARTIAL           | `test_two_pipelines_with_other_columns_evolve_a_shared_target` stops one stage early                                                                        | C22     |
| MultiPipeline    |   5 | different keys, KEY_SCHEMA_DRIFT    | PARTIAL           | `test_a_second_pipeline_with_other_keys_is_refused` pins the condition end to end. Rust pins parameters on other values                                     | C23     |
| Evolution        |   1 | nullable column, mixed values       | PARTIAL           | `test_a_nullable_column_merges_mixed_values`                                                                                                                | C24     |
| Evolution        |   2 | widening refused                    | PARTIAL           | `test_a_type_change_between_runs_is_refused[INT-BIGINT...]`                                                                                                 | C25     |
| Evolution        |   3 | narrowing refused                   | PARTIAL           | Same test, `BIGINT-INT`                                                                                                                                     | C25     |
| Evolution        |   4 | new source column added             | PARTIAL           | `test_a_new_source_column_is_added_to_the_target`                                                                                                           | C26     |
| Evolution        |   5 | broadening selection                | PARTIAL           | `test_broadening_the_selection_adds_the_column`                                                                                                             | C26     |
| Evolution        |   6 | narrowing selection                 | PARTIAL           | `test_narrowing_the_selection_keeps_the_column`                                                                                                             | C26     |
| Evolution        |   7 | dropped source column               | PARTIAL           | `test_a_dropped_source_column_keeps_its_rows_and_is_null_on_new_ones`                                                                                       | C26     |
| Evolution        |   8 | nested struct field dropped         | PARTIAL           | `test_dropping_a_nested_struct_field_is_refused`                                                                                                            | C27     |
| Evolution        |   9 | new field in array of structs       | COVERED           | `test_a_new_field_in_an_array_of_structs_is_added`, same data and same final assertion                                                                      |         |
| Evolution        |  10 | field dropped from array of structs | PARTIAL           | `test_dropping_a_field_in_an_array_of_structs_is_refused`                                                                                                   | C27     |
| Evolution        |  11 | case-only name, AMBIGUOUS_REFERENCE | COVERED           | `test_a_column_differing_from_the_target_by_case_is_ambiguous`. Condition matched, parameters are wildcards in Spark. Query context dropped as a diagnostic |         |
| Evolution        |  12 | extra target columns preserved      | COVERED           | `test_extra_target_columns_survive_the_merge`, identical select and rows                                                                                    |         |
| Evolution        |  13 | TIMESTAMP to STRING refused         | PARTIAL           | `test_a_type_change_between_runs_is_refused[TIMESTAMP-...]`                                                                                                 | C25     |
| TargetDurability |   1 | preloaded rows, lower and higher    | PARTIAL, metadata | `test_a_preloaded_row_outranks_a_lower_sequence`                                                                                                            | M7      |
| TargetDurability |   2 | preloaded rows, aux lazy            | PARTIAL, metadata | `test_preloaded_rows_merge_and_the_auxiliary_table_appears_on_the_first_run`                                                                                | M8      |
| TargetDurability |   3 | metadata column auto-added          | PARTIAL, metadata | `test_a_target_without_the_metadata_column_gains_it`                                                                                                        | M9      |

## Closures

All Python closures run on both engines through `Cdc`, `rows`, `Landing`, `cdc_view_graph` and `pipeline_factory`, unless marked Rust.

### Shared helpers

```python
# both files
META = ("__spark_autocdc_metadata.deleteSequence", "__spark_autocdc_metadata.upsertSequence")

def recorded_keys(spark):
    properties = {row[0]: row[1] for row in spark.sql(f"SHOW TBLPROPERTIES {AUXILIARY}").collect()}
    return json.loads(properties["pipelines.autocdc.keyColumnNames"])

# test_autocdc_semantics.py, on Cdc
def auxiliary(self, *keys):
    return sorted(tuple(row) for row in self.spark.table(AUXILIARY).select(*keys, *META).collect())

# conftest.py, pipeline_factory
def create(catalog=None, database=None):
    graph_id = client.create_dataflow_graph(pipeline_spark, catalog, database, None)
```

`rows(space, "*")` compares whole rows, because a `Row` is a tuple and a nested struct compares to `(None, 5)`. Where the target is pre-created as Spark's is, it pins column position and metadata in one stroke.

### Metadata only: one edit per test

| Id  | Test                                                 | Replacement assertions                                                                                  |
| --- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| M1  | `test_a_dropped_auxiliary_table_is_recreated`        | `rows(space, "id", "name", "seq", *META) == [(1, "alicia", 2, None, 2)]`                                |
| M2  | `test_two_flows_...` second half                     | Select `"id", "seq", *META`: `t_a == [(1, 5, None, 5)]`, `t_b == [(1, 10, None, 10)]`                   |
| M3  | `test_a_tombstone_drops_...`                         | `cdc.target("id", "name", *META) == [(2, "fresh", None, 20)]`, `cdc.auxiliary("id") == [(1, 10, None)]` |
| M4  | `test_duplicate_keys_...`                            | `cdc.target("id", "name", *META) == [(1, "newer", None, 20)]`                                           |
| M5  | `test_a_late_delete_...`                             | `cdc.target("id", "name", *META) == [(1, "alice", None, 5)]`, `cdc.auxiliary("id") == [(1, 2, None)]`   |
| M6  | `test_a_delete_losing_...`                           | `cdc.target("id", "name", *META) == [(1, "bob", None, 3)]`                                              |
| M7  | `test_a_preloaded_row_outranks_...`                  | `rows(space, "id", "name", "seq", *META) == [(1, "alice", 5, None, 5), (2, "bob2", 10, None, 10)]`      |
| M8  | `test_preloaded_rows_merge_...`                      | `rows(space, "id", "name", "seq", *META) == [(1, "bob", 2, None, 2)]`                                   |
| M9  | `test_a_target_without_the_metadata_column_gains_it` | `rows(space, "id", "name", "seq", *META) == [(1, "alice", 1, None, 1)]`                                 |

### Everything else

**C1, AuxDurability:151.** Add to `test_the_auxiliary_table_records_keys_in_declared_order`:

```python
assert pipeline_spark.table(AUXILIARY).columns == ["region", "id", "__spark_autocdc_metadata"]
assert recorded_keys(pipeline_spark) == ["region", "id"]
```

**C2, AuxDurability:223.** Replace the fixture and assert the property after each run. Sail creating a Delta table with `"` or `\` in a column name is unverified, so this may find a real gap.

```python
names = ["it's", "name with spaces", 'a"b', "c\\d"]
schema = ", ".join(f"`{name}` STRING" for name in names) + ", seq BIGINT"
cdc = Cdc(pipeline_spark, pipeline_factory, tmp_path, schema)
cdc.arguments = {}
cdc.keys = [f"`{name}`" for name in names]
cdc.send(("v1", "v2", "v3", "v4", 1))
cdc.run()
assert recorded_keys(pipeline_spark) == names
cdc.send(("v1", "v2", "v3", "v4", 2))
cdc.run()
assert recorded_keys(pipeline_spark) == names
```

**C3, KeyDrift:208.** Spark's target has a nullable `id`, so pre-create it. Add to the suites file:

```python
def test_key_nullability_and_metadata_changes_are_not_drift(space, pipeline_factory, broker):
    space.sql(f"CREATE TABLE {TARGET} (id INT, name STRING, seq BIGINT NOT NULL, {METADATA}) {USING}")
    broker.send({"id": 1, "name": "a", "seq": 1, "noise": "x"})
    cdc_view_graph(space, pipeline_factory, broker.url,
                   lambda f: f.select(sf.coalesce("id", sf.lit(0)).alias("id"), "name", "seq"))
    broker.send({"id": 2, "name": "b", "seq": 2, "noise": "x"})
    cdc_view_graph(space, pipeline_factory, broker.url,
                   lambda f: f.select(sf.col("id").alias("id", metadata={"description": "primary key"}), "name", "seq"))
    assert rows(space, "id", "name") == [(1, "a"), (2, "b")]
```

**C4, SinglePipeline:118.** In `test_two_flows_...` send `write(left, (1, 10), (2, 10))` and, after run 1, assert:

```python
assert read("t_a") == [(1, 10, None, 10), (2, 10, None, 10)]   # read selects "id", "seq", *META
assert read("t_b") == [(1, 10, None, 10)]
assert spark.catalog.tableExists(f"{PREFIX}__spark_autocdc_aux_state_t_a")
assert spark.catalog.tableExists(f"{PREFIX}__spark_autocdc_aux_state_t_b")
```

**C5, Flow:211, :234.** Types through the target. Column and metadata nullability stay with the Rust typed test, because a file source cannot declare a non-null column.

```python
@pytest.mark.parametrize(("selection", "kept"), [
    ({"column_list": ["id", "seq"]}, [("id", "int"), ("seq", "bigint")]),
    ({"except_column_list": ["name"]}, [("id", "int"), ("seq", "bigint")]),
])
def test_a_selection_fixes_the_target_schema(pipeline_spark, pipeline_factory, tmp_path, selection, kept):
    clean(pipeline_spark)
    cdc = Cdc(pipeline_spark, pipeline_factory, tmp_path, "id INT, name STRING, seq BIGINT")
    cdc.arguments = selection
    cdc.send((1, "a", 1))
    cdc.run()
    metadata = ("__spark_autocdc_metadata", "struct<deleteSequence:bigint,upsertSequence:bigint>")
    assert [(f.name, f.dataType.simpleString()) for f in pipeline_spark.table(TARGET).schema] == [*kept, metadata]
```

**C6, Flow:255.** One line in `test_a_sequence_expression_types_the_metadata`:

```python
assert metadata.simpleString() == "struct<deleteSequence:int,upsertSequence:int>"
```

**C7, ChangeArgs:254.** The Sail unit under test has no client surface, so this tests the observable half. Whether Sail's general resolver raises `UNRESOLVED_COLUMN.WITH_SUGGESTION` was not checked.

```python
def test_a_literal_dot_key_resolves_only_when_quoted(pipeline_spark, pipeline_factory, tmp_path):
    clean(pipeline_spark)
    cdc = Cdc(pipeline_spark, pipeline_factory, tmp_path, "`a.b` INT, c INT, seq BIGINT")
    cdc.arguments = {}
    cdc.keys = ["`a.b`"]
    cdc.send((1, 2, 1), (3, 4, 1))
    cdc.run()
    frame = pipeline_spark.table(TARGET)
    assert sorted(tuple(row) for row in frame.select("`a.b`").collect()) == [(1,), (3,)]
    with pytest.raises(FAILURE, match="UNRESOLVED_COLUMN.WITH_SUGGESTION"):
        frame.select("a.b").collect()
```

**C8, Handler:84.** Tighten the existing test. Oracle text: ``AutoCDC flow on table `cat`.`ns1`.`target` in batch 1 ... contains 1 row(s) with a null sequencing value``.

```python
with pytest.raises(FAILURE, match=r"(?s)NULL_SEQUENCE.*`target` in batch 1 .*contains 1 row\(s\) with a null sequencing value"):
    cdc.run()
assert cdc.target("id", "name", *META) == [(1, "alice", None, 1)]
assert cdc.auxiliary("id") == []
```

**C9, Handler:113.** Same shape with Spark's batch:

```python
cdc.send((None, "no-id-1", 5, False), (2, "ok", 6, False), (None, "no-id-2", 7, True))
with pytest.raises(FAILURE, match=r"(?s)NULL_KEY.*`id`=2"):
    cdc.run()
assert cdc.target("id", "name", *META) == [(1, "alice", None, 1)]
assert cdc.auxiliary("id") == []
```

**C10, Handler:145.** Seeding one good row keeps both tables present on either engine. Spark's target is empty here, which is the one deviation.

```python
def test_a_composite_null_key_reports_every_column(pipeline_spark, pipeline_factory, tmp_path):
    clean(pipeline_spark)
    cdc = Cdc(pipeline_spark, pipeline_factory, tmp_path, "country STRING, city STRING, seq BIGINT, is_delete BOOLEAN")
    cdc.keys = ["country", "city"]
    cdc.send(("US", "Boston", 1, False))
    cdc.run()
    cdc.send((None, "Boston", 1, False), ("US", None, 2, False), (None, None, 3, False))
    with pytest.raises(FAILURE, match=r"(?s)NULL_KEY.*`country`=2, `city`=2"):
        cdc.run()
    assert cdc.target("country", "city") == [("US", "Boston")]
    assert cdc.auxiliary("country", "city") == []
```

**C11, Handler:233.** Spark's test bypasses the flow by passing a batch with a map column to a processor typed LONG. A real run types the metadata as the map too, and whether Spark reaches the validator there is unverified. If the oracle reports something else, this row is Rust-only, and the existing Rust validator test plus a run-path call would be the limit.

```python
def test_a_map_sequence_fails_before_any_merge(cdc):
    cdc.sequence = sf.create_map(sf.lit("k"), sf.col("id"))
    cdc.send((1, "alice", 1, False))
    with pytest.raises(FAILURE, match=r"(?s)NON_ORDERABLE_SEQUENCE.*map<string,int>"):
        cdc.run()
    assert cdc.target("id") == []
    assert cdc.auxiliary("id") == []
```

**C12, Handler:327.** Replace the batches with Spark's:

```python
cdc.arguments["except_column_list"] = ["seq", "is_delete"]
for batch in [[(1, "alice", 1, False), (1, "bob", 3, False)], [(1, "carol", 2, False)],
              [(1, "dave", 4, False)], [(1, None, 2, True)]]:
    cdc.send(*batch)
    cdc.run()
assert cdc.target("id", "name", *META) == [(1, "dave", None, 4)]
for batch in [[(1, None, 5, True)], [(1, "ghost", 4, False)]]:
    cdc.send(*batch)
    cdc.run()
assert cdc.target("id") == []
assert cdc.auxiliary("id") == [(1, 5, None)]
assert "seq" not in cdc.spark.table(TARGET).columns
```

**C13, Handler:480.**

```python
schema = "country STRING, city STRING, population BIGINT, seq BIGINT, is_delete BOOLEAN"
cdc = Cdc(pipeline_spark, pipeline_factory, tmp_path, schema)
cdc.keys = ["country", "city"]
cdc.arguments["except_column_list"] = ["seq", "is_delete"]
cdc.send(("US", "New York", 8000000, 1, False), ("US", "Los Angeles", 4000000, 1, False), ("UK", "London", 9000000, 1, False))
cdc.run()
assert cdc.target("country", "city", "population", *META) == [
    ("UK", "London", 9000000, None, 1), ("US", "Los Angeles", 4000000, None, 1), ("US", "New York", 8000000, None, 1),
]
assert cdc.auxiliary("country", "city") == []
```

**C14, Handler:599.**

```python
cdc.keys, cdc.sequence = ["ID"], "SEQ"
cdc.arguments = {"apply_as_deletes": sf.expr("IS_DELETE"), "column_list": ["ID", "NAME"]}
cdc.send((1, "alice", 1, False))
cdc.run()
cdc.send((1, "bob", 2, False))
cdc.run()
assert cdc.target("id", "name", *META) == [(1, "bob", None, 2)]
assert cdc.auxiliary("id") == []
```

**C15, Handler:621.** Same arguments as C14 under case sensitivity. Oracle text: ``[AUTOCDC_KEY_NOT_IN_SELECTED_SCHEMA] Using case-sensitive column name comparison, the AutoCDC key column `ID` ...``.

```python
cdc.spark.conf.set("spark.sql.caseSensitive", "true")
cdc.send((1, "bob", 2, False))
with pytest.raises(AnalysisException, match=r"(?s)AUTOCDC_KEY_NOT_IN_SELECTED_SCHEMA.*case-sensitive.*`ID`"):
    cdc.run()
```

**C16, ConnectInvalid:658.** No new test. Run the existing node on the oracle: `scratchpad/jvm/on-jvm.py` with `test_connect_invalid.py::test_auto_cdc_flow_targeting_a_temporary_view`. If it passes, the row is COVERED, because Spark's qualified form is hand-built in Scala and a client registers a single-part temporary view (the handler reading is inference until that run).

**C17, Python:1166, :1218.** Declare the flow before `bronze`, so declaration order cannot stand in for the dependency edge. On Sail `PREFIX` is empty, so the qualified case uses the current database.

```python
def direct_source(spark, factory, target, source, bronze, **defaults):
    _, registry, start = factory(**defaults)
    with graph_element_registration_context(registry):
        dp.create_streaming_table(target, **FORMAT)
        dp.create_auto_cdc_flow(target=target, source=source, keys=["id"], sequence_by="seq")

        @dp.materialized_view(name=bronze)
        def bronze_rows():
            return spark.sql("SELECT * FROM VALUES (1, 'alice', 1L), (1, 'alicia', 2L) AS t(id, name, seq)")
    start()

@pytest.mark.parametrize("qualified", [False, True])
def test_a_source_named_directly_is_the_flows_input(space, pipeline_factory, qualified):
    prefix = f"{ORACLE or space.catalog.currentDatabase()}." if qualified else PREFIX
    direct_source(space, pipeline_factory, f"{prefix}target", f"{prefix}bronze", f"{prefix}bronze")
    assert rows(space, "id", "name") == [(1, "alicia")]
```

Spark's exact `inputs == Set(src)` has no client surface. To pin the set itself, Rust only: analyze a graph with `src` and `target`, then assert `analyzed.dependencies[&target] == BTreeSet::from([src])` in `tests/execute.rs`.

**C18, Python:1186.** Needs the `create(catalog, database)` helper above.

```python
def test_a_single_part_source_inherits_the_graph_defaults(space, pipeline_factory):
    catalog, database = ORACLE.split(".") if ORACLE else (space.catalog.currentCatalog(), "cdc_defaults")
    space.sql(f"CREATE NAMESPACE IF NOT EXISTS {catalog}.{database}")
    direct_source(space, pipeline_factory, "target", "bronze", "bronze", catalog=catalog, database=database)
    frame = space.table(f"{catalog}.{database}.target")
    assert sorted(tuple(row) for row in frame.select("id", "name").collect()) == [(1, "alicia")]
```

On Sail this proves the database half only, because the graph's catalog equals the session's. The catalog half is Rust only: `tests/graph.rs`'s `graph()` already defaults to `test_catalog.test_db`, so assert that `source_of` returns `["test_catalog", "test_db", "src"]`. `source_of` is private to `execute.rs` and would need `pub(super)`.

**C19, Multi 1.** Two directories. `Landing` calls `mkdir` without parents, so create the root first.

```python
(tmp_path / "second").mkdir()
second = Landing(tmp_path / "second")
broker.send({"id": 1, "name": "alice", "seq": 100})
run(space, pipeline_factory, broker.url, BASE, name="t_a", flow="flow_a")
second.send({"id": 9, "name": "bob", "seq": 1})
run(space, pipeline_factory, second.url, BASE, name="t_b", flow="flow_b")
assert rows(space, "id", "name", "seq", *META, table="t_a") == [(1, "alice", 100, None, 100)]
assert rows(space, "id", "name", "seq", *META, table="t_b") == [(9, "bob", 1, None, 1)]
```

**C20, Multi 2.** `rows(space, "*", table="downstream") == [(1, "alice", 1), (2, "bob", 1)]`.

**C21, Multi 3.** As C19, flow_two reading `second`. After run 1 assert `rows(space, "*") == [(1, "alice", 1, (None, 1)), (2, "bob", 1, (None, 1))]`. After run 2 assert `[(1, "alice", 1, (None, 1)), (2, "bob-v2", 2, (None, 2)), (3, "carol", 1, (None, 1))]` and `space.catalog.tableExists(AUXILIARY)`.

**C22, Multi 4.** Add the third stage, with flow_two reading `second`:

```python
broker.send({"id": 1, "name": "alice-v2", "seq": 2}, {"id": 4, "name": "dave", "seq": 1})
run(space, pipeline_factory, broker.url, BASE, flow="flow_one")
assert rows(space, "*") == [
    (1, "alice-v2", 2, (None, 2), None), (2, "bob-v2", 2, (None, 2), 25),
    (3, "carol", 1, (None, 1), 30), (4, "dave", 1, (None, 1), None),
]
```

**C23, Multi 5.** Oracle text: `AutoCDC flow spark_catalog.default.flow_two detected an invalid state: The AutoCDC flow's current key columns name STRING do not match the keys recorded in the auxiliary table cat.ns1.__spark_autocdc_aux_state_target (recorded keys id INT).`

```python
match=(r"(?s)AUTOCDC_INVALID_STATE\.KEY_SCHEMA_DRIFT.*AutoCDC flow \S*flow_two detected.*"
       r"current key columns name STRING do not match the keys recorded in the auxiliary table "
       r"\S*__spark_autocdc_aux_state_target \(recorded keys id INT\).*SQLSTATE: 42000")
```

**C24, Evolution 1.** Pre-create the target as Spark does and assert after each run: `rows(space, "*") == [(1, "alice", None, 1, (None, 1))]`, then `[(1, "alice2", "a@x.com", 2, (None, 2))]`.

**C25, Evolution 2, 3, 13.** Replaces the two `in` checks. Oracle text: `Failed to merge incompatible data types "BIGINT" and "INT".`

```python
with pytest.raises(FAILURE, match=rf'(?s)Failed to merge incompatible data types "{left}" and "{right}".*SQLSTATE: 42825'):
```

**C26, Evolution 4 to 7.** Pre-create the target with Spark's DDL and use whole rows.

| Row | DDL before `{METADATA}`                                           | After run 1                               | After run 2                                                               |
| --- | ----------------------------------------------------------------- | ----------------------------------------- | ------------------------------------------------------------------------- |
| 4   | `id INT NOT NULL, name STRING, seq BIGINT NOT NULL`               | `[(1, "alice", 1, (None, 1))]`            | `[(1, "alice", 1, (None, 1), None), (2, "bob", 2, (None, 2), "b@x.com")]` |
| 5   | same                                                              | same                                      | same                                                                      |
| 6   | `id INT NOT NULL, name STRING, email STRING, seq BIGINT NOT NULL` | `[(1, "alice", "a@x.com", 1, (None, 1))]` | `[(1, "alice", "a@x.com", 1, (None, 1)), (2, "bob", None, 2, (None, 2))]` |
| 7   | as row 4                                                          | `[(1, "alice", 1, (None, 1), "a@x.com")]` | `[(1, "alice", 1, (None, 1), "a@x.com"), (2, "bob", 2, (None, 2), None)]` |

**C27, Evolution 8, 10.** Oracle text: `Cannot write incompatible data for the table `: Cannot find data for the output column `value`.`b`.`c`.``

```python
match=r"(?s)CANNOT_FIND_DATA.*table ``: Cannot find data for the output column `value`\.`b`\.`c`"
match=r"(?s)CANNOT_FIND_DATA.*table ``: Cannot find data for the output column `vals`\.`element`\.`b`\.`d`"
```

### Rust only

**R1, MergeSuite:476 caseSensitive=true.** A client cannot reach this. The flow check rejects a mis-cased key first on both engines, and a source column `ID` would be added to the target instead (Spark's KeyDrift:315 comment describes this). Add a separate test in `tests/merge_execution.rs`, seeded as the existing one. `context()`'s config must also set `case_sensitive`, because `Case::Sensitive` only shapes the merge and name resolution reads the config.

```rust
let failure = merge_target(&ctx, config.clone(), &[key("ID")?], valued(&[(1, "new", (None, Some(20)))])?, Case::Sensitive).await;
assert_eq!(structured(failure).map(|e| e.condition), Some("UNRESOLVED_COLUMN.WITH_SUGGESTION".into()));
assert_eq!(rows(&ctx, config.clone(), &target_name()).await?, vec![row(&["1", "old", &meta("NULL", "10")])]);
```

Sail's condition on this path is unverified, so this may need error mapping in production.

**R2, BatchProcessor:390.** A client cannot reach this. `AUTOCDC_RESERVED_COLUMN_NAME_PREFIX_CONFLICT` rejects such a source column first on both engines. Rust: assert `AMBIGUOUS_REFERENCE`, `42704`, with `name` and `referenceNames`, in `a_key_column_named_like_the_winning_row_column_fails`. This needs `deduplicate` to raise that condition, so it is a production change for an unreachable path. Reclassifying to NOT_APPLICABLE is the alternative, and that is the owner's call.

**R3, BatchProcessor:640.** A client cannot reach this. Production passes the batch's own type, so the mismatch cannot arise. Rust: assert `DATATYPE_MISMATCH.CAST_WITHOUT_SUGGESTION`, `42K09`, in `extend_fails_when_the_sequencing_column_cannot_be_cast`. Same production-change note and same alternative as R2.

**R4, ConnectInvalid:608.** A client cannot declare a persisted view without a query. Replace the Debug match in `auto_cdc_flow_targeting_a_persisted_view_is_rejected`, and delete its stale comment. Identifier spelling should follow what `flow_query_type_error` renders for the test graph.

```rust
check_error(
    post_resolution_checks(&graph),
    "INVALID_FLOW_QUERY_TYPE.STREAMING_RELATION_FOR_PERSISTED_VIEW",
    "42000",
    &[("flowIdentifier", QUOTED_TARGET_VIEW), ("viewIdentifier", QUOTED_TARGET_VIEW)],
);
```
