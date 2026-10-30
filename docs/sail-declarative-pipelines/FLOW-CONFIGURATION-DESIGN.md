# Flow configuration phases for Spark 4.2.1 parity

Status: reference behavior established for the thirteen cases in the
[packet](evidence/flow-config-fusion-reference/README.md); native Sail binding seam
and its full CTE/subquery coverage still require a prototype before activation.
Sail source is163b2fb52; reference source is617618396. No production config-fusion
change is selected by this document. The [batch ownership design](BATCH-PROVIDER-MIGRATION-DESIGN.md)
continues to govern admission, provider lifetime and per-command plan maps.

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

## Sail implementation sequence

1. Keep these exact inputs and observed errors as the differential baseline. Add
   graph-default overlays, CTE shadowing/unused definitions and relation-bearing
   scalar expressions before qualifying a general input-binding primitive. Do not
   replace the ten current mismatches with assertions of Sail's existing behavior.
2. Prototype a native, request-local binding stage that resolves input relations
   in Spark-compatible order before ordinary semantic expression resolution. Reuse
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
The next design decision is the minimum native seam that can preserve binding
order across SQL/Connect plans and CTEs while leaving normal callers unchanged.

## Review and limits

Fable68a11000 identified the complete post-success merge path. CF-0252 supplied
public failure-order evidence; Fable2bc290f7/CF-0253 accepted that the final union's
order independence does not remove first-pass ordering requirements. Both review
snapshots are included in the packet. The original Scala suites have not been
executed against Sail; their assertions are reference requirements, not passed
acceptance. Three of thirteen differential cases currently match and ten differ.
