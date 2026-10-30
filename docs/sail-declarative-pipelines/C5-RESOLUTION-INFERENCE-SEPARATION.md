# C5: separating flow resolution from schema inference (proposal)

Status: proposal for Codex's decision, revised after CF-0064 and CF-0066; the
failure model (`pipelines/failures.rs`) is offered as Sail `bc23c8db6`; the
resolution algorithm below is not implemented.
Pinned Spark `617618396`; Sail base `779cb136d`; Fable head `33a883091`.
Revision 1 (first-direct-error identity, A/B attribution difference) is
withdrawn; what replaces it is below.

## What Spark does, read from source

- `DataflowGraph.validationFailure` runs `validateSuccessfulFlowAnalysis`
  first and `inferredSchema` last (`DataflowGraph.scala:198–207`).
- During analysis a flow reads an upstream dataset through
  `FlowAnalysis.readGraphInput` → `ctx.availableInput(id).load(asStreaming)`
  (`FlowAnalysis.scala:216–240`). For a table that input is a
  `VirtualTableInput`, whose `load` returns an empty DataFrame with the
  declared schema or, failing that, `SchemaInferenceUtils.inferSchemaFromFlows`
  over the flows resolved **so far** (`elements.scala:165–201`). So Spark
  also merges upstream flow schemas during analysis; the difference from
  Sail is where a merge failure lands:
  - with a downstream reader, the merge runs inside the reader's analysis
    and the reader is a **direct** failure attributed to the reader;
  - without a reader, the table's merge runs only in `inferredSchema`, last.
- `validateSuccessfulFlowAnalysis` (`GraphValidations.scala:288–329`)
  collects every failed flow, partitions them into direct failures and
  failures caused by a failed upstream, detects cycles among the failed
  subgraph, and throws one `UnresolvedPipelineException` naming both sets;
  the per-flow causes are logged, not carried in the exception's class.

Sail today (`analysis.rs`): one loop resolves each output's flows and
immediately calls `schema::infer` (merge of the flows' schemas plus the
declared-schema check), returning the **first** error it meets, whether a
resolution error or a merge error, in declaration order. That is the
divergence fixtured in `test_schema_merge_inside_resolution_runs_in_declaration_order`.

## The contract the pinned suites assert

