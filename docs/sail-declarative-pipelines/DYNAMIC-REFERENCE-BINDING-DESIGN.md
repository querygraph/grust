# Dynamic identifiers and Connect references in SDP

Status: active design checkpoint, announced to the user before starting. The first
implementation unit, literal-identifier normalization, is committed. Computed-target
lookup and namespace policy are committed in two separate qualified source units;
Connect-reference expansion/registration lifetime is not yet activated.
No opaque provider slot, cached relation overload, session mutation or streaming
permission is selected here. Preserve Sail's pure definitions, schema/publication
exports and per-command fresh provider maps.

## Evidence that constrains the design

Spark4.2.1 AstBuilder.withIdentClause immediately turns a non-null string Literal
into a named logical relation using parseMultipartIdentifier. Other expressions
remain PlanWithUnresolvedIdentifier, even when constant-foldable. FlowAnalysis
substitutes CTEs and traverses UnresolvedRelation before Dataset.ofRows performs
ordinary semantic analysis. ResolveIdentifierClause materializes computed names
later. Treating a string literal and CONCAT as equivalent early graph reads changes
behavior.

The initial nine public Spark observations demonstrate this distinction:

- IDENTIFIER('z_sensitive') reads the local graph view and inherits its settings.
  With true settings, selecting Foo from its foo output fails unresolved-column
  analysis. A materialized table producer is also a graph input for this form.
- IDENTIFIER(concat('z_', 'sensitive')) does not find that temporary graph view in
  the catalog. It fails TABLE_OR_VIEW_NOT_FOUND instead of inheriting its config.
- A literal external read succeeds with an unrelated configured graph view.
  Adjacent static true-view reads still affect its semantic column resolution.
- The literal CTE reference works. Further computed-name/CTE/sampling observations
  are retained in the expanded oracle; use the packet rather than inference.

The six-case public protobuf WithRelations oracle establishes a separate split:

- A used scalar plan-ID reference contributes graph-view settings, including when
  nested under a function. With conflicting outer-view settings, the two probes
  reach DUPLICATE_FLOW_SQL_CONF after successful semantic analysis.
- Unused references, including an unused SubqueryAlias in the generic form, do
  not contribute settings. Both controls return value2.
- SQL root + nonempty all-SubqueryAlias references triggers Spark Connect's
  SQLWithRefs path. Each reference is analyzed and temporarily registered during
  transformation, then root SQL is executed and temporary views removed.
  A local graph-view parameter fails TABLE_OR_VIEW_NOT_FOUND at registration;
  an external-table parameter registers and subsequently returns Foo9.

The seventh lifetime witness replaces that external catalog entry after flow
registration, keeping the original external files intact. The current catalog
returns bar10, while the pipeline still returns Foo9. This rules out treating SQL
parameter registration as validation followed by fresh name resolution on every
run. The input binding is observably frozen across catalog replacement.

Spark generic transformWithRelations builds a plan-ID map and substitutes
UnresolvedPlanId expression nodes. SQLWithRefs is selected from the original
protocol form before SQL is lowered. A structural references-first traversal is
not equivalent to either path. Source comments require acyclic references; exact
missing-ID, duplicate-ID and nested-reference behavior still needs qualification.

## First review unit: literal normalization

Normalize only spec::Expr::Literal(Utf8(Some(name))) in the SQL analyzer, through
Sail's existing object-name parser, into ReadType::NamedTable. Leave computed,
cast, null and parameter forms as DynamicTable. Preserve aliases and samples.
The grammar's missing IDENTIFIER TABLESAMPLE field is supplied with the same
TableSampleClause parser used for ordinary tables; both read variants retain it.
Original SQL remains in persisted definitions. Do not evaluate helpers in parsing.

This makes the existing ordered trace see exactly the statically named relation,
without extending that trace with a second expression evaluator. Direct AST
comparisons with ordinary table syntax test multipart names, quoted dots, aliases
and samples. Invalid literal names fail during parsing; computed/null forms remain
late. The runtime test's name is updated because a literal SQL identifier is now
intentionally a named relation, not a witness for the computed dynamic path.

## Implemented native policies and remaining review units

