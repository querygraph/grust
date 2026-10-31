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
Clippy and fmt clean in the build worktree. The metadata field's nullability was first taken as nullable; `AutoCdcFlowSuite.scala:270–278` pins it as not nullable with nullable members, corrected in `9ef96af61`. The checks run nowhere yet: the SCD1 write unit
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

### Unit A4b: the two merges as MERGE INTO commands

`autocdc/merge.rs`: `auxiliary_merge` and `target_merge` build
`spec::MergeInto` values over a reconciled microbatch registered as a
temporary view (`sail-catalog` `TemporaryViewManager` holds a
`LogicalPlan`; the write unit registers it with `replace`). Clause order,
conditions and assignments follow `Scd1BatchProcessor.scala:250–380`
exactly: auxiliary merge on the keys with update-metadata, delete-tombstone
and insert-tombstone clauses; target merge with delete, update-non-keys and
insert-all-columns clauses, the key exclusion under the session resolver.
Spark qualifies target columns by the quoted table identifier; Sail's
resolver takes aliases, so the auxiliary table is aliased `auxiliaryTable`
and the destination `destination`, with Spark's `reducedMicrobatch` and
`microbatch` source aliases. Three structural tests (`tests/merge.rs`)
pin sources, aliases, join keys, clause order, conditions and assignments;
execution needs a row-level target (Delta/Iceberg through
`sail-plan/src/resolver/command/merge.rs`) and belongs to the write unit's
activation tests. Commit `ffad1d382` on `ef9472065`; 281 pipelines tests,
strict Clippy and fmt clean.

Gate: `9dcb9ed08` (test port) VERDICT all 0, pytest 338, at
2026-10-31T18:19:40Z; sail-catalog strict Clippy and 20 tests at that head.
A4a/A4b gate running on the rebased shas.

## Unit A4c: the SCD1 write component (design pin)

What Spark does per flow start and per microbatch, and the Sail seams:

- `createAuxiliaryTableIfNotExists` (`FlowExecution.scala:398–440`): if the
  auxiliary identifier does not exist, create it with the auxiliary schema
  (A3), the target's declared format as provider when present, and the
  properties `pipelines.autocdc.scdType` = SCD label and
  `pipelines.autocdc.keyColumnNames` = the compact JSON of the key names;
  an existing table is left untouched (drift validation ran first). Sail:
  `spec::CommandNode::CreateTable { table, definition }` through
  `execution::run_command`, the `TableDefinition` as `materialize.rs`
  builds it, with `file_format` from the destination's format.
- `Scd1ForeachBatchHandler.execute` (`:39–72`): validate (A2
  `microbatch::validate`), reconcile against the auxiliary table read (A4a
  `reconcile`), register the reconciled plan as a session temporary view
  (`CatalogManager::create_temporary_view` with `replace`, the
  `TemporaryViewManager` holding the `LogicalPlan`), then run the A4b
  auxiliary merge and target merge as `spec::CommandNode::MergeInto`
  through `run_command`, in that order; the retry argument at `:55–60`
  holds unchanged.
- Expressions: the flow's `sequencing` and `delete_condition` are
  `spec::Expr`; the resolver's `resolve_expression` is crate-private, so
  the handler resolves them by resolving a `spec` projection over the
  microbatch view and taking the projection's expressions, which binds
  them to the view's qualifiers exactly as the batch columns are bound.
- Tests: native, with `sail-delta-lake` as a dev-dependency registering
  `DeltaLakeSource` in the pipelines test context (it is already compiled
  through `sail-session`), so a Delta destination accepts the merges;
  cases from `AutoCdcScd1SinglePipelineSuite`, the durability suite's
  "dropped auxiliary table is recreated" and the full-refresh suite's
  second runs, expressed as two handler invocations over MemTable batches.
  No streaming runner, checkpoint or `execution::execute` wiring: the
  handler is invoked by tests only, and activation is the next design
  checkpoint (user-notified).

### Unit A4c: write component, delivered

