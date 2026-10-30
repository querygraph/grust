# Fable unit 1: Spark 4.2.1 Auto CDC definition validation

This packet records the first Fable implementation unit from the
[parallel handoff](../../STREAMING-CDC-PARALLEL-HANDOFF.md): the Spark 4.2.1
Auto CDC argument and definition validation, ported as pure checks with the
original error classes, SQL states and parameters. No durable store, no
reconciliation, no MERGE and no execution path is added. `provenance.json`
pins every source, command and outcome; `assertions.json` maps each original
Spark test call site to its Sail port and status.

## Commits offered for review

| Repository | Branch                         | Commit         | Content                                                                                                                               |
| ---------- | ------------------------------ | -------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Grust      | `work/sdp-streaming-cdc-fable` | `1493d8a36ea8` | `crates/grust-columns`: dependency-free column selection, reserved-prefix and required-name kernel under a caller-supplied comparator |
| Sail       | `work/sdp-streaming-cdc-fable` | `d07a95c2cb0c` | `vendor/grust-columns` with `SOURCE.json`; workspace member; no consumer                                                              |
| Sail       | `work/sdp-streaming-cdc-fable` | `167d577c6567` | `pipelines/autocdc` module, `DefineFlow` arm, graph validations, Rust and Connect-level tests                                         |

Base: Sail `779cb136d988c759a381ea1ace6c2e7649e3dbbc`, Grust
`502cd4f2fedd4c5ab2fd4e5eae3078ce150fa230`, Spark
`617618396087429b5627a86ce933bb0f5d6645cb`.

## Which validation runs where

Spark separates definition-time argument checks from resolution-time schema
checks and from per-microbatch row validation. The port keeps the same
phases; `DefineFlow` never analyzes its inputs.

| Phase in Spark       | Reference                                                                | Condition                                                                                                                                                                                                                                                                        | Sail status                                                                                                                                                                                                                                                                                                                                         |
| -------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| DefineFlow (handler) | `PipelinesHandler.buildAutoCdcFlow`                                      | `AUTOCDC_MISSING_SOURCE`, `AUTOCDC_MISSING_SEQUENCE_BY`, `PARSE_EMPTY_STATEMENT` (blank source), `AUTOCDC_NON_COLUMN_IDENTIFIER`, `AUTOCDC_MULTIPART_COLUMN_IDENTIFIER`, `AUTOCDC_BOTH_COLUMN_LIST_AND_EXCEPT_COLUMN_LIST`, `Unsupported AutoCDC SCD type`, `AUTOCDC_EMPTY_KEYS` | Wired, in this order, in `autocdc::definition` called from `PipelineGraph::define_flow`                                                                                                                                                                                                                                                             |
| DefineFlow (handler) | `PipelinesHandler.handleDefineFlow` once check                           | `DEFINE_FLOW_ONCE_OPTION_NOT_SUPPORTED`                                                                                                                                                                                                                                          | Already wired before graph lookup; covered for Auto CDC by a Connect test                                                                                                                                                                                                                                                                           |
| Graph validation     | `GraphValidations.validateMultiQueryTables`, `validateFlowStreamingness` | `AUTOCDC_MULTIPLE_FLOWS_TO_TARGET`, `INVALID_FLOW_QUERY_TYPE.AUTOCDC_RELATION_FOR_TEMPORARY_VIEW`, unsupported sink destination                                                                                                                                                  | Wired in `GraphDefinition::validate` through `autocdc::validate_target`, before the materialized-view multiple-queries check; runs for dry and real runs                                                                                                                                                                                            |
| Graph validation     | `validateFlowStreamingness`                                              | `INVALID_FLOW_QUERY_TYPE.STREAMING_RELATION_FOR_MATERIALIZED_VIEW` / `_PERSISTED_VIEW`                                                                                                                                                                                           | Already wired by Sail's existing arms (condition only, no parameters)                                                                                                                                                                                                                                                                               |
| Flow resolution      | `AutoCdcMergeFlow` constructor                                           | `AUTOCDC_RESERVED_COLUMN_NAME_PREFIX_CONFLICT`, `AUTOCDC_COLUMNS_NOT_FOUND_IN_SCHEMA`, `AUTOCDC_KEY_NOT_IN_SELECTED_SCHEMA`, `AUTOCDC_SCD2_NOT_SUPPORTED`, output schema with `__spark_autocdc_metadata` last                                                                    | Implemented as pure functions over field names in `autocdc::schema` and exercised by tests; **not wired** into analysis. The prepared CDC input unit wires them where the resolved source schema and `spark.sql.caseSensitive` are available. Until then a dry run analyzes the flow as a streaming read of its source without the metadata column. |
| Planning             | `FlowPlanner`                                                            | `AUTOCDC_SCD2_NOT_SUPPORTED`, `AUTOCDC_TARGET_DOES_NOT_SUPPORT_MERGE`                                                                                                                                                                                                            | Not reachable: the proto has no SCD2 value and execution of any streaming-table pipeline is still rejected before a write (`execution::execute`)                                                                                                                                                                                                    |
| Microbatch           | `ScdBatchValidator`                                                      | `AUTOCDC_MICROBATCH_VALIDATION.*` on original rows before dedup                                                                                                                                                                                                                  | Unit 2; untouched here                                                                                                                                                                                                                                                                                                                              |
| Incremental run      | `FlowExecution` key drift                                                | `AUTOCDC_INVALID_STATE.*`                                                                                                                                                                                                                                                        | Later unit; untouched here                                                                                                                                                                                                                                                                                                                          |

