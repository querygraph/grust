# Review: batch provider ownership and caller migration

Fable's source-pinned review of Codex's draft
`BATCH-PROVIDER-MIGRATION-DESIGN.md` and its excerpt packet
`evidence/batch-provider-migration` (coordinator Grust, working files),
requested in CF-0224. Read only: no code, no runtime change; A–D/E′ and the
Status question untouched.

## Pins

| Item        | Pin                                                                                                                                                                                                             |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sail        | `17b8ac254139e9213327dfcc7fc8badb4fdd27b2`; test-only `954e025c5` (analysis artifact/clock characterization, integrated CF-0226)                                                                                |
| Spark 4.2.1 | `617618396087429b5627a86ce933bb0f5d6645cb` at `/Users/alexy/src/spark-sdp-4.2.1`                                                                                                                                |
| Sail files  | `pipelines/analysis.rs`, `pipelines/execution.rs`, `pipelines/materialize.rs`, `pipelines/sql.rs`, `pipelines/graph.rs`, `sail-plan/src/lib.rs`, `sail-plan/src/resolver/command/catalog/view.rs`               |
| Spark files | `graph/FlowExecution.scala`, `graph/DataflowGraph.scala`, `graph/GraphOperations.scala`, `graph/DatasetManager.scala`, `graph/FlowAnalysis.scala`, `graph/FlowAnalysisContext.scala`, `graph/FlowPlanner.scala` |

Every statement below was read at those pins; Codex's packet pins the same
blobs with SHA-256 in `source-pins.json`.

## 1. What the draft says that the source confirms

- **Sail retention.** `analysis.rs:174–186` keeps a full plan only for
  `OutputType::TemporaryView`; other outputs become `EmptyRelation` with the
  inferred schema. `materialize::views` resolves `CreateView` over
  `analyzed.relations` (`materialize.rs:267–269`) and
  `resolve_catalog_create_view` uses the resolved input for schema and
  columns only, persisting the definition (`command/catalog/view.rs:39–70`).
  `execution.rs:39–91` starts a fresh `resolved` map, resolves temporary
  views itself under each view's own `plan_config_with_overrides(flow.
sql_conf)` (`:69`), and reads every other output through `read_output`
  (`:144–165`). That map, not `analyzed.relations`, is the cross-command
  provider cache. My earlier reuse claim was wrong and is retracted
  (CF-0223).
- **Sail command dispatch.** `run_command` (`execution.rs:100–112`) calls
  `resolve_and_execute_plan_with_scope` (`sail-plan/src/lib.rs:46–80`): resolve
  → `execute_logical_plan(ctx, plan)` (`:60`, authority dispatch through
  `SessionContext::execute_logical_plan`) → `optimize` (`:62`) → streaming
  rewrite (`:63–67`) → `create_physical_plan` on the returned state (`:69–72`)
  → `rename_physical_plan` (`:73–77`), then `runner.execute`. Admission is
  indeed after all of that.
- **Spark reanalysis.** `BatchTableWrite.executeInternal`
  (`FlowExecution.scala:254–287`) wraps the write in
  `SparkSessionUtils.withSqlConf(spark, sqlConf)`, calls
  `graph.reanalyzeFlow(flow).df`, then appends. `reanalyzeFlow`
  (`DataflowGraph.scala:149–168`) collects the upstream closure with
  `dfsInternal(…, downstream = false, stopAtMaterializationPoints = true)`,
  builds a subgraph of those flows and views plus the destination table or
  sink, and resolves it. `dfsInternal` (`GraphOperations.scala:70–100`) stops
  at a node iff `table.contains(currNode) && currNode != startDestination`:
  a materialization point is a **table**; views, persisted or temporary, are
  traversed. The `sqlConf` on `BatchTableWrite` is the flow's
  (`FlowPlanner.scala:45–49`).
- **Spark view publication.** `DatasetManager.materializeView`
  (`:204–233`) builds `CreateViewCommand(plan = flow.df.logicalPlan,
originalText = view.sqlText, isAnalyzed = true, allowExisting = true,
replace = true, …)` and runs it with the flow's `queryContext` catalog and
  namespace installed, restored in `finally`. Deriving publication metadata
  while analysis owns the input is what Spark does.
- **Spark per-flow conf.** `FlowAnalysis` installs a private `SQLConf` per
  flow through `SQLConf.withExistingConf(ctx.flowConf)` and sets the flow's
  own confs first (`:45–72`, `:62–63`); `readGraphInput` then fuses an
  upstream **`Flow`** input's `sqlConf` by `ctx.setConf` (`:256–260`), which is
  `flowConf.setConfString` (`FlowAnalysisContext.scala:65–67`), an overwrite.
  Table inputs (`VirtualTableInput`) fuse nothing.

## 2. Findings

- **2.1 Conf fusion (corrected after CF-0250): a union with conflicts
  rejected, not an overwrite.** The earlier text read only
  `readGraphInput`'s `setConf` and called the rule "upstream overwrites
  consumer in input-read order". That overwrite happens inside the first
  analysis pass only. The rule that determines a flow's conf is
  `CoreDataflowNodeProcessor.attemptResolveFlow`
  (`CoreDataflowNodeProcessor.scala:118–190`): after the first successful
  call, it collects `FlowConf(key, value, flowIdentifier)` for the flow's own
  confs plus the confs of every **`Flow`** input it actually used
  (`f.inputs`, so views; `VirtualTableInput` tables contribute nothing);
  if any key carries more than one distinct value across those flows it
  throws `AnalysisException("DUPLICATE_FLOW_SQL_CONF", key, datasetName,
flowName1, flowName2)` (names sorted by value); otherwise `newSqlConf` is
  the union, and if it differs from the flow's own confs the flow function
  is called again under the union. `ResolvedFlow.sqlConf` is
  `funcResult.sqlConf` (`Flow.scala:194`), so the merged conf is what
  `BatchTableWrite.sqlConf` (`FlowPlanner.scala:49`) applies with
  `withSqlConf` around `reanalyzeFlow`. Pipeline-level defaults are folded in
  at registration as `defaultSqlConf ++ flowDef.sqlConf`
  (`GraphRegistrationContext.scala:62`), so a flow's own value wins over the
  pipeline default and does not count as a conflict. `FlowFunctionResult.
