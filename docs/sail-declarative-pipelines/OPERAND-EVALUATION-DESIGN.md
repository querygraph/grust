# Arithmetic operand evaluation checkpoint

This checkpoint was announced to the user before design began (CF-0343–0344).
It remains active. Spark4.2.1 source is617618396087429b5627a86ce933bb0f5d6645cb;
DataFusion55.2.0 is pinned by Sail's Cargo.lock. No final arithmetic deviation
is accepted. Streaming/CDC provider or durable-effect authority is unchanged.

## Required behavior

Spark `DivModLike.eval`, in arithmetic.scala, evaluates the right operand first.
It returns NULL without evaluating left when right is NULL, or zero in legacy
mode. Otherwise it evaluates left once; NULL left returns NULL even with an ANSI
zero right. Only then does it check ANSI zero and evaluate the arithmetic kernel.
`DIV`, `/`, `%`, and `pmod` share this contract. Integral overflow, decimal result
precision, coercion, invalid domains and error context still require independent
qualification. A zero-divisor predicate must not cause another volatile draw.

The [numeric divisor guard](evidence/numeric-divisor-guard/README.md) closes two
specific mechanisms: an arithmetic CASE duplicated its divisor, and DataFusion
`CaseExpr::nullable` evaluated its volatile predicate on a dummy batch during
physical planning. The guard preserves original numeric types and native kernels.
It cannot provide conditional left evaluation because ScalarFunctionExpr evaluates
all argument expressions before calling a scalar UDF. ScalarUDFImpl's
short_circuits/conditional_arguments are optimizer annotations, not a physical
argument evaluator. The generic CASE issue remains independently reproducible.

## Existing Sail seam

Sail already lowers `ConvertTzLazy` and `SparkSequenceLazy` to higher-order
functions with lambda bodies. DataFusion HigherOrderFunctionExpr constructs
LambdaArgument handles, including projected captured columns, without evaluating
lambda bodies; the implementation chooses when and over which rows to evaluate.
Sail already serializes these higher-order expressions/lambdas through its
converter and explicit HigherOrderUdf variants. Reuse this seam before adding a
custom physical-expression planning framework.

The existing evaluate_lambdas_until_null helper runs one whole argument batch
before the next. ConvertTzLazy explicitly records the remaining row-major/error
ordering gap. A failed-batch replay would repeat volatile/stateful evaluation;
it cannot establish Spark parity. Do not use either technique as the correctness
baseline for DivModLike.

## Proposed internal component

SparkDivModLazy takes exactly three lambdas:

1. Right thunk, with an unused fresh dummy parameter.
2. Left thunk, with an unused fresh dummy parameter.
3. Native operation over `(left_value, right_value)` parameters.

The right/left lambda output fields determine the third lambda's parameter
fields through LambdaParametersProgress. The result is the operation field with
nullable=true and metadata retained. The third lambda preserves native kernels
and their analyzer coercion; it must contain bound parameter references rather
than copies of the original operand subtrees. Existing typed divisor checking
belongs there, after the component has handled conditional operand evaluation.
The component needs only ANSI mode for its skip policy; operator/error kind stays
in the existing operation expression. It is internal, not a SQL registry entry.

A single invocation visits rows in order. For each row it evaluates right once,
skips on null/legacy zero, evaluates left once, skips on null, and invokes the
operation with already evaluated values. It stops on the first reached error.
There is no retry or speculative evaluation. The numeric zero mask is shared
with SafeNumericDivisor, including both floating zero signs and decimals. Empty
batches preserve the result type. Initial admission is numeric/Null right only;
string/temporal coercion is not silently guessed.

## Incremental build and activation conditions

The first source unit is the component, shared zero-mask extraction, and native
regressions only. It does not change arithmetic lowering or worker encoding.
Tests must prove right-first order, ANSI left-null suppression, legacy-zero and
right-null skip, no failed replay, first-error ordering across rows, signed zero,
NaN/infinity, captured columns, operation parameters used without a prefix,
metadata, empty input, invalid admission, and optimizer handling of a skipped
failing constant operand. Retain failed attempts and production-only unchanged
controls. Any gate verdict is scoped to its exact detached source commit.

