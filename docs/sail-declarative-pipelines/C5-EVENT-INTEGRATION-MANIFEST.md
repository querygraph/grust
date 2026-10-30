# C5 / Flow-Event Integration Manifest

Read-only packaging review of the offered C5 (resolution/inference
separation) and flow-failure-event commits against Codex's root, prepared at
Codex's request (CF-0199). It identifies the smallest independently buildable
import units, their prerequisites, the files they share with the root, the
Auto CDC coupling, and the Spark 4.2.1 assertions each covers. It proposes
no code change and chooses no runtime or error policy; the original offers
are preserved and nothing is replayed as a stack.

## 1. Source pins

| Item                  | Pin                                                                                              |
| --------------------- | ------------------------------------------------------------------------------------------------ |
| Sail root (Codex)     | `09d2f0cb89cbb92f186f5096ba04ade7a665282c` (`work/spark-declarative-pipelines`, CF-0199)         |
| Offered head (Fable)  | `d88467e41` on `work/sdp-streaming-cdc-fable`                                                    |
| Common base           | `779cb136d988c759a381ea1ace6c2e7649e3dbbc` (`git merge-base` of the two)                         |
| Spark 4.2.1 source    | `617618396` at `/Users/alexy/src/spark-sdp-4.2.1`                                                |
| Designs this executes | `C5-RESOLUTION-INFERENCE-SEPARATION.md` (revision 3, accepted CF-0082), `FLOW-FAILURE-EVENTS.md` |
| Merge oracle          | `evidence/fable-merge-oracle` (JVM `StructType.merge`, cases 1–4)                                |

## 2. What the root already has, and what remains

Every pure component is on the root (CF-0197/0199): bounded contract,
control model, binding, admission with the signature rule and fixtures, the
dynamic inline UDTF guard, the lowerer, the typed error chain, and the
resolved-clock lowering tests. The root as a whole has moved far from the
common base (114 files, mostly Codex's `sail-plan`, `sail-execution`,
`sail-common-datafusion`, `sail-cache` and session ownership work, plus the
imported pure components). Restricted to the fourteen files the C5/event
commits edit (§3), the root differs from the common base only by Fable's own
imports: `analysis.rs` (+16, `GraphScope::new` from unit 3),
`pipelines/mod.rs` (+1, `mod streaming`) and `sql/tests.rs` (the shared
`resolution_context()`); `git diff --stat 779cb136d 09d2f0cb8 -- <those
files>` lists exactly those three. That is a statement about textual
application against those files, not about semantic non-interference with
the rest of the root; the latter is what Codex's per-unit source review and
actual-parent gates establish.

The remaining offered delta against the root, excluding `streaming/`, is two
stacks:

- **C5/event** (this manifest): `analysis.rs`, `failures.rs` (new),
  `schema.rs`, `schema_merge.rs`, `graph.rs`, `execution.rs`,
  `materialize.rs`, `pipelines/mod.rs`, Connect `error.rs` and `schema.rs`,
  `sql/tests.rs`, and the Python tests `test_resolution_failures.py` (new,
  24 tests), `test_file_sources.py`, `features/sql.feature`.
- **Auto CDC** (not this manifest): the `autocdc/` module and its tests,
  `vendor/grust-columns`, `sail-common` ROOT lowercase, the `Flow.auto_cdc`
  field and `AutoCdcFlowDetails` decoding in `graph.rs`, `mod autocdc`,
  `test_autocdc_definition.py`, `features/views.feature`, and the
  `grust-columns`/`sail-function` dependency edges.

## 3. Offered C5/event commits, in order

Each row is one offered commit. "Applies cleanly" records only the dry run
in §6: a cherry-pick without conflict, not a build and not a verdict on
semantics; rows marked _expected_ were not dry-run past E. Build evidence
for a unit exists only when a detached exact-commit VERDICT on its actual
root parent is posted.

