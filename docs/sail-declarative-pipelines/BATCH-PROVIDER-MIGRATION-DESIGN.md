# Batch provider ownership and caller migration

Status: active Astra design checkpoint, announced before source work. Source
Sail `17b8ac254139e9213327dfcc7fc8badb4fdd27b2`, Spark4.2.1, DataFusion55.2.0.
This continues [capture transfer](CAPTURE-EXECUTION-TRANSFER-DESIGN.md) and
[pre-planning ownership](PRE-PLANNING-OWNERSHIP-DESIGN.md). It selects no public
activation, new catalog contract, Delta change, cluster transport or CDC effects.

## Historical boundary at Sail17b8ac254 (before the publication artifact)

| Phase | Current behavior | Ownership implication |
| --- | --- | --- |
| Graph analysis | Resolves flow specs in dependency order; full plans for pipeline temporary views, EmptyRelation/schema for every other output | Analysis-local providers can remain in temporary-view artifacts; table/persisted-view artifacts contain schemas |
| Table materialization | Consumes analyzed schemas; checks catalog, truncates/creates/alters selected tables before batch flow writes | Catalog calls precede individual run_command admission today; preserve phase order and failure effects |
| Persisted-view publication | Re-resolves the definition against analyzed.relations, extracts columns, emits CatalogCommand::CreateView with SQL and metadata | No resolved input/provider is stored in CreateViewOptions; schema resolution may itself run helper queries |
| Batch execution | Starts a fresh resolved map; resolves temporary-view definitions, lazily reads catalog outputs and caches plans | This cache is distinct from analyzed.relations and can retain providers across commands |
| run_command | Resolves/executes DataFrame authority dispatch, optimizes/rewrites/plans, then calls runner.execute | Admission is currently too late for resolver/provider/physical-planning work |

These distinctions correct an overbroad inference in the earlier Fable review:
we have not observed an analysis-time Delta provider being physically scanned by
batch execution merely because analyzed.relations is passed to materialize.views.
Only temporary views keep full analysis plans; persisted views are schema
placeholders, and analysis rejects persisted views referring to pipeline temporary
views. The CreateView resolver stores original SQL, columns, comments, replace/
if-not-exists and namespace properties, discarding its resolved query input.
Execution creates its own map. Do not label metadata derivation as a table scan.

The general Delta hazard remains: a DeltaTableSource retains its creating Session's
log store, later log/CDF/commit paths use it, and data scans acquire a planning
Session store. Current plain store Arcs are not revoked by closing a scope. The
execution map's cached temporary views and read_output plans therefore cannot be
carried unchanged between future fresh command owners. An owner-aware router
would make that lineage split visible; fresh admission alone would not fix it.

Normal graph analysis calls PlanResolver::resolve_named_plan without the final
DataFrame optimizer. Do not infer that every current_timestamp is folded into an
analysis-time literal on this path. TimestampNow folds when simplification supplies
query_execution_start_time; resolution-time helper queries can optimize their
own plans. Catalog-string folding separately uses with_current_time, independent
of the captured Session clock (Fable CF-0221). Arbitrary custom rules/providers can
also introduce their own dependencies; a normal-path probe cannot qualify them.

## Spark reference observations

Pinned Spark source617618396087429b5627a86ce933bb0f5d6645cb supports a
consumer-local reanalysis boundary. BatchTableWrite.executeInternal calls
graph.reanalyzeFlow(flow).df before its append write (FlowExecution.scala256–294).
DataflowGraph.reanalyzeFlow149–168 collects the upstream closure while stopping
at tables (views, persisted or temporary, are traversed), creates a new subgraph and resolves the requested flow.
This is stronger evidence than assuming Sail's current run-wide plan cache is a
required Spark invariant. Runtime result/error comparisons are still required.

DatasetManager.materializeView205–234 builds CreateViewCommand from the already
analyzed flow.df.logicalPlan, original SQL/properties/comments, isAnalyzed=true,
and the flow's catalog/database context. That supports deriving publication
metadata during analysis rather than re-running a schema-dependent definition
after its provider owner has closed. Do not infer that every Catalyst validation
can be replaced by a schema copy; reproduce native Sail/Spark field and error rules.