Next units are explicit codec support (ANSI mode, existing lambda converter,
round-trip execution) and lowering integration, each separately reviewable.
Before integration qualify logical constant/foldability validation, SQL aliases,
projection/window extraction and filter/join/sort expression contexts; higher-order
bound variables must not become external dependencies. Extracted Python UDFs,
subqueries and windows may be evaluated outside these thunks, so inspect Sail's
existing transformations and Spark's corresponding phase; do not claim laziness
across an independently evaluated operator. Run exact native/public/probe gates,
retain all known failing conformance cases and update full-suite coverage.

The straightforward per-row implementation allocates/takes per reached row.
It is a correctness baseline with an unresolved performance cost, not approval
for an unmeasured blanket arithmetic slowdown. A faster path needs an argument
that speculative batch evaluation cannot change observable error/evaluation
order, or a compiled row kernel; it must not use catch-and-replay. Measure before
activation and distinguish pure column/literal arithmetic from fallible or
volatile expression bodies. Do not give up required cases to obtain a faster gate.

This component orders operands and rows within its own invocation. It does not
establish query-wide ordering across different projection expressions, scheduling
partitions, extracted window inputs or generic CASE predicates. Those limits must
remain explicit and tested; passing component checks is not full Spark SDP parity.


## First component qualification (CF-0359)

Sail c1befda7a8f29937c9bbc32d3f516379732e9eae is the first component unit,
with402 full function-library tests, fmt/strict Clippy and an unchanged-source
test failing0/1 when production order is reversed. The six tests include two
identical lazy calls over a volatile thunk: exactly2 calls, results8 and4, zero
at frame construction. The seam works and CSE preserves that descendant in this
fixture. [Full evidence](evidence/ordered-divmod-component/README.md) retains
three failed attempts, two passing401 checkpoints and a failed batch fixture.
Arithmetic lowering/registry/protobuf/codec blobs remain unchanged. No native
component verdict is promoted to a public runtime or full Scala-suite verdict.

A fresh Spark8-case oracle and Fable710d0b73 independently confirm a concrete
public error difference: first-row left raise before later right invalid cast
reports USER_RAISED_EXCEPTION; reversed input reports CAST_INVALID_INPUT,
with whole-stage codegen on/off and a single partition. Partition races do not
justify discarding the observed same-partition ordering. A selected-batch-only
prototype reports the later right error on the same native callback fixture.

The prototype also checks equal successful1024-row outputs and records an
unoptimized shared-host diagnostic: row/native ratio about80.3, selected/native
about2.94. This is not an optimized production estimate. No blanket row-major
activation is chosen. Representative optimized runs, whole-projection CSE costs,
coercion and all expression contexts remain prerequisites.

Fable e30236fe proposes a narrower fast path: batch selection for deterministic
thunks, ordered replay only on reproducible data errors, row-major initially for
volatile thunks. Spark Expression.deterministic excludes mutable/internal and
implicit inputs and non-deterministic children; DataFusion volatility and Stable
query-time functions require corresponding treatment. This is under review,
not added to the component. An Execution error from an arbitrary UDF is not alone
proof that retry is effect-free or reproducible. Use explicit replay-safe body
and data-error admission; preserve I/O/resource/cancellation/internal failures.
Never replay a volatile/stateful body, and do not create streams or retain partial
batch state merely to retry. Constant/foldability validation must understand the
internal bound variables before lowering; do not admit arbitrary user lambdas as
identifier constants. Operation parameters need fresh names against input field
names as well as enclosing lambda variables; the initial fixture collision is
retained as evidence for this requirement.


## Worker representation and staged decoder (CF-0360–0368)

Two separate source units follow the component. Generic04f1e8cc7 adds staged
physical lambda decoding and five native fixtures (235 execution libraries,
fmt/strictClippy, unchanged retention/limit/prefix0/1 controls). Wire036dc6dde
adds HigherOrderUdf tag13 with ANSI mode and four full-tree round-trip fixtures
(239 execution libraries, fmt/strictClippy, unchanged mode0/1 control). Bodies,
captured columns and parameter fields use the existing lambda converter. Error
class/condition/22012/config, null/zero skips, only-right parameters, operation
captures and malformed arities are tested by executing decoded trees. See the
[codec evidence](evidence/ordered-divmod-codec/README.md).