1. Computed targets use native CTE lookup first and ordinary catalog lookup after
   graph substitution. The target does not become a graph dependency, even if
   folding yields a local graph name. A native `RelationScope::resolve_late_bound`
   hook defaults to existing lookup; SDP declines only that final target. Actual
   subqueries in the identifier expression remain visible to the input tracer.
2. Namespace policy needs a separate late hook. The Spark namespace oracle creates
   graph/external_input in binding_a (foo9), switches the session to binding_b
   (foo10), then runs: ordinary and literal names return foo9, computed CONCAT
   returns foo10, and the session stays binding_b. Therefore SDP's
   `qualify_late_bound` returns the unqualified name for ordinary live catalog
   lookup; named reads keep graph capture. Defaults preserve other callers;
   stored-view child scopes forward late lookup while retaining the view's
   creation namespace. No session catalog mutation is required.
3. Retain the SQL-parameter versus generic-reference distinction at the Connect
   boundary. Today SQL is parsed away before spec::WithRelations, so its source
   form cannot reliably be reconstructed from a Project node. A pure mode/tag or
   frontend normalization may be needed; no representation is selected yet.
4. For generic references, use lexical plan-ID lookup and expand only actual
   occurrences, preserving expression traversal order, plan IDs and canonical
   attribute identity. Add a typed plan-reference visitor instead of silently
   skipping nested Expr::Subquery IDs. Preserve repeated uses and local shadowing;
   detect malformed/cyclic references with native-compatible diagnostics.
5. SQL parameters require registration-time validation under ordinary session
   rules, outside graph lookup. That alone does not prove correct later binding.
   The provider/schema lifetime witness establishes that fresh name resolution
   changes the observed source across catalog replacement. An explicit immutable
   source description or owned binding contract is required before this path can
   be claimed compatible. Do not retain
   LogicalPlan/providers in sail-common or quietly reintroduce analyzed graph
   provider exports to imitate Spark. If an immutable source descriptor or owned
   binding capability is required, review it with the existing ownership design.
6. Prove each unit using the original public protocol, then Rust native witnesses,
   unchanged controls and a fresh combined CLI. Do not represent helper tests as
   upstream Scala execution or close broad binding parity from rows alone.

## Remaining design work

The raw protocol, source pins, initial/expanded observations and failures are in
[evidence/dynamic-binding-design](evidence/dynamic-binding-design/README.md).
Registration versus analysis versus execution errors remain separate observations.
The provider-freezing representation/lifetime, generic reference cycles/duplicates,
computed-name helper errors, scope/config changes between calls, native CTE policies and command closure
changes remain unfinished. Captured preparation/admission, session shutdown,
streaming/Iggy/CDC durability and full original Scala acceptance remain separate
required work. The goal is active; this document does not select an easier target.

## Helper diagnostics and frozen-source review

Two Spark expression probes (`IDENTIFIER((SELECT Foo FROM z_sensitive))` and the
exact-case `foo` variant) both fail `NOT_A_CONSTANT_STRING.NOT_CONSTANT` before
semantic column resolution. The diagnostic subtree already contains the graph
view substitution. Visiting expression inputs remains necessary, but resolving the
subquery's columns first can produce a different error. These observations do not
qualify Sail's helper diagnostics; preserve this as an open compatibility item.

Fable's Grust cd41f154 review (§14 of BATCH-PROVIDER-MIGRATION-REVIEW.md) identifies
existing file-scan identity transport, versioned table snapshots and graph-owned
registry patterns. These are reuse candidates, not an activated frozen-input API.
A resolved Sail plan may still list files during physical planning. The existing
DROP/recreate oracle proves original location/schema retention; it does not alone
prove what happens when files are added to the *original* location. Qualify add,
delete and replace behavior before selecting fixed listing versus stronger object
version identity. Also cover arbitrary parameter query composition, registration
I/O cancellation and graph-lifetime cleanup. Do not introduce stricter etag/version
semantics without a Spark oracle. Source snapshot capture is separate from C0.

New namespace, expression, native and SDP evidence belongs in
[evidence/computed-identifier-binding](evidence/computed-identifier-binding/README.md).

The follow-up Spark4.2.1 file-mutation oracle now qualifies that boundary for local
Parquet and a composed parameter (`SELECT foo + 1 AS v`): after registration,
appending foo10 makes a fresh path read return foo9/foo10 but the pipeline returns
only v10; deleting the original file fails the run; replacing the original path's
contents with foo11 makes the pipeline return v12. Thus the file set is frozen,
while file contents are read later. Enforcing the old etag/content hash would change
this observed behavior. This does not establish remote object-store versioning,
Delta/Iceberg capture or every composed-relation form. The exact inputs, raw errors
and outcomes are archived in `spark-frozen-files` in the new packet.

