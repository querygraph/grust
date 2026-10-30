# Fable unit 2: Auto CDC microbatch validation and deduplication

Pure components ported from Spark 4.2.1 (`617618396`) with their suite
assertions, offered as Sail `b7118b953` (validation, unit 2a) and `f7adb3f05`
(deduplication, unit 2b) on `work/sdp-streaming-cdc-fable`. Nothing is wired
into a flow; no writer, control store, sink or Iggy effect exists.
`provenance.json` pins the commits and detached gate verdicts;
`assertions.json` maps every original call site to its Sail port and status;
`logs/` holds the gate logs and the test run.

## What runs where

| Spark | Sail | Contract |
| --- | --- | --- |
| `ScdBatchValidator.validateMicrobatch` | `autocdc/microbatch.rs::validate` | sequencing type orderable (`OrderUtils.isOrderable` over Arrow types, `dataType` rendered by `SparkPlanFormatter`), then one aggregation over the original rows: null sequence count, then null count per key in configured order; `AUTOCDC_MICROBATCH_VALIDATION.{NON_ORDERABLE_SEQUENCE,NULL_SEQUENCE,NULL_KEY}` (22000) with `tableName` quoted, `batchId`, `nullCount` / `nullKeyCounts` |
| `Scd1BatchProcessor.deduplicateMicrobatch` | `autocdc/dedup.rs::deduplicate` | group by key field indices, `max_by(struct(all columns), sequencing)` under `__spark_autocdc_winning_row`, unpacked to the input schema |

Inputs the wiring unit must supply: the batch as a `LogicalPlan`, the
sequencing expression resolved against the batch schema, key columns as batch
field indices resolved by the `StructType` lookup under the session's case
setting (with the user's spelling for messages), the target identifier parts
and the batch id. Validation precedes deduplication, as
`Scd1ForeachBatchHandler.execute` orders them.

## Reuse: Sail's `max_by`

`MaxByFunction` is reused as the handoff asked. Its optimizer rewrite is
`last_value(struct) ORDER BY sequencing ASC NULLS FIRST FILTER sequencing IS
NOT NULL`, so a null sequence loses to any non-null one, a key whose
sequences are all null yields a row of nulls, and among equal sequences the
last row in that order survives. All three are inside the pinned contract
(the suite ports the first two; Spark leaves ties undefined and the port
asserts exactly one survivor). `StructFunction` names fields exactly, so
literal-dot names survive the pack and unpack.

## Status counts

19 original cases: 14 ported, 5 partial. The four validation cases marked
partial carry exact error identity and parameters; only their untouched
aux/target table assertions wait for a writer. The reserved-name collision
case asserts failure only, because Spark's `AMBIGUOUS_REFERENCE` comes from
its analyzer while DataFusion rejects the aggregate's duplicate output column
with its own error. Three supplemental tests are listed separately and not
counted as ports.