The converter previously rejected Partial before decoding any lambda. Staged
resolution retains prior fields on None, includes steps0..=signature limit,
rejects nonconvergence and malformed fields/arity, and infers known bodies only
when another resolution pass is needed. Complete may have optional trailing
sets, matching the existing physical constructor; Partial is exact like the
logical resolver. A real physical-constructor fixture proves the distinction.
This does not close the dependency CASE nullable/predicate evaluation issue.

SQL lowering, constant checks and evaluation policy are still unchanged. The
next validation unit needs lexical parameter scopes: admit only the exact
SparkDivModLazy implementation's three direct lambda arguments, walk every body
under the existing scalar variant/volatility/async rules, and pop each argument's
names before visiting its sibling. Internal bound variables are constant only
inside their scope; free variables, columns, other HOFs and arbitrary lambdas
remain rejected. Nested internal evaluators/shadowing need fixtures. Existing
LiteralEvaluator remains the evaluation path. End-to-end IDENTIFIER arithmetic
and wrapped SET CATALOG fixtures must actually use new lowering at activation;
passing old-lowering examples now would not prove this new validator seam.

Fable d5b1d8cc/5a5ff593/a683b52d reviewed the wire and staged API. Native tests
caught the initial converter assumption, then review caught retention/bound
semantics not covered by the initial integrated234 checks. All failed drafts
and passing unadvanced checkpoints are retained. No fast-path flag, blanket
lambda allowance, replay policy or provider/streaming effect is introduced.


## Scoped constant eligibility (CF-0369–0371)

Sail4070e895b69338eb19f22643f0e40815da89ff34 replaces the flat eligibility
walk with a private lexical visitor. Ordinary variants and Volatile/async scalar
rejection are unchanged. Only the exact internal SparkDivModLazy implementation
with three direct lambda arguments opens scopes. Each body is walked under its
own parameter names, removed before siblings; nested evaluators can shadow and
capture outer bindings. Free variables, columns, arbitrary lambdas and different
HOF implementations (including the same function name) remain rejected. Type and
parameter-arity validation stay in the existing analyzer/evaluator.

The [validation packet](evidence/scoped-constant-validation/README.md) qualifies
114 plan libraries/fmt/strictClippy and four unchanged0/1 production controls.
Seven fixtures use the real LiteralEvaluator for internal arithmetic/string and
nested scope results; retain type-before-error, null-left/zero-right suppression
and skipped failing-left behavior; reject scope leaks, provenance and immutable
async functions without invoking bodies. There were no failed candidate attempts.
This is internal eligibility proof, not end-to-end new SQL lowering proof.

The next significant checkpoint, flagged to the user, is fast-path/performance
and error-replay policy. No execution mode/flag/default changes in this unit.
Literal folding and actual Sail optimizer behavior for fallible conditional
bodies need probes before activation. Do not infer a Sail failure solely from
DataFusion literal Cast behavior: Sail already uses SparkAnsiStringCast for
supported ANSI string targets. Preserve volatile/stateful cardinality/order and
resource/I/O/cancellation identity; no catch-and-replay shortcut is selected.
Fable's CF-0370 read-only review request for this exact unit is pending as of
CF-0371; incorporate further review before activation. Full original goal remains
active and unqualified by these native component gates.


## Fast-path checkpoint evidence (CF-0372–0375)

The [checkpoint packet](evidence/operand-fastpath-design/README.md) retains the
optimized prototypes, actual Sail optimizer observations, Spark oracle and raw
error controls. Product4070 remains unchanged. Avoid all-active take/scatter;
18 Int32 mask cases pass, but batched first-error selection still differs from
the ordered reference. Shared-host tiny-kernel ratios are diagnostic only.

Replay requires two independent proofs: explicitly admitted deterministic native
bodies, and admissible raw data errors. CommonErrorCause collapses resource/join
errors into Execution and cannot supply the latter proof. Unknown wrappers must
not become replayable by source-chain peeling. Unknown/custom/async/volatile
bodies remain ordered. No classifier/mode/default/worker flag has been selected.