| #   | Offered commit | Subject                                                                  | Files                                                                                                                                                                                                                                                                                                                         | Prerequisites                                                                     | Applies cleanly (dry run); not built                                          |
| --- | -------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| A   | `92ab01326`    | typed schema merge error reporting the top-level field pair              | `pipelines/schema.rs`, `pipelines/schema_merge.rs`, Connect `src/schema.rs` (`format_ddl_type`, `quote_field_name` → `pub(crate)`)                                                                                                                                                                                            | none                                                                              | yes                                                                           |
| B   | `bc23c8db6`    | per-flow resolution failure model and its wrapper                        | `pipelines/failures.rs` (new), `pipelines/mod.rs` (`pub(crate) mod failures`)                                                                                                                                                                                                                                                 | none                                                                              | yes                                                                           |
| C   | `105967e17`    | carry typed resolution causes through the relation-scope callback        | `pipelines/failures.rs`                                                                                                                                                                                                                                                                                                       | B                                                                                 | yes                                                                           |
| D   | `798cd35c9`    | raise the per-flow failure report as a retained typed error              | Connect `src/error.rs` (`SparkError::UnresolvedPipeline(Box<FailureReport>)` → `AnalysisException`, no condition), `failures.rs`, `pipelines/mod.rs`                                                                                                                                                                          | B, C                                                                              | yes                                                                           |
| E   | `b61da2c98`    | resolve flows as Spark does, with per-flow failures and phased inference | `analysis.rs` (loop + phases 2–9), `execution.rs`, `materialize.rs` (`GraphScope::new`), `failures.rs`, `schema.rs` (`merged`/`demand`/`infer`/`unable_to_infer`), Connect `schema.rs`, `sql/tests.rs`; Python: `test_resolution_failures.py` (14 tests), `test_file_sources.py`, `sql.feature`, `test_autocdc_definition.py` | A–D; **two Auto CDC call sites and two `graph.rs` methods from CDC commits** (§5) | **no**: conflicts in `analysis.rs` and `test_autocdc_definition.py` (dry run) |
| F   | `2561606e9`    | report datasets without flows in phase 6, after resolution               | `analysis.rs`, `graph.rs` (`validate_every_dataset_has_flow`, `validate` restructured), Python (5 tests)                                                                                                                                                                                                                      | E                                                                                 | expected                                                                      |
| G   | `7962984be`    | port the multiquery predicate of `validateMultiQueryTables`              | `graph.rs` (`validate_multiquery_tables` predicate, `StructuredSparkError`), Python (3 tests)                                                                                                                                                                                                                                 | `validate_multiquery_tables` present (E′, §5)                                     | expected                                                                      |
| H   | `2456618dd`    | render Spark's flow failure events from the retained report              | `failures.rs` (`FailureReport::events`, `client_message`)                                                                                                                                                                                                                                                                     | B–E                                                                               | expected                                                                      |
| I   | `13e0d4f96`    | emit Spark's flow failure events before the unresolved wrapper           | `failures.rs`, `pipelines/mod.rs` (post-select emission), Python (`test_resolution_failures.py` +2 tests, one amended; `test_file_sources.py`)                                                                                                                                                                                | H                                                                                 | expected                                                                      |
| J   | `3ef4e238a`    | hold analysis on an HTTP source with an entry barrier                    | Python only (`test_resolution_failures.py`, the cancellation fixture)                                                                                                                                                                                                                                                         | I                                                                                 | expected                                                                      |
| K   | `37c4d9c4a`    | descend shared wrappers for context lines; own the fixture's setup       | `failures.rs` (`cause_lines` through Context/Shared/Diagnostic), Python                                                                                                                                                                                                                                                       | I                                                                                 | expected                                                                      |

Every row was gated on the offered branch with a detached exact-commit
verdict when offered (CF-0088, 0093, 0096, 0098, 0102, 0111, 0115/0119,
0123; model and carriers in their own entries). None adds a dependency: the
`grust-columns`, `sail-function` and `sha2` edges on the offered branch
belong to Auto CDC and to the already-imported lowerer.

## 4. Spark 4.2.1 assertions each unit covers

Citations are to `617618396`.

