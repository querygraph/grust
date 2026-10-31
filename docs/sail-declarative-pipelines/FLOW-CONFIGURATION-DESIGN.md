# Flow configuration phases for Spark 4.2.1 parity

Status: the selected implementation uses an ordered graph-input trace with the
existing resolver. Native source-case separation (`b4d83ef72`), pure raw-map
arithmetic (`349771bd9`) and input tracing (`fa78d067c`) are integrated separately.
Runtime activation `1bc9d1562` carries accepted settings through analysis
and per-command reanalysis; inspect its [exact gates and limitations](evidence/flow-config-runtime/README.md).
No opaque provider slot or captured physical-preparation activation is included.

The identical thirteen public probes now all match error-condition/success-row
outcomes, against the historical three-of-thirteen
[baseline](evidence/flow-config-fusion-reference/README.md) and eight-of-thirteen
runtime integration. General resolver diagnostics at `7b5667c1f` close the five
unresolved-column differences, with twelve additional ordinary SQL oracles;
[exact metadata and message comparisons](evidence/unresolved-column-errors/README.md)
state their boundary. Duplicate-flow parameter/provenance parity and full original
Scala acceptance are not established by this comparison. The
[twelve CTE/default oracles](evidence/flow-config-cte-reference/README.md) and
[metadata oracle](evidence/flow-config-external-read-reference/README.md) remain
requirements, not claims of full Sail parity. [Shared listing validation](evidence/parquet-column-validation/README.md)
at `005fcb078` now passes the five session-false duplicate checks and both direct
controls using the original Spark bytes, plus six partition-schema/row probes.
The two session-true/private-false cases reach ambiguity but lack its structured
condition. Original Scala-suite execution, configured dynamic/opaque-reference
binding and broader per-format support remain.
The [batch ownership design](BATCH-PROVIDER-MIGRATION-DESIGN.md) continues to govern
admission, provider lifetime and per-command plan maps.

## Required behavior

Pipeline defaults are overlaid by explicit flow settings at registration.
The resulting map is the flow's declared configuration. This overlay itself is
not a duplicate-setting error. Runtime session defaults remain a separate base.

For each attempt to resolve a flow, Spark first calls its flow function under the
declared map. FlowAnalysis clones the session SQLConf, applies that map to the
private clone, substitutes graph inputs, then invokes Catalyst analysis. Each
referenced upstream Flow contributes its **resolved** configuration at the point
readGraphInput loads it; a table contributes no flow settings. Repeated reads
therefore matter during this substitution pass. These changes affect the private
analysis configuration; they do not mutate the shared run session.

Only after this first semantic analysis succeeds does FlowResolver collect the
flow's declared map and the resolved configurations of its actual Flow inputs.
A key with distinct values is DUPLICATE_FLOW_SQL_CONF. Its parameters include key,
datasetName, flowName1 and flowName2; source sorts contributing flows by value to
choose the two names. Do not promise deterministic choice of conflicting key when
multiple keys conflict: the source searches a grouped map. Identical values merge.
Tables stop this merge. A view's resolved map includes its own accepted upstream
union, so later consumers inherit that union transitively.

If the compatible merged map differs from the declared map, Spark invokes the
flow function again under that union. The resolved flow stores the configuration
passed to this second call. The first call's private overwrites are not themselves
the exported map. A dependency set suffices for successful union membership, but
cannot reproduce the earlier pass's errors or traversal order.

BatchTableWrite uses that resolved map around command reanalysis and append.
Reanalysis constructs a graph containing the selected target and upstream views,
stopping at tables. Its view bodies and table reads must respect that command's
base settings and each flow's overrides without restoring a run-wide provider
cache. Already captured publication metadata remains independent of this command
reanalysis. Early planning admission and backend ownership remain separate work.

## Evidence that rules out shortcuts

With z_sensitive declaring caseSensitive=true and a_insensitive declaring false,
SELECT Foo from z_sensitive then a_insensitive reaches a duplicate-setting error.
Reversing the SQL reads fails unresolved-column analysis before conflict checking.
The output column is lower-case foo in both inputs' definitions. Both names,
queries, configs, events and errors are retained in the packet.

A consumer declaring true and reading a false view reaches a conflict; the
upstream overwrite does not authorize successful last-wins execution. A consumer
reading an otherwise unconfigured intermediate view inherits the root view's
accepted true setting. Reading a table produced under true instead accepts Foo
under the consumer's false default. Equal values and disjoint keys both execute.

