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

Spark builtin TypeOf overrides foldable=true and evaluates only its child's
resolved datatype, even if the discarded expression contains rand(). A blanket volatile
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

## Expression-local provenance design, after Fable review

The collector prototype18de98927 retained function provenance in an optional state
boolean outside ConfigScope; it passed its gates but was never advanced. Fable's
532bbdff review identified a smaller representation: preserve non-foldability in
the lowered expression itself. Committed25534e8ea uses a private type-preserving
Volatile marker, introduced only in constant contexts. Existing validation rejects
it; builtin TypeOf discards its child's expression naturally after reading its
type. Registered/HOF markers are attached after the actual selected branch resolves
arguments and lambdas. No mutable observer/context frame or function-registry
rewrite is needed. LiteralEvaluator also guards the marker before physical
materialization, including inactive branches; it does not undo earlier simplification.

The existing eager table/catalog guard remains separate from read-only
constant_context. Arithmetic builders still consult the older flag and need the
next independent split to preserve scalar type-before-evaluation priority. Five
additional function annotations need their context oracles before activation.
Both engines report sessionOrder=second, but Spark's builtin-first path and Sail's
registered-first lookup choose different typeof functions; that generic catalog
issue is retained rather than masked here. Full structured metadata remains open.

## Qualified provenance and arithmetic units; next catalog checkpoint

25534e8eaf8aecc7e769309acae357aab14fd127 is committed after140 shared +100 plan +177
Connect tests, formatting/strict Clippy, four unchanged controls and a fresh300+67
public run plus4 original parameter tests. 3ffb497d3e5dcbb48c56a5dd06687044ef994508
is a separate three-predicate arithmetic change, qualified by101+177 libraries,
an unchanged0/1 control and its own fresh public/parameter run. Both retain earlier
binding comparisons. Provenance improves11/20→19/20 behaviors (complete metadata11);
validation34 now matches29 behaviors; arithmetic improves2/14→6/14 (metadata3).
Remaining failures are retained per case, with no full Scala acceptance claim.

The next substantial design phase is catalog expression policy, announced before
implementation. Fable's independent025fe2a8/55-row oracle shows that bare
SET CATALOG e is determinism-checked, optimized and then evaluated, while its
IDENTIFIER(e) form is evaluated during analysis. Bare current_catalog() succeeds;
the wrapped form is nonconstant. Bare typeof(rand()) is nondeterministic, while
its wrapped form evaluates the type. Bare assert_true(true) simplifies to NULL
before type validation; its wrapped form is nonconstant. typeof(raise_error(...))
and typeof(assert_true(true)) both reach catalog void lookup. Root's14-case probe
corroborates the type-only/catalog boundary. The existing helper collapses these
forms and its old tests encode identifier policy for bare expressions too.

Do not fix this by disabling all provenance in bare expressions: deterministic
registered UDFs and HOFs can remain intrinsically non-foldable after current-like
replacement. Preserve actual nondeterminism before type-only lowering erases its
argument. Fable's87f423c0 function-property survey is a review checklist; individual
context oracles and Sail's ownership/phase boundaries still determine implementation.
The five additional annotations, complete diagnostics/origins, function lookup,
frozen bindings and streaming durability remain separate required work.

## Catalog policy implementation sequence (active)

Committed f0a232af259fa2bf33c089d5439ffb45fa78061e replaces the internal boolean
with `ConstantContext`, initially
Ordinary/Identifier, without activating bare-catalog execution. Its separate
foldability-retention and arithmetic-deferral decisions make the phase distinction
explicit without changing ordinary query planning or identifier error priority.
No additional public setting or function lookup order is introduced.

Bare-catalog activation must follow these constraints, derived from the pinned
Spark rules and Fable's 025fe2a8/198f6076 probes:

1. Finish semantic resolution before whole-expression determinism checks. Preserve
   children of type-only functions until that check; a lowered string literal
   cannot expose the nondeterministic argument it replaced. Artificial Volatile
   provenance markers must not themselves count as original nondeterminism.
