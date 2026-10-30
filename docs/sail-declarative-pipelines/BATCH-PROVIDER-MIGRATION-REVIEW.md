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

- **2.1 Fusion precedence is "upstream view's flow overwrites consumer,
  in input-read order", and Sail does neither today.** Because the
  consumer's confs are set before any input is read and each upstream
  `Flow` input's confs are written afterwards by `setConfString`, a key set
  on both takes the upstream value; two upstream views conflicting on a key
  resolve to whichever is read last. Sail resolves a consumer under its own
  `sql_conf` only, and resolves each temporary view's body under the view's
  own `sql_conf` before splicing the plan (`execution.rs:69–84`,
  `analysis.rs:124`). So a conf set only on the consumer does not reach the
  view body in Sail but does in Spark, and a conf set only on the view does
  not reach the consumer's analysis in Sail but does in Spark. The draft's
  "preserve the ordering/precedence of that fusion" and its direction text
  "resolve required temporary views … preserving each definition's own SQL
  config" describe two different behaviours; the second is Sail's current
  one. Pick one explicitly in the design (the Spark rule is the one above)
  and make the parity check a fixture with a conf that changes analysis
  visibly, for example `spark.sql.caseSensitive` on view and consumer in
  each combination.
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
