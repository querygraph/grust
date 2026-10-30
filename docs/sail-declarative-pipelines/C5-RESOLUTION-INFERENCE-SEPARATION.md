# C5: separating flow resolution from schema inference (proposal)

Status: proposal for Codex's decision, revised after CF-0064; no Sail edit.
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

## Per-flow failure model for Sail

```text
struct FlowFailure { flow: Name, cause: SparkError }      // typed, never a string
struct UnresolvedPipeline {
    direct: BTreeMap<Name, SparkError>,                   // the flow's own failure
    downstream: BTreeMap<Name, SparkError>,               // UnresolvedDataset { dataset } naming the first failed/pending input it read
}
```

Resolution loop (`analysis.rs`), smallest change preserving downstream
binding:

1. A flow whose resolution returns an error other than `UnresolvedRelation`
   is a **direct failure**: record `direct[flow] = error`, mark its output
   failed, continue.
2. An output whose flows all resolved runs `schema::infer` as today (this is
   what `VirtualTableInput.load` does for readers). If the merge fails, the
   failure is attributed the way Spark attributes it: **to the first flow
   that reads this output** if any flow reads it (Spark raises it inside the
   reader's analysis, so the reader is the direct failure and the merged
   output itself is not a failed flow), otherwise to the output's own
   flow(s) as `UNABLE_TO_INFER_PIPELINE_TABLE_SCHEMA`, which is what Spark's
   last-phase `inferredSchema` raises when nothing read it. Either way the
   output is marked failed so no further flow binds to it.
3. A flow whose read hits a failed or still-pending output stays pending.
   When a pass makes no progress, every pending flow becomes a **downstream
   failure** with `UnresolvedDataset { dataset }` naming the first failed or
   pending input it requested, unless the pending set contains no failed
   input at all, in which case `detectCycle` over the pending subgraph runs
   first and raises `PIPELINE_CIRCULAR_DEPENDENCY` with Spark's
   `CircularDependencyException` message (`PipelinesErrors.scala:191–200`),
   exactly `GraphValidations.scala:288–329`'s order: cycle in the failed
   subgraph before the wrapper.
4. If either map is non-empty, raise `UnresolvedPipeline` as a Spark
   `AnalysisException` with Spark's exact message template (no error
   condition, as upstream), carrying both maps.
5. Otherwise continue to the post-resolution validations of `769914891`.

The downstream cause name and message are Spark's
(`UnresolvedDatasetException`), with the dataset in unquoted form.

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

Scope: `analysis.rs` (loop failure path, classification, wrapper), a small
`UnresolvedDataset` builder in `pipelines/graph.rs` or a new
`pipelines/failures.rs`, tests, and the three Fable Python tests. No
`PlanResolver`, session or event-path change.