2. Distinguish current-like replacement from intrinsic non-foldability. Replacing
   current_catalog/current_database/current_user does not authorize folding
   registered UDFs, higher-order functions or raise_error. Select the actual
   function before assigning its properties; the existing function-path gap stays
   visible. Nested IDENTIFIER retains its analyzer-time validation.
3. After determinism checking, discard deferred type-only children before general
   simplification can evaluate raise_error or arithmetic underneath them. For bare
   commands, optimization/evaluation precedes the command's type check. The
   existing IDENTIFIER type-before-evaluation path remains separate.
4. Keep SDP directive evaluation separate from public command execution. Fable's
   fb208427 review found a third policy in Spark's pinned
   `sql/pipelines/.../SqlGraphRegistrationContext.scala:541–562`: the handler
   calls `analyzer.executeAndCheck`, then `getCatalogName`, without optimization.
   Root verified that source path. Its bare directive therefore needs
   CheckAnalysis before the identifier rule, while wrapped IDENTIFIER resolves
   earlier during analysis. Current-like functions remain non-foldable in bare
   directives. The focused32-case public/directive probe confirms these phase distinctions.
   The earlier namespace-overlay proposal was unnecessary: directive expressions
   are analyzed against the Session, not the file's virtual namespace. Preserve
   the existing callback, commit-time clone/recheck, sequential directive state,
   and live-session evaluation of current_* inside flow queries.

The representation for deferred type-only nodes is still to be implemented and
qualified. Bare deterministic Python-UDF and subquery INTERNAL_ERROR observations
remain Spark outcomes in the comparison; a Sail NOT_CONSTANT response does not
count as matching them. Before activation, compare bare and wrapped forms,
ANSI on/off, dead branches, deterministic/nondeterministic UDFs, type-only parents
and SDP directive registration using fresh exact-source CLIs.

This refactor passed101+177 Rust tests, fmt/strict Clippy, fresh300+67 public
executions, four parameter tests and unchanged14+20 focused outcomes/metadata;
see [the policy packet](evidence/constant-name-policy/README.md). The behavior
activation and full original Scala acceptance remain incomplete.

[Catalog phase oracle](evidence/catalog-command-phases/README.md): the same eight
expressions, bare/wrapped in public/directive contexts, confirm all three phases
on Spark4.2.1. Sailf0a232af2 matches13/32 behaviors and2 metadata sets; all19
differences remain recorded. Both sessions keep their namespace, graphs are
dropped, owned servers stop and no flow runs or writes occur.

Public bare typeof(1 DIV 0) reaches bigint catalog lookup in the oracle. Bare
policy therefore must defer lowering-time arithmetic too: discard type-only
children before evaluation, then evaluate raw1DIV0 before the command type check.
Reusing the ordinary eager-zero path globally would violate this priority.

## Wrapped catalog identifiers and registration error boundaries

Committed4ab0d74bfa8d02c3a9486f4aaa8bf15e174f1091 resolves catalog IDENTIFIER
using the existing scalar helper in an empty schema, with the shared
analyzer_identifier stance for subqueries/type-only expressions. Fableb31c0bc0
caught the table-helper column-precedence mismatch before advancement; the
48-case Spark oracle confirms all three wrapped missing-column cases use
UNRESOLVED_COLUMN.WITHOUT_SUGGESTION. The table-only remap remains table-only.
The reviewed table-route candidate16da863ca is retained, unadvanced.

[Wrapped catalog evidence](evidence/wrapped-catalog-identifier/README.md) qualifies
104plan+177Connect/fmt/strictClippy, unchanged0/3+0/1 controls, a fresh300+67 CLI
run and4 parameter tests. Original32 outcomes improve13→15; expanded48 matches25
behaviors/8 metadata sets, with all failures retained. Earlier14 arithmetic and20
provenance outcomes/metadata are unchanged. Bare catalog behavior stays pending.

The newly preserved structured missing-column errors expose a separate SDP
registration boundary: only string AnalysisError was wrapped; structured
AnalysisException escaped directly. The dependent integration unit catches the
existing structured analysis class, preserving arithmetic/evaluation errors.
Fable98839112 reviewed this boundary against Spark's AnalysisException catch.
A future structured ParseException producer would also need classification;
current parse failures already enter the existing string-analysis path.

