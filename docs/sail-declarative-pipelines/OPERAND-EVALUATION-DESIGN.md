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
