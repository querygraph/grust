# CDC units on the current base

Fable's CDC implementation units on Sail's accepted source, after the
division of labour was restored on 2026-10-31 (CF-0532/CF-0533). Each unit
names its Spark 4.2.1 pin sources (`617618396`), what it wires, what it leaves
unexecuted, and its detached gate verdict. Design constraints are in
`STREAMING-CDC-PARALLEL-HANDOFF.md` and `SDP-FABLE-DESIGN-REVIEW.md`; the
earlier validation units on the old base (`work/sdp-streaming-cdc-fable`) are
listed in `FABLE-HANDOFF-FABLE.md` and are ported forward unit by unit.

## Unit A1: auxiliary table identity and full-refresh cleanup

Base `a690e2ce9` (`work/sdp-cdc-build`).

Spark contract:

- `object AutoCdcAuxiliaryTable` (`graph/FlowExecution.scala:321–372`): the
  auxiliary table identifier is the target's catalog and database with the
  table part `__spark_autocdc_aux_state_<table>` (`AutoCdcReservedNames.prefix`
  = `__spark_autocdc_`); reserved properties `pipelines.autocdc.scdType` and
  `pipelines.autocdc.keyColumnNames`; the key column names are stored as a
  compact JSON string array and parsed back only when the text is a JSON
  array of strings (`AutoCdcAuxiliaryTableSuite`, five tests).
- `DatasetManager.materializeTable` (`:301–328`): an existing target is
  truncated when the refresh is full or the target is a batch table; on a
  full refresh the auxiliary table is dropped with `DROP TABLE IF EXISTS`,
  unconditionally, for every fully refreshed target, before the alter/create
  step; the existing schema is merged only for an incremental streaming
  refresh, a full refresh takes the output schema as is.
- `DatasetManager.constructFullRefreshSet` (`:397–430`): a table selected
  for full refresh whose `pipelines.reset.allowed` is false is refreshed
  instead, with an informational log.
- `AutoCdcScd1FullRefreshSuite` (three tests): full refresh wipes target rows
  and the auxiliary table; a sequence below the previous run's watermark then
  lands; a selective full refresh wipes only the requested target's auxiliary
  state. The metadata half of each (truncate, drop, keep the other target's
  state) is what this unit ports; the streaming half (MemoryStream runs,
  watermark rows) needs the SCD1 write path and stays with later units.

Sail:

- New `pipelines/autocdc/mod.rs` (reserved prefix) and
  `pipelines/autocdc/auxiliary.rs` (`table_name`, the two property keys,
  `serialize_key_column_names`, `parse_key_column_names`), with the five
  suite tests ported plus the compact form and the name derivation pinned.
- `materialize::tables`: the "streaming table metadata full refresh"
  rejection is replaced by the Spark behaviour above, including the
  `reset.allowed` downgrade and the unconditional auxiliary drop through
  `spec::CommandNode::DropTable { if_exists: true }`.
- Tests: the former rejection test now asserts that public execution still
  rejects incremental outputs before any catalog effect and that full-refresh
  metadata materialization creates absent targets empty; a new test seeds a
  target and two auxiliary tables, shows the `reset.allowed = false`
  downgrade (rows, merged schema and auxiliary state kept), then the full
  refresh (truncated, schema as declared, only that target's auxiliary table
  dropped) and the no-op repeat.

Out of scope, pinned: `State.reset` (`State.scala:72–100`) rolls the
streaming checkpoint directory of every flow selected for full refresh;
Sail has no streaming checkpoint yet, so this lands with the streaming
runner. Creation of the auxiliary table (`AutoCdcMergeWriteBase
.createAuxiliaryTableIfNotExists`, `FlowExecution.scala:398–440`) belongs
to the SCD1 write unit.

### Finding T1: TRUNCATE left the session's directory listing cache stale

