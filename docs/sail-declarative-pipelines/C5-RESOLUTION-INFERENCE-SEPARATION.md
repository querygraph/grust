# C5: separating flow resolution from schema inference

Status: implemented. Revision 3 was accepted in CF-0082; the typed merge
error prerequisite is Sail `92ab01326` (gated, CF-0088) and the loop unit is
Sail `b61da2c98`, offered with its detached gate. Earlier: the failure model
(`pipelines/failures.rs`, `bc23c8db6`), the carriers (`105967e17`) and the
retained error variant (`798cd35c9`). Pinned Spark `617618396`; Sail base
`779cb136d`.

Deltas from §5 as implemented, all disclosed in the offer: `GraphScope`
gains an `unavailable` map (tables whose producers resolved but whose
demand-time merge failed; a read of one carries the reader's
`UNABLE_TO_INFER_PIPELINE_TABLE_SCHEMA` cause) and a `GraphScope::new`
constructor used by `materialize.rs` and `execution.rs`; `schema.rs` grew
`merged`, `demand`, `relation`, `unable_to_infer`, `sql_type_name` (a
private `toSQLType` renderer over the retained spec types, per CF-0089) and
`raw_merge_error`; `FailureReport::record_downstream_cause`;
`crate::schema::format_ddl_type` and `quote_field_name` are `pub(crate)`.
The flow cause reaching the client through flow failure events is a strict
`xfail` until the diagnostics unit.

Revision 2 said a reader's demand-time inference ran "over the flows resolved
so far". That is wrong and is withdrawn: Spark makes a table available only
once every flow writing to it has resolved, so the flow set a reader merges is
always complete (§1). Revision 2 also treated every table nobody reads as a
"final phase" case; CF-0074 is right that the user-schema validation phase
infers earlier for tables that have a same-named flow (§3).

## 1. Availability, read from source

`DataflowGraph.resolve` runs `DataflowGraphTransformer.transformDownNodes`
with `CoreDataflowNodeProcessor.processNode` (`DataflowGraph.scala:231–239`).

- Flows are the work queue. A flow's transform is `attemptResolveFlow` over
  `resolvedInputs`, the inputs available at that moment
  (`CoreDataflowNodeProcessor.scala:48–56`).
- A destination (table, view or sink) is transformed **only when every flow
  writing to it is in `resolvedFlowsMap`**
  (`DataflowGraphTransformer.scala:218–222`); the leader thread then calls
  `processNode(table, flowsTo(table))`, which installs a `VirtualTableInput`
  whose `availableFlows` are the resolved results of _all_ its flows
  (`CoreDataflowNodeProcessor.scala:70–91`), and marks the destination
  resolved (`:271–283`). A view is installed from its single flow (`:92–103`).
- A flow whose read finds a dataset that is defined but not yet installed
  throws `UnresolvedDatasetException` (`FlowAnalysis.scala:223–231`), which
  `attemptResolveFlow` turns into `TransformNodeRetryableException(dataset,
ResolutionFailedFlow)` (`CoreDataflowNodeProcessor.scala:181–194`); the
  transformer parks that flow under the dataset and requeues it when the
  dataset is installed (`DataflowGraphTransformer.scala:180–211, 271–283`).
  Any other failure is `TransformNodeFailedException` and is final.
- At the end, a destination with any unresolved flow was never installed, so
  it is a failed table or sink (`:316–325`); its resolved flows are kept as
  `ResolvedFlow`s in `failedFlows` (`:326–336`), the parked flows and the
  failed queue join them as `ResolutionFailedFlow`s, and `getDataflowGraph`
  returns all of them (`:345–357`).

Consequence for CF-0074's condition. `VirtualTableInput.load` does use a
declared schema verbatim without inspecting producer results
(`elements.scala:182–189`), but that method runs only for an installed table,
and a table with a failed producer is never installed. So in the reference a
failed producer **does** make every reader of that table fail, with
`UnresolvedDatasetException(table)`, whether or not the table declares a
schema; this is not an inference of mine but the transformer's gate at
`:218–222`. What the declared-schema arm changes is the schema an available
table presents: the declaration, never merged with producer schemas at
demand time. A producer whose schema disagrees with the declaration therefore
fails no reader; the disagreement is caught in phase 2 of §3 if the table has
a same-named flow, and otherwise not inside `validate` at all.

## 2. Classification and cycles, read from source