Actual Sail optimizer probes establish an earlier prerequisite: ANSI decimal
and legacy DOUBLE casts can throw during simplification even inside a skipped
internal thunk. Spark rightNULL returnsNULL for every tested target/mode. Keep
the twenty required conformance failures visible; native internal literal7
operations prove conditional behavior only, not new arithmetic/schema parity.
Fix general Sail casts with qualified invalid-input/rounding/overflow/error/wire
semantics before activation. Runtime error replay cannot repair optimizer errors.
Fable acknowledged read-only validator/wire/design review atCF-0374; its new
verdict is pending. Existing provider/streaming/CDC boundaries remain unchanged.


## Legacy floating cast prerequisite (CF-0376–0377)

Sail63f5bd3b3f0f8bd9b23607161d5988df853a738c routes legacy string-to-float
casts through existing TryCast semantics. [Evidence](evidence/legacy-floating-cast/README.md)
qualifies117 plan libraries, unchanged0/3 production control and fresh300 public
plus67 upstream; native resolved conditional bad casts with rightNULL/right0
now returnNULL rather than fail during optimization. ANSI/wire/evaluator policy
and arithmetic lowering are unchanged. Spark/public136 retains16 suffix/hex
behavior gaps and20 ANSI nullability mismatches; no full cast parity is claimed.
ANSI decimals still need conditional/folding semantics before SQL activation.
No production replay mode/classifier/default or provider/streaming effect changed.


Fable reviewbdd5962d (CF-0377, acknowledgedCF-0379) accepts407/04/036.
It correctly bounds the earlier NULL-divisor oracle to VALUES/local relations:
Spark parent-first folding and conditional branches can skip invalid casts,
while an invalid foldable child under a nonfoldable real-source division can
fail during planning. Exact source/phase behavior remains required; a lenient
runtime result is not final Spark parity. The current legacy floating correction
is valid in either case because Spark legacy invalid casts returnNULL.
Replay list direction remains unresolved: missed data errors can select a wrong
row, but pure value semantics alone do not prove repeated system failures are
safe. Audit each admitted native body's reachable raw error vocabulary before
choosing a classifier/default. No replay activation is implied by this review.


## Verified source/phase and decimal contract (CF-0382–0384)

The [new packet](evidence/source-dependent-cast-folding/README.md) corrects the
VALUES-only interpretation using fresh Spark/public56. ANSI bad literal casts
under nonfoldable Parquet division fail during Spark planning, includingNULL
right values; fully foldable parents, conditional branches and early local
relations have different rules. Outcomes match34/56; schema/phase together16.
Keep eager failures and skipped results as equally required. No always-deferred
cast wrapper can establish exact behavior across these contexts.

Fresh decimal192 matches114 outcomes/101 with schemas. Spark Unicode decimal and
exponent digits, Java trim boundaries, extreme zero exponents and three distinct
error kinds are executable fixtures. Existing ordinary HALF_UP cases match Sail;
follow the actual Arrow cast/decimal.rs path rather than the separate parse
utility. A focused typed decimal UDF/shared bounded parser is the candidate
next component, unactivated until scalar/array/nullability/metadata, captured
error/negative-scale policy, worker wire and folding context are qualified.

Fable806d6678 reconciles replay: known data errors only, from exact admitted
bodies and data types; preserve other errors. Add executable error fixtures and
invalidate source/dependency audits on changes. Do not claim a token search
proves exhaustive reachability. Fablec41fba30 identifies physical optimizer and
worker decode reproof as candidates without a wire eligibility bit. The generic
ExecutionPlan expression visitor is read-only; node rebuild and scan pushdown
coverage still need proof. QueryPlanner can instead rewrite final logical Exprs
before native construction, requiring audit of later physical rewrites. No seat,
mode/default/classifier or arithmetic SQL activation is selected by this packet.


## Callable decimal component (CF-0386–0389)

Sail8a7bf8ca4d98d43437eb005dde5db5b1f024e13c adds SparkStringToDecimal
without registration or resolver/wire/folding activation. Its
[packet](evidence/decimal-scalar/README.md) qualifies410 function libraries,
formatting/strictClippy, four unchanged0/1 controls, original Spark192 reduced
to96 distinct policies plus32 fresh negative-scale-policy cases, each scalar
and array in three string layouts. Java BMP digit mapping is exhaustive against
JDK20 and identical under JDK17; supplementary digits are rejected as UTF16
surrogate pairs, rather than admitting every Unicode Nd code point.