| Unit | Spark behaviour pinned                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | Evidence carried                                                                       |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| A    | Raw `StructType.merge` failure: `CANNOT_MERGE_INCOMPATIBLE_DATA_TYPE`, SQLSTATE 42825, left/right are the top-level field types' `.sql` names (`DataTypeErrors.scala:153–158`); `SMALLINT`-class rendering from the JVM oracle.                                                                                                                                                                                                                                                                                                                                                                        | 4 tests in `schema_merge.rs`; `evidence/fable-merge-oracle`                            |
| B    | Wrapper message and shape of `UnresolvedPipelineException` (`PipelinesErrors.scala:164–185`, `:31–35`); direct vs downstream classification: downstream iff the flow reads a failed flow's destination (`GraphValidations.scala:288–329`).                                                                                                                                                                                                                                                                                                                                                             | `failures.rs` unit tests (7 at head, across B–K)                                       |
| C    | Sail mechanism only: typed causes carried through `DataFusionError::External` and recovered; keeps `TABLE_OR_VIEW_NOT_FOUND` / `UNABLE_TO_INFER_PIPELINE_TABLE_SCHEMA` identities intact across the resolver callback.                                                                                                                                                                                                                                                                                                                                                                                 | `failures.rs` tests                                                                    |
| D    | The wrapper is an `AnalysisException` without an error condition at the Connect boundary (`ErrorUtils.scala:76–177` mapping).                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | `failures.rs` tests; Python assertions on `AnalysisException` in E                     |
| E    | Destination installed only when every producer resolved (`DataflowGraphTransformer.scala:218–222`); `UnresolvedDatasetException` parking and retry (`FlowAnalysis.scala:223–231`, `CoreDataflowNodeProcessor.scala:48–91, 181–194`); failed flows kept (`DataflowGraphTransformer.scala:180–211, 271–283`); `validateSuccessfulFlowAnalysis` incl. `detectCycle` (`GraphValidations.scala:288–355`); phase order (`DataflowGraph.scala:198–207`); user schema vs inferred (`elements.scala:182–189`, `SchemaInferenceUtils.scala:43–78`, `GraphValidations.scala:264–276`); raw `inferredSchema` last. | 14 Python tests (`test_resolution_failures.py`), `test_file_sources.py`, `sql.feature` |
| F    | `validateEveryDatasetHasFlow` after resolution (`DataflowGraph.scala:216–226`), `PIPELINE_DATASET_WITHOUT_FLOW`, its place after `validatePersistedViewSources` and before streamingness (`GraphValidations.scala:36`).                                                                                                                                                                                                                                                                                                                                                                                | 5 Python tests                                                                         |
| G    | `validateMultiQueryTables` predicate: tables with more than one flow and any non-streaming flow, `MATERIALIZED_VIEW_WITH_MULTIPLE_QUERIES` (`GraphValidations.scala:56–75`).                                                                                                                                                                                                                                                                                                                                                                                                                           | 3 Python tests                                                                         |
| H    | Flow FAILED event text: downstream "Failed to resolve flow due to upstream failure: '<name>'." then direct "Failed to resolve flow: '<name>'." (`PipelineExecution.scala:112–118`); `messageWithError` (`PipelineEvent.scala:43–56`); logger/sender shape (`FlowProgressEventLogger.scala:137–162`, `PipelineEventSender.scala:94–106`).                                                                                                                                                                                                                                                               | `failures.rs` renderer tests                                                           |
| I    | Events emitted before `throwRunFailure` (`PipelinesHandler.scala:533–568, 581–588`); Connect proto event carries timestamp and message only.                                                                                                                                                                                                                                                                                                                                                                                                                                                           | 2 Python tests + 1 amended; `test_file_sources.py`                                     |
| J    | Cancellation of a held analysis by dropping the graph (`DATAFLOW_GRAPH_NOT_FOUND`), fixture made deterministic.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | 1 Python test (HTTP-held source, entry barrier)                                        |
| K    | `client_message` mirrors Sail's Status policy; context lines through Context/Shared/Diagnostic. Open question to Codex (CF-0121): `Shared`/`External(Context(Plan))` render as DataFusion display text, pinned by equality, not changed.                                                                                                                                                                                                                                                                                                                                                               | `failures.rs` tests; Python                                                            |

## 5. Auto CDC coupling

The dry run (§6) and `git grep` over the offered head locate every coupling
between the C5/event stack and Auto CDC:

1. **Two call sites in `analysis.rs` phases.** Phase 4 calls
   `super::autocdc::validate_multiple_flows_globally(graph)?` before
   `graph.validate_multiquery_tables()`; phase 8 calls
   `super::autocdc::validate_temporary_views(graph)?` after
   `graph.validate_streamingness()`. Spark runs the Auto CDC multiflow and
   temporary-view clauses inside those validations; Sail places them beside
   them. These two lines (with their comments) are the only `autocdc`
   references in `analysis.rs`.
2. **Two `graph.rs` methods first appear in CDC commits but are CDC-free.**
   `validate_multiquery_tables` (introduced in `550bb198a`, predicate
   corrected in G) and `validate_streamingness` (introduced in `769914891`)
   contain no Auto CDC logic; `auto_cdc` appears in `graph.rs` only in the
   `Flow` field, the `AutoCdcFlowDetails` decoding, and one comment. The C5
   loop (E) calls both.
3. **`Flow.auto_cdc` and `mod autocdc`** are not read by any C5/event file
   (`failures.rs`, `schema.rs`, `execution.rs`, `materialize.rs`, `error.rs`);
   `sql.rs` sets `auto_cdc: None` in one `Flow` literal only on the offered
   branch.
4. **Python assertions in `test_autocdc_definition.py`.** E changes four
   expectations there from `SparkConnectGrpcException` with the cause text to
   `AnalysisException` with the wrapper text ("Flows with errors: …"), and
   rewrites one test's docstring and branch to the post-C5 behaviour. The
   file does not exist on the root, so the hunk is Auto CDC's to carry when
   it lands, already in wrapper form.
5. **Dependencies.** None of A–K changes `Cargo.toml` or `Cargo.lock`.

The coupling therefore reduces to a decoupled form of E, written **E′**.
E′ is a proposal only: Codex has not authorized its preparation (CF-0202),
which waits on source review of the actual A–D parent, including E's batch
phase behaviour, the CDC-free graph predicates, its interaction with the
already-imported `GraphScope`/lowerer, and the error and event expectations.
Its shape would be:

- `analysis.rs` as in E minus the two `autocdc::` lines and their comments;
- `graph.rs` gains `validate_multiquery_tables` and `validate_streamingness`
  exactly as the offered head has them before G (so G applies on top), or G's
  form directly if G is folded into the same import, which the manifest does
  not recommend because it would merge two offers;
- the `test_autocdc_definition.py` hunk dropped;
- everything else byte-identical to E, including the 14 Python tests.

**Reintegration obligation, explicit.** Dropping the two call sites and the
four CDC Python assertions from E′ is not a permanent compatibility gap: the
Auto CDC import must re-add `validate_multiple_flows_globally` at phase 4
and `validate_temporary_views` at phase 8 and carry the wrapper-form
assertions in `test_autocdc_definition.py`, and the manifest for that import
must list both as prerequisites. Until then the root's batch phases run
without the Auto CDC clauses, and that is a known, recorded omission.

**Reintegration obligation added after CF-0234.** Codex's publication units
add a publication-options map (one field) to `AnalyzedGraph` in
`pipelines/analysis.rs`, produced during analysis and consumed by
`materialize::views` instead of a second query resolution. E′ rewrites
`analysis.rs` and touches its callers in `execution.rs` and `materialize.rs`;
when E′ is prepared it must carry that field and its producer through the
loop rewrite and keep `materialize::views` consuming it. The manifest's
"shared files" table therefore gains `analysis.rs`, `execution.rs` and
`materialize.rs` as root-changed files once those units land, and E′'s dry run
must be redone against that root.

## 6. Dry run against the root

Performed in a throwaway detached worktree on `09d2f0cb8`, cherry-picking
the offered commits in order and stopping at the first conflict; the
worktree was removed afterwards and nothing was built or pushed:

```
OK       92ab01326
OK       bc23c8db6
OK       105967e17
OK       798cd35c9
CONFLICT b61da2c98: crates/sail-spark-connect/src/pipelines/analysis.rs
                    python/pysail/tests/spark/pipelines/test_autocdc_definition.py
```

The `analysis.rs` conflict is context: E's parent has the `550bb198a` and
`769914891` edits around the post-loop phases and the root does not; the
root's `GraphScope::new` (unit 3) has the same three-argument signature as
E's, which adds the `unavailable` field and fills it with an empty map in
`new`, so `execution.rs` and `materialize.rs` compile against either and E's
`new` supersedes unit 3's. The Python conflict is modify/delete: the file is
absent on the root. F–K were not dry-run past E and are listed as _expected_
clean because each edits only files whose root state equals E's result, with
one note: `sql/tests.rs` on the root carries `std::slice::from_ref(&resolved)`
where E needs `&[&resolved]` after `schema::infer` changes its slice type;
E's hunk rewrites that line and the shared-helper edit sits elsewhere in the
file.

## 7. Proposed import units

Smallest independently buildable sequence, each gated on its actual root
parent as Codex does. Codex's decision (CF-0202): A–D stay four logical
units and may be prepared on a separate branch from the exact root, each
with its own detached verdict; A must carry its assertion evidence (the
`schema_merge.rs` tests against the JVM merge oracle), not only clean
application. E′ and F–K wait for source review of the resulting A–D parent.

1. A `92ab01326` typed merge error.
2. B `bc23c8db6` failure model.
3. C `105967e17` callback carriers.
4. D `798cd35c9` retained typed error.
5. E′ decoupled loop (§5), from `b61da2c98`; the first unit with public
   effect (wrapper message, flow analysis order); gate must run
   `test_resolution_failures.py` (14 tests at this point) and
   `test_file_sources.py`.
6. F `2561606e9` phase 6.
7. G `7962984be` phase 4 predicate.
8. H `2456618dd` events renderer (no public effect until I).
9. I `13e0d4f96` events emission (public effect: FAILED flow events before
   the wrapper).
10. J `3ef4e238a` cancellation fixture.
11. K `37c4d9c4a` context lines and fixture ownership.

Units 5–7 should stay separate because each adds its own Spark-cited Python
assertions and F reorders `graph.validate`; whether 8–11 are grouped is
Codex's call at review time.

## 8. Out of scope and open

- No change to root runtime, catalog, Delta, codec or JobService is
  implied; A–K touch Connect pipelines, Connect `error.rs`/`schema.rs`, and
  Python tests only.
- The Status-policy question from CF-0120/0121 (rendering of
  `Shared`/`External(Context(Plan))`) remains pinned by equality and open to
  Codex; K does not change it.
- Auto CDC import packaging is a separate manifest once Codex asks for it;
  its own coupling to C5 is the mirror of §5.
- Codex's root import of unit 3 kept `GraphScope::new` for the lowerer; E′
  supersedes it with the same signature, so no lowerer change follows.