Ordinary SELECT typeof(1 DIV 0) is another required generic-SQL correction:
Fablee732cce1's Spark probe5 shows bigint (also with input rows), while Sail's
ordinary eager-zero lowering fails before the type-only parent can discard its
child. This does not justify changing the catalog oracle or preserving that
ordinary behavior as a compatibility requirement. Intrinsic annotations, bare
CheckAnalysis/optimizer policy, catalog lookup diagnostics, frozen bindings and
full original Scala acceptance remain required.

The dependent unit is committed4761d0064b592f66647dec807801c57fcfc546c9:
[boundary evidence](evidence/catalog-analysis-boundary/README.md) records178Connect,
fmt/strictClippy, unchanged0/1 control and its own fresh300+67 public run, four
parameter tests and unchanged14+20 observations. The same48 cases improve25→28
behaviors (metadata8); all20 remaining differences are retained. The plan crate
is byte-identical to4ab. Both product units and all owned gates/probes are terminal;
no full original Scala-suite acceptance or bare catalog activation is claimed.

## Explicit catalog loads and native error hierarchy

Committed55c237c489d551bb82b1aa9da3d6b035ab4a57ca adds one typed error factory
beside quote_sql_identifier and applies it only to SetCurrentCatalog execution.
Catalog API and public SET CATALOG keep the native CatalogNotFoundException,
CATALOG_NOT_FOUND/42P08, quoted catalogName and configuration parameters. The
existing transport derives the measured five-class hierarchy from this known
class, allowing PySpark to select SparkException without replacing the native
reason. There is no new serialized field, dependency, catalog provider branch,
manager/planner change or analysis-time existence check.

Fable973788dd and the independent16-case Spark oracle established the critical
scope boundary: namespace resolution falls back to the current catalog and has
different errors. The broader planner-map candidateba7 passed439 tests but was
never advanced. Final55 leaves plan/catalog trees byte-identical to476, gates the
physical conversion on SetCurrentCatalog and preserves CommitStateUnknown.
Fable885c91eb reviewed that bounded implementation without a requested change.

[Explicit-load evidence](evidence/missing-catalog-errors/README.md) records439 Rust
libraries/fmt/strictClippy, diagnostic/hierarchy controls each0/1, a fresh300+67
public run and4 parameter tests. The new16 queries improve0→12 behavior/public
metadata matches, with ten matching native reason/hierarchy/metadata groups.
Malformed names retain INVALID_ATTRIBUTE_NAME_SYNTAX; their existing single-class
analysis hierarchy remains a wire difference. Three namespace errors are unchanged
including public messages; Sail's existing USE CATALOG grammar extension remains
a difference from Spark's parse error. No transient IDs/full stack/origin equality
is claimed. The comparator includes explicit getCondition as well as display codes.

The same48 catalog cases improve28→33 behaviors, metadata8→13; arithmetic14
improves6→8, metadata3→5. All earlier positive cases remain positive and20 provenance
observations are unchanged. Bare public/directive phase checks, intrinsic function
annotations, ordinary arithmetic lowering, fallback resolution/frozen bindings and
full original Scala SDP acceptance remain required work. No flow run or data write.

## Arithmetic lowering and the next evaluation checkpoint

Committeda49082801e79a6a9cea545186fecb7171d54a4b5 removes all three eager zero
paths and the arithmetic-deferral exception. The existing guard uses two typed
internal error kinds with the existing StandardUdf envelope; generic raise_error
is unchanged. The transport preserves the native arithmetic class and measured
six-class hierarchy. A real signed-zero regression from the first public run is
fixed with a widened abs predicate for ANSI and nested typed NULLIF outside ANSI;
the non-ANSI divisor appears once and the result type stays intact.

[Arithmetic evidence](evidence/deferred-arithmetic/README.md) qualifies909 Rust
libraries/fmt/strictClippy, unchanged eager1pass/2fail and codec0/1 controls, its own
fresh300+67 public run and4 parameter tests. Core40 improves17→40 outcomes and
metadata/raw field comparisons; all33 successful schemas match. Earlier48 stays33,
14 arithmetic improves8→10, metadata5→7;20 provenance observations are unchanged.
The initial import/envelope fixture failures and d53's298/300 signed-zero failure
are retained rather than relabeled. Source55's catalog behavior remains intact.