Unit A1's regression test failed on its first run: after the full refresh the
target directory was empty on disk, yet a same-session read still returned the
seeded row. The control that located the cause: clearing only the DataFusion
list-files cache (`ctx.runtime_env().cache_manager.get_list_files_cache()`)
made the read return zero rows, while clearing the file statistics and
metadata caches changed nothing. Sail's session runtime installs
`MokaFileListingCache` by default (`sail-session/src/runtime.rs:140–148`) and
`list_all_files` (`sail-data-source/src/listing/utils.rs:314–330`) serves the
cached listing keyed by `TableScopedPath { table: None, path: url.prefix() }`.
`CatalogCommand::TruncateTable` (`sail-catalog/src/command.rs:830–925`)
replaced the directory but never touched the cache; Spark's
`TruncateTableCommand` refreshes the table after truncation. A second control
(an MV refreshed twice in one session) read one row both times, so the batch
MV path did not expose it, but it ran the same stale listing.

Fix, declared as a shared-file change in CF-0536: after the directory is
replaced or its partition directories cleared, remove the list-files cache
entry for the table directory's `ListingTableUrl` prefix. The pipelines-level
test is the regression test: it exercises the real session runtime with the
cache enabled, failed before the fix and passes after it.

### Unit A1 commits

On accepted head `0cc165ab3` (rebased from `a690e2ce9`, no overlap):
`cef7d6db1` fix(catalog): drop the cached directory listing after TRUNCATE
TABLE; `06e1bf1a1` feat(pipelines): AutoCDC auxiliary table identity and
full-refresh cleanup. Local checks in the build worktree: fmt, strict Clippy
on sail-catalog and sail-spark-connect, sail-catalog 20 tests, pipelines
146 tests. Detached gate (`sail-gate.sh`, gate worktree, own target):
`cef7d6db1` VERDICT fmt=0 clippy=0 rust_common=0 rust_common_datafusion=0
rust_pipelines=0 maturin=0 pytest_pipelines=0 (334 passed) at
2026-10-31T17:48:32Z; `06e1bf1a1` VERDICT fmt=0 clippy=0 rust_common=0
rust_common_datafusion=0 rust_pipelines=0 maturin=0 pytest_pipelines=0 (334
passed) at 2026-10-31T17:53:49Z; sail-catalog strict Clippy and 20 tests in
the gate worktree at the same head.

## Unit A2: Auto CDC definition and input validation on the current base

Commit `a65668134` on `06e1bf1a1`; `922a69c45` after the rebase onto
`c0a824053` (CF-0539 head move, no overlap). A port,
not new behaviour: the modules of units 1, 2a, 2b and correctives C1–C6 from
`work/sdp-streaming-cdc-fable` (`FABLE-HANDOFF-FABLE.md`), each gated there,
moved onto the accepted batch head. Contents: `ChangeArgs` and definition
validation (`ChangeArgsSuite`, `PipelinesHandler.buildAutoCdcFlow`,
`AutoCdcMergeFlow`, `GraphValidations`), source-schema validators with the
JDK ROOT lowercase and break-iterator ports, the field lookup reproducing
Scala `Map1–4`/CHAMP order against `lookup_oracle.json`, microbatch input
validation and `MaxBy` deduplication, the prepared-input contract with its
identity digest, and the 101 native tests that name their Spark source
tests. Wiring: `Flow.auto_cdc`, `define_flow` accepts `AutoCdcFlowDetails`,
and `GraphDefinition::validate` runs the Auto CDC multiflow clause before the
materialized-view clause and the temporary-view clause after streamingness.

Adaptations, both fixture-side: the new base validates in one function, so
the ported graph test calls it once instead of the two old phase methods;
`sail-function` returns to a regular dependency because deduplication uses
`MaxByFunction` in production. Pipelines tests 246 pass, strict Clippy and
fmt clean in the build worktree; detached gate pending.

Nothing executes: no auxiliary table creation, reconciliation or MERGE; a run
with a streaming-table output is still rejected in `execution::execute`.

