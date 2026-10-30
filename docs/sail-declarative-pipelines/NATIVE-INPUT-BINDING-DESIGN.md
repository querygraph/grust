# Native input binding for flow configuration analysis

Status: the next prototype uses an ordered graph-view read trace with the existing
PlanResolver/GraphScope. A new opaque provider-binding representation is deferred.
The [configuration phases](FLOW-CONFIGURATION-DESIGN.md) and thirteen-case baseline
remain the target. The [external-file oracle](evidence/flow-config-external-read-reference/README.md)
does not establish per-occurrence metadata configuration: Parquet checks here
follow run-session settings, independently of the private semantic settings.
No production configuration fusion has been activated.

## Problem and required boundary

Spark substitutes input relations before semantic analysis. Sail's normal
PlanResolver resolves child expressions while recursively building a logical plan.
The nested-projection and scalar-subquery reference cases show why merely changing
its config during recursive lowering is insufficient. A semantic discovery pass
can fail before it reaches the input whose setting would make analysis succeed.

An upfront compatible-map merge still changes first-pass semantic error precedence.
However, the claim that external metadata necessarily observes the private config
at each read point is not established. Seven Parquet cases and two ordinary SQL
controls instead separate run-session metadata settings from private flow semantic
settings. Do not select a new prepared-provider framework on the earlier source
inference. These results do not prove equivalence for arbitrary SDK callbacks or
helper/metadata errors; qualify those boundaries independently.

The existing per-command table-bounded provider maps remain useful for upstream
views and committed tables. They do not provide an identity for two occurrences
of an external read, nor a general pre-semantic binding stage.

## Selected next prototype

Use typed structural navigation to collect graph-view reads in the required order,
interpreting CTE scope under the initial flow settings. Derive the first pass's
private semantic configuration from declared settings plus encountered views'
accepted maps. Resolve through the existing native PlanResolver and GraphScope.
Only on success validate/merge compatible maps, and call again if changed. Table
inputs stop flow-config propagation; repeated view reads remain in the trace.

Keep provider/session configuration distinct from private semantic settings where
the reference establishes that split. SourceInfo.read_case_sensitive currently
comes from PlanConfig.case_sensitive at the native read sites. A minimal explicit
read-case override, defaulting to current behavior for ordinary callers, is a
candidate native seam for pipeline analysis; validate the precise scope before
activation. The ordinary source Session and explicit source options remain native.
This does not justify inventing defaults for unqualified formats/callbacks.

The trace is not semantic resolution. Dynamic identifiers, CTE/parameter-view scope,
missing inputs and mixed metadata/helper failures need explicit behavior and tests;
do not silently omit a read that cannot be identified statically. Generic resolver
case matching and unresolved-column error typing should be improved in Sail, rather
than hidden in a pipeline-only exception translator. Correct rows alone do not
close the reference matrix's error-condition differences.

## Deferred fallback candidate: prepared input occurrences

The following representation remains a review fallback if direct evidence shows
that ordinary resolution with the phase-separated settings cannot preserve an
input observation or helper boundary. It is not the next implementation target.

Use a request-local native BoundQuery that owns the query and its prepared input
plans. Represent each prepared occurrence by an opaque slot in that one query,
with original name/provenance retained separately. An internal typed bound-input
node is a fallback candidate; adding such a spec variant would require a narrow
Sail design review before implementation. Keep DataFusion plans/providers in
sail-plan, never in sail-common's spec. No new dependency is required by this
representation. No global store, catalog registration or broker state is involved.

A normal resolver must reject an unbound/unknown slot. The opaque wrapper must
keep the rewritten query and slot table together; callers must not assemble a
query with another request's providers accidentally. Serialized spec IDs alone
must not be a replay capability. Do not install a generic fallback that resolves
an unknown bound slot by name through the catalog.

The binding pass would use typed query/expression traversal to visit graph inputs
and external reads in the required order. CTE scope and policy belong to the
native binder, not the structural visitor. It must honor the initial CTE resolver
settings before later graph-input overwrites, retain applicable unused definitions,
and distinguish qualified graph names from bare temporary views. Recursive and
legacy policies still need dedicated qualification. WithRelations reference
lookup must preserve Spark Connect plan IDs; structural reference order alone is
not a proof of its binding semantics.