`validateSuccessfulFlowAnalysis` (`GraphValidations.scala:288–329`) collects
`(flow, failure.head)` for every `ResolutionFailedFlow`. A failed flow is a
**downstream** failure iff some _failed_ flow writes to any dataset in its
`funcResult.requestedInputs`; otherwise it is **direct** (`:299–311`).
`requestedInputs` is every dataset the flow function asked for before it
threw (`FlowAnalysis.scala:223`). The rule is by requested inputs, not by
exception type: a flow with its own analysis error that had already requested
a table with a failed producer is downstream. Resolved flows whose destination
failed are not `ResolutionFailedFlow`s and appear in neither map.

Cycle detection runs over the failed subgraph only, `failed flow → failed
flows writing to its requested inputs` (`:299–312`); a cycle raises
`CircularDependencyException(downstreamDataset, upstreamDataset)` for the
first back edge `detectCycle` meets (`:313–321, 339–355`;
`PipelinesErrors.scala:190–199`), before the wrapper. Otherwise
`UnresolvedPipelineException(graph, direct, downstream)` is raised
(`PipelinesErrors.scala:164–185`).

Parallelism (`parallelism = 10`) does not change the final sets: a parked flow
is retried whenever its blocking dataset is installed, and the
`ResolutionFailedFlow` kept is that of its last attempt.

## 3. Inference phases, read from source

`validationFailure` runs, in this order (`DataflowGraph.scala:198–207`):

| #   | Phase                                | Inference performed                                                                                                                                                                                                                                                                                           |
| --- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `validateSuccessfulFlowAnalysis`     | none; wrapper or cycle (§2)                                                                                                                                                                                                                                                                                   |
| 2   | `validateUserSpecifiedSchemas`       | for each table `t` with a flow whose identifier equals `t`'s (`flows.flatMap(f => table.get(f.identifier))`, `GraphValidations.scala:255–257`): `inferSchemaFromFlows(all flows to t, t.specifiedSchema)` **before** `specifiedSchema.foreach`, then equality with the declaration if one exists (`:258–281`) |
| 3   | `validateGraphIsTopologicallySorted` | none                                                                                                                                                                                                                                                                                                          |
| 4   | `validateMultiQueryTables`           | none                                                                                                                                                                                                                                                                                                          |
| 5   | `validatePersistedViewSources`       | none (`INVALID_TEMP_OBJ_REFERENCE`, `:358–380`)                                                                                                                                                                                                                                                               |
| 6   | `validateEveryDatasetHasFlow`        | none                                                                                                                                                                                                                                                                                                          |
| 7   | `validateTablesAreResettable`        | none                                                                                                                                                                                                                                                                                                          |
| 8   | `validateFlowStreamingness`          | none                                                                                                                                                                                                                                                                                                          |
| 9   | `inferredSchema`                     | for every destination with flows: `reduce(SchemaMergingUtils.mergeSchemas)` over the flows' schemas, raw (`DataflowGraph.scala:174–182`)                                                                                                                                                                      |

Demand time (§1) is a tenth point, inside each reader's analysis:
`VirtualTableInput.load` returns the declaration verbatim, else
`inferSchemaFromFlows(availableFlows, None)` (`elements.scala:182–189`).

Error shapes, which differ by phase:

- `inferSchemaFromFlows` (`SchemaInferenceUtils.scala:43–78`): empty flow set
  → the declaration or an empty `StructType`, never an error; a merge failure
  → `UNABLE_TO_INFER_PIPELINE_TABLE_SCHEMA` with the merge exception as
  cause; with a declaration, `mergeSchemas(declared, inferred)` failure →
  `incompatibleUserSpecifiedAndInferredSchemasError` (`:80–100`).
- Phase 2 adds the equality check with the same incompatible error and no
  cause (`GraphValidations.scala:264–276`).
- Phase 9 is the raw `StructType.merge`: `SparkException`
  `CANNOT_MERGE_INCOMPATIBLE_DATA_TYPE` (`DataTypeErrors.scala:153–158`) or the
  decimal-scale variant, not an `AnalysisException` and not wrapped.

Which tables reach which phase:

- a table with a same-named flow (every `@dp.table`/`@dp.materialized_view`
  with a query; `api.py:176, 280`): phase 2, whether or not it is read and
  whether or not it declares a schema;
- a table whose producers are only differently named flows (append flows to
  a table defined without a query): phase 9 only, raw shape; a declared
  schema on such a table is never compared with its producers inside
  `validate`;
- a read table: demand time first, in each reader; a merge failure there is
  the reader's direct failure (`UNABLE_TO_INFER…` as the reader's cause) and
  phase 2 is not reached because phase 1 raises the wrapper.