## Qualified source units

Sail d2ada245e5464fee71782332419e76b525499402 adds the native late lookup and
qualification seam with default-preserving behavior; dd4c9344adc063d73e8350cf77002c075d0dd49c
activates it for SDP and skips only the eventual computed target in input tracing.
Exact native94+176 and combined94+177 library gates pass formatting/strict Clippy.
Independent lookup/namespace bypasses each fail the unchanged native opt-out test;
restoring early graph binding fails the unchanged SDP runtime regression. The
combined fresh CLI passes300 selected public cases and67 upstream Python executions.
Dynamic comparisons improve from10/13 to13/13; namespace3/3 matches.

The two expression-subquery comparisons remain different0/2: uppercase Foo reaches
Sail's unresolved-column diagnostic, exact foo reaches an unstructured constant
failure, while Spark reports NOT_A_CONSTANT_STRING.NOT_CONSTANT for both. Fix
helper validation/diagnostic ordering while preserving parameter substitution,
private configuration and expression-input tracing. Full metadata parity and full
original Scala acceptance are not established by these selected probes.

## Constant-validation phase boundary

The expanded public SQL oracle now covers34 cases, with separate7-case runtime
replacement observations. Table identifiers reject subqueries before semantic
column/table analysis, while scalar identifiers first resolve their expressions:
a missing scalar-subquery column remains UNRESOLVED_COLUMN. Table arguments that
remain unresolved, including bare missing columns, produce NOT_CONSTANT. For
resolved constants, foldability precedes type validation, then evaluation and null
validation. Preserve parameter substitution before guarded constant checks.

Builtin typeof is a runtime replacement: its argument's resolved type can become
a literal even if the discarded expression contains rand(). A blanket volatile
walk over the raw spec would reject valid inputs. The native refinement uses the
existing request-local ConfigScope, with a table-identifier context that preserves
early subquery refusal while allowing builtin typeof to resolve its discarded
arguments without the eager foldability requirement. A registered function named
typeof retains ordinary UDF rules. Catalog constant expressions retain their own
context; Spark SET CATALOG typeof(rand()) fails INVALID_NON_DETERMINISTIC_EXPRESSIONS,
not the table-identifier condition. Sail's earlier catalog condition remains an
open mismatch, not permission to admit the command.

The [constant-validation packet](evidence/identifier-constant-validation/README.md)
keeps initial28, expanded30 and final34 inputs, the unchanged parameter tests, the
initial constructor compile failure and the unadvanced candidate whose7-case
probe exposed a false rejection of a valid type replacement. Behavioral conditions
and full structured condition/state/parameters are reported separately. The two
SDP helper probes require the right condition, but that alone does not qualify
ordinary SQL diagnostic metadata.

Scalar dead-current_catalog still exposes non-foldable provenance erased during
lowering. The later function-foldability design must preserve that provenance
without rejecting valid typeof replacements or changing semantic error precedence.
Fable's Grust3faece7a review also corrects the renderer boundary: IdentifierResolution
uses a resolved/coerced expression (DIV operands include casts), whereas the
CheckAnalysis table error uses the unresolved expression. One unresolved-spec
renderer cannot cover both. Existing display helpers describe column names rather
than Catalyst expr.sql; positional parameter names need real source offsets, not
fabricated ordinals. These remain explicit design and implementation requirements.

The native unit is now committed at15fd1888c3a474a361afe46d235d52051738229c after
exact97+177 libraries, formatting/strict Clippy, four unchanged2-pass/1-fail controls,
fresh300+67 public and4 existing parameter tests. Earlier dynamic13/13 and namespace3/3
remain matching; SDP helper conditions improve0/2→2/2. The broader34-case oracle
matches28 behaviors and11 complete metadata sets; replacement7 matches6 behaviors.
Remaining primary differences are string division-by-zero diagnostics, four unbound
parameter routes and scalar dead-current_catalog. Counts retain every observation;
they do not establish full identifier metadata, frozen bindings or Scala acceptance.