FlowAnalysisContext carries a private per-flow SQLConf; FlowAnalysis.readGraphInput
also fuses a referenced Flow's sqlConf into the consuming context. Preserve the
ordering/precedence of that fusion when resolving a command's temporary-view
closure. Sail currently derives PlanConfig from each flow's sql_conf; this is
separate from DataFusion SessionConfig captured by the preparation. Map actual
phase consumers before claiming complete per-flow configuration isolation. The
new APIs alone do not atomically capture both authority stores or merge all native
configuration options. No shared-session mutation is selected to fill that gap.

## Characterization evidence

[Test-only Sail954e025c5](evidence/batch-analysis-artifacts/README.md) resolves
actual registered graph SQL with a mock provider lease and zero scan callbacks.
Temporary analysis plans retain the provider until artifact drop; materialized
and persisted outputs release it and export schema-only plans. Normal temporary
current_timestamp remains an unresolved ScalarFunction. Exact fmt/strict Clippy/
139 Connect libraries pass under explicit PySpark4.2.1 environment. Same-source/
same-binary environment control retains the initial137pass/2ORCfail and corrected
139pass. An unchanged-test all-plan-export control gives1pass/3fail.

[Source packet](evidence/batch-provider-migration/README.md) pins Sail/Spark excerpts
and the revised Fable77ac6eda review retracting the earlier batch inference and
withdrawing the unreachable child-native-analyzer fixture request. These checks
qualify artifact shape and the source trace, not real backend lifetime/effects.

## Required boundaries

1. Keep finite analysis, bounded-history run control, and fresh finite command/
   attempt owners distinct. No drained scope is reopened, no long-run scope
   accumulates every finished I/O record, and no analysis plan becomes a substitute
   for a later owner's provider bindings.
2. Admit before provider/resolver/physical-planning work. Run borrowed planning on
   the caller, select against latched cancellation, drop planning before releasing
   its guard, and await independent cleanup when a response can still be delivered.
3. Use with_scoped_query_session for newly captured callers. Generic mode deliberately
   keeps native analysis on authority and is not the migration target. Catalog
   manager access and session commands retain authority until their own owned-call
   seam is implemented. Do not swap shared runtime or copy operation state back.
4. Preserve analysis/selection, materialize-tables, publish-views, then batch-flow
   order. Preserve upstream-table reads after committed writes, excluded-table
   view publication, original SQL, namespace, columns/comments and error timing.
5. Preserve full schema semantics and dependency edges. A table reference means the
   committed output, not producer recomputation. A graph-local view is an expression
   definition. Traverse temporary and persisted view definitions within the
   consuming command, stopping at tables, with the Spark configuration fusion
   and qualified namespace rules below.
6. Keep typed primary and cleanup outcomes independently available. Cancellation
   or drained resources do not establish target rollback/commit confirmation.
7. Cluster capture remains unsupported. Driver Session/registry Arcs are not worker
   transport. No local-only route may silently promise whole-cluster ownership.

## Direction for review: definitions across owners, plans within owners

An analysis working set may contain full plans while its finite owner is active:
resolving later definitions can require actual temporary-view expressions, including
resolution-time helper execution. Replacing that working set with EmptyRelation
schemas before analysis finishes can change dynamic schema inference. Keep it
local to analysis and dispose it before ending that owner.

The exported analysis result should carry dependency/order/schema/publication
metadata, not executable providers or folded expressions from analysis. Capture
owned schema/field metadata explicitly; an Arrow schema alone is not replay identity
or proof that backend metadata is pinned. Do not serialize providers into the
controller or retain an analysis scope indefinitely to keep them valid.

For persisted-view publication, do not blindly replace its input bindings with
schema-only plans and re-run the entire resolver: dynamic schema helpers can
execute during resolution. Prefer deriving the exact publication options while
analysis owns its input, then carrying only the same CatalogCommand::CreateView
metadata to its publication command. Reuse the native resolver's column/name/
comment/namespace rules through a focused helper rather than a second implementation.
Check refresh-time config/schema behavior against Spark before selecting this API.
The representation is now the existing CreateViewOptions, produced by native
resolve_view_publication and carried separately from schemas. No new catalog DTO
is introduced. The implemented publication unit below uses this path.

For an execution command, build a fresh relation scope from graph/flow specs and
committed table names. Select Spark's rule explicitly: traverse both temporary
and graph-local persisted view definitions, stopping at tables; do not substitute
a catalog read for a graph-local persisted view's flow. Persisted-view publication
still occurs as its own phase, independently of how consumers resolve that flow.
External catalog views keep the catalog resolver's namespace semantics.