The nested-projection case is especially restrictive: the inner SELECT Foo reads
the true view, followed by a false view in the outer query. Spark reaches conflict
validation. A recursive resolver that applies true and immediately resolves the
inner Foo would instead fail too early. Spark substitutes input relations before
semantic analysis. Likewise, the scalar-subquery case reaches conflict validation;
naively walking FROM left-to-right and then scalar expressions predicts the wrong
first-pass configuration. Exact Catalyst traversal is part of the design input.

## CTE and binding boundaries

The twelve-case reference packet establishes graph-default overlays, CTE shadowing,
unused definitions, filter subqueries and union order. For these pure queries,
CTESubstitution keeps WithCTE: it does not simply inline each reference and discard
unused definitions. WithCTE visits definitions before its main query, so even an
unused definition can contribute graph-input settings, trigger a conflict, or
change which semantic error occurs. Case-insensitive CTE lookup shadows the graph
under the false default; namespace-qualified access to a bare temporary output in
this fixture fails table lookup. Do not generalize that result to persisted views.
Recursive/legacy CTE policies and dynamic identifier binding remain unqualified.

Sail's bounded binder already walks expressions before plan inputs, and contains
native-aligned eager CTE-definition traversal. Reuse its typed expression descent;
its set-valued ReadSet does not preserve ordering or repetition. The native CTE
resolver's exact-case lookup still needs reconciliation with the reference result;
copying that behavior wholesale would not establish Spark parity. The bounded
binder's helper refusals are admission policy, not a batch SQL limitation.

## Sail implementation sequence

1. Keep these exact inputs and observed errors as the differential baseline. The
   added graph-default/CTE/filter/union cases now constrain the primitive; complete
   recursive/legacy CTE and dynamic-name coverage before claiming general parity. Do not
   replace outstanding mismatches with assertions of Sail's existing behavior.
2. Prototype an ordered graph-view configuration trace before ordinary native
   semantic expression resolution, using existing GraphScope and PlanResolver. Reuse
   Sail's parsing, CTE namespace and catalog/view resolution rules. Preserve plan
   IDs, alias identities and repeated-reference behavior. No serialized-tree walk,
   duplicate SQL parser, shared-session mutation or provider export is selected.
   A semantic first pass merely used to discover reads is insufficient: it may
   fail before reaching the input whose configuration makes the query resolvable.
3. Add a pure merge/validation module with provenance per contributing flow, and
   invoke it only after the first successful semantic pass. Keep declared and
   accepted maps distinct. Resolve again under the compatible union when changed.
   Export accepted maps by flow identity alongside schemas/publication metadata,
   not logical plans. Multiple-flow targets must not collapse flow configurations
   into an output-keyed map accidentally.
4. Use accepted command settings for per-command view/table input reanalysis and
   the native write resolver. Preserve table-only stops and all pre-write failure
   ordering. Re-run the differential cases, upstream Python suite and expanded
   public pipeline tests against the exact combined source and rebuilt binary.
5. Activate captured physical preparation and admitted planning separately, with
   provider-bound SDK/store lifetime evidence. Config parity alone is not ownership
   or cleanup qualification and does not enable streaming/CDC effects.

Each numbered change is a review boundary, not permission for a large combined
refactor. The native binding prototype may need smaller preparatory commits.
The next native seam is ordered graph-view configuration tracing plus an explicitly
qualified semantic/provider-setting split. Additional prepared-provider machinery
remains deferred; normal callers keep their existing defaults.

## Preparatory implementation

[Two units](evidence/expression-subquery-traversal/README.md) are integrated:
744b16867 classifies subqueries hidden in wildcard replacements, with a native
resolver witness and unchanged failing control; 7a50f2875 extracts pure typed
Expr/Window.visit_subqueries into sail-common and reuses it in the bounded binder.
Ordered/repeated callbacks and first-error identity are tested. This provides the
expression portion of an input-binding walk; it does not resolve query/CTE scope,
plan-ID references or providers and does not activate configuration fusion.

## Review and limits

Fable68a11000 identified the complete post-success merge path. CF-0252 supplied
public failure-order evidence; Fable2bc290f7/CF-0253 accepted that the final union's
order independence does not remove first-pass ordering requirements. Both review
snapshots are included in the packet. CF-0259 qualifies the later reference-site
CTE suggestion with the twelve direct observations; accepted-map reuse for command
reanalysis remains an optimization requiring binding/phase equivalence evidence.
The original Scala suites have not been
executed against Sail; their assertions are reference requirements, not passed
acceptance. All thirteen public differential condition/success-row outcomes match after the general missing-column diagnostic unit; full original Scala acceptance and broader binding requirements remain open.