5a1142bcd90b97385314610f1342e1a9a4879690 corrects only the cfg(test) fixture:
floating signed-zero checks use / and %, while integer DIV is covered separately.
Spark rejects floating DIV; the separate two-row conformance check still fails in
both ANSI modes. The106-plan/fmt/Clippy fixture gate is pinned to5a, public/runtime
proof to production-identical a490. No public verdict on5a itself is claimed.

Runtime semantics remain required work. The12-case NULL/volatile/window/pmod probe
retains six ANSI failures and its check exits1. A deterministic volatile-divisor
Rust test, appended only on unadvanced20832708b, fails0/1: six calls where one is
required and a typed error despite an initial nonzero divisor. Its original fixture
returned the error before measuring; the corrected fixture asserts the count first.
This is observed across optimization/execution, not proof of a single physical
stage cause. The current ANSI CASE also contains two divisor references.

The next substantial design checkpoint, announced to the user, is operand evaluation
order/cardinality. A unary divisor guard can preserve native kernels and remove
syntactic divisor duplication; NULL-dividend/right-first behavior and domain checks
need further design. Arbitrary dividend duplication was rejected because volatile
expressions are excluded from CSE; no window deviation is an acceptable final
state. Query origins/full diagnostic summaries, bare catalog phases, intrinsic
annotations and full original Scala SDP acceptance remain unqualified.


## Numeric operand evaluation checkpoint (CF-0344–0350)

The user-notified checkpoint is active. Sail b857dabb74da0484b781c096f9a9cd6a78daaa5c
adds a type-preserving unary numeric/Null divisor guard, retaining native kernels
and the existing name-keyed StandardUdf codec. It closes syntactic divisor
repetition and avoids arithmetic CASE predicate pre-evaluation. Nonnumeric
fallbacks and intervals/durations retain their previous lowering. The
[numeric divisor packet](evidence/numeric-divisor-guard/README.md) records913 Rust,
strict Clippy/fmt, two unchanged failing controls, fresh300+67 public executions,
all40 core outcomes/metadata/raw fields and33 successful schemas. Legacy decimal
remainder also improves two schemas from decimal(10,2) to Spark decimal(5,2).

Own backtraces and Fable's independent phase probe establish a distinct dependency
issue: DataFusion55.2.0 CaseExpr::nullable evaluates predicates on a dummy batch
without volatility checking. Stable callback counts: plain1, abs1, explicit
CASE6; guarded division7 before and1 after. Lowering/frame construction calls0.
The generic CASE defect remains required work; no registry source was modified.

The extra22 decimal/CASE/string probes preserve all parent rows/errors. Apart
from the two remainder schema improvements, schemas remain identical. Decimal /
precision, CASE result nullability and string arithmetic domains remain wrong;
Spark rejects the two-string arithmetic queries in ANSI mode and accepts them
in legacy mode; mixed numeric/string pairs are accepted in both. A blanket
string-to-double fallback is not justified. CF-0351–0352 corrects the first prose
summary; raw original22-case observations and comparison counts were correct. Fable's2b6c00cb review and
fresh Spark/parent diagnostics are retained. Initial Decimal JSON recorder
failures on both engines are preserved separately from engine outcomes.

Six runtime NULL-input/volatile/window/pmod cases and two floating DIV domain
cases still fail. Spark DivModLike evaluates right first and can skip left for
null/legacy-zero divisors. A unary UDF alone cannot provide that contract.
DataFusion ScalarUDFImpl::short_circuits/conditional_arguments annotate optimizer
behavior; ScalarFunctionExpr::evaluate still evaluates every argument before
invoke_with_args. Existing projection rewrites cover only one expression context.
Further selection must preserve cardinality/order across filters, joins, sorts,
windows and workers; it must not duplicate volatile operands or erase coercion.
The original Scala suites remain unqualified; full goal stays active.