The constructor captures p/s, fail_on_error and allow_negative_scale. The latter
changes input-range errors even for positive-scale targets; it is not a third
error mode. Negative target refusal stays resolver-owned. Parsing validates
Java trim, grammar and i32 scale before the zero shortcut; HALF_UP rescaling is
bounded by target precision and errors retain the correct original or canonical
value. Fields are nullable, type-only and clear extension metadata. The shared
invalid-string factory preserves the existing primitive caster's error contract.
Fable6b7fe4de accepts the component without correctness findings.

Next commit: worker serialization carrying all four fields and typed errors,
then generic Sail config/type policy and exact source/conditional folding before
SQL resolver routing. Public CLI remains qualified63f5; scalar component gates
are not an8a7 public verdict. Add the new NUMERIC_* conditions to the audited
raw vocabulary before this class enters any future native fast-path admission.


## Decimal worker wire (CF-0390–0393)

Sailb48162de9c9ee9cf4f386fa7eb3ebf683601a64d adds ExtendedScalarUdf tag43
carrying precision/scale/fail_on_error/allow_negative_scale; tags1..42 unchanged.
[Evidence](evidence/decimal-codec/README.md):243 execution libraries/fmt/strictClippy,
five unchanged0/1 controls for both policy bits, sign and both checked narrowing
conversions. Full physical HOF round trips preserve captured string columns,
skipped failing casts, typed errors and empty batches. Malformed257/258/-256
would wrap to valid native values and are rejected before construction.
Fableb38215b4 accepts this unit. Direct codec/expression tests do not establish
live worker RPC or new public SQL; the qualified CLI remains63f5.

The next design checkpoint, explicitly flagged to the user atCF-0393, is generic
config/type policy capture and exact source/conditional folding before resolver
activation. Negative target refusal remains resolver-owned, while input range
policy is captured and now travels in the worker payload. No folding/planner-seat,
fast-path mode/default/classifier or provider/streaming authority was selected by
the wire unit. The source-dependent failure baseline remains required.


## Generic decimal config capture (CF-0394–0399)

Sail226b0c1cfc9ac72dadc3ec8a81667f7acc3aacec captures
legacy_allow_negative_scale_of_decimal in PlanConfig and validates its SET before
mutation. [Qualification](evidence/decimal-config/README.md):117plan+183Connect,
formatting/strictClippy, four unchanged0/1 controls, fresh300 public+67 upstream,
and exact Spark/Sail config12 comparison (raw strings, rollback, exception type,
condition/state/parameters). Snapshot/override tests feed the callable caster and
preserve independent old semantics across SET/UNSET. Fabled527d8ed accepts.

Shared Java-trim/strict-boolean extraction retains ORC's existing error mapping.
The new key carries INVALID_CONF_VALUE.TYPE_MISMATCH/22022 and the complete
SparkIllegalArgumentException hierarchy. Other older boolean paths remain a
separate parity item. The only dependency change is a dev-only test edge.

An initial test borrow fix and omitted-environment native failure are retained.
The env-only same-binary control and full same-source pass show the latter cause;
the operational helper now supplies all three pinned Python environment values.
Source/gate and CLI are qualified226; no new scalar SQL routing, negative-target
guard or folding rule is enabled. The next part of the already user-flagged
checkpoint is exact source/conditional folding and target-type policy before
resolver activation. Prior source/phase and decimal conformance failures remain
required; config/transport parity alone does not establish their resolution.


## Folding implementation boundary and conditional normalization (CF-0400–0401)

Spark pin617618396087429b5627a86ce933bb0f5d6645cb implements the generic
folding recursion in catalyst/optimizer/expressions.scala: parent-first whole
foldable subtrees, lenient recursion into every child of non-foldable
ConditionalExpression, and eager failures elsewhere. The four concrete kinds
are If, CaseWhen, Coalesce and NaNvl. And/Or are outside that set. Failed
conditional folds carry FAILED_TO_EVALUATE to prevent retries. ConvertToLocalRelation
runs in an earlier batch; its row-wise projection evaluation explains why VALUES
can skip casts that fail while planning the corresponding real-source query.
These are separate required behaviors, not a single lenient optimizer policy.
Fabledec11b85 section6.14 is checked against that source.