## Unit A3: auxiliary state contract (schema, key drift, merge support)

Pure component on `a65668134`; no catalog effect is issued. Spark pin:

- `AutoCdcMergeWriteBase` (`graph/FlowExecution.scala:385–600`):
  `requireDestinationSupportsRowLevelOps` raises
  `AUTOCDC_TARGET_DOES_NOT_SUPPORT_MERGE` (0A000, `tableName` quoted,
  `format` = declared format, else the table's provider property, else
  `<unknown>`) when the target is not a `SupportsRowLevelOperations` table;
  `validateNoAutoCdcKeyDriftIfAuxTableExists` runs only when the auxiliary
  table exists, and in this order: the `pipelines.autocdc.keyColumnNames`
  property missing → `AUTOCDC_INVALID_STATE.AUXILIARY_TABLE_PROPERTY_MISSING`;
  not a JSON array of strings → `…PROPERTY_MALFORMED` with `rawValue`; a
  recorded name absent from the auxiliary schema (resolver lookup) →
  `…AUXILIARY_TABLE_KEY_COLUMN_MISSING` with `keyColumnName`, the first
  missing in recorded order; then drift: recorded and expected lengths
  differ, or an expected key has no recorded field of the same name under
  the resolver, or the found field's type is not `sameType` →
  `…KEY_SCHEMA_DRIFT` with `expectedKeySchema`/`recordedKeySchema`. All four
  are AnalysisException, SQLSTATE 42000, message = parent template "AutoCDC
  flow <flowName> detected an invalid state:" + " " + sub template
  (`ErrorClassesJsonReader.getMessageTemplate:122`).
- `sameType` (`DataType.scala:90–95`) is `equalsIgnoreNullability` under
  case-sensitive analysis, else `equalsIgnoreCaseAndNullability`
  (`:599–617`: struct field names compared ignoring case, nullability
  ignored at every depth, otherwise equality).
- `StructType.toDDL` = fields `toDDL` joined by "," (`StructType.scala:458`);
  `StructField.toDDL` = `quoteIfNeeded(name) + " " + dataType.sql + nullDDL`
  (+ default, comment) with `nullDDL` = " NOT NULL" when not nullable
  (`StructField.scala:294, :309–312`); `quoteIfNeeded` backticks a name that
  does not match `^[a-zA-Z_][a-zA-Z0-9_]*` (`QuotingUtils.scala:46–54`).
- Expected key fields come from the flow's selected schema in declared key
  order (`expectedAuxiliaryKeyFields`, `:450–465`); the auxiliary schema is
  those fields plus the `__spark_autocdc_metadata` field found in the flow
  schema (`Scd1MergeStreamingWrite.auxiliaryTableSchema`, `:661–690`), whose
  type is `struct<deleteSequence: T, upsertSequence: T>` with `T` the
  resolved sequencing type (`Scd1BatchProcessor.cdcMetadataColSchema`,
  `:434–442`).