`ConnectInvalidPipelineSuite.scala` ("Missing source", "Correctly
differentiate between upstream and downstream errors") and
`ViewSuite.scala:133–147` intercept `UnresolvedPipelineException`
(`PipelinesErrors.scala:164–185`) and assert:

- the wrapper's message contains "Failed to resolve flows in the pipeline",
  "Flows with errors: b, e" and "Flows that failed due to upstream errors:
  c, f" (unquoted identifiers, sorted);
- `directFailures.keySet` and `downstreamFailures.keySet` are exactly the
  expected sets;
- `directFailures(b)` is the typed nested cause with condition
  `TABLE_OR_VIEW_NOT_FOUND`; `directFailures(e)` is an `AnalysisException`
  whose message names the missing column;
- `downstreamFailures(c)` is an `UnresolvedDatasetException` whose message is
  "Failed to read dataset '<b>'. Dataset is defined in the pipeline but could
  not be resolved".

So the model is per flow: every failed flow carries its own typed cause, the
wrapper carries both maps, and nothing is flattened to a first error.

## Per-flow failure model for Sail (offered as `bc23c8db6`)

`pipelines/failures.rs`: `FailureReport { direct: BTreeMap<Name, SparkError>,
downstream: BTreeMap<Name, SparkError> }`, `unresolved_dataset(dataset)`
building `UnresolvedDatasetException`'s exact message, `message()` rendering
Spark's template verbatim with both sorted unquoted lists, and
`into_error()` producing `SparkError::AnalysisError`, which the existing path
maps to class `org.apache.spark.sql.AnalysisException` with that message and
no condition (demonstrated by converting to a tonic `Status` and reading the
`ErrorInfo`). Unwired.

## Resolution algorithm, revised after CF-0066

The loop keeps **resolved flow plans** separately from any table schema;
a table's schema is never stored as a resolution result. Two inference
points exist, both derived from the resolved flow plans:

- **demand-time** (`VirtualTableInput.load` in Spark): when a flow's read of
  a local table is resolved, `GraphScope::resolve` computes that table's
  schema from the flows of that table resolved so far (declared schema if
  present, else the merge); the reader binds to an empty relation with that
  schema;
- **final** (`inferredSchema` in Spark): after every flow has resolved and
  after the other post-resolution validations, every table's schema is
  inferred from all of its flows for materialisation.

Failure handling, per flow:

1. **Direct failure.** A flow whose own resolution fails (any `PlanError`
   other than `UnresolvedRelation`) is recorded in `direct` with its typed
   cause, and its output is marked failed. A demand-time merge failure is a
   direct failure of **the reader whose resolution computed it**: if B and D
   both read a table whose flows merge badly, each of B and D records its
   own cause when its own resolution runs (CF-0066 point 1). The callback
   that preserves this is narrow: `GraphScope::resolve(name)` returns
   `PlanError::AnalysisError` built from the merge error for that reader,
   through the same `From` path the loop already uses for any resolution
   error; nothing is guessed after the fact.
2. **Downstream failure.** A flow whose read hits a failed or still-pending
   table stays pending. When a pass makes no progress, each pending flow is
   recorded in `downstream` with `unresolved_dataset(<first failed or pending
   input it requested>)`.
3. **Cycle detection runs over the failed subgraph unconditionally**
   (CF-0066 point 3): before the wrapper is raised, build the map from each
   failed or pending flow to the failed or pending flows that write its
   requested inputs (`GraphValidations.scala:299–312`) and run `detectCycle`
   (`:339–355`); a cycle raises `PIPELINE_CIRCULAR_DEPENDENCY` with Spark's
   `CircularDependencyException` message, whether or not another component
   of the graph failed for a different reason.
4. If either map is non-empty, raise the wrapper (`FailureReport::into_error`).
5. **Tables nobody read** (CF-0066 point 2): a table whose flows all resolved
   but which no flow read is not a failure during analysis. Its schema is
   inferred in the final phase, after the post-resolution validations of
   `769914891`, where a merge failure raises
   `UNABLE_TO_INFER_PIPELINE_TABLE_SCHEMA` (or the declared-schema
   incompatibility) as Spark's last phase does. No synthetic direct failure
   of its flows is recorded.

Order of phases after the loop: wrapper or cycle (step 3–4) → Auto CDC
multiflow → MV multiflow → resettability → streamingness → temporary-view
Auto CDC → final inference per table. Downstream binding is preserved
because demand-time inference happens exactly where Spark does it, inside
the reader's resolution.

Fixtures (both declaration orders where ordering matters):

- the two `ConnectInvalidPipelineSuite` cases, exact key sets and nested
  conditions;
- A incompatible, B and D both read A, C undefined: direct `{B, D, C}`, each
  of B and D carrying its own merge cause;
- A incompatible, nobody reads A, nothing else fails: analysis succeeds, the
  final phase raises `UNABLE_TO_INFER_PIPELINE_TABLE_SCHEMA` for A, no
  wrapper;
- A incompatible, nobody reads A, C undefined: wrapper with direct `{C}`
  only; A's inference failure is never reached;
- disconnected cycle (`x` reads `y`, `y` reads `x`) plus an independent
  undefined source `z`: `PIPELINE_CIRCULAR_DEPENDENCY` first;
- disconnected cycle plus a downstream chain (`b` reads undefined, `c` reads
  `b`): still the cycle first, then on removing the cycle the wrapper with
  direct `{b}`, downstream `{c}`;
- the post-resolution phases unchanged when nothing fails.

## Transport boundary, compared from source

Spark Connect serialises a throwable as an `ErrorInfo` with the class list
and, with error enrichment, a `FetchErrorDetails` chain built from
`getCause` (`ErrorUtils.scala:76–177`). `UnresolvedPipelineException` has
no cause and no error class; its per-flow causes live in its two maps and in
the per-flow failure events, not in the cause chain. A Python client
therefore sees an `AnalysisException` whose message carries the two lists,
and nothing else, in Spark too.

Upstream Python assertion forcing an outer condition: **none**. The pinned
`python/pyspark/pipelines/tests` contain no assertion on `Failed to resolve`,
`TABLE_OR_VIEW_NOT_FOUND` or a condition of an unresolved pipeline (grep
over the pinned tree); the only `getCondition` assertions there are the
session-mutation tests. The Sail tests that assert the inner condition in the
message string are Fable's own (`test_unresolved_source_is_reported_before_the_temporary_view_rule`
and the two both-order fixtures) and will be rewritten to the wrapper
message plus the two lists; the feature scenarios assert nothing about
unresolved datasets.

Connect exposure in Sail, two separately reviewable units:

1. **Source model and wrapper** (this unit): the structure above; the
   wrapper reaches the client as `AnalysisException` with Spark's message
   through the existing `spark_status` path (`error.rs`), which is what
   Spark's client sees as well. Sail's `fetch_error_details` is
   unimplemented, so no chain is served either way today.
2. **Per-flow diagnostics** (later, Codex's event path): Spark logs each
   flow failure as a flow progress event before the wrapper; Sail's
   pipeline event stream (`event(...)` in `pipelines/mod.rs`) is where the
   per-flow causes would be emitted so a client can see which flow failed
   with which condition, matching "look for flow failures that precede this
   log". Not part of the resolution unit.

## Fixtures (ports, both declaration orders where ordering matters)

- "Missing source": `b` reads `a` undefined → direct `{b: TABLE_OR_VIEW_NOT_FOUND}`,
  message lists.
- "Correctly differentiate": `a` ok, `b` reads nonexistent, `c` reads `b`,
  `d` ok, `e` selects a missing column, `f` reads `e` → direct `{b, e}`,
  downstream `{c, f}` with the dataset messages; both key sets exact.
- merge failure with a reader: `A` incompatible flows, `B` reads `A`, `C`
  undefined source → direct `{B: merge error, C: TABLE_OR_VIEW_NOT_FOUND}`,
  both orders; without `B`: direct `{A's flow: UNABLE_TO_INFER_...}`.
- cycle plus an undefined source: `x` reads `y`, `y` reads `x`, `z`
  undefined → Spark: `z` is a direct failure and `x`, `y` pending with no
  failed input → `detectCycle` fires first → `PIPELINE_CIRCULAR_DEPENDENCY`;
  the fixture asserts that order.
- the post-resolution phases unchanged when nothing fails; the existing
  both-order fixtures move to the wrapper message.

Scope: `analysis.rs` (resolved-plan map, demand-time schema callback in
`GraphScope::resolve`, failure recording, failed-subgraph cycle check,
wrapper, final inference phase), `schema.rs` (split merge from declared
check so both inference points reuse it), tests, and the three Fable Python
tests. `pipelines/failures.rs` is already offered. No `PlanResolver`,
session or event-path change.