Sail today (`analysis.rs:168–176`, `schema.rs:37–87`): `schema::infer` runs
in the loop for every output as soon as its flows resolve, before other flows
are attempted; the first error of any kind returns immediately. `schema::infer`
itself is phase 2's body (producer merge → `UNABLE_TO_INFER`, declared merge
→ `NOT_COMPATIBLE`, equality → `NOT_COMPATIBLE`); only its placement and its
table set are wrong.

## 4. The contract the pinned suites assert

`ConnectInvalidPipelineSuite.scala` ("Missing source", "Correctly
differentiate between upstream and downstream errors") and
`ViewSuite.scala:133–147` intercept `UnresolvedPipelineException` and assert
the wrapper message ("Flows with errors: b, e" / "Flows that failed due to
upstream errors: c, f", unquoted, sorted), the exact key sets of both maps,
`directFailures(b)` with condition `TABLE_OR_VIEW_NOT_FOUND`,
`directFailures(e)` naming the missing column, and `downstreamFailures(c)` as
`UnresolvedDatasetException` with "Failed to read dataset '<b>'. Dataset is
defined in the pipeline but could not be resolved". Per flow, typed, never
flattened. Delivered: `FailureReport` with both maps and the verbatim
template, raised as `SparkError::UnresolvedPipeline` and served as
`AnalysisException` with that message (`798cd35c9`).

## 5. Resolution algorithm, revision 3

Three structures, kept distinct as CF-0074 asks:

- `resolved_flows: BTreeMap<Name, LogicalPlan>` keyed by **flow** name: the
  resolved flow plans, the only resolution result;
- `available: BTreeMap<Name, LogicalPlan>` keyed by **output** name: the
  input definition a reader binds to, created when and only when every flow
  targeting the output is in `resolved_flows` (§1's gate): a temporary view's
  single plan; for a table, an empty relation with the demand-time schema
  (declaration verbatim, else `schema::merge` over its producers' plans). A
  failed merge is not stored: the reader whose `GraphScope::resolve` computed
  it gets `carry(UNABLE_TO_INFER…)` and records it as its direct cause; the
  next reader computes it again and records its own;
- `inferred: BTreeMap<Name, Schema>` keyed by output: phase outcomes (§3),
  never consulted by readers.

Per flow, each pass attempts **every** flow not yet in `resolved_flows`
(the current `break` on the first pending flow of an output is removed: a
sibling flow with its own error must still be attempted and reported, as
Spark attempts every flow). Outcomes:

1. **resolved**: plan stored in `resolved_flows`; if its target's flows are
   now all resolved, the target enters `available`.
2. **blocked**: `PlanError::UnresolvedRelation(dataset)` from
   `GraphScope::resolve` for a defined output not in `available`: the flow
   stays pending with `(requested inputs so far, dataset)` recorded; it is
   re-attempted when `dataset` enters `available` (every later pass attempts
   it; the same sets result, §2).
3. **failed**: any other error: `recover(error)` recorded as the flow's
   cause together with its requested inputs; final.

The loop ends when a pass resolves nothing new. If any flow is blocked or
failed: classify each by §2's rule over its recorded requested inputs
(downstream iff a blocked or failed flow writes to one of them; a blocked
flow's cause is `unresolved_dataset(dataset)`); build the failed subgraph and
run `detectCycle` with Spark's traversal, raising `PIPELINE_CIRCULAR_DEPENDENCY`
with `CircularDependencyException`'s message for the first back edge;
otherwise raise the wrapper. An undefined dataset is a direct failure of the
reader (`pipelineLocalDatasetNotDefinedError`, Sail's existing
`TABLE_OR_VIEW_NOT_FOUND`), as today.

After a clean loop, phases 2–9 in Spark's order:

- phase 2: `schema::infer(output, producer plans)` for each table output that
  has a flow with `flow.name == output.name` (Sail's `Flow.name` is the
  Spark flow identifier; `@dp.table` names the flow after the table), in
  `graph.flows` order, stored in `inferred`;
- phase 3: `topology::order` (already run);
- phase 4: `validate_multiquery_tables` (with the Auto CDC multiflow clause
  as in `769914891`);
- phase 5: the `INVALID_TEMP_OBJ_REFERENCE` check moves out of the loop to
  here, over the resolved reads;
- phase 6: every dataset has a flow (registration already enforces it; no
  change);
- phases 7–8: resettability, streamingness, temporary-view Auto CDC, as in
  `769914891`;
- phase 9: for every output with flows, `schema::merge` over its producers'
  schemas, raw; a failure is served as `SparkException`
  `CANNOT_MERGE_INCOMPATIBLE_DATA_TYPE` (Sail has the `SparkException`
  throwable class, `error.rs:252, 303`); the result fills `inferred` for
  outputs phase 2 did not cover.

`AnalyzedGraph.relations` keeps its meaning for `materialize.rs` and
`execution.rs` (empty relation per table, plan per temporary view): the
declaration when declared, else the phase-9 schema. Materialisation is
otherwise untouched.

File scope: `analysis.rs` (loop, classification, phase order; about eighty
lines changed), `schema.rs` (`infer` split into `merge` and the declared
check; `merge` reused at demand time and in phase 9), `graph.rs` (no
change expected), `failures.rs` (no change), tests. `schema_merge.rs`,
`topology.rs`, `autocdc/*` and `materialize.rs` unchanged.

## 6. Fixtures (both declaration orders where ordering matters)

Reference outcomes derived in §1–§3; each names the phase that raises.

- `ConnectInvalidPipelineSuite` "Missing source" and "Correctly
  differentiate": exact key sets, nested conditions, dataset messages (phase
  1).
- **Declared-schema table with a failing producer and a reader** (CF-0074):
  `T` declares `(id INT)`, its only flow reads an undefined source, `R` reads
  `T`: direct `{T's flow}`, downstream `{R}` with `unresolved_dataset(T)`;
  the declaration does not make `T` available (§1).
- **Multiple producers, one failing**: `T` has `f1` (resolves) and `f2`
  (undefined source), `R` reads `T`: direct `{f2}`, downstream `{R}`; `f1` in
  neither map.
- **Two readers**: `A` has two producers whose schemas do not merge, `B` and
  `D` read `A`, nothing else fails: direct `{B, D}`, each with its own
  `UNABLE_TO_INFER…` cause; downstream empty.
- **Two readers, declared schema**: as above but `A` declares a schema: `B`
  and `D` resolve (declaration verbatim at demand time); phase 2 raises
  `UNABLE_TO_INFER…` for `A` (same-named flow present).
- **Sibling with its own error**: `T` has `f1` reading a blocked dataset and
  `f2` reading an undefined source: direct `{f2}`, downstream `{f1}`; `f2`
  is attempted although `f1` is blocked.
- **Own error after a failed upstream**: `R` reads `T` (failed producer) and
  also references a missing column, with `T` requested first: downstream
  `{R}` (§2's rule is by requested inputs).
- **Competing validation errors, both shapes** (CF-0074): (i) `A` with a
  same-named flow plus an append flow whose schema does not merge, nobody
  reads `A`, and a streamingness violation elsewhere: phase 2
  `UNABLE_TO_INFER…` for `A` wins, before phase 8; (ii) `A` defined without
  a query and fed by two append flows that do not merge, same streamingness
  violation: phase 8 wins, and with the violation removed phase 9 raises the
  raw `CANNOT_MERGE_INCOMPATIBLE_DATA_TYPE`.
- **Unread incompatible table plus undefined source**: wrapper with direct
  `{C}` only; no inference phase is reached.
- Disconnected cycle plus an independent undefined source:
  `PIPELINE_CIRCULAR_DEPENDENCY` first; disconnected cycle plus a downstream
  chain: cycle first, then without the cycle direct `{b}`, downstream `{c}`.
- Post-resolution phases unchanged when nothing fails; the existing
  `test_schema.py` cases (same-named flows) keep their conditions through
  phase 2; `views.feature:120` keeps `INVALID_TEMP_OBJ_REFERENCE` through
  phase 5; `test_execution.py:254` keeps `PIPELINE_CIRCULAR_DEPENDENCY`;
  `test_autocdc_definition.py:420, 514` move from the inner condition to the
  wrapper message with both lists.

## 7. Transport boundary and callbacks (unchanged from revision 2)

Spark Connect serialises `UnresolvedPipelineException` as an `ErrorInfo`
with the class list; it has no cause and no condition, so a Python client
sees an `AnalysisException` carrying the two lists and nothing else
(`ErrorUtils.scala:76–177`). Sail serves the same through `error.rs`
(`798cd35c9`); `fetch_error_details` is unimplemented on both paths today.
Per-flow causes reach a client only through flow progress events, Codex's
event path, in a later unit.

`failures::carry` / `recover` (`105967e17`) round-trip a `SparkError`
through `PlanError::DataFusionError(DataFusionError::External)` unchanged, so
the demand-time merge failure in `GraphScope::resolve` reaches the loop as
the typed value, never re-parsed from text.