- Oracle tests: `AutoCdcScd1KeyDriftSuite` (13 tests): add key → drift
  "region STRING,id INT NOT NULL" vs "id INT NOT NULL"; drop key; swap key
  name at equal arity; recorded type differs ("id BIGINT NOT NULL"); reorder
  `[a,b]`→`[b,a]` is not drift; nullability or metadata change is not drift;
  adding or dropping backticks is not drift; a case-only difference drifts
  under `spark.sql.caseSensitive=true` ("Id INT NOT NULL" vs "id INT NOT
  NULL") and not under the default; property missing, malformed
  (`rawValue` "not-a-json-array") and key column missing (`["region"]`
  recorded, `region` absent). `AutoCdcScd1SinglePipelineSuite:168–216`:
  parquet target → `AUTOCDC_TARGET_DOES_NOT_SUPPORT_MERGE` with
  `tableName` "`cat`.`db`.`target_no_merge`", `format` "parquet".
  `AutoCdcScd1AuxiliaryTableDurabilitySuite`: a dropped auxiliary table is
  recreated transparently; the property survives identifiers with `'`,
  spaces, `"` and `\`.

Sail: `autocdc/auxiliary.rs` gains `KeyField`, `expected_key_fields`,
`metadata_field`, `auxiliary_schema`, `validate_no_key_drift` (over the
catalog's columns and properties) and `require_merge_support`;
`autocdc/ddl.rs` ports the Spark `.sql` type renderer from the old branch
for the DDL parameters and implements `sameType`; `errors.rs` gains the
five conditions. Tests: the thirteen KeyDriftSuite cases, the parquet
target case and the schema-order cases, over the pure contract (10 native
tests). Commit `f273442aa` on `922a69c45`; pipelines tests 256, strict
Clippy and fmt clean in the build worktree. One pin still open: the
nullability of the `__spark_autocdc_metadata` field is taken as nullable
here; `AutoCdcMergeFlow`'s schema construction decides it and the SCD1
write unit must read it. The checks run nowhere yet: the SCD1 write unit
calls them before creating the auxiliary table.

### Public test port and finding O1: validation runs before resolution

`9dcb9ed08` ports the 40 Connect-level Auto CDC definition tests from the
old branch; 33 pass unchanged. Seven assert Spark's order between
resolution failures and later validations: `PipelineExecution.scala:113`
is `unresolvedGraph.resolve().validate()` and `validationFailure`
(`DataflowGraph.scala:197–208`) begins with
`validateSuccessfulFlowAnalysis` before `validateMultiQueryTables` and
`validateFlowStreamingness`. The current base's `analyze()` calls
`graph.validate()` before resolving anything, so
`INVALID_FLOW_QUERY_TYPE.BATCH_RELATION_FOR_STREAMING_TABLE` and
`AUTOCDC_MULTIPLE_FLOWS_TO_TARGET` preempt a missing source. Not
CDC-specific: the streamingness half reproduces with no Auto CDC flow. The
seven are strict expected failures with that reason and flip when the
order is corrected. Declared to Codex as CF-0540 (analysis.rs is shared);
the fix is to keep only registration-level checks before resolution and
run the `DataflowGraph.validate` set after it, as the old base's analysis
phases did.

## Unit A4: SCD1 write path (design pin)

Spark contract, `autocdc/Scd1ForeachBatchHandler.scala` and
`autocdc/Scd1BatchProcessor.scala` at the pin:

1. `Scd1ForeachBatchHandler.execute(batch, batchId)` (`:39–72`): validate
   the original rows (`ScdBatchValidator`, ported in `microbatch.rs`), then
   `reconcileMicrobatch` against the auxiliary table read, then
   `mergeMicrobatchOntoAuxiliaryTable`, then `mergeMicrobatchOntoTarget`.
   The comment at `:55–60` pins the retry argument: the auxiliary merge only
   advances a tombstone on a strictly newer delete or removes it on a `>=`
   upsert, so a retry after a failure between the two merges makes the
   auxiliary merge a no-op and replays the target merge as a first run.
2. `reconcileMicrobatch` (`:40–51`): `deduplicateMicrobatch` (ported,
   `dedup.rs`: `max_by` of the packed row by the sequencing expression,
   grouped by keys); `extendMicrobatchRowsWithCdcMetadata` (`:131–150`):
   `deleteSequence = when(deleteCondition, sequencing) else null` (null when
   there is no delete condition) and `upsertSequence = when(deleteSequence
is null, sequencing) else null`, packed into `__spark_autocdc_metadata`
   with both members cast to the resolved sequencing type;
   `projectTargetColumnsOntoMicrobatch` (`:152–200`): drop the metadata
   column, apply the flow's `ColumnSelection` under the session case setting
   (ported, `schema.rs`), then re-append the metadata column;
   `applyTombstonesToMicrobatch` (`:202–248`): left anti join of the batch
   with the auxiliary table on all keys equal and
   `greatest(deleteSequence, upsertSequence) < aux.deleteSequence`.
3. `mergeMicrobatchOntoAuxiliaryTable` (`:250–300`): source is the batch
   reduced to keys plus metadata; `incomingRowRepresentsDeleteEvent =
   incomingDelete is not null and (incomingUpsert is null or incomingDelete
   > incomingUpsert)`; clauses in order: when matched and delete event and
`incomingDelete > auxDelete`update the metadata column; when matched
and not a delete event and`incomingUpsert >= auxDelete` delete; when
   > not matched and delete event insert all.
4. `mergeMicrobatchOntoTarget` (`:302–380`): on all keys equal;
   `incomingWinsUpsert = upsert is not null and upsert >= target.upsert`;
   `incomingWinsDelete = delete is not null and delete > target.upsert`;
   clauses in order: when matched and wins delete → delete; when matched
   and wins upsert → update every non-key batch column (resolver-matched);
   when not matched and `delete is null` → insert every batch column.

Sail shape: the reconciliation is a pure DataFusion `LogicalPlan`
transformation (`autocdc/reconcile.rs`, tested in-process over MemTable
inputs as the ported deduplication tests are); the two merges are
`spec::MergeInto` values with `MergeSource::Query` and the clauses above
(`autocdc/merge.rs`, tested on the constructed spec and, where a lake
target is available in tests, on execution through Sail's merge resolver,
`sail-plan/src/resolver/command/merge.rs`). Targets without row-level
operations fail with the A3 merge-support check. Execution wiring (running
the handler per microbatch from the streaming runner, checkpoints, the
`DatasetManager` auxiliary creation at flow start) is the activation step
and stays separate.

### Unit A4a: reconciliation plan transforms

`autocdc/reconcile.rs`: `extend_with_metadata`, `project_selected`,
`apply_tombstones` and `reconcile` (which composes the ported
`deduplicate`) as pure `LogicalPlan` transformations; the caller resolves
the sequencing and delete expressions against the batch schema. Tests
(`tests/reconcile.rs`, 21 functions covering the 22 suite cases at
`Scd1BatchProcessorSuite.scala:480–1197`) run in-process over MemTable
inputs with rows rendered by Arrow's formatter. Two pins from the port:
`when(deleteCondition, seq).otherwise(null)` yields null, hence an upsert,
when the condition evaluates to null, in both engines; DataFusion's
`greatest` ignores nulls as Spark's does, which the tombstone cases rely on.
The incompatible-cast case (`:640`) fails at execution in Sail without
Spark's `DATATYPE_MISMATCH.CAST_WITHOUT_SUGGESTION`, a diagnostic gap
recorded, not a behaviour difference. Strict Clippy and fmt clean; the
module is `expect(dead_code)` outside tests until the write unit wires it.

## Chain state after the rebase onto `9f80ea48e` (CF-0541)

Commits on Codex's accepted head `9f80ea48e` (rebases onto `c0a824053` and
`9f80ea48e` conflict-free, no file overlap): `a0b3cecb2` catalog TRUNCATE
cache fix, `bd782c422` A1, `38031dde3` A2, `49b20336a` A3, `2a24a8774`
public test port, `ef9472065` A4a. Gate verdicts at `c0a824053`:
`922a69c45` (A2) VERDICT all 0, pytest 338, at 2026-10-31T18:14:12Z;
`f273442aa` (A3) VERDICT all 0, pytest 338, at 2026-10-31T18:17:04Z; the
test-port verdict is recorded when it lands. Chunk 1 (catalog fix + A1)
offered to Codex for inspection and gating (CF-0542). Codex owns the
finding O1 fix in `analysis.rs` (CF-0541) and keeps the seven strict xfails
as known integration failures, not a conformance claim.