Sail represents IF/CASE as Expr::Case and Coalesce as the concrete DataFusion
CoalesceFunc. Spark Nvl2 is RuntimeReplaceable with replacement
If(IsNotNull(expr1),expr2,expr3) (nullExpressions.scala:271–282). Sail's ordinary
NVL2 path instead passed all three arguments to DataFusion NVL2Func, whose
coerce_types includes the tested argument in the result common type; its
simplify callback rewrites to CASE only later. A fresh Spark16/parent226 CLI16
probe demonstrates wrong string results and rejection of array/boolean tests.
The next source unit normalizes NVL2 through the existing IF builder and the
analyzer's shared CASE coercion helper, retaining the date/timestamp conversion.
An initial candidate passed native119/public300+67 yet failed the existing NVL2
common-type feature: CASE types are inspected before the analyzer runs. The
revised unit must therefore coerce branches during lowering, with type tests
before analysis and public typeof checks. Preserve that failed candidate and
its4pass/1fail feature result. This is a directly exercised prerequisite for
matching conditional folding and type coercion.

DataFusion55.2 ExprSimplifier runs private ConstEvaluator before its private
algebraic Simplifier in every cycle. There is no public API to disable only
constant evaluation. ConstEvaluator preserves most failed folds but propagates
Cast/TryCast over literal failures; neither policy implements Spark's recursion.
Replacing Sail's default SimplifyExpressions rule alone would leave direct
ExprSimplifier users: Sail constant/identifier/window resolution, session timestamp,
Delta/Iceberg predicate conversion; DataFusion decorrelation and UDF preimage
simplification also call it. A replacement design must account for those callers,
existing algebraic rewrites, type/field metadata, and deferred-failure persistence
across optimizer passes. Merely prepending an eager pass does not protect a
failed raw Cast beneath a conditional from a later DataFusion pass.

NaNvl needs an execution audit before activation too: DataFusion's concrete
NanvlFunc (functions/math/nanvl.rs) evaluates two ordinary arguments, whereas
Spark's eval reads the right only when the non-null left is NaN. A conditional
classification alone cannot establish lazy value/error semantics. Do not use
function names or generic short_circuits flags as the Spark conditional set.
No new folding rule, masking wrapper, dependency fork, scalar routing or replay
mode is selected by this checkpoint. Required next work is the replacement
mechanism and executable real-source/local-relation phase tests; the existing
source/phase and decimal SQL failures remain required.

Fable1388873f/257368dc proposes retaining DataFusion optimization after a Spark
folding pre-pass. This is viable only with an inventory proving every fallible
raw Cast/TryCast reachable in a deferred context eliminated or nonthrowing,
including implicit coercions, non-string casts and nested/extension types.
Typed string UDF routing alone is insufficient. Coercion must precede that
pass. CF-0408 corrects the claim that VALUES needs no treatment: the eager
pre-pass itself would raise the bad cast over VALUES(NULL), losing the already
verified skipped result, unless equivalent row-wise local evaluation occurs
first. Keep source identity, phase and row-order cases in acceptance. No phase
requirement is waived by observing that later ordinary execution is lazy.


## Qualified NVL2 prerequisite and next shared coercion unit (CF-0410)

Sail982877d859bed7b7e82662d6873a6b7f88eb04a3 is committed and
[qualified](evidence/nvl2-conditional/README.md):119plan+51optimizer pass with
one existing ignored, formatting/strictClippy, unchanged control0/2, fresh
public300+upstream67, all6 NVL2 feature scenarios. Spark16/final16 matches every
row and12schemas, versus parent2rows/1schema. Four cast/CASE nullability gaps
remain. Fable92bce2d3 accepts the revised lowering; the final source only fixes
an adjacent documentation-comment placement and is independently gated.

The same packet retains a fresh8-case Spark/final-CLI follow-up: typeof of
ordinary IF or CASE with Int32/Int64 or Int32/decimal branches reports int in
Sail and bigint/decimal(11,1) in Spark, both ANSI settings. The next separate
human-reviewable source unit should apply the shared coercion before those
expressions expose their type, then remove the NVL2-specific wrapper if redundant.
Native tests must inspect types before analysis; public typeof and temporal
cases must pass. This inherited gap is not declared fixed by the NVL2 unit.