Factor the existing native read resolver only as far as necessary to separate
relation preparation from semantic processing of the containing query. Prepared
occurrences would retain phase-appropriate configuration and the caller's query
Session; the private flow conf is not automatically the metadata conf.
Do not resolve a full leaf through a second independent resolver and then assume
its generated field/qualifier IDs can be used in another resolver state. Reuse
native field registration, alias construction and missing-input boundaries when
installing the prepared relation in the semantic pass.

Time travel, dynamic identifiers, table sampling, table functions and callbacks
need explicit phase decisions. Some require expression evaluation to identify the
input; some run helper plans. Sampling percentages can reach a subquery before
foldability failure, as the native witness shows. ROWS is currently unsupported
by the generic resolver; no successful execution or hidden-I/O witness is claimed
for it. Do not silently force all modifiers through an earlier helper phase, or
route valid batch operations through the bounded streaming refusal policy.

After binding, ordinary native semantic resolution must consume prepared inputs
without consulting their providers/catalogs again. Only after that succeeds does
flow configuration merging reject distinct values and accept a union. If changed,
perform a new binding/resolution call under the union, as Spark does. Keep the
configuration of each call separate from the flow's declared and accepted maps.

The analyzed graph would export accepted maps per **flow identity**, schemas and
publication options; no BoundQuery/providers would be exported. Publication retains
original SQL and creation namespace; opaque binding IDs must never replace the
stored definition. Batch command reanalysis constructs new bindings under its
accepted command map and table-bounded closure. Reusing earlier maps remains an
optimization requiring phase/binding equivalence evidence, not a guarantee from
unchanged definitions. Capture/admission/provider supervision remains governed by
[the ownership design](BATCH-PROVIDER-MIGRATION-DESIGN.md).

## Alternatives ruled out or requiring more evidence

- Merge a sorted dependency set before analysis: changes failure precedence and
  read-point observations; dependency membership is not an ordered trace.
- Mutate config during ordinary lowering: nested expressions are resolved too early.
- Resolve once to discover reads: discovery itself performs semantic analysis and
  can fail before later inputs are bound.
- Require per-occurrence slots without an oracle: the thirteen semantic cases need
  an ordered view-config trace, not a new provider registry. If distinct preparation
  observations are later established, a name-only prepared-provider cache would
  need separate qualification.
- Reuse plan_id for binding IDs: conflates private slots with Connect attribute and
  CTE reference identity.
- Overload CachedRemoteRelation: that is backed by RemoteCheckpointRegistry and its
  checkpoint schema/storage/lifecycle contract, not a private prepared-input map.
- Use AST pointer addresses as persistent slot IDs: moves/clones and helper rewrites
  make that an unsuitable identity contract.
- Duplicate SQL parsing or create synthetic catalog names: bypasses native binding
  rules and introduces unintended catalog/session state.

## Reviewable implementation and evidence

1. Prototype the ordered graph-view read trace and first-pass semantic config through
   the existing resolver, covering the thirteen semantic and twelve CTE/default
   cases. Make missing/dynamic inputs explicit and preserve native query identity.
2. Qualify the minimum semantic/provider-setting separation against the seven
   external metadata cases and ordinary caller controls. Do not add slots/spec
   variants unless direct evidence requires them.
3. Add post-success conflict/union validation, conditional second resolution and
   accepted maps by flow identity. Assert exact errors and metadata outcomes;
   neither an upfront conflict check nor value-only comparisons satisfy parity.
4. Carry accepted maps into actual command reanalysis, retaining publication DTOs,
   table-only stops, refresh selection and pre-write failure effects. Rebuild and
   run the expanded differential/public/upstream gates on the exact source.
5. Qualify admission and backend/provider lifetime separately before broadening
   ownership or enabling streaming/CDC effects. Prepared-plan lifetime alone does
   not qualify live SDK supervision. Revisit the deferred fallback only if needed.

The thirteen differential cases currently remain3 matches/10 differences. The
structural navigation and bounded-admission fixes do not change that inventory.
The next implementation is the smaller graph-view trace and phase-config contract.
No claim is made that arbitrary input preparation is already equivalent or free of
helper effects. Fable CF-0273/0274 agrees on keeping the slot design as a fallback.