`autocdc/write.rs`: `ensure_auxiliary_table` and `handle_microbatch` as
pinned above, with one design choice recorded: the flow's `sequencing` and
`delete_condition` (`spec::Expr`) are evaluated once as the reserved helper
columns `__spark_autocdc_sequence` and `__spark_autocdc_delete` of a
projection over the batch view, which is how Spark evaluates them as
`Column`s over the microbatch; the helper columns are dropped before the
reconciled view is published, and the resolved sequencing type is the
evaluated column's type. Tests (`tests/write.rs`, 6) run the handler
in-process against a Delta destination created in the test warehouse,
using the production session's analyzer, optimizer and physical optimizer
rules (finding: the pipelines test context lacked them, and the Delta merge
path plans an explicit repartition only Sail's physical rules remove).
Cases: `AutoCdcScd1SinglePipelineSuite` empty-target upsert (`:43`), the
one-run upsert/delete/re-upsert convergence with the delete flag excluded
(`:74`), the parquet rejection (`:168`); `AutoCdcScd1AuxiliaryTableDurabilitySuite`
cross-run upsert (`:42`), suppression below a recorded delete with the
tombstone visible in the auxiliary table (`:83`), and recreation of a
dropped auxiliary table (`:184`). The full-refresh suite's second-run cases
compose A1's drop with this handler and are left to the activation tests.

Gate: A4a `ef9472065` VERDICT all 0 (pytest 379 passed, 7 xfailed) at
2026-10-31T18:33:02Z; A4b `ffad1d382` VERDICT all 0 at 18:36:10Z.

### Chain state after the rebase onto `3847d4e57` (CF-0543, O1 fix)

A4c `7ed24b112` VERDICT all 0 at 2026-10-31T18:45:58Z. Codex integrated the
O1 order fix as `3847d4e57` (`validate_bindings` before resolution, the
semantic validator after; my hooks stay in `validate()`); the chain rebased
cleanly: `dc89eff36` catalog fix, `29552513b` A1, `910aeed42` A2,
`c488974fb` A3, `8968be9e4` test port, `39d700423` A4a, `969b25981` A4b,
`bf3d81141` A4c; 288 pipelines tests pass. On that head the seven strict
xfails still fail, now for the wrapper rather than the order: the missing
source wins (`[TABLE_OR_VIEW_NOT_FOUND] Table or view not found:
no_such_source`) but Spark reports it through `UnresolvedPipelineException`
("Flows with errors: <flow names>"), which Sail does not produce; recorded
as finding O2 in the markers' reason.

## Unit A5: triggered SCD1 flow run (delivered under the stated defaults)

`autocdc/run.rs`: `RunRecord` (authority statement, descriptor digest,
captured frontier, progress, continuing batch id; JSON written by rename),
`checkpoint_dir` (`<root>/_checkpoints/<destination>/<flow>/<n>`, reset
creates `n + 1`), and `run_flow` (ensure the auxiliary table, capture the
frontier, loop `next_intent` → `SourceBinding` → `lower` →
`handle_microbatch` → advance and store). Tests (`tests/run.rs`, 3) run the
`DeterministicSource` against a Delta destination: two runs continue from
the record with an idle run doing no batch; a batch whose record advance
was lost replays with the target unchanged; a reset creates version `1`
and restarts from the earliest position. The three design decisions stay
open; the unit implements their defaults (local record with the boundary
stated in every record, no `execution::execute` arm, Spark's checkpoint
layout under the warehouse) and nothing public is activated. Codex
(CF-0546) flagged the activation checkpoint to the user as Astra design
work; A5 is the component that checkpoint would wire.

## Chain state after chunk 1 integration (CF-0546)

Codex integrated chunk 1 as `bfd105744` (catalog) and `26500918b` (A1),
blobs identical to mine. Rebased onto `26500918b`, the chain is
`23aa26eff` A2, `abfac64c2` A3, `9fa5609c3` test port, `6bc37f2c2` A4a,
`5189c8392` A4b, `8a3a8a063` A4c, `b38ecbbfb` xfail reasons (finding O2),
`d34441e10` A5; 291 pipelines tests pass; gate on `8a3a8a063` and
`d34441e10` running. Chunk 2 = those eight commits.

### Full-refresh runs composed (test-only commit after A5)

`tests/run.rs` adds `AutoCdcScd1FullRefreshSuite.scala:34–71` and `:73–113`
as real sequences: a run, `materialize::tables` under `full_refresh_all`
(A1's truncate and auxiliary drop against the declared streaming table),
then a run in the reset checkpoint version. The second run brings only its
own events; an event below the old recorded delete lands. The selective
case (`:115`, two flows in one run) waits for run orchestration. Gate:
A4c rebased `8a3a8a063` VERDICT all 0 at 2026-10-31T19:00:04Z.

### Unit A5b: sequential multi-flow runs and the selective full refresh

`run_flows` runs a pipeline run's flows one at a time in the given order and
stops at the first failure with the completed outcomes
(`TriggeredGraphExecution`'s topological start, without `maxConcurrentFlows`
or watchdog retries). Test: `AutoCdcScd1FullRefreshSuite.scala:115–182` as
two real runs over two flows with a selective full refresh of `t_a` through
`materialize::tables` (`full_refresh_selection`) between them; `t_a` takes
the lower sequence, `t_b` keeps suppressing it. Gate: A5 `d34441e10`
VERDICT all 0 at 2026-10-31T19:03:03Z; `f6be32bc7` VERDICT all 0 at 19:07:27Z;
`b302e1c28` VERDICT all 0 at 19:10:32Z. Chunk 2, the ten commits
`23aa26eff..b302e1c28` on `26500918b`, offered to Codex (CF-0548).

### Merge-execution suite ported (test-only commit)

`tests/merge_execution.rs`: the 18 cases of
`Scd1BatchProcessorMergeSuite.scala:107–541` run the A4b `spec::MergeInto`
commands through Sail's merge resolver against seeded Delta tables, with
the microbatch published as the write component's temporary view. All pass
on the first run; the case-sensitive half of the grid case (Spark's
`UNRESOLVED_COLUMN` for a mis-cased key) is not portable because the key is
resolved by the flow definition before any merge in Sail. With this, every
Spark SCD1 suite at the pin is ported or accounted for: ChangeArgs, flow
and schema validators (A2), auxiliary state (A3), batch processor
transforms (A4a), merges (A4b, this suite), handler and single-pipeline
runs (A4c), durability and full refresh (A5, A5b); the remaining
unported assertions are the MemoryStream/checkpoint halves that need the
activation runner.