sqlConf` is the raw confs passed to that call (`FlowAnalysis.scala:72`),
  which is the phase distinction CF-0250 names: raw per call, merged on the
  resolved flow. Spark's own tests pin this: `ConnectValidPipelineSuite`
  "Connect retains and fuses confs" (`:264–288`, `d` over `a→b` and `c`
  yields the union of all four), "Confs aren't fused past materialization
  points" (`:289–321`, a table `b` reading view `a` gets `a`'s conf, but a
  consumer of `b` does not), "Setting the same conf with the same value is
  totally cool" (`:322–345`), "Pipeline level default spark confs are
  applied with correct precedence" (`:460–490`); `ConnectInvalidPipelineSuite`
  "view-table conf conflict" (`:350–373`) and "view-view conf conflict"
  (`:374–`) assert `DUPLICATE_FLOW_SQL_CONF`. Sail today applies neither
  the union nor the conflict check: a consumer resolves under its own
  `sql_conf` and each view body under the view's own (`execution.rs`,
  `reanalysis.rs`, `analysis.rs:124`). The design's target should therefore
  be: resolve a command's view closure and its own query under the union of
  the consumer's and the traversed views' flow confs, fail with
  `DUPLICATE_FLOW_SQL_CONF` on conflicting values, stop the union at tables,
  and fold pipeline defaults under flow confs. Qualification from Codex's
  live Spark 4.2.1 probes (CF-0252, `evidence/flow-config-fusion-reference/