Case handling follows the pinned call sites: `ColumnSelection.applyToSchema`
looks names up through `StructType.getFieldIndexCaseInsensitive`
(`CaseInsensitiveMap`, `Locale.ROOT` lower-casing), while the key and
reserved-prefix checks use the analysis `Resolver`
(`String.equalsIgnoreCase`). Sail supplies both comparators
(`Case::field_lookup`, `Case::resolver`, the latter through the existing
`spark_case_insensitive_name_eq` with JDK 17 oracle tests); the vendored
kernel carries no case folding of its own.

## Reuse inventory

| Candidate                                                                                   | Contract                                                                        | Decision                                                                         |
| ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `sail-common/src/utils/string.rs::spark_case_insensitive_name_eq`                           | JDK 17 `equalsIgnoreCase` with oracle tests                                     | Reused as the resolver comparator                                                |
| `sail-common-datafusion/src/column_change.rs::validate_field_names`, `names_match`, `index` | Arrow `FieldRef` duplicates and ASCII-only insensitive matching for ALTER TABLE | Not reused: Arrow-bound, ASCII-only, no ordered selection or missing-name report |
| `pipelines/schema_merge.rs`                                                                 | Type merging of flow schemas                                                    | Not applicable: no name resolution                                               |
| `grust-sail/src/lib.rs` column matching (`eq_ignore_ascii_case`)                            | Graph column lookup                                                             | Candidate consumer of the kernel later; untouched                                |
| LakeCat `lakecat-core`, `lakecat-sail`                                                      | Catalog seam types, no name resolution                                          | Nothing to reuse                                                                 |
| New `grust-columns`                                                                         | Selection, reserved prefix, required names under a caller comparator            | Vendored; 16 kernel tests; first consumer is `autocdc::schema`                   |

## Known divergences

- Temporary view identifiers: Sail keeps temporary views single-part, so
  `AUTOCDC_RELATION_FOR_TEMPORARY_VIEW` reports `` `target_view` `` where
  Spark reports the fully qualified identifier.
- `AUTOCDC_NON_COLUMN_IDENTIFIER` renders the offending expression through a
  best-effort Catalyst `Expression.sql` port (`(value + 1)` for the pinned
  case); other expression shapes may differ from Spark's text.
- `STREAMING_RELATION_FOR_MATERIALIZED_VIEW` / `_PERSISTED_VIEW` keep Sail's
  existing unstructured form (condition only); the persisted-view case is
  ported in Rust only, because a persisted view without a query cannot be
  registered through the Python client.
- Dry-run analysis of an Auto CDC flow does not yet append the metadata
  column to the target schema (resolution-time unit).

## What remains unexecuted

Everything after definition: the auxiliary state table, original-row
validation, deduplication, metadata projection, tombstones, both MERGEs,
checkpointing, full refresh and key-drift detection. Spark's
`AutoCdcScd1*` graph suites, `Scd1BatchProcessor*` and
`Scd1ForeachBatchHandlerSuite` are not touched by this unit.