Resolve table reads only after upstream writes, under the consuming command's
owner and effective configuration, rather than the session-only plan_config used
by read_output today. Cache plans within this command, then discard them. Keep
definitions/committed identities and bounded progress in run control.

Configuration target: start with the consumer's flow settings; reading an upstream
Flow fuses that flow's settings by overwrite, in input-read order, matching Spark's
readGraphInput/setConfString. This is a parity change from Sail's current separate
view-body and consumer settings, not a property to claim already preserved. Fixture
both caseSensitive combinations and conflicting settings on multiple/repeated
view reads. BTreeSet dependency edges do not preserve read order: capture an ordered
trace as well as the deduplicated dependency graph before selecting an algorithm.
Do not infer that a topological traversal or merging sorted names gives the same
precedence. Resolve exact producer/consumer analysis phases against those fixtures;
no configuration fusion implementation is selected in this refactor.

Do not inline upstream table producer queries to avoid reading a table: that changes
nondeterministic results and recomputes already committed effects. Do not treat
persisted views and temporary views as interchangeable. Existing CTE precedence,
shadowing, qualified names and schema/field renaming must remain unchanged.

Re-resolution can incur repeated metadata work and can observe changing external
metadata. Avoid introducing a new cross-command snapshot guarantee by accident.
Where Spark or a later streaming replay contract requires pinned identity, keep
explicit version/identity descriptors and rebind under the new owner with that
identity. Delta re-resolution alone does not establish durable replay or atomic CDC.

## Physical preparation and command authority

The legacy Sail helper intentionally invokes SessionContext::execute_logical_plan
before optimization and streaming rewrite. DataFusion dispatch there can execute
native DDL, SET/RESET, prepared statements and other authority operations eagerly.
A captured helper cannot replace it with Session::create_physical_plan for every
logical plan and claim identical behavior.

Trace the actual SDP command set (CreateTable/AlterTable/Truncate/WriteTo/CreateView)
to Sail catalog/barrier/row-level nodes. Share optimizer, streaming rewrite, field
renaming and diagnostics where possible, while retaining explicit authority
handling for logical statements that require it. DataFusion55.2.0 Copy follows its generic DataFrame::new branch; it is not an
eager authority arm. Ddl and Statement also need their subvariant behavior traced.
Use an exhaustive match over LogicalPlan variants for authority/captured dispatch,
so added variants require an explicit decision. Unsupported branches must report
unsupported rather than silently run a different captured/legacy path. Admission
must precede eager effects; any required authority mutation precedes the snapshot
that is promised for subsequent query planning.

A first caller can use capture(None) to validate config/owner transfer, but that
alone does not supervise plain object stores, catalog SDK calls or custom callbacks.
Do not call such an intermediate state complete provider ownership. A supplied
registry must be complete or explicitly composed with parent resolution, because
capture replaces it wholesale. Provider-bound stores and catalog calls need their
own admitted operations and error/settlement policy before the guarantee expands.

## Review response CF-0227

Fable7b240a4e confirms the source trace and identifies the previously ambiguous
view/config rules. The target is Spark parity: table-only stopping points,
graph-local persisted-view reanalysis, upstream flow settings overwriting the
consumer in input-read order, and table reads under command configuration. The
current helper extraction preserves Sail behavior; those semantic changes need
separate observable fixtures and commits. Normal per-command clock folding already
matches this direction; avoid exporting folded plans rather than inventing an
analysis-time clock defect. Publication metadata must match isAnalyzed=true semantics. The implemented unit
now checks captured schema/columns/SQL/namespace and source unavailability; other
Catalyst/backend validation and runtime parity requirements remain open.

## First preparatory implementation

Sail5717f1c50 extracts private pure column/namespace conversion from the native
CreateView resolver, preserving resolution/validation/name/authority order.
Five direct tests and exact fmt/strict Clippy/83+139 libraries pass. A fresh
combined CLI run on5717f1c50 passes300 public+67 upstream Python cases with
Spark4.2.1; rebuilt binary pinned, owned server stopped. See the
[metadata packet](evidence/view-publication-metadata/README.md). No public API,
publication DTO, pipeline artifact or semantic configuration change is selected
by this extraction. Deriving and carrying already-analyzed publication metadata is implemented below.