attempt-02/observations.json`): the successful union and the conflict
  check are order-independent, so the `BTreeSet` topology suffices for them,
  but the first-pass failure precedence is not. With one upstream view
  setting `caseSensitive=true` and another `false`, a consumer whose first
  pass runs under the last-written value can fail `UNRESOLVED_COLUMN` before
  the merge validation ever throws `DUPLICATE_FLOW_SQL_CONF`; reversing the
  SQL input order flips which error is reported. Reproducing that observable
  precedence needs the ordered pre-analysis input binding, not only the set.
- **2.2 Persisted views are not materialization points in Spark.** The
  closure stops at tables only; an upstream persisted view's defining flow is
  re-analyzed inside the consumer's subgraph. Sail publishes the view at
  `materialize::views` and later `read_output`s it from the catalog
  (`execution.rs:53–62`), where the catalog re-resolves the stored SQL at read
  time against the session. The two agree only when the published SQL
  re-resolves identically: the view flow's `sql_conf` and pipeline namespace
  are not applied to the catalog re-parse, and the read uses the session
  `plan_config()` (2.3). The draft's "a table reference means the committed
  output" is right for tables; for persisted views it should say which
  behaviour is intended and test the conf/namespace case. (Sail's rule that a
  persisted view may not read a pipeline temporary view removes the hardest
  case.)
- **2.3 `read_output` resolves under the session config, not the consuming
  flow's.** `execution.rs:157` builds the resolver with
  `ctx.extension::<SparkSession>()?.plan_config()`, while the consumer's own
  query uses `plan_config_with_overrides(flow.sql_conf)`. In Spark the read
  happens inside the consumer's analysis under the fused conf. The direction
  text "resolve committed table/view reads … under that same owner" should
  add "and under that command's configuration".
- **2.4 Per-command clock already matches Spark on the batch path, for the
  reason the characterization shows.** `954e025c5`'s
  `analysis_temporary_clock_remains_unfolded` pins that a temporary view's
  `current_timestamp()` stays a `timestamp_now` `ScalarFunction` in the
  analysis plan; execution's cached view plan is likewise unoptimized, and
  folding happens in each command's `optimize` (`lib.rs:62`) with that
  command's `query_execution_start_time`. Spark re-analyzes per
  `BatchTableWrite`, so each write has its own clock too. The design's
  per-command re-resolution preserves this; what it must not do is export a
  folded plan from analysis (the draft already says so). The clock
  characterization is therefore evidence for the direction, not a gap.
- **2.5 Authority dispatch fork for a captured helper (corrected after
  CF-0231).** The only step of `resolve_and_execute_plan_with_scope` that
  needs authority is `execute_logical_plan` (`lib.rs:60`). Checked at
  DataFusion 55.2.0 `context/mod.rs:686–770`: the eager arms are specific
  `DdlStatement` subvariants (`CreateExternalTable`, `CreateMemoryTable`,
  `CreateView`, `CreateCatalogSchema`, `CreateCatalog`, `DropTable`,
  `DropView`, `DropCatalogSchema`, `CreateFunction`, `DropFunction`; any other
  `Ddl` falls through to `DataFrame::new`) and specific `Statement`
  subvariants (`SetVariable`, `ResetVariable`, `Prepare`, `Execute`,
  `Deallocate`); every other plan, `Copy` included, takes the default
  `DataFrame::new(self.state(), plan)` with no eager effect. My earlier text
  named `Copy` as an authority candidate without checking; withdrawn.
  `optimize` exists on `ScopedSession`, `rewrite_streaming_plan` and
  `rename_physical_plan` are pure, and `Session::create_physical_plan` is
  implemented by `ScopedSession`, so a captured variant keeps the same shape
  with one fork keyed on those exact subvariants. The acceptance test is that
  the fork enumerates the `DdlStatement` and `Statement` subvariants
  explicitly (no default arm over them), so a new subvariant fails to compile
  rather than silently taking either path; the outer `LogicalPlan` default arm
  is then correct, because DataFusion's own default is the non-eager path.
- **2.6 Boundaries 1–7 are consistent with the capture review.** Finite
  owners and drained scopes (§1.4, §6 of the capture review), admit-before-
  planning with planning dropped before the guard (§1.6, §7), cluster
  unsupported (§3), typed primary separate from cleanup (§1.1). Nothing to
  add.

## 3. On the artifact characterization (`954e025c5`)

Test-only, parent `17b8ac254`, four cases: a temporary view's artifact holds
a mock provider lease until the artifact drops; materialized tables and
persisted views export schemas without a provider; a temporary view's clock
stays unfolded. These match `analysis.rs:174–186` exactly and give the
design its "definitions across owners, plans within owners" baseline. The
negative control (CF-0226, export every plan) failing three of four is the
right discriminator.

## 4. Not reviewed, open

- The publication DTO's exact API, and whether Spark's `isAnalyzed = true`
  publication (schema fixed at the analysis that published it) is to be
  matched or merely approximated by column metadata, is left to the design's
  unit 2.
- No live backend verdicts; no original Scala-suite execution; only source
  reading at the pins above.

## 5. Publication helper extraction (CF-0228): `5717f1c50` on `954e025c5`

Files: `resolver/command/catalog/view.rs` (−48 lines), new
`view/publication.rs` (`columns`, `set_namespace`), `view/publication/tests.rs`
(five tests). Compared line by line against the parent's
`resolve_catalog_create_view` (`view.rs:22–75` at `954e025c5`).

**Behaviour preserved.** `columns(schema, explicit, names)` is the former
`if let Some(columns)` block verbatim: the same count check with the same
`AnalysisError` text, the same `zip` over `schema.fields()`, the same
`data_type`/`nullable`/`comment` carry-over for explicit columns and
`comment: None` for inferred ones. The field-name lookup is passed as an
`FnOnce` closure (`|| Self::get_field_names(schema, state)`) and is called only
in the inferred branch, exactly where the parent called it; `get_field_names`
stays `pub(super)` in `resolver/schema.rs:102`, so the Spark field-naming rule
and its dependence on `PlanResolverState` remain native and outside the
helper. `set_namespace` is the former `retain`/`push`/`extend` sequence
verbatim. Call order in the resolver is unchanged: resolve input → columns →
`CatalogManager` lookup → namespace → `set_namespace` → `CreateViewOptions`
(`view.rs:18–37` at the candidate), so explicit-count validation still
precedes name resolution, which still precedes authority access.

**Tests.** Explicit columns keep types, nullability and comments without
calling the name callback; inferred columns use the callback's names and do
not inherit input comments; the count error wins over name resolution (the
callback is not called); a name-resolution failure keeps its original
`PlanError` variant; namespace properties replace the reserved keys and keep
unrelated properties in order. Each is a pure test of the helper; none
touches resolution or the catalog.

**Observations, no change requested.**

- The helper is a correct boundary for the design's unit 2: a future
  analysis-time publication caller must hand it the same resolved
  `DFSchema` and the same native name callback, which keeps Spark's
  field-name rule in the resolver rather than in a DTO.
- `zip` truncates silently if `names()` ever returned a different length than
  the schema has fields; that is the parent's behaviour too, and by
  construction the names come from the same schema. Not a fixture request.
- No public API, DTO or pipeline change; the design's publication
  representation remains a candidate, as stated.

## 6. View publication entry (CF-0234): `31dfb2cc9` on `5717f1c50`

Files: `resolver/command/catalog/view.rs` (+36/−5), tests
`resolver/query/view_publication_tests.rs` (three cases) and a module line in
`session_tests.rs`. Read only; the candidate was under Codex's gates at review
time.

**Shape.** One private `resolve_view_definition(definition, state) ->
(LogicalPlan, CreateViewOptions)` holds the former body of
`resolve_catalog_create_view` unchanged (resolve input → `publication::
columns` with the lazy native name callback → `CatalogManager` → namespace →
`publication::set_namespace` → options). The native entry now destructures
`(_input, options)` and builds the same `CatalogCommand::CreateView`; the
resolved input is bound (a named `_input`, not `_`) and so lives to the end of
the function as before. The new public `resolve_view_publication(definition)
-> (NamedPlan, CreateViewOptions)` starts a fresh `PlanResolverState`, calls
the shared function, then applies `preserve_order_sensitive_aggregate_sorts`
and `get_field_names(plan.schema(), &state)`, which is exactly the
`spec::Plan::Query` arm of `resolve_named_plan` (`resolver/plan.rs:21–25`). So
the returned plan is what a query resolution of the view body would have
produced, with the publication options derived from the same resolution and
the same naming state. `CreateViewOptions` is the representation: SQL
definition, columns, comment, flags, properties; no plan, no provider.

**Behaviour.** The native command path is unchanged in order and content.
The publication entry adds a public method to `PlanResolver`; it publishes
nothing and creates no owner. When explicit columns are given, `NamedPlan.
fields` carries the resolver's field names while `options.columns` carries
the explicit names, which is the native split as well (the plan keeps
resolver names; the catalog view gets the declared list). For pipelines, corrected
after CF-0237: `pipelines/sql.rs:321–333` wraps the input with
`with_view_columns(definition.columns.clone())` but does not clear
`definition.columns`, so explicit columns and comments stay `Some` and the
publication path carries them as the native path does; the two name lists
differ exactly when the user declared names, as in native SQL.

**Tests.** Explicit and inferred options are compared for equality against
the options the native `CatalogCommandNode::CreateView` carries, together with
field names, comment, flags and namespace properties; a bad column count
returns the same native error text from both entries with no publication, no
planner call and no registered resource. Adequate for a representation unit.

**Observations, no change requested.**

- The returned plan is analysis-local by contract only: nothing in the
  signature prevents a caller from retaining it. The design already says the
  `AnalyzedGraph` map must hold options, not plans; the consuming unit
  should drop the plan after schema use, and a test there that the map holds
  no `LogicalPlan` would pin it.
- `resolve_view_publication` is new public surface on `sail-plan`; the only
  intended caller is Connect's analysis. Worth a `pub(crate)`-or-`pub` decision
  when the Connect unit lands, since `sail-plan` is also consumed by
  `sail-session`.
- For the C5 reintegration, the `AnalyzedGraph` field this leads to is
  recorded in the manifest (CF-0234/0235); E′ must carry its producer through
  the loop rewrite.

## 7. Schema-only analysis export and captured view publication (CF-0237): `f0ac099e6` on `f4a6a541f`

Files: `pipelines/analysis.rs` (+29/−?), `pipelines/execution.rs` (+17),
`pipelines/materialize.rs` (+47/−?), `pipelines/analysis_artifact_tests.rs`.
Unit 2 (`f4a6a541f`, `sail_plan::prepare_catalog_command` sharing
`prepare_named_plan` with the ordinary path) read for context. Read only;
Codex's gates were pending at review time.

**Analysis.** `AnalyzedGraph` loses `relations: BTreeMap<Name, LogicalPlan>`
and gains `schemas: BTreeMap<Name, SchemaRef>` (every output's exported
Arrow schema, taken from the working set at return) and `publications:
BTreeMap<Name, CreateViewOptions>`. In the loop (`analysis.rs:112–150`) the
per-flow resolver is unchanged (`GraphScope` over the working `resolved`,
`plan_config_with_overrides(flow.sql_conf)`, `with_relation_scope`); for an
output with `view: Some(definition)` it now calls
`resolve_view_publication(definition.clone())`, stores the options and keeps
the plan for the existing `rename_logical_plan`/install path. The working
plans stay local to `analyze` and are converted to schemas on return, so no
`LogicalPlan` leaves analysis by type.

**Declared view columns.** `sql.rs:321–333` replaces `definition.input` with
`with_view_columns(input, columns.clone())` (a `ToDf` rename to the declared
names) and keeps `definition.columns`, so `resolve_view_publication` resolves
the renamed input: the plan's fields and the exported schema carry the
declared names, and `publication::columns`' explicit branch carries the
declared names and comments into the options. Downstream flows that read a
persisted view during analysis therefore see the same column names as
before (`views.feature:9–11` chains `pv1 → pv2 → pv3`; `:66` and `:97` cover
declared columns with comments). I checked this because the raw-input case
would have changed the exported names; it does not arise.

**Publication.** `materialize::views` no longer re-resolves: it takes the
options, forces `replace = true` and `if_not_exists = false` as before, and
runs `run_catalog_command(ctx, CatalogCommand::CreateView { view, options })`
→ `sail_plan::prepare_catalog_command` → `prepare_named_plan`, which is the
ordinary tail (`execute_logical_plan` → optimize → streaming rewrite →
physical → rename) over an `Extension(CatalogCommandNode)`. An `Extension`
takes DataFusion's default `DataFrame::new` arm, so no eager authority
dispatch is involved; `CatalogCommandNode::try_new(ctx, command)` only
derives the node schema (`catalog.rs:29–35`). Execution runs through the
same runner drain as every other command. The flow lookup that produced
`PIPELINE_DATASET_WITHOUT_FLOW` at publication is gone; that condition is
reported by analysis's phase 6 already.

**Execution.** `execution.rs` keeps its own `resolved` map and `GraphScope`
(`:72`); `materialize::tables` now reads `analyzed.schemas` where it read
`relations[..].schema().as_arrow()`. No remaining reference to `relations` in
`pipelines/` outside tests.

**Error timing (corrected after CF-0241).** Most persisted-view definition
failures already surfaced in analysis before this unit: the view's flow query
is the same `ToDf`-wrapped input, so unresolved inputs, incompatible view
reads and bad declared-column counts failed `resolve_named_plan` in the loop,
and `views.feature:113–130` already pins that a failing persisted view leaves
an otherwise valid materialized table unpublished. What this unit changes is
narrower: after a successful analysis there is no second resolution of the
definition or its sources at publication, demonstrated by the
source-unavailable publication test and its re-resolution control (5 pass /
1 fail). Spark's order (`DatasetManager.scala:204–233` runs an
already-analyzed command) is matched by both the old and the new code; the
new code additionally cannot observe a source that changed between analysis
and publication. No additional Python fixture is needed for the creation
invariant.

**Tests.** The artifact tests now require every provider `Weak` lease to be
released on return, temporary outputs included; a `Tail` over a temporary
mock table proves the working plan is still available to analysis helpers
(one scan) before schema-only export; the publication test makes the source
unavailable after analysis and publishes through the real planner, runner and
catalog with the captured SQL, types, nullability, comments and namespace and
zero scans; the clock test still finds `timestamp_now` unfolded before
export. These are the right discriminators for "definitions across owners,
plans within owners".

**Findings.** None requiring change. Two notes:

- The exported `schemas` are Arrow schemas (`plan.schema().as_arrow()`,
  which is the inner `Schema` with its own and its fields' metadata,
  `datafusion-common/src/dfschema.rs:142–144, 867–869`); what the boundary
  drops is DataFusion's qualifiers and functional dependencies, not Arrow
  metadata (corrected after CF-0241). Execution re-derives qualified schemas
  by re-reading outputs, so nothing consumes the dropped information today.
  An Arrow schema is still not replay identity, as the design says.
- For the C5 reintegration, E′'s loop must produce exactly these two maps and
  call `resolve_view_publication` for `view: Some` outputs; the manifest
  records this (Grust `7fa7d83b`).

## 8. Per-command upstream resolution (CF-0244): `f72120882` on `f0ac099e6`

Files: `pipelines/execution.rs` (−65), new `pipelines/reanalysis.rs`
(`inputs`, `resolve_inputs`), `pipelines/reanalysis/tests.rs` (three tests),
`pipelines/mod.rs`. Read only; Codex's gates were pending at review time.

**Closure rule.** `inputs(graph, analyzed, target)` walks
`analyzed.dependencies` from the target's inputs: a dependency that is a
temporary view or a persisted view (`output.view.is_some()`) is traversed
into its own dependencies; anything else (a table) is included and stops the
walk. That is Spark's `dfsInternal(stopAtMaterializationPoints = true)`
(`GraphOperations.scala:70–100`): tables stop, views of both kinds are
traversed, and the start node is excluded because the walk begins at the
target's inputs. `resolve_inputs` then resolves the required names in
`analyzed.order`: a view through its flow query under
`plan_config_with_overrides(flow.sql_conf)` with a `GraphScope` over the
command-local map (so its own upstream views and tables are already there),
a table through a plain `ReadNamedTable` under the **consuming command's**
`PlanConfig` with no relation scope. The map is returned to the caller,
used for one `run_command`, and dropped at the end of that iteration.

**Execution loop.** `execution.rs:36–59`: `materialize::tables` →
`materialize::views` → for each output in `analyzed.order`, skip persisted
views, temporary views and anything `selection.runs` excludes; otherwise
build the command-local map, a `GraphScope::new(graph, &resolved, flow)` and
run the write. The run-wide `resolved` map, the lazy `read_output`, and the
`Selection::required` gate are gone from the loop (`required` is still
computed; Codex plans its removal separately). Table reads happen when the
consuming command runs, after upstream writes by topological order, as
before.

**Behaviour changes, all toward Spark.**

- A persisted view read by a downstream command is now resolved from its
  defining flow under its own namespace and config, not read from the
  catalog's published copy. Spark traverses persisted views in
  `reanalyzeFlow`; §2.2 of this review asked for exactly this choice.
- A table read uses the consuming command's `PlanConfig`
  (`read_case_sensitive` in the test) instead of the session's; §2.3.
- Providers created for one command's inputs are released when its map
  drops, as far as the command-local map and the tests' mock factory leases
  show (all three tests assert every `Weak` lease is gone). Qualified per
  CF-0247: session-level and factory caches and SDK task settlement are not
  audited by this unit, so "no provider survives across commands" holds for
  the plan map, not yet for every store an owned-store activation would
  need. The execution-cache owner hazard from CF-0222 is removed at its
  source within that boundary.
- A graph output missing from the command-local map is an
  `UnresolvedRelation` from `GraphScope::resolve` (`analysis.rs:48–68`),
  never a silent catalog read, so a wrong closure fails loudly.

**Not changed, by design.** View bodies are resolved under their own flow
config; upstream→consumer conf fusion and read-order metadata are the next
unit (§2.1). Materialize-tables/views order and the unsupported-mode guard
are unchanged. Namespace qualification and field renaming are the native
`GraphScope::qualify` and `rename_logical_plan` as before.

**Tests.** Separate commands re-resolve shared views through fresh factory
calls with per-command lease release and no unrelated inputs; a committed
table stops the walk (no producer recomputation) and is read with the
consuming command's case sensitivity; a graph persisted view is re-resolved
under `view_db`/`caseSensitive=true` from a consumer in `test_db`/`false`,
without a published catalog view existing. Real resolver and memory catalog,
mock provider factories, no scans. Adequate for the closure and lifetime
claims.

**Findings.** None requiring change. Notes:

- Repeated metadata work per command is now the rule (each command re-reads
  every upstream table's metadata and re-resolves every upstream view); the
  design accepts this and it is Spark's cost model too.
- `PIPELINE_DATASET_WITHOUT_FLOW` inside `resolve_inputs` is an internal
  guard; phase 6 of analysis makes it unreachable for a valid analyzed
  graph.
- For C5: E′ touches `execution.rs` only at `GraphScope::new` (already the
  root's form); F–K do not reach the execution loop. Recorded in the
  manifest (Grust `8900b491`).

## 9. Configuration phases: the proposed split and reusable Sail machinery (CF-0254, CF-0256)

Pins: Spark `617618396` (`FlowAnalysis.scala:90–140`, `CoreDataflowNodeProcessor.scala:118–190`,
`DataflowGraph.scala:149–168`, `QueryPlan.scala:609–627`); Sail `163b2fb52`
(`pipelines/streaming/binding.rs`, `pipelines/analysis.rs`, `pipelines/graph.rs:232–233`,
`resolver/query/{project,filter,join,cte}.rs`, `resolver/state.rs`,
`resolver/expression/wildcard.rs`). Codex's `FLOW-CONFIGURATION-DESIGN.md`
(Grust `4cc4356f`) read. Read only.

### 9.1 What Spark actually does, phase by phase

1. **Ordered input binding (corrected after CF-0259).** `FlowAnalysis.analyze`
   first runs `CTESubstitution(plan)`. The source comment speaks of
   inlining, but on a plain query the rule runs with `forceInline = false`
   and yields `WithCTE(plan, cteDefs)` whose `children` are `cteDefs :+ plan`
   (`cteOperators.scala:239–245`, verified at the pin; the rule itself is not
   in the pinned checkout's tree), so the pre-order visit below binds every
   CTE definition's reads first, in definition order, used or not, and then
   the main plan's reads. Codex's twelve-case probe confirms it:
   `cte_unused_definition` reaches `DUPLICATE_FLOW_SQL_CONF` although the
   CTE is unused, and `cte_nested_shadow_unused_outer` fails
   `UNRESOLVED_COLUMN` with the unused outer CTE's conf bound
   (`/tmp/sail-sdp-config-cte-reference/observations.json`, Grust
   `evidence/flow-config-cte-reference`). It then runs `transformWithSubqueries` over `UnresolvedRelation`, which is
   `transformDownWithSubqueries`: pre-order, the node first, then the
   subqueries inside its expressions, then its children left to right
   (`QueryPlan.scala:609–627`). Each read calls `readGraphInput`, which loads
   the input and, for a `Flow` input, writes that flow's **resolved** conf
   into the private analysis conf (`FlowAnalysis.scala:256–260`); a table
   writes nothing. The private conf after the last read is the first-pass
   conf for the whole query.
2. **First semantic analysis** of the substituted plan under that conf
   (`Dataset.ofRows`), which may fail (`UNRESOLVED_COLUMN` in the probes).
3. **Merge and validation** (`attemptResolveFlow`): declared map plus the
   resolved maps of the `Flow` inputs actually used; any key with distinct
   values is `DUPLICATE_FLOW_SQL_CONF`; the union is the accepted map; if it
   differs from the declared map the flow function runs again under it, and
   `ResolvedFlow.sqlConf` is the map of that last call.
4. **Command reanalysis.** `reanalyzeFlow` builds the table-bounded subgraph
   and calls `subgraph.resolve()`, so phases 1–3 run again for every flow in
   the subgraph (each view under its own fusion, the consumer under its),
   and `BatchTableWrite` wraps the write in the consumer's accepted map.

### 9.2 Assessment of the proposed split

The four-phase split in CF-0254 matches 9.1. Three refinements:

- **Phase 4 is a re-run of phases 1–3 over the closure, not "resolve under
  the accepted map".** Spark re-derives each flow's conf during reanalysis.
  Reusing the accepted maps exported from analysis is a candidate
  optimization, not shown equivalent: unchanged definitions do not by
  themselves prove unchanged binding, dependencies or provider observations
  at command time (CF-0259). Keep actual command reanalysis with table stops
  until that equivalence is qualified.
- **Accepted maps are per flow, not per output.** A target with several
  flows has several accepted maps; the design already warns against an
  output-keyed collapse. The publication export (§7) is output-keyed, so the
  conf export must be a separate flow-keyed map.
- **Phase 1 must be a non-semantic traversal.** Sail's resolver resolves
  inputs before expressions (`project.rs:33→37`, `filter.rs:19→23`,
  `join.rs:65–66→108`), post-order where Catalyst is pre-order; that is why a
  semantic first pass cannot supply the order and why the nested-projection
  and scalar-subquery cases fail early today. The design's step 2 says this;
  the traversal below is the candidate.

### 9.3 Reusable Sail machinery

- **`streaming/binding.rs` `Walker` (my unit 4 component).** Exhaustive over
  `spec::QueryNode` and `spec::Expr`, including `InSubquery`, `ScalarSubquery`
  and `Exists` as plans, and already in Catalyst's order within a node:
  expressions (with their subqueries) before inputs for `Filter`, `Project`,
  `Aggregate`, `Sort`, `Limit`, `WithColumns`, `LateralView`, `Pivot`,
  `Unpivot` and the grouped-map nodes; `Join`: condition, left, right;
  `SetOperation`: left, right (`binding.rs` `walk`). It qualifies names
  through the flow's namespace (`GraphScope::qualify`) and records
  classification. Gaps for the fusion seam, in order of importance:
  1. `ReadSet` is three `BTreeSet`s, so encounter order and repetition are
     lost; the shared traversal Codex plans (CF-0256 unit 2) should expose an
     ordered visit of every read, repeats included.
  2. `WithCtes` walks the kept (last-wins) definitions once at the definition
     site, then the body, mirroring `resolve_query_with_ctes`
     (`cte.rs:96–129`). Corrected after CF-0259: this is also Spark's order,
     because `WithCTE.children = cteDefs :+ plan` and unused definitions are
     still bound (9.1). My earlier recommendation of reference-site emission
     with no emission for unused CTEs was wrong and is withdrawn; the
     definition-site order is reusable as is. Open for Codex's probes:
     whether Spark binds a _shadowed_ (duplicate-name) definition that Sail
     drops, and the case-insensitive shadowing case the probe lists
     (`cte_case_insensitive_shadow`), before the keep-last rule is declared
     parity.
  3. `UnresolvedStar` is a leaf while `WildcardOptions.replace_columns`
     carries expressions the native resolver resolves
     (`wildcard.rs:248–254`); CF-0256 unit 1 fixes this (my miss).
  4. `WithRelations` (Connect plan-id references) walks references before the
     root; Catalyst substitutes plan-id-tagged subplans and propagates
     `PLAN_ID_TAG` (`FlowAnalysis.scala:121–127`). Preserve the same visit so
     Connect DataFrame flows bind in the same order as SQL ones.
- **`GraphScope` as `RelationScope`** records reads during semantic
  resolution into a set (`analysis.rs:47–68`); keep it for dependency edges
  and refusal of unknown outputs, not for order.
- **`PlanResolverState`** holds the resolver's CTE semantics
  (`enter_cte_scope`, `insert_cte` with `CteKind::Definition`) and the plan-id
  to field registration (`register_plan_id_for_field`); the binding seam
  should reuse the keep-last and recursive-scope rules from it and change
  only the emission point.
- **`PlanConfig` is immutable per resolver**, which is the right primitive
  for the two passes: first pass under `plan_config_with_overrides(declared
⊕ last-writer overrides from the ordered reads)`, second pass under the
  accepted union. `graph.rs:232–233` already folds pipeline defaults under
  flow confs (`sql_conf.extend(definition.sql_conf)`), matching
  `defaultSqlConf ++ flowDef.sqlConf`.
- **Merge/validation** has no Sail counterpart yet; the design's pure module
  with per-flow provenance is the right shape, and `DUPLICATE_FLOW_SQL_CONF`'s
  parameter rule (names sorted by value, first conflicting key found in a
  grouped map, not deterministic across keys) should be copied literally.

### 9.4 What this does not settle

Codex's thirteen-case differential (3 match, 10 differ) is the acceptance
baseline; the CTE, default-overlay and unused-input probes it lists are
still needed before the seam is activated, and nothing here changes the
bounded lowerer, which refuses helper-executing constructs pre-resolution
and does not fuse confs.

## 10. Shared expression-subquery traversal (CF-0261): `7a50f2875` on `744b16867`

Files: new `sail-common/src/spec/subqueries.rs` (`Expr::visit_subqueries`,
`Window::visit_subqueries`, `visit_exprs`, `visit_sort_orders`),
`spec/subquery_tests.rs` (four tests), `spec/mod.rs`, and
`pipelines/streaming/binding.rs` (−137 lines). Read only.

**Traversal.** `Expr::visit_subqueries<'a, E>(&'a self, visitor: &mut impl
FnMut(&'a QueryPlan) -> Result<(), E>)` matches every `spec::Expr` variant
with no default arm: leaves return `Ok`, `UnresolvedStar` walks
`replace_columns[*].expression` (unit 1's fix carried over), functions walk
positional then named arguments then `filter` then `order_by`, `Window`
walks the function then the window's cluster/partition/order expressions
and the frame's `Preceding`/`Following`/`Value` boundaries, `InSubquery`
walks the expression then calls the visitor, `ScalarSubquery` and `Exists`
call the visitor, and `Subquery { in_subquery_values }` (a Connect plan-ID
reference) walks only its values and leaves the referenced plan to the
caller, as the Rustdoc says. Order is field order and list order; repeats
are preserved; the first callback error stops the walk unchanged. The only
`_ => {}` is over `WindowFrameBoundary`'s three non-expression kinds
(`CurrentRow`, `UnboundedPreceding`, `UnboundedFollowing`,
`spec/expression.rs:288–296`); enumerating them would make a future
expression-bearing boundary a compile error instead of a silent skip. Minor.

**Reimport.** The binder's `expr` and `window` now reduce to
`expr.visit_subqueries(&mut |query| self.walk(query, cte_scope))` (and the
window equivalent), so every embedded query is still walked as a plan under
the enclosing CTE scope and every refusal inside it (`Tail`, `Stat*`, pivot
inference, dynamic UDTF, unbound or mixed-mode reads) is reached as before.
No classification semantics moved; 137 lines of duplicated expression
matching left `binding.rs`.

**Tests.** Order, repetition and pointer identity of visited queries; first
error stops and is returned by identity; wildcard replacements and window
bounds are expression children (visited in reverse-numbered order as
constructed); query contents and plan-ID references stay the caller's.
Codex's reversal control (two failing) confirms the order and error tests
bite.

**Findings.** None requiring change. Two notes for the seam this serves:

- The traversal gives expression-embedded queries in Catalyst's within-node
  order; the node-level order (expressions before inputs, `Join` condition
  → left → right, `WithCtes` definitions then body) remains in the binder's
  `walk`, so the fusion seam's ordered visitor must wrap both, not only this
  helper.
- CTE name matching is a parity point to settle before the seam declares
  Spark order: Sail keys CTEs by exact `TableReference` and dedupes by exact
  `spec::Identifier` (`resolver/state.rs:100`, `query/cte.rs:100–110`),
  while Spark's `CTESubstitution` matches with `conf.resolver`, which is
  case-insensitive unless `spark.sql.caseSensitive` is set, and checks name
  conflicts (`CTESubstitution.scala`, pinned object `617618396`,
  `assertNoNameConflictsInCTE`; Codex's `cte_case_insensitive_shadow` case).
  As Codex says, this is a general resolver parity concern, not something to
  copy silently into the new phase.