## Implemented analysis-time publication

[Three units](evidence/analysis-time-view-publication/README.md) expose native
resolved-plan/publication options (31dfb2cc9), shared catalog-command preparation
(f4a6a541f), then pipeline schema/publication-only export (f0ac099e6). Full plans
stay in analysis's working set until helper work/schema derivation ends. The
returned AnalyzedGraph has schemas: BTreeMap<Name,SchemaRef> and publications:
BTreeMap<Name,CreateViewOptions>, with no executable plan field. All mock provider
leases release on return, including temporary outputs. Arrow metadata is retained;
DataFusion qualifiers/functional dependencies are not carried as replay identity.

Persisted views are resolved once in analysis. Publication consumes the native
options through ordinary Sail planning and runner execution, without resolving the
query again; source-unavailable publication succeeds with captured metadata and
zero scans. The unchanged re-resolution control gives5pass/1fail. A Tail count
still uses the working plan during analysis, and a clock stays unfolded before
schema export. Final86+143 libraries/fmt/strict Clippy and fresh300+67 public CLI
regression pass on Spark4.2.1, owned server stopped. This does not wire captured
owners or fix execution's separate provider-plan cache/config fusion.

Many invalid view definitions already failed in initial analysis before this
change; the new guarantee is absence of a second resolution after successful
analysis. Existing private-view failure coverage asserts both the view and a valid
materialized table are not published. Do not overstate changed error timing or
infer all Catalyst/backend checks from metadata capture. Fable review and precision
response are retained in the packet.

## Implemented per-command input resolution

[f72120882 plus cleanup163b2fb52](evidence/command-input-reanalysis/README.md)
replace execution's run-wide provider map with an upstream map resolved for each
selected table command. Both graph-local view kinds are traversed through their
flow definitions; only tables stop the walk and are read under the consuming
command's configuration after upstream writes. No eager post-write read caches an
unused target provider. The obsolete run-wide Selection.required/with_dependencies
calculation is removed; refresh/reset selection and validation remain unchanged.

Three factory/Weak-lease tests pin fresh per-command view plans, table stopping
with command read-case configuration, and persisted-view definition namespace
without catalog publication. Mock leases release with each map; SDK tasks and
factory/session caches are not qualified. Two controls independently give2pass/
1fail for traversing behind a table and reading under session config. Both exact
fmt/strict Clippy/146 libraries and a fresh combined300+67 CLI regression pass,
Spark4.2.1, rebuilt binary pinned and owned server stopped.

View bodies retain their current flow-specific config in this unit. Upstream→
consumer configuration fusion and ordered read handling still need their own
reference fixtures/design. No early planning admission, captured Session or owned
store activation follows from removing the plan cache.

## Incremental review units and evidence

1. Characterize analysis artifact/provider retention and unresolved clocks; archive
   source traces distinguishing analysis, publication and execution caches.
2. Implemented31dfb2cc9/f4a6a541f/f0ac099e6: reuse CreateViewOptions and native
   metadata rules, prepare catalog commands through ordinary stages, export only
   schemas/publications and drop provider plans. Preserve the exact evidence above;
   further Catalyst/backend parity is not implied by these checked properties.
3. Per-command resolution/cache removal and selection cleanup are implemented at
   f72120882/163b2fb52 as above. Next qualify full input-read-order configuration
   fusion, nondeterministic temporary/table behavior and backend identity before
   ownership activation; current immutable per-flow settings are not full parity.
4. Add captured physical preparation preserving Sail's optimizer/rewrite/rename/
   authority behavior, and qualify each actual SDP command shape. Keep legacy tests.
5. Wire one admitted local command path through resolver/planner/execution and
   primary+cleanup observation. Test held planning/provider I/O, stop/RPC loss,
   unpolled futures/streams, cleanup error/unknown effects and fresh next owners.
6. Qualify catalog/store/provider routing and cluster capability separately, then
   activate other callers. Gate each combined source parent; rebuild public CLI
   selections and run original Spark fixtures appropriate to the change.

The above does not replace remaining ORC writer, Python analysis, durable streaming/
Iggy/CDC, catalog coverage or full Spark4.2.1 SDP acceptance. Local unit tests and
source traces are evidence for their stated scope only. Only explicit units above
are qualified. Remaining ownership, configuration fusion and captured physical
preparation are not activated.
