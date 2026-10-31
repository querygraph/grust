# Operand evaluation: unit reviews

Continues §11–§12 of `FOLDABILITY-PROVENANCE-REVIEW.md`, which passed its
practical length. Read-only reviews of Codex's operand-evaluation units; Spark
`617618396`, DataFusion 55.2.0.

## 1. Unary numeric divisor guard, candidate `b857dabb7` (CF-0347)

Parent `5a1142bcd`. `SafeNumericDivisor` (`sail-function/src/scalar/math/divisor.rs`)
is a unary `Immutable` UDF with four name-coded variants
(`spark_divisor_{ansi,legacy}_{divide,remainder}`), registered stateless in
the codec (`codec.rs`, decode by name, encode by `is::<SafeNumericDivisor>()`).
`make_safe_divisor` (`sail-plan/.../math.rs`) now emits
`guard(divisor)` for numeric or `Null` divisor types and keeps the previous
`CASE` path for everything else; `ZeroDivisionKind::error()` is the shared
structured constructor.

### 1.1 Array validity and value semantics, checked against the source

- `return_type` returns the input type; `return_field_from_args` clones the
  input field with `nullable = true`, so metadata survives and the result is
  nullable as Spark's `DivModLike` is. Tested for `Float16`, `Decimal32/64/
128/256` and metadata (`divisor_tests.rs:28–88`).
- Zero detection is `eq(array, zero)` with `ScalarValue::new_zero(type)`,
  plus `or(.., eq(array, -zero))` for floating types. Arrow's `eq` yields
  `null` for null rows and `or` propagates nulls, so a null divisor never
  counts as zero and `true_count()` ignores it; `-0.0` is caught by the
  second test (probe 9 says Spark treats it as zero); `NaN` and infinities are
  not equal to zero under total order and pass through, matching Spark's
  `NaN` result; decimals compare by value at the input's precision and
  scale. Sliced arrays go through `to_array` and `nullif` with offsets
  respected (`:91–142`).
- ANSI: any zero row in the batch raises the typed error; Spark raises on
  the first zero row it reaches, so the outcome for a batch is the same.
  Legacy: `nullif(array, zeros)` nulls exactly the zero rows; a scalar zero
  returns a typed null scalar. A `Null`-typed input is returned unchanged.
- Single evaluation: the divisor is one function argument, so no second
  syntactic occurrence and no `CASE` predicate for `CaseExpr::nullable` to
  pre-evaluate (§12.4–12.5). The counter regression in `arithmetic_tests.rs`
  pins once-per-row-set for an alternating volatile divisor.

No change requested on the guard itself. Three things to check before
advancement, none a defect in the file:

1. **Decimal result types end to end.** The previous `nullif(divisor, lit(0))`
   went through DataFusion's `nullif` coercion, which can widen a decimal
   divisor against the `Int32` zero; the guard is strictly type-preserving.
   That is the right direction, but the division's result precision and
   scale for decimal operands may differ from before, so the decimal rows of
   the arithmetic replay should be compared against Spark, not only against
   the previous Sail output.
2. **The non-numeric fallback keeps the `CASE`.** For a divisor whose
   resolved type is not numeric (a string that DataFusion will coerce later),
   `make_safe_divisor` still builds `CASE WHEN divisor = 0 …`, so the
   duplication and the planning-time predicate evaluation of §12 remain on
   that path. Spark coerces string operands to double at analysis; casting
   such divisors to `Float64` before the guard would retire the `CASE` path
   entirely. A follow-up, with a probe for `'1' / '0'` under both modes.
3. **Guard inside a `CASE` predicate.** `CaseExpr::nullable` replaces column
   references with nulls before pre-evaluating a predicate, so a guarded
   division over a column yields `NULL` there; a literal zero divisor in a
   predicate (`CASE WHEN 1 / 0 > 0 …`) makes the guard raise during that
   pre-evaluation, which `evaluate_predicate` treats as "not evaluable" and
   ignores. No failure, but worth one fixture so the behaviour is pinned
   rather than incidental.

Still open, as CF-0347 states: NULL dividend, right-first order, `DIV`
domain errors, `pmod`, and the generic `CASE` dependency.

### 1.2 Oracle rows for the three checks (CF-0349)

Probe 10 (`probe10_string_arith_decimal_types.py`, appended to
`evidence/set-catalog-oracle/output.txt`, classic mode, ANSI toggled at
runtime with `spark.conf.set`):

| Query                                                  | ANSI on                                            | ANSI off                      |
| ------------------------------------------------------ | -------------------------------------------------- | ----------------------------- |
| `'7' / '2'`, `'1' / '0'`, `'7' % '2'`                  | `DATATYPE_MISMATCH.BINARY_OP_WRONG_TYPE`           | `3.5`, `NULL`, `1.0` (double) |
| `7 / '2'`, `1 / '0'`                                   | `3.5`, `DIVIDE_BY_ZERO` (string coerced to double) | `3.5`, `NULL`                 |
| `'7' DIV '2'`                                          | `DATATYPE_MISMATCH.BINARY_OP_WRONG_TYPE`           | same                          |
| `DECIMAL(10,2) / DECIMAL(10,2)`                        | `decimal(23,13)`                                   | same                          |
| `DECIMAL(10,0) / DECIMAL(10,0)`                        | `decimal(21,11)`                                   | same                          |
| `DECIMAL(38,0) / DECIMAL(38,0)`                        | `decimal(38,6)`                                    | same                          |
| `DECIMAL(10,2) / 3`                                    | `decimal(14,6)`                                    | same                          |
| `DECIMAL(10,2) % DECIMAL(10,2)`, `DECIMAL(10,2) DIV …` | `decimal(10,2)`, `bigint`                          | same                          |
| `CASE WHEN x > 0 THEN x ELSE 2 END` over non-null `x`  | `int`, nullable `false`                            | same                          |
| `CASE WHEN x > 0 THEN x END`                           | `int`, nullable `true`                             | same                          |

Corrections and consequences:

- My §1 note said Spark coerces string operands to double at analysis. That
  holds for a string operand paired with a numeric one in both modes, and for
  two string operands only outside ANSI; under ANSI two string operands are a
  `DATATYPE_MISMATCH`. CF-0349 reports the two-string cases rejected in
  _both_ modes; my runtime-toggled run accepts them outside ANSI, so the
  mode under which that probe ran is worth confirming before the domain
  investigation records it. Either way a blanket cast is wrong, and the
  non-numeric fallback's right target is mode-dependent: reject two strings
  under ANSI, coerce the string side to double otherwise.
- Decimal division types are Spark's `DecimalPrecision` rule (integer digits
  `p1 - s1 + s2`, scale `max(6, s1 + p2 + 1)`, then the 38-digit adjustment),
  which is how `(10,2)/(10,2)` reaches `(23,13)` and `(38,0)/(38,0)` reaches
  `(38,6)`. Sail's `(16,6)` versus `(18,8)` in CF-0349 is therefore a
  pre-existing rule gap in the decimal arm of `spark_divide` (the `TODO` at
  `math.rs` about precision and scale after division says as much), not an
  effect of the guard; the parent run will show the same numbers.
- `CASE` nullability: Spark's `CaseWhen.nullable` is false when every branch
  and the `ELSE` are non-nullable; DataFusion's `CaseExpr::nullable` is the
  function §12.4 found pre-evaluating predicates, and it reports nullable
  here. A generic gap, as CF-0349 classifies it.

## 2. `SparkDivModLazy`: challenge of the three-lambda design (CF-0353)

Read only, Sail `b857dabb7`, the vendored DataFusion 55.2.0 with lambda
support. CF-0353 proposes an internal higher-order UDF with three lambdas
(right thunk, left thunk, native operation over the two values), evaluated
row-major in one pass through `evaluate_lambda_rows`, so that each operand
runs at most once per row in Spark's order and the typed divisor guard still
raises after the left value is known.

### 2.1 What the seams already give

- `HigherOrderUDFImpl` (`datafusion-expr/higher_order_function.rs:523–808`)
  with `lambda_parameters`, `return_field_from_args` and `invoke_with_args`
  over `HigherOrderFunctionArgs`; `LambdaArgument::evaluate(params, spread_captures)`
  (`physical-expr/higher_order_function.rs:236,372`) evaluates a body on a
  batch laid out `[captures..., params...]`, where `spread_captures` decides
  which rows of the captured columns the body sees. `ConvertTzLazy` and
  `SparkSequenceLazy` use it through `evaluate_lambdas_until_null`
  (`functions_nested_utils.rs:70–118`), which is batch-major with a shrinking
  active-row set, and `evaluate_lambda_rows` (`:61`), which takes the
  captures for an explicit row list; `scatter_active_rows` puts a compact
  result back. Lambda parameters are inferred by `LambdaParametersProgress`
  (`sail-plan/function/scalar/lambda.rs:125`); the lowering site for a lazy
  UDF is `datetime.rs:894`.
- Lambdas survive the pipeline: Sail's `TypeCoercion` resolves lambda bodies
  through `value_fields_with_higher_order_udf` (`type_coercion.rs:1094–1107`);
  `ResolveLambdaVariables` refreshes variable fields after folding
  (`resolve_lambda_variables.rs:20–27`); `tree_node.rs:116,346` descends into
  bodies, so `expr_to_columns` sees captured columns and
  `OptimizeProjections` keeps them; `PushDownFilter` treats `Lambda` as an
  ordinary node (`push_down_filter.rs:268`); the proto and Sail's codec
  carry `LambdaExpr`/`LambdaVariable` and `HigherOrderFunctionExpr`
  (`codec.rs:4917–4934,7893–7915`). Distributed encoding is therefore the
  existing path, plus one name-keyed entry for the new UDF.

### 2.2 Challenges

1. **Row-major single pass is a blanket slow path on the hottest operator.**
   `evaluate_lambda_rows(lambda, rows)` builds a `UInt64Array`, `take`s every
   captured column for the row set, allocates a `NullArray` dummy, and
   evaluates the body on that batch. A row-major loop does this once per row
   per thunk: three body evaluations and two capture `take`s per row, each a
   kernel dispatch on a one-row batch. Division appears in nearly every
   analytical query; this would replace one vectorised kernel over a batch
   with thousands of one-row evaluations. CF-0353 says per-row is the
   correctness baseline, not a performance claim, and asks for a fast-path
   argument before activation. Here it is: Spark's row-local rules (right
   first; skip left when right is null or, outside ANSI, zero; skip the
   operation when left is null; raise only then) are preserved by
   batch-major evaluation with selection, which is exactly what
   `evaluate_lambdas_until_null` already does: evaluate the right thunk over
   the batch once, compute the active set (right not null, and not zero
   outside ANSI), evaluate the left thunk once over the `take` of that set,
   drop rows whose left is null, run the native operation over the survivors,
   then the typed zero check, then scatter. Every operand is evaluated at
   most once per row, no row is replayed, and the guard raises after the
   left value is known. The only thing it does not reproduce is the order in
   which errors from _different rows_ surface when one row fails in the right
   thunk and an earlier row would have failed in the left thunk. That
   cross-row ordering is not a Spark-defined semantic: Spark's own
   whole-stage codegen is row-major within a partition but partitions race,
   so the first error of a multi-error batch is already non-deterministic
   across the job, and no public outcome depends on it. I would make
   batch-major the design, with the convert_tz note's row-major caveat kept
   as the one documented difference, rather than ship per-row for every `/`.
   If row-major must be kept as a mode, it should be opt-in by configuration
   with a measured cost, never the default. Also, when the active set is the
   whole batch, pass the captures straight through instead of `take`-copying
   them; `evaluate_lambda_rows` always copies today.
2. **A lambda-lowered division is not a constant expression to the
   simplifier or the identifier checks.** `ConstEvaluator` excludes
   `Expr::Lambda` (`expr_simplifier.rs:700–701`), and
   `require_constant_expression` admits only the listed variants
   (`constant.rs`, `Expr::ScalarFunction` with a volatility test, everything
   else non-constant). Division becomes `Expr::HigherOrderFunction`
   (`datafusion-expr/expr.rs:429`), so `SELECT IDENTIFIER(CAST(4 / 2 AS STRING))`
   and `SET CATALOG IDENTIFIER(...)` would turn `NOT_CONSTANT`, the §11
   arithmetic replay rows would regress, and `SELECT 1 / 2` would stop
   folding at plan time. Activation therefore needs the identifier
   allow-list to admit the new UDF with its three bodies checked by the same
   walk, and the `LiteralEvaluator` path to evaluate it (it goes through
   `create_physical_expr`, which already plans `HigherOrderFunctionExpr`, so
   that part is fine). Test these before the lowering unit, not after.
3. **`CommonSubexprEliminate` stops at lambdas** (`common_subexpr_eliminate.rs:733–734`):
   nothing inside a body is extracted and nothing from a body is shared with
   the rest of the projection. `(a + b) / c` and `(a + b) * 2` in one
   `SELECT` lose the shared `(a + b)` once the first becomes a lambda body;
   today both are plain expressions and CSE extracts the sum. Measure on a
   representative projection before accepting; it is the second performance
   cost after item 1.
4. **Nested and extracted operands.** `WindowRewriter`, `ExplodeRewriter`
   and the aggregate rewrite run as `TreeNodeRewriter`s after lowering
   (`project.rs:38–43`), and `transform` descends into lambda bodies
   (`tree_node.rs:346`), so a window or aggregate operand inside a thunk is
   still replaced by a column of the new input node and then captured. A
   division inside another lambda (`transform(arr, x -> x / y)`) nests
   `LambdaVariable`s; the fresh-parameter helper must allocate indices that
   do not collide with the enclosing lambda's, and
   `ResolveLambdaVariables` must refresh both levels. One fixture each.
5. **Optimizer handling of conditional bodies.** `SimplifyExpressions`
   does rewrite inside bodies (`transform` descends), which is what you
   want for `CAST` elimination, but `ConstEvaluator` will not fold a body
   that references a lambda parameter, so a thunk over a literal (`1 / 2`)
   stays unevaluated until execution; combined with item 2 this is the
   plan-shape change to expect in `EXPLAIN` and in any test asserting folded
   literals.
6. **Field inference order.** `LambdaParametersProgress` infers the
   operation lambda's parameter fields from the thunks' result fields, so the
   operation body is typed only after both thunks resolve; Sail's
   `TypeCoercion` must then coerce inside the operation body (decimal
   precision rules, the §1.2 types) with the thunk fields as the inputs. The
   result field is the operation's with `nullable = true` and metadata
   retained, as CF-0353 says; the §1.2 decimal rows are the oracle.

Summary: the component is sound and the seams exist; the objections are to
row-major as the default and to activating without the identifier and
constant-folding consequences handled. Pure component tests first, as
CF-0353 proposes, with the batch-major selection variant measured against
the row-major one on the same fixture.

### 2.3 Candidate `89599e5cc`, read against its diff

Four `sail-function` paths, no lowering or codec. `SparkDivModLazy`
(`math/div_mod_lazy.rs`): `HigherOrderSignature::exact` of three lambdas,
`Immutable`; `lambda_parameters` gives the two thunks a dummy `Null`
parameter and the operation `[left, right]` from the thunk fields, `Partial`
until both are known; `return_field_from_args` validates the divisor type
(numeric or `Null`) and returns the operation field with `nullable = true`;
`short_circuits()` is true; `coerce_value_types` admits no value arguments.
`invoke_with_args` loops rows: evaluate the right thunk on the row, return
`NULL` if it is null or, outside ANSI, zero (via the shared
`numeric_zero_mask`, extracted from `divisor.rs` so `±0` and decimals have
one definition); else evaluate the left thunk on the row, return `NULL` if
null; else evaluate the operation with the two one-row arrays as parameters
and the row's captures; `concat` the one-row chunks. This is Spark's
`DivModLike.eval` order exactly, each thunk at most once per row, no replay,
and the ANSI zero error comes from the operation body's guard after the left
is known. The tests pin right-first/null/legacy-zero skips with a call trace,
first-row error before a later right operand, `±0`/`NaN`/`inf`/empty batch,
field metadata and admission, and an optimizer pass that keeps a
conditional failing operand and a captured column. As a correctness
baseline it is right; no change requested to the component.

Two things to verify by fixture before it meets lowering:

- **CSE through a lambda body.** `Expr::is_volatile_node` matches only a
  `ScalarFunction` with `Volatile` signature (`datafusion-expr/expr.rs:2159–2160`);
  the `HigherOrderFunction` node is `Immutable`. `CommonSubexprEliminate`
  refuses to extract `Lambda`/`LambdaVariable` nodes and volatile nodes
  (`common_subexpr_eliminate.rs:701–704`) and its `test_volatile` shows a
  volatile _descendant_ protects an ordinary parent; whether that protection
  travels through a `Lambda` child to the HOF node is what decides if two
  identical `spark_divmod_lazy` calls with `rand()` in a thunk get merged
  into one evaluation, which would break the cardinality this component
  exists for. One fixture with two such calls in a projection settles it.
- **Per-row cost shape.** Each row does two `take_arrays` of the captures,
  a `NullArray` dummy, up to three body evaluations on one-row batches, and
  a `new_null_array`/`concat` at the end. Fine for a baseline, not for
  activation (§2.2 item 1, revised below).

### 2.4 Cross-row error selection: Spark's rule, observed, and the fast path it allows

CF-0355 did not accept that cross-row error order is unobservable, and it
was right. Probe 11 (`probe11_cross_row_error_order.py`, appended to
`evidence/set-catalog-oracle/output.txt`), ANSI on, `local[1]` and
`local[2]`, whole-stage codegen on and off, with row 1 failing on the left
operand (`raise_error`, `USER_RAISED_EXCEPTION`) and row 2 on the right
(`CAST('y' AS INT)`, `CAST_INVALID_INPUT`):

| Rows                                     | Spark 4.2.1 (all four configurations) |
| ---------------------------------------- | ------------------------------------- |
| row 1 left fails, row 2 right fails      | `USER_RAISED_EXCEPTION`               |
| row 1 right fails, row 2 left fails      | `CAST_INVALID_INPUT`                  |
| row 1 left raises, row 2 divides by zero | `USER_RAISED_EXCEPTION`               |
| row 1 divides by zero, row 2 left raises | `DIVIDE_BY_ZERO`                      |
| the first case under `REPARTITION(2)`    | `USER_RAISED_EXCEPTION`               |

Within a partition Spark is strictly row-major and the first failing row's
error is the public outcome, in both interpreted and generated code; only
the cross-partition case is scheduling-dependent, and the two-row
repartition did not even separate the rows. So §2.2 item 1's claim that the
order is "not a Spark-defined semantic" is withdrawn for the same-partition
case: a selected-batch evaluation that runs the right thunk over the whole
batch first would report `CAST_INVALID_INPUT` where Spark reports
`USER_RAISED_EXCEPTION`, and that is public metadata.

The fast path survives in a narrower, exact form, and Spark's own contract
says where the line is. `Expression.deterministic`'s documentation
(`Expression.scala:118–131`): "The non-deterministic expressions should not
change in number and order. They should not be evaluated during the query
planning." Deterministic expressions carry no such contract, and Spark
re-evaluates them freely (task retries re-run a deterministic projection).
Therefore:

- When every thunk is deterministic (no `Volatile` function in any body),
  evaluate batch-major with selection: right over the batch, left over the
  selected rows, operation over the survivors. If every step succeeds the
  result is identical to row-major and nothing was evaluated twice. If any
  step errors, discard and re-run the same batch row-major from the first
  row; the first failing row's error is then Spark's. Replaying a
  deterministic batch is within Spark's contract, and the cost lands only
  on the error path, which terminates the query anyway.
- When any thunk is nondeterministic, run row-major from the start: the
  at-most-once-per-row and order contract forbids replay, and exact error
  order requires it. This is the rare path, and it is the component as
  committed.

`SimplifyExpressions`-style volatility detection over the three bodies
(`Expr::is_volatile`, recursive, `expr.rs:2170`) decides the mode at
lowering, so the physical function can carry it as a flag. The remaining
caveat is cross-partition, which Spark leaves to scheduling in both
engines. With this, the §2.2 performance objection and CF-0355's
observability objection are both met without a documented deviation.

### 2.5 Replay-safe classification for the deterministic fast path (CF-0357)

CF-0357 accepts the deterministic batch-then-replay path as a candidate
subject to three conditions. Proposed predicates, read-only:

- **Replay-safe thunk.** No `Volatile` descendant in any of the three
  bodies (`Expr::is_volatile`, recursive). `Stable` functions (`now()`,
  `current_date()`, `current_timestamp()`) are deterministic within a
  query by DataFusion's definition and Spark's (`CurrentTimestampLike` is
  foldable, evaluated once per query at `ComputeCurrentTime`), so they do
  not block the fast path. A registered Python UDF declared deterministic is
  replay-safe by Spark's own contract (task retries re-run it); one declared
  nondeterministic is `Volatile` in Sail (`pyspark_udf.rs:57–58`) and takes
  the row-major path. Decide at lowering, carry as a flag on the physical
  function, never re-derive at execution.
- **Replayable error.** Replay only when the batch step failed with a
  _data_ error, the kind a row-major pass would reproduce on the same row:
  `DataFusionError::External(StructuredSparkError)` carrying a data
  condition (`DIVIDE_BY_ZERO`, `REMAINDER_BY_ZERO`, `CAST_INVALID_INPUT`,
  `USER_RAISED_EXCEPTION`, …), `ArrowError`-derived compute and cast
  errors, and `Execution` errors raised by a UDF body. Never replay
  `ResourcesExhausted`, I/O, cancellation or internal errors
  (`CommonErrorCause::build` already classifies these,
  `common-datafusion/error.rs`): those propagate unchanged, because the
  row-major rerun would only hide the real cause or double the resource
  use. A conservative first cut is an allow-list of replayable classes with
  everything else propagated; a mis-classified replayable error then costs
  Spark's error order on that one class, never correctness.
- **Cancellation.** The replay runs inside the same `invoke_with_args`
  call on the same batch, so task cancellation reaches it the way it
  reaches any kernel: there is no new stream, no retained state, and the
  partial batch-major results are dropped before the rerun. No new
  cancellation surface.

With the CSE fixture now pinned (two identical lazy calls over a volatile
thunk evaluate exactly twice, zero at frame construction), the remaining
activation conditions are the §2.2 items 2–6 and the measured cost of both
modes on the same fixture.

### 2.6 Component committed; cost figures; narrowing of the replayable set (CF-0359)

Codex committed the pure component as `c1befda7a` (four `sail-function`
paths, lowering/codec/proto identical to `b857dabb7`, no activation). Its
test-only probe `9cdfb015c` shows the two orders diverging on the same
fixture (row-major reports the row-0 left error, selected-batch the row-1
right error) with identical successful 1024-row outputs, and an unoptimized
shared-host diagnostic of about 80× native for row-major and about 2.9×
native for selected-batch over 20 evaluations: not a production estimate,
but it settles the direction of §2.2 item 1. Accepted correction to §2.5:
a UDF's `Execution` error does not by itself establish a reproducible data
failure (a worker crash or exhaustion also arrives as `Execution`), so the
replayable set should start from structured data conditions and Arrow
compute/cast errors only, and admit UDF failures per source chain after
review, as CF-0359 says. Remaining prerequisites before lowering are
unchanged: identifier constant validation and folding (§2.2 item 2),
operation fields and fresh names, nested/extracted/window contexts, CSE
cost, and optimized representative measurements.

## 3. Codec unit `f8ba01b87` and the scoped constant-validation design (CF-0361)

### 3.1 Codec, read against its diff on `c1befda7a`

Five paths. `physical.proto` appends `SparkDivModLazyUdf div_mod_lazy = 13`
to the `HigherOrderUdf` oneof with one field, `bool ansi_mode = 1`;
`decode.rs` constructs `SparkDivModLazy::new(ansi_mode)`; `encode.rs`
downcasts and writes the mode; the lambda bodies, parameter names and
captures go through the unchanged `RemotePhysicalProtoConverter`
(`LambdaExprNode.params`, `LambdaVariable` by index and field,
`extend_lambda_schema` laying captures before parameters). The three tests
round-trip through `try_encode_physical_expr`/`try_decode_physical_expr`
and _execute_ original and decoded: both modes × both kinds with the unary
guard in the operation body (structured `22012` errors with the right
condition under ANSI, `NULL` outside), an operation that uses only its right
parameter plus a captured column at a non-prefix offset, and a one-row batch
whose left thunk would raise but is skipped because the right is `NULL`
(both modes) or zero (legacy). Wire semantics: an absent or zero `ansi_mode`
decodes to legacy, the non-raising mode, which is the safe default for a
missing field; a worker older than tag 13 rejects the unknown oneof variant
rather than guessing. No change requested.

### 3.2 The scoped visitor for `require_constant_expression`

The design in CF-0361 is the right shape and matches §2.2 item 2. Points to
hold while writing it:

- **Scope by name, as DataFusion does.** `Lambda.params` is `Vec<String>`
  and `LambdaVariable` carries `name` and an optional `field`
  (`datafusion-expr/expr.rs:1472–1477,519–522`), so the visitor's stack holds
  parameter names pushed on entering each of the three `Lambda` arguments
  and popped on exit; a `LambdaVariable` is admitted only if its name is on
  the stack, inner names shadow outer, and the thunks' dummy parameter counts
  as bound even though no body references it. Anything else that was
  non-constant stays non-constant: a free `LambdaVariable`, a `Column`, a
  `HigherOrderFunction` whose `inner()` is not `SparkDivModLazy`, a `Lambda`
  not in argument position of that HOF.
- **Bodies keep the existing tests.** Inside the bodies the same variant
  allow-list and the same `Volatile`/async scalar rejection apply, so
  provenance (`mark_non_foldable`) and type-only behaviour are unchanged;
  the unary guard and the typed error function are `Immutable` and pass,
  and the evaluation error they raise surfaces from `LiteralEvaluator`
  exactly where Spark raises `DIVIDE_BY_ZERO` from `eval()`.
- **Order of checks is preserved.** `IDENTIFIER(1 DIV 0)` must still be
  `WRONG_TYPE` before any evaluation: `Expr::HigherOrderFunction::to_field`
  resolves the result field through `lambda_parameters` and the operation
  body, so `get_type` yields `bigint` without evaluating, as today.
- **Fixtures named in CF-0361 are the right set**; add
  `IDENTIFIER(CAST(4 / 2 AS STRING))` end to end (today's §11 arithmetic
  rows) so the unit proves the regression it exists to prevent does not
  occur, and `SET CATALOG IDENTIFIER(CAST(1 / 1 AS STRING))` for the wrapped
  catalog form.

### 3.3 Staged converter, candidate `29fb36c79` (CF-0363)

The old converter called `lambda_parameters(0, ..)` once and rejected
`Partial`; the three-lambda evaluator is `Partial` until both thunk bodies
are typed, so it could not be decoded. The candidate loops: call
`lambda_parameters(step, value_or_lambda)`, decode every lambda that has
parameter fields with `extend_lambda_schema` (fields renamed to the
parameter names, the same as the reference's `field.renamed(name)`), record
each body's `return_field` as that lambda's output, and build the
`HigherOrderFunctionExpr` on `Complete`. Compared line by line with
DataFusion's logical-side loop (`datafusion-expr/higher_order_function.rs:1240–1340`),
which is the semantics the physical side must mirror:

| Aspect                                | Reference loop                                                   | Candidate                                                 | Verdict                        |
| ------------------------------------- | ---------------------------------------------------------------- | --------------------------------------------------------- | ------------------------------ |
| `Partial` entry `Some(fields)`        | resolve body with fields, set the lambda's output field          | same, by re-decoding the body                             | match                          |
| `Partial` entry `None`                | leave the lambda's current field _unchanged_                     | **clears** it: `decoded_values[i] = None`, `Lambda(None)` | diverges; mirror the reference |
| `Partial` length ≠ number of lambdas  | error                                                            | shorter → error; longer → extra sets ignored              | mirror: exact count            |
| `Complete` length ≠ number of lambdas | error                                                            | shorter → error at construction; longer → ignored         | mirror: exact count            |
| declared params > provided fields     | error                                                            | error                                                     | match                          |
| duplicate parameter names             | error (`all_unique`)                                             | error via `LambdaExpr::try_new` (`lambda.rs:65–68`)       | match                          |
| iteration bound                       | steps `0..=limit`, error when `step > limit` (`limit + 1` calls) | `for step in 0..limit` (`limit` calls)                    | off by one; mirror             |
| output field of a resolved lambda     | `to_field` of the variable-resolved body                         | `body.return_field(&extended schema)`                     | match                          |
| single-step UDFs                      | `Complete` at step 0                                             | one decode pass, identical to the previous converter      | match                          |

The one semantic divergence is the clearing. In the reference, `None` in a
`Partial` means "nothing new for this lambda this step", and a UDF may
return `None` for a lambda it already typed; the candidate would drop that
lambda's decoded body and field, and either fail with "missing decoded
higher-order argument" at `Complete` or never complete. `SparkDivModLazy`
happens to return `Some` for both thunks at every step, so the tests pass,
but the converter is generic and the next UDF may not. Keep the previous
field when `None` arrives, as the reference does. The two length checks and
the bound are consistency items; a UDF that needs exactly `limit + 1` calls
would decode logically and fail physically today. No evaluation happens in
the loop, as CF-0363 says, and the generic `CASE` nullability boundary is
untouched. With the clearing fixed and the counts mirrored, no further
change.

### 3.4 Complete-length leniency: the physical contract is the right one to mirror (CF-0365)

CF-0365 corrects the `None` retention and the inclusive bound, and keeps one
deliberate difference from the logical loop: a `Complete` vector may be
longer than the lambda count, `Partial` vectors must be exact. Checked
against both DataFusion layers:

- Physical: `HigherOrderFunctionExpr::resolve_lambda_parameters`
  (`datafusion-physical-expr/higher_order_function.rs:204–238`) calls
  `lambda_parameters(0, fields)` once with every lambda's return field
  known, rejects `Partial`, and for `Complete` errors only when
  `items.len() < num_lambdas`, with the comment that implementors return
  parameters for all lambdas including optional trailing ones (Spark
  `reduce`), "so we can't do equality check".
- Logical: the planning loop requires equality for `Partial` (`:1266`) and
  for `Complete` (`:1333–1335`).

So the two layers already disagree, and the stricter one is the logical
planner. The converter constructs a physical expression and hands it to
`try_new_with_schema`, which applies the physical rule regardless; a
converter that insisted on equality for `Complete` would reject wire that
the physical constructor accepts, while admitting nothing new, since any
expression that came through logical planning already satisfied equality
there. Mirroring the physical contract is therefore correct, and the
exactness of `Partial` mirrors the only layer that ever sees a `Partial`
beyond step 0, the logical loop. Two notes: the leniency is reachable only
by physical construction or foreign wire (a Spark-`reduce`-style UDF that
returns parameters for an omitted optional lambda is rejected at `:1333`
before it could be planned), which is exactly why a native fixture that
constructs `HigherOrderFunctionExpr` with extra `Complete` sets is the right
proof; and the split into a generic staged-converter unit (two paths, mock
UDF tests, no tag 13) followed by the DivMod proto/encode/decode unit on
that base is the right order, since the first is a dependency fix any
multi-step higher-order UDF needs. No change requested.

## 4. Scoped constant validator, committed `4070e895b` (CF-0370, CF-0371)

Three paths on `036dc6dde`: `resolver/constant.rs` delegates to a new
`constant/validation.rs` (96 lines) and `constant/validation_tests.rs`
(263 lines). Read read-only against the diff and against DataFusion
55.2.0's visitor contract; no Sail edits.

### 4.1 Parity with the old variant

The old `exists` closure listed twenty node kinds as constant and treated
`ScalarFunction` as non-constant when `Volatile` or async; everything else
was non-constant. The visitor's `Frame::Ordinary` arm lists the same twenty
kinds, and its `ScalarFunction` guard is the complement of the old
predicate (`!= Volatile && as_async().is_none()`), so `Stable` functions
stay admitted as before. Every other variant falls to `_ => None`, which
sets `constant = false` and stops. Parity holds; Codex's "ordinary allowed
node sets compared against parent, unchanged" is what the diff shows.

### 4.2 Lexical boundary, read against the visitor contract

`TreeNode::visit` runs `f_down`, then the children only if `f_down`
returned `Continue` (`visit_children`), then `f_up` only if the children
returned `Continue` (`visit_parent`); `Stop` skips `f_up`
(`datafusion-common-55.2.0/src/tree_node.rs:539–572`). `Expr::apply_children`
visits a higher-order function's `args` (`datafusion-expr-55.2.0/src/tree_node.rs:115`)
and a `Lambda`'s `body` (`:346`). Consequences for the frame stack:

- Every `f_down` that returns `Continue` pushes exactly one frame and the
  matching `f_up` pops it, so the stack is the lexical ancestry of the
  current node. A `Stop` leaves the stack dirty, but the visitor is
  discarded, so nothing reads it.
- `Expr::Lambda` is admitted only when the top frame is `Evaluator`, which
  is true only for a direct argument of an admitted `SparkDivModLazy`
  (sibling frames are popped before the next argument is entered). A
  lambda inside a body, a lambda under an alias, or a lambda argument of
  any other higher-order function is rejected; the tests cover all three.
- `LambdaVariable` is admitted when any enclosing `Lambda` frame declares
  its name. That is lexical capture, including across a nested evaluator,
  which is what `LambdaArgument::evaluate(params, spread_captures)`
  implements at runtime (§2.1), so the nested test's `6` is the right
  answer and not a leak.
- Admission of the evaluator is by exact Rust type (`Any::is`), argument
  count three, and all arguments literally `Expr::Lambda`. The same-name
  spoof is rejected by the type test.

What the visitor does not check, and why that is fine here: lambda
parameter counts (1, 1, 2) and types. Those are decided by
`lambda_parameters`/`return_field_from_args` during type inference, which
the `eligible_expressions_preserve_type_null_and_error_evaluation_phases`
test shows runs before any evaluation (type `Int32` first, `DIVIDE_BY_ZERO`
only on `evaluate`). A malformed internal expression therefore still errors,
and before any thunk runs. Codex's split (foldability here, arity there) is
the right one.

### 4.3 Verdict

Accept. The lexical boundary is exact under the visitor contract, old
variant parity holds, volatile and provenance descendants are rejected
without invocation (`counter == 0`), and the `IMMUTABLE` async fixture
exercises the async predicate on its own. The two end-to-end identifier
fixtures from §3.2 remain activation items, and Codex's point stands that
before lowering they would exercise the old expression rather than prove
new-HOF admission.

## 5. Generic staged decoder `04f1e8cc7` and DivMod codec `036dc6dde` (CF-0367, CF-0368)

### 5.1 Decoder, against the §3.3 and §3.4 checklist

- `Partial` `None` is retained: the loop `continue`s past a `None` entry
  and leaves `decoded_values[index]` and `value_or_lambda[index]` as the
  previous step left them. The `RetainNone` mock fails at step 2 with
  "previous lambda output was lost" if either is dropped, so the test is
  not vacuous.
- The step range is `0..=lambda_parameters_max_iterations`. The logical
  loop calls step 0, and after each `Partial` increments and errors only
  when `step > limit` (`datafusion-expr-55.2.0/src/higher_order_function.rs:1312–1327`),
  so its last call is at `step == limit`; the decoder makes the same calls.
  Codex's CF-0367 wording "make limit exclusive (including 0)" does not
  describe the committed code; the committed code and the test
  `resolution_includes_zero_and_last_allowed_steps` (limits 0, 1, 2) are
  the inclusive bound, which is the correct one.
- `Partial` counts must equal the lambda count; `Complete` may be longer
  but not shorter. That is the physical `HigherOrderFunctionExpr`
  contract (`datafusion-physical-expr-55.2.0/src/higher_order_function.rs:218–231`)
  rather than the logical one, as argued in §3.4; the `CompleteCount(2)`
  mock proves the decoded arguments construct a real physical expression.
- Over-declared lambda parameters (`params.len() > fields.len()`) are
  rejected; under-declared are accepted through the `zip` in
  `extend_lambda_schema` (`converter.rs:407–413`), matching the physical
  `LambdaExpr` rule that trailing lambda parameters are optional.
- The final pass re-decodes every lambda body against the `Complete`
  fields and discards the partial-pass bodies; `body.return_field` is
  computed only on partial passes. Codex's "extra final-pass
  `body.return_field` work is avoided" is accurate.
- Failing bodies (`SparkZeroDivisionError`) decode without invocation, so
  the decoder never evaluates wire.

### 5.2 Codec

Tag 13 is unused in the `HigherOrderUdf` oneof (1–12 taken);
`SparkDivModLazyUdf { ansi_mode }` is encoded by downcast and decoded by
construction, the same shape as the other HOF arms. The four tests
evaluate the original and the decoded physical expression on the same
batches:

- Three-row skip semantics in both modes and both kinds: `(NULL, 0)`,
  `(8, 2)`, `(8, NULL)` give `NULL, 4|0, NULL`. The first row is `NULL`
  under ANSI because the dividend-null check precedes the ANSI zero check
  in `DivModLike.eval` (§1.2, probe 8), so the test pins the order, not
  only the values.
- `(8, 0)` under ANSI surfaces `org.apache.spark.SparkArithmeticException`,
  `DIVIDE_BY_ZERO`/`REMAINDER_BY_ZERO`, SQLSTATE `22012`, `config` =
  `"spark.sql.ansi.enabled"` after the round trip; legacy returns `NULL`.
- A captured column (`offset`) and a non-prefix parameter
  (`_right_value` alone) survive the wire.
- A failing left thunk stays skipped on a one-row batch in both modes.
- Malformed wire: a missing third lambda fails in
  `SparkDivModLazy::lambda_parameters` ("three lambda arguments"); an
  over-declared lambda fails in the decoder.

Verdict: accept both units. Together they satisfy the §3.1 and §3.3
checklists, and the `Complete` leniency is the physical contract as
settled in §3.4.

## 6. Fast-path and replay design checkpoint (CF-0372, CF-0373, CF-0375, CF-0376)

### 6.1 Raw error classification: verified, and a challenge to the direction of the list

Codex's finding is in the source: `CommonErrorCause::build` maps
`DataFusionError::Execution`, `ExecutionJoin` and `ResourcesExhausted` all
to `CommonErrorCause::Execution`
(`crates/sail-common-datafusion/src/error.rs:188–190`), and the
`Collection` arm picks the first non-retryable member. That enum is a
transport and job policy; it cannot decide replay. Agreed.

The challenge is to the shape of the predicate, not its inputs. Under the
proposed fast path (batch first; on an _admitted data error_ discard the
partial arrays and run the ordered row evaluator once), the two ways the
predicate can be wrong are not symmetric:

- A false negative (a real data error the allow-list does not recognise)
  propagates the batch error, which may be the wrong row's error: the
  retained counterexample reports right-row 1 where the ordered evaluator
  reports left-row 0. That is a silent deviation from Spark's row-major
  first-error rule (§2.4, probe 11), and the user cannot tell.
- A false positive (a system error replayed) costs one ordered re-run of a
  body that is already proven deterministic and side-effect free. The
  outcome is the same system error again, or success where the ordered
  path's smaller peak memory avoids the exhaustion. For `ExecutionJoin`
  from cancellation the enclosing future is being dropped and replay
  observes nothing new.

So the predicate pays in correctness on one side and in latency on the
other. The list should therefore be a short deny-list of errors for which
replay is pointless or harmful (`ExecutionJoin`, `CommitStateUnknown`,
and `ResourcesExhausted` if fail-fast is wanted), with every other error
from an admitted body replayed, rather than an allow-list that must
enumerate every data-error shape to stay correct. Two rows of the
prototype matrix show why: `opaque_source` (an unknown envelope whose
source is the Spark `DIVIDE_BY_ZERO` structured error) classifies as
non-data and is not replayed, while `CommonErrorCause` reports the same
error to the client as `Structured`, so the client sees a Spark data
error from possibly the wrong row; and `collection_mixed` refuses replay
although its data member is the one Spark would have raised first. Under
a deny-list both replay, and the "direct `Execution` is a data error only
because admission excludes arbitrary UDFs" special case disappears,
because admission is doing that work already. The admission policy itself
(ordered by default; batch only for an exact native class set, with
unknown UDFs, HOFs, async, volatile, provenance and subqueries ordered)
is the right one and is not challenged.

### 6.2 Conditional casts: Codex's oracle does not generalise beyond `VALUES`

CF-0373 concluded from a sixteen-query Spark run that "right NULL always
returns NULL" for `CAST('bad' AS T) / d`, and from that derived a
"crucial activation prerequisite" that Sail's optimizer must not fail the
cast before lazy evaluation. The oracle's source was `VALUES`. Probe 12
(`evidence/set-catalog-oracle/probe12_cast_laziness_by_source.py`,
output `probe12_output.jsonl`, 56 cases, Spark 4.2.1 `local[1]`) varies
the source and the shape, with `explain()` forced before `collect()` so a
plan-time failure is distinguishable from an execution failure. For each
of `INT`, `DOUBLE`, `DECIMAL(5,2)`, `DECIMAL(38,10)` the result is the
same:

| shape                                                                   | ANSI                                           | legacy |
| ----------------------------------------------------------------------- | ---------------------------------------------- | ------ |
| `… / d FROM VALUES (CAST(NULL AS INT))`                                 | `NULL`                                         | `NULL` |
| `… / d FROM parquet` with `d` all `NULL`                                | plan time `CAST_INVALID_INPUT` (explain fails) | `NULL` |
| `… / d FROM parquet` with `d = 0`                                       | plan time `CAST_INVALID_INPUT`                 | `NULL` |
| `CAST('bad' AS T) / CAST(NULL AS INT)` (foldable, any source)           | `NULL`                                         | `NULL` |
| `CASE WHEN d IS NULL THEN 1 ELSE CAST('bad' AS T) END` (parquet)        | `1`                                            | `1`    |
| `FROM IDENTIFIER(CAST(CAST('bad' AS T) / CAST(NULL AS INT) AS STRING))` | `NOT_A_CONSTANT_STRING.NULL`                   | same   |

The mechanism is in the pinned source. `ConstantFolding.constantFolding`
is parent-first: a foldable expression is evaluated as a whole
(`optimizer/expressions.scala:95`), so a foldable `Divide` runs its own
`eval`, which checks the divisor first and never evaluates the cast. The
children of a non-foldable parent are folded one by one, and a failure
propagates unless the child is inside a conditional branch
(`:63–72`, `:79–80`, the `FAILED_TO_EVALUATE` tag). `VALUES` is a
`LocalRelation`, and the batch `LocalRelation early`
(`Optimizer.scala:201–202`) runs `ConvertToLocalRelation` before the
operator-optimization batch, evaluating the whole projection row by row
with `InterpretedMutableProjection` (`:2622–2626`), which is why the
`VALUES` form sees `Divide.eval`'s laziness. `hasNoSideEffect` treats a
legacy `Cast` as side-effect free (`:58`) because it returns `NULL`.

On the DataFusion side the asymmetry Codex observed is deliberate:
`ConstEvaluator` keeps a failing expression for execution time, except a
`Cast`/`TryCast` whose input is a literal, which it fails at plan time
"rather than deferring to execution time"
(`datafusion-optimizer-55.2.0/src/simplify_expressions/expr_simplifier.rs:559–571`).
A scalar UDF cast such as `SparkAnsiStringCast` is preserved; an
`Expr::Cast` is not.

Consequences for the checkpoint:

1. For a column-dependent division over a real source, Spark under ANSI
   fails at plan time too. Sail failing in `simplify_expressions` is the
   same phase; the difference is the error (DataFusion's cast message
   versus `CAST_INVALID_INPUT`, `NumberFormatException` class). The
   prerequisite there is error-class parity, not laziness.
2. Laziness is required exactly where Spark is lazy: constant contexts
   (`IDENTIFIER`, `SET CATALOG`, directives, any fully foldable
   expression, all parent-first), conditional branches, and local
   relations. In a constant context the internal evaluator plus
   `ConstEvaluator`'s preservation of a failed UDF call reproduces
   parent-first evaluation, so option (A), a typed immutable cast UDF
   covering decimals (and the legacy float fix that CF-0376 has started),
   delivers both the error class and the constant-context laziness.
3. Option (A) over-delivers in one direction: with the cast preserved and
   the HOF lazy at runtime, `CAST('bad' AS DECIMAL(5,2)) / d` over parquet
   with every `d` NULL returns `NULL` in Sail where Spark fails at plan
   time. That is a bounded, documented deviation in the lenient direction,
   the direction Spark itself moved for conditional branches. If exact
   parity is wanted, the one place to encode Spark's rule is a Sail
   analyzer or optimizer rule that eagerly folds foldable children of a
   non-foldable, non-conditional parent and propagates their errors; it
   should not be a property of the cast.
4. Option (B), a deferred-cast wrapper over the native kernel, is
   dominated by (A): it gives laziness without the error class.
5. The `decimal(38,10)` in Sail's error for a requested `DECIMAL(5,2)` is
   Sail's coercion of the division; Spark's own result type for
   `DECIMAL(5,2) / INT` is `decimal(16,13)` (probe 12 `types`), so the
   comparison should be on the resolved division type, not the cast.

### 6.3 String-to-numeric cast oracle for the CF-0376 unit (probe 13)

Probe 13 (`probe13_string_cast_matrix.py`, output `probe13_output.jsonl`)
casts thirty strings from a parquet column to `DOUBLE`, `FLOAT`, `INT`,
`BIGINT`, `DECIMAL(5,2)`, `DECIMAL(38,10)` with `CAST` and `TRY_CAST` in
both modes (720 cells; a failing whole-column query is re-run per row to
get each input's condition). The rows a legacy float cast unit and the
later decimal unit need:

- Legacy `CAST` of a malformed string returns `NULL` for all six targets.
  ANSI `CAST` raises `CAST_INVALID_INPUT` (`NumberFormatException`); decimal
  overflow raises `NUMERIC_VALUE_OUT_OF_RANGE.WITH_SUGGESTION`
  (`ArithmeticException`) for `'1e3'`, `'123456'`, `'99999.999'` into
  `DECIMAL(5,2)`, and `NUMERIC_OUT_OF_SUPPORTED_RANGE` for `'1e400'` and
  forty nines. `TRY_CAST` returns `NULL` in both modes for every error
  cell.
- `DOUBLE`/`FLOAT` accept: surrounding whitespace, `d`/`f` suffixes,
  exponents, `'NaN'`/`'nan'`, `'inf'`/`'+inf'`/`'-inf'`/`'Infinity'`/
  `'-Infinity'` (case-insensitive), `'0.'`, `'.5'`, `'+1'`; `'1e400'` is
  `inf`, `'1e-400'` is `0.0`, forty nines is `1e40` as `DOUBLE` and `inf`
  as `FLOAT`; `'99999.999'` as `FLOAT` is `100000.0`. Rejected (`NULL` or
  error by mode): `''`, `' '`, `'0x10'`, `'1_000'`, `'1,000'`.
- Decimals round `HALF_UP` (`1.235 → 1.24`, `1.245 → 1.25`,
  `-1.235 → -1.24`), accept whitespace, exponent, `'0.'`, `'.5'`, and
  reject the `d`/`f` suffixes, `NaN`/`inf`, hex and separators.
- Integers: legacy `CAST` truncates a decimal string (`'1.5' → 1`,
  `'99999.999' → 99999`, `'.5' → 0`) but `TRY_CAST` and ANSI `CAST`
  reject it; exponents are rejected for integers in every mode.

Codex's planned minimal change (route only legacy string to `Float32`/
`Float64` through the existing `TryCast` path) is consistent with the
`DOUBLE`/`FLOAT` legacy column above provided DataFusion's float parser
accepts the same lexical set; the suffix, special-value and whitespace
rows are the ones to test, since Arrow's parser is stricter than Java's
`parseDouble` on at least the suffixes.

### 6.4 Rule placement and costs

Sail prepends its custom optimizer rules and appends
`ResolveLambdaVariables` after the built-ins because folding changes
lambda argument types (`crates/sail-logical-optimizer/src/lib.rs:44–66`);
the analyzer runs `ResolveLambdaVariables` first, Sail's `TypeCoercion` in
place of DataFusion's, and `ExtractScalarIteratorUDF` last (`:22–42`). An
admission proof that needs post-coercion types and post-folding bodies
has two candidate seats: the last optimizer position (after
`ResolveLambdaVariables`), which runs once per optimizer pass, or the
physical planner (`ExtensionQueryPlanner`, §2.1), which sees the final
logical expression once. The second is the cheaper and the one that
cannot be invalidated by a later rule; Codex's "carry it in explicit
worker state with ordered default" fits it.

The cost figures (row/native 851.77 and 901.43, selected-batch/native
12.45 and 3.53, shared host, 1024 integer rows) rank the three paths and
nothing more: the ordered row evaluator cannot be a broad default, and the
all-active zero-copy path is the only candidate for one. They are not
before/after numbers and should not be cited as such.

### 6.5 Legacy floating string casts, committed `63f5bd3b3` (CF-0378)

One five-line resolver arm on `4070e895b`: a non-`TRY` cast from
`Utf8`/`LargeUtf8`/`Utf8View` to `Float32`/`Float64` with `ansi_mode`
false resolves to `try_cast`, placed after the ANSI `SparkAnsiStringCast`
arm and the legacy `Int32` arm (`resolver/expression/cast.rs:269–273`), so
ANSI and explicit `TRY_CAST` are untouched. Two hundred and thirty-one
lines of tests: three string layouts × two widths over a column
(malformed, empty, signed zero, `NaN`, infinities, overflow, underflow,
bit-exact comparison), literal and `VALUES` conditional forms through the
Sail analyzer and optimizer, and ANSI error versus `TRY_CAST` in both
modes.

Against the pinned Spark rule: `castToDouble` on a string is Java
`parseDouble`, and on `NumberFormatException` the trimmed, lower-cased
special literals `inf`, `+inf`, `infinity`, `+infinity`, `-inf`,
`-infinity`, `nan`, else `NULL` in legacy mode or `CAST_INVALID_INPUT`
under ANSI (`expressions/Cast.scala:456–466`, `:1156–1169`). Against the
Arrow parser the arm now delegates to: `Float64Type::parse` is
`lexical_core::parse`, retried after trimming surrounding whitespace
(`arrow-cast-59.2.0/src/parse.rs:468–476`); lexical-core 1.0.6 matches its
special strings `NaN`, `inf`, `infinity` uncased after an optional sign
(`lexical-parse-float-1.0.6/src/parse.rs:963–971`, `options.rs:242–244`).
So the whitespace, sign, exponent, `.5`/`0.`, overflow-to-infinity and
every special-literal row of probe 13 (§6.3) agree, and the legacy
malformed column (`NULL` for `''`, `' '`, `'bad'`, `'0x10'`, `'1_000'`,
`'1,000'`) agrees. The residue is what Java accepts beyond lexical: the
`d`/`f`/`D`/`F` suffixes and hexadecimal floating literals (`0x1.0p2`),
which is the sixteen-case gap Codex retained. Those are a parser
extension, not a resolver arm, and belong to a later unit.

Verdict: accept. One note for the record rather than a finding: because
the result is `TryCast`, `ConstEvaluator` folds a malformed literal to
`NULL` at plan time, which is also what Spark's `ConstantFolding` does for
a legacy cast (`hasNoSideEffect`, §6.2), so the literal and conditional
tests pass for the same reason on both engines.

### 6.6 Error vocabulary of the admitted bodies: the three-way model, audited (CF-0379)

Codex's objection to §6.1 is fair on one point: "a replayed system error
only costs a re-run" was asserted from value determinism, which says
nothing about allocation, cancellation or ownership. Rather than argue it,
audit what the admitted bodies can return. The proposed native set is
`SafeNumericDivisor`, `SparkZeroDivisionError`, `SparkAnsiStringCast`,
`SparkDiv`/`SparkPmod`, `RaiseError`, and the DataFusion `BinaryExpr`,
`CastExpr`, `CaseExpr`, literal and column nodes they are built from.

- No cancellation point and no memory-pool reservation exists inside
  synchronous scalar evaluation. In `datafusion-physical-expr-55.2.0` the
  only files that mention `async`, `tokio`, `MemoryReservation`,
  `try_grow` or `ResourcesExhausted` are `async_scalar_function.rs`
  (excluded by admission) and `expressions/dynamic_filters/mod.rs` (not a
  body). So `ExecutionJoin`, `ResourcesExhausted` and
  `CommitStateUnknown` cannot originate from an admitted body; they can
  only wrap the whole task, outside the evaluation the fast path
  classifies. Allocation failure in Rust aborts the process and is not an
  error value at all.
- Arrow numeric kernels return `ArrowError::DivideByZero`
  (`arrow-arith-59.2.0/src/numeric.rs:342`), `ArithmeticOverflow`
  (`arithmetic.rs:124`, `numeric.rs:636`), `ComputeError` and
  `InvalidArgumentError` (`numeric.rs:172`, `:265`, `:456–506`).
- `CastExpr` on strings returns `ArrowError::CastError`
  (`arrow-cast-59.2.0/src/cast/string.rs:109`, `:422`) and `ParseError`.
- `SafeNumericDivisor` and `SparkZeroDivisionError` return
  `DataFusionError::External(StructuredSparkError)` (`divisor.rs:95`,
  `zero_division.rs:60`, `:71`); `SparkAnsiStringCast` maps a root
  `ArrowError::CastError` to `External(StructuredSparkError)`
  `CAST_INVALID_INPUT` (`spark_ansi_string_cast.rs:61–68`, `:112–113`,
  `:172–173`); `RaiseError` returns `DataFusionError::Execution(message)`
  (`misc/raise_error.rs:39`, `:75`).
- Everything else the DataFusion nodes can return is `Internal` from
  invariant checks (`expressions/binary.rs:286`, `:406`, `:446`, `:462`;
  `expressions/case.rs:408–1370`) and one `exec_err` for a malformed CASE
  (`case.rs:668`).

So for the admitted set the three buckets are: known data = the list
above; known system = empty by construction; unknown = `Internal` and
whatever a future edit adds. The §6.1 deny-list and Codex's allow-list
then prescribe the same behaviour on every error these bodies can
produce, and the disagreement reduces to the unknown bucket, where the
batch error should be kept: an `Internal` invariant breach is not
row-attributable, so the wrong-row concern does not apply to it. The
synthetic `opaque_source` and `collection_mixed` shapes cannot be
produced by an admitted body; admission excludes the UDFs that could
produce them.

Reconciled rule: replay if and only if the raw error is in the known-data
vocabulary; keep the batch error otherwise; and pin the vocabulary with a
test that, for each admitted body, enumerates the error constructors it
can reach, so that adding a body or an error path to a body fails the
test until the vocabulary is extended. That is the deferred edit as a
failing test (AGENTS.md), and it is what makes "unknown" a bucket that
stays empty rather than a hope. Codex's seat for the proof, the physical
planner over the final expression, is agreed (§6.4).

### 6.7 Where a physical-planner proof can actually sit (CF-0382)

Codex's caution is correct: `ExtensionQueryPlanner` implements
`QueryPlanner::create_physical_plan` (`crates/sail-session/src/planner.rs:88`)
and `ExtensionPhysicalPlanner` implements `ExtensionPlanner::plan_extension`
(`:172`), which is consulted only for logical extension nodes. Native
expression construction, including `Expr::HigherOrderFunction` to
`HigherOrderFunctionExpr`, happens in
`datafusion-physical-expr-55.2.0/src/planner.rs:548–630`, called from
`DefaultPhysicalPlanner::create_physical_expr`
(`datafusion-55.2.0/src/physical_planner.rs:180`), which is a plain method
rather than a hook, and Sail registers no `ExprPlanner`. So the planner
cannot intercept the HOF as it is built.

Two seats remain, both already present in Sail:

1. A `PhysicalOptimizerRule` in `crates/sail-physical-optimizer`, next to
   the eight rules there (`barrier.rs:36`, `collect_left.rs:29`,
   `explicit_repartition.rs:30`, `filter_pushdown.rs:14`,
   `input_file_name.rs:37`, `:96`, `:389`, `join_reorder/mod.rs:133`),
   that walks each node's expressions and rewrites a
   `HigherOrderFunctionExpr` over `SparkDivModLazy` whose bodies pass the
   admission proof into the batch-eligible form. It runs once on the
   final physical expressions, after logical folding and type coercion.
2. The decoder on the worker (`converter.rs`, §5.1), which also
   constructs the final physical expression once.

The proof is a pure function of the final expression, so it can be
recomputed wherever the expression is constructed. That is the cleaner
choice for the wire: the driver-side rule marks local plans, and the
decoder recomputes the same proof for remote plans, so the
`SparkDivModLazyUdf` message keeps its single `ansi_mode` field and no
eligibility bit travels. If instead the driver's decision must be
authoritative on the worker, the message needs a mode field and the
codec tests of §5.2 need a mode round trip. Either way the proof and the
evaluator mode stay out of the logical plan, which is what "explicit
worker state with ordered default" asked for.

### 6.8 String-to-decimal cast: the contract, pinned, and the candidate UDF challenged (CF-0384)

Spark's rule, from the pin (`sql/api/src/main/scala/org/apache/spark/sql/types/Decimal.scala`):

- Parse: Java `trim` (code points at or below U+0020, so NBSP stays and
  fails), then `new java.math.BigDecimal(s)` (`:645–649`): optional sign,
  digits with an optional point, optional `e`/`E` exponent with sign, any
  Unicode `Nd` digit accepted through `Character.digit`, no suffixes, no
  hex, no `NaN`/`inf`. Failure is `NumberFormatException`.
- Zero fits every decimal type whatever its exponent (`:661–668`);
  otherwise more than 38 integral digits (`precision - scale`, computed in
  `Long`, `:641–642`) is the unsupported range (`:669–672`): `null` for
  legacy and `TRY_CAST`, `NUMERIC_OUT_OF_SUPPORTED_RANGE` (22003,
  `SparkArithmeticException`, parameter = the original string) under ANSI
  (`:686–699`).
- Then `changePrecision(p, s)` with `HALF_UP` (`:352–353`), with Spark's
  own bounded shortcut: when the scale change exceeds 38 the result is
  decided from the integral-digit count without `setScale` (`:460–472`),
  which is the "no exponent-sized allocation" requirement already in
  Spark. Overflow is `null` for legacy and `TRY_CAST`,
  `NUMERIC_VALUE_OUT_OF_RANGE.WITH_SUGGESTION` (22003,
  `SparkArithmeticException`, parameter = the parsed value in plain form,
  e.g. `1000` for `'1e3'`) under ANSI (`Cast.scala:1081–1092`,
  `:1107–1115`).
- Malformed input under ANSI is `CAST_INVALID_INPUT` (22018,
  `NumberFormatException`), the same factory the primitive UDF already
  carries (`spark_ansi_string_cast.rs:61–84`).
- Nullability: a non-`TRY` cast from `STRING` is nullable in every mode
  (`Cast.scala:630–631`, `forceNullable` `:433`), `TRY_CAST` too. The
  UDF's return field is therefore `nullable = true` always; the "ANSI CAST
  nullability mismatches" Codex counted should be checked against that
  rule before being treated as Sail defects.

Arrow's parser, which the current `Expr::Cast`/`TryCast` path uses,
cannot be bent to this: `parse_string_to_decimal_native`
(`arrow-cast-59.2.0/src/cast/decimal.rs:534–600`) uses Rust `str::trim`
(Unicode whitespace, so it strips NBSP), splits on `.` only, requires an
ASCII digit first, has no exponent, rounds `HALF_UP` only on the
fractional overflow, and reports precision overflow as `None` under
`safe` or a single `CastError` otherwise (`:649–672`). Codex's "differs
in ASCII/trim/exponent/range" is confirmed, and so is the consequence
that today's `TRY_CAST('1e3' AS DECIMAL(38,10))` is `NULL` in Sail and
`1000` in Spark, which makes "one UDF reused by ANSI, legacy and
`TRY_CAST`" the right shape rather than a convenience.

Challenges to the candidate `SparkStringToDecimal`:

1. Two modes, not three. Probe 13's legacy `CAST` and `TRY_CAST` decimal
   columns are identical in every cell, and the source agrees (`null` on
   both failure kinds in both). One `fail_on_error: bool` plus
   `(precision, scale)` is the whole constructor and the whole wire
   message.
2. Grammar in one bounded pass over the bytes: sign, `Nd` digits (a
   table of `Nd` block starts, each a run of ten, is about sixty-five
   entries; `char::to_digit` is ASCII only), at most one point, optional
   exponent parsed into `i64` with saturation; count significant digits
   after stripping leading zeros and compute integral digits in `i64`
   before touching an `i128`/`i256`. Apply the zero shortcut and the
   38-integral-digit check first, then rescale with `HALF_UP` into
   `i256` and check the target precision. No `BigDecimal`-sized
   allocation exists on any path.
3. Three typed factories, one shared. Extract `invalid_input` from the
   primitive UDF into a common factory parameterised by the SQL target
   name (`DECIMAL(p,s)`), and add the two 22003 factories; their classes
   and parameters are fixed by probe 13's messages (§6.3).
4. Negative scale is a type question, not the UDF's: Spark rejects it
   unless a legacy conf allows it (`Decimal.createUnsafe` calls
   `checkNegativeScale`, `:705–706`), and Arrow permits `i8` scales, so
   the resolver must refuse a negative-scale target before constructing
   the UDF.
5. Array and scalar: implement once over `StringArrayType` for the three
   string layouts, as Arrow does, with the scalar case as a one-element
   array; no metadata is involved.
6. Worker footprint is the same five paths as the primitive cast: one
   proto message with `precision`, `scale`, `fail_on_error`
   (`physical.proto:297`, `:1369` for the precedent), the decode arm
   (`codec.rs:3868–3878`), the encode arm (`:4491`), and a round-trip
   test module.
7. Folding stays a separate unit. As a UDF the cast is preserved by
   `ConstEvaluator` on failure (§6.2), which gives constant-context and
   conditional laziness; the eager parity Spark shows over a real source
   is the folding-policy rule, as Codex says.

### 6.9 Physical seat, continued (CF-0384)

Codex is right that `ExecutionPlan::apply_expressions` is a read-only
visitor (`datafusion-physical-plan-55.2.0/src/execution_plan.rs:326–352`)
and that no `with_new_expressions` exists in that crate, so a physical
rule must rebuild each node type it rewrites (`ProjectionExec::try_new`,
`FilterExec`, the projection pushed into `DataSourceExec`, and so on) and
leave every other node ordered. That makes the physical rule the more
expensive seat. The alternative Codex named is cheaper: rewrite the final
optimized logical plan inside `ExtensionQueryPlanner::create_physical_plan`
(`sail-session/src/planner.rs:88`) before delegating to the default
planner. It is one pass over logical expressions with post-optimization
types, needs no per-node enumeration, and makes one decision that then
travels inside the HOF's UDF value. The price is a mode field in
`SparkDivModLazyUdf` and a mode round trip in the §5.2 tests, which is
small, and it removes the duplicate-predicate drift Codex worries about,
since the worker never re-derives anything. Recommend that seat with the
wire field; keep decoder recomputation only if the wire must stay frozen.

### 6.10 `SparkStringToDecimal`, candidate `8a7bf8ca4` on `63f5bd3b3` (CF-0387)

Eleven paths: the class (`scalar/spark_string_to_decimal.rs`, 192 lines),
the scanner and rescaler (`spark_string_to_decimal/parse.rs`, 183), a
shared `CAST_INVALID_INPUT` factory (`scalar/cast_error.rs`, 37) that the
primitive caster now delegates to with an identical message, and tests
with three recorded fixtures (96 deduplicated Spark cells, 32 policy
cells, the digit table). Read read-only against `parse.rs` and the
sources pinned in §6.8; no Sail edits.

Scanner, checked rule by rule against Java and Spark:

- Trim is `c <= U+0020` on both ends, which is `String.trim`; NBSP and a
  BOM stay and fail, as in Spark.
- One optional sign, digits through a 37-block BMP table with the ASCII
  fast path, at most one point, then an optional `e`/`E` exponent with
  sign; anything left over is invalid. Supplementary digits are single
  Rust `char`s outside the table and are rejected, which is what Java's
  UTF-16 `Character.digit(char, 10)` does to a surrogate pair. I
  recomputed the table on the installed JDK 17 and JDK 20
  (`evidence/set-catalog-oracle/DigitBlocks.java`): both give the same
  37 block starts and 370 digits, so the JDK-20 pin also holds for the
  JDK 17 the pinned Spark oracle runs on.
- Exponent: Java's `parseExp` skips leading zeros only while more than
  ten characters remain and then rejects more than ten
  (`BigDecimal.java:713–734` in the JDK 20 `src.zip`); counting
  significant digits and rejecting above ten is the same predicate.
  The resulting scale is `fraction - exponent` in `i64` and must fit
  `i32`, which is Java's `checkScale` with the zero leniency
  (`:4399–4409`); the boundary tests pin `0e2147483648` accepted,
  `0e2147483649` and `0e-2147483648` rejected.
- Leading zeros are stripped so `digits.len()` is Java's `precision`;
  an all-zero mantissa returns `0` for any target, Spark's zero fast
  path (`Decimal.scala:661–668`).
- Unsupported range is `digits - scale > 38` unless
  `allow_negative_scale`, exactly `numDigitsInIntegralPart > 38 &&
!allowNegativeScaleOfDecimalEnabled` (`:641–642`, `:669–672`). Codex's
  point that the flag is orthogonal to the target's sign is in that
  source: it is a session conf read per row, not a property of the
  target type, and the 32 policy cells show it flipping the condition
  for `1e39` on `DECIMAL(5,2)`.
- Rescale: `kept = digits + target_scale - scale` is the digit count at
  the target scale; `kept < 0` is zero; `kept > precision` is overflow
  before any arithmetic; otherwise at most 38 digits are folded into an
  `i128`, the first dropped digit decides `HALF_UP` away from zero, and
  a post-rounding `10^precision` check catches `999.995` into `(5,2)`.
  Work is bounded by the input length and the target precision, which is
  the property Spark's own shortcut (`:460–472`) exists for.
- Overflow rendering follows `numericValueOutOfRange`
  (`DataTypeErrors.scala:199–222`): plain unless the parsed scale is
  below `-1000`, then `BigDecimal.toString`. The rendering uses the
  parsed decimal, not the rounded one, which is right because
  `changePrecision` leaves the receiver unchanged on failure
  (`Decimal.scala:455–480`), and trailing mantissa zeros are retained
  (`1.230E+2147483648`).

Class: `Immutable`, three string layouts for scalar and array, scalar
preserved without a one-row array, first failing row wins in order,
return field `nullable = true` with extension metadata cleared, and
`try_new` validates the `Decimal128` precision and scale. Two policy
fields plus precision and scale is the constructor §6.8 asked for, plus
the orthogonal range flag that the source requires.

Verdict: accept. No correctness findings. For the later units: the
resolver must capture `allow_negative_scale` from the session conf at
resolve time, and the wire message carries all four fields; the two
22003 conditions enter the replay vocabulary (§6.6) only with this
class's per-type fixtures, as Codex already notes.

### 6.11 Decimal cast wire, candidate `b48162de9` on `8a7bf8ca4` (CF-0391)

Three paths: `physical.proto` adds `SparkStringToDecimalUdf` as tag 43 of
the `ExtendedScalarUdf` oneof (41 is the ANSI string cast, 42 the time
precision cast, nothing above), with `uint32 precision`, `int32 scale`,
`bool fail_on_error`, `bool allow_negative_scale`; `codec.rs` adds the
import, a decode arm and an encode arm; a 328-line test module.

- Decode validates the function name before construction, narrows
  `u32 → u8` and `i32 → i8` with `try_from`, then runs the constructor's
  `Decimal128` bounds. The malformed-wire test includes 257 and 258 and
  -256, which a wrapping cast would turn into precision 1, scale 2 and
  scale 0 and accept; that is what makes Codex's "replace each checked
  narrowing with a wrapping cast" controls fail rather than pass by
  accident.
- Proto3 omits a `false` bool from the wire, so `round_trip(…, false,
false)` exercises the decode-from-absent path, and both absent values
  decode to the lenient policy and to Spark's default range conf. That is
  the right failure direction for a field a future writer forgets, though
  it is not Spark's default ANSI mode; it matters only across schema
  evolution, not within one build.
- Values: `(5,2)`, `(38,10)` and the negative-scale `(5,-2)` (`150 → 2`)
  across both policies, three string layouts, scalar and array, with
  signature equality after the round trip.
- Error vocabulary after the round trip: `CAST_INVALID_INPUT` with all
  four parameters, `NUMERIC_VALUE_OUT_OF_RANGE.WITH_SUGGESTION` with the
  plain rendering, and the policy-dependent `1e39` flipping to
  `NUMERIC_OUT_OF_SUPPORTED_RANGE` when the range flag is off. Legacy
  returns `NULL` for all three inputs.
- Full physical tree: `SparkDivModLazy` over a captured string column
  with the decoded cast as the left thunk and a typed lambda parameter as
  the operation (returning the left value, so the fixture isolates cast
  laziness and claims nothing about division). Rows `("bad", NULL)`,
  `("1.235", 2)`, `(NULL, 0)` give `NULL, 1.24, NULL` in both modes: the
  first is skipped on the `NULL` divisor, the third is `NULL` because the
  dividend-null check precedes the ANSI zero check (§5.2). An empty batch
  and a one-row `("bad", 2)` batch that actually invokes the decoded cast
  complete it, with the typed error or `NULL` by policy.

Verdict: accept. Nothing blocking; the four fields are the ones §6.10
said the wire must carry.

### 6.12 Config capture for `spark.sql.legacy.allowNegativeScaleOfDecimal`: premises pinned (CF-0394)

Codex's plan for the capture unit rests on five claims; all five are in
the pinned sources, so the review of the candidate can be confined to
the diff.

- Key, default and visibility: `buildConf("spark.sql.legacy.allowNegativeScaleOfDecimal").internal().booleanConf.createWithDefault(false)`
  (`SQLConf.scala:5732–5740`), read at evaluation through
  `SqlApiConf.get.allowNegativeScaleOfDecimalEnabled`
  (`Decimal.scala:663`, `:670`), which is the executing query's conf, so
  capturing it at resolve time is equivalent.
- `SET` validates before it mutates and stores the raw string:
  `setConfString` runs `entry.valueConverter(value)` and only then
  `setConfWithCheck(key, value)` (`SQLConf.scala:8797–8806`).
- The boolean converter is `s.trim.toBoolean`
  (`ConfigBuilder.scala:40–46`): Java `trim` (≤ U+0020, so NBSP fails)
  then Scala's `toBoolean`, which is Java `equalsIgnoreCase` against
  `true` and `false`. For those two words the only non-ASCII character
  Java folds is the long s U+017F in the `s` position of `false`
  (`Character.toUpperCase('ſ') == 'S'`); no other code point
  upper-cases to T, R, U, E, F, A or L. That is why `falſe` is accepted
  and `1`, `0`, `yes`, `''` are not.
- The error is `SparkIllegalArgumentException`
  `INVALID_CONF_VALUE.TYPE_MISMATCH` with `confName`, `confValue`,
  `confType = "boolean"` (`ConfigBuilder.scala:112–120`), SQLSTATE 22022
  with the message "The value '<confValue>' in the config "<confName>"
  is invalid. It should be a/an '<confType>' value."
  (`error-conditions.json` under `INVALID_CONF_VALUE`).
- Sail already has the parser: `parse_spark_bool`
  (`crates/sail-data-source/src/options/parsers.rs:30–44`) accepts
  `true`/`false` ASCII-case-insensitively plus the `falſe` fold with the
  reason in its comment, and the ORC path applies the Java trim before
  it (`sail-spark-connect/src/config/orc.rs:24–36`). Extracting that
  pure step is the right reuse; the ORC error mapping stays where it is.

Nothing to challenge at plan level. The candidate's review will check:
the trim is applied before the parser for the new key; the raw accepted
string is what the session stores and returns; the typed error carries
the three parameters and reaches the client with the
`SparkIllegalArgumentException` hierarchy; and snapshot overrides do not
leak into other sessions.

### 6.13 Negative-scale config capture, candidate `226b0c1cf` on `b48162de9` (CF-0396)

Eight paths, read against the §6.12 premises:

- `PlanConfig.legacy_allow_negative_scale_of_decimal: bool`, default
  `false` (`sail-plan/src/config.rs`), the Spark default.
- `SparkRuntimeConfig::set` validates the new key with
  `parse_config_bool` after the removed-key check and before
  `self.config.insert` (`sail-spark-connect/src/config.rs:153–181`), so
  an invalid `SET` leaves the previous value in place; the stored value
  is the raw accepted string, which `get` returns unchanged, as Spark's
  `setConfString` does. `PlanConfig::try_from` parses the stored string
  with the same function, so the typed flag and the raw string cannot
  disagree. Overrides clone the runtime config and `set` on the clone
  (`session.rs:109–117`), so a rejected override cannot touch the
  session.
- `config/boolean.rs`: `parse_sql_bool` is the Java trim (≤ U+0020)
  followed by the existing `parse_spark_bool`, extracted from the ORC
  path, whose error mapping is unchanged; `parse_config_bool` wraps a
  failure as `SparkIllegalArgumentException`
  `INVALID_CONF_VALUE.TYPE_MISMATCH`, SQLSTATE 22022, with `confName`,
  `confValue` (the raw, untrimmed value, as `toBoolean(s, key)` passes
  it) and `confType = "boolean"`, and the message in Spark's template
  wording.
- `error.rs` adds the class chain
  `SparkIllegalArgumentException → IllegalArgumentException →
RuntimeException → Exception → Throwable → Object`, which is the
  pinned declaration (`SparkException.scala:525–530`), and PySpark's
  client maps `java.lang.IllegalArgumentException`
  (`pyspark/errors/exceptions/connect.py:483`), so the client raises
  `IllegalArgumentException` as it would against Spark.
- Tests pin the 4.2 metadata explicitly, cover default, `true`/`false`,
  tab and NUL trimming, `falſe`/`FALſE`, unset, snapshot independence
  (an earlier `Arc<PlanConfig>` keeps its semantics after a later `SET`
  or `UNSET`), the ANSI-off `NULL` path through the callable caster, and
  six invalid values (`1`, `0`, `yes`, empty, NBSP-wrapped, `truſe`)
  rejected at both `SET` and override with the prior value retained and
  the full error details read back through `tonic::Status`.
- The dev-only `sail-function` edge exists so the test can feed the
  captured settings to the real caster; it is not a production
  dependency.

One note, not a finding: the older flags in `PlanConfig::try_from`
(`ansi_mode`, `legacy_type_coercion_datetime_to_string`, …) still parse
with Rust `trim().to_lowercase().parse::<bool>()`, which accepts NBSP
padding and rejects `falſe`; the new key is the first to use the Spark
rule. Aligning the others is a separate, pre-existing parity item.

Verdict: accept.

### 6.14 The lenient set for a source- and conditional-aware folding rule (pre-pinned for the next unit)

Codex's next unit mirrors Spark's `ConstantFolding` in Sail. The rule's
one data-dependent input is which parents make a failing foldable child
survive to execution. From the pin:

- `ConditionalExpression` (`expressions/Expression.scala:566–583`) has
  exactly four implementors: `If` (`conditionalExpressions.scala:45`),
  `CaseWhen` (`:169`), `Coalesce` (`nullExpressions.scala:53`) and
  `NaNvl` (`:347`). Its `foldable` is `final` and `children.forall`
  (`:567`), so a fully foldable conditional folds whole, parent-first,
  through its own lazy `eval`.
- `And` and `Or` (`predicates.scala:842`, `:938`) are not conditional
  expressions: `TRUE AND CAST('bad' AS INT) > 0` over a real source
  fails at plan time under ANSI, exactly like the division in §6.2.
- For a non-foldable conditional, `constantFolding` recurses into every
  child with `isConditionalBranch = true`
  (`optimizer/expressions.scala:79–80`), including the always-evaluated
  inputs (`If.predicate`, `CaseWhen` conditions, the first `Coalesce`
  argument). A failing predicate is therefore also left in place, tagged
  `FAILED_TO_EVALUATE` so it is never re-tried (`:63–72`, `:92`), not
  only a failing branch value.
- Everything else follows the generic arm (`:107–112`): children are
  folded first, and if the rebuilt parent is foldable it is folded as a
  whole, which is where the failure propagates for a non-conditional,
  non-foldable parent.

So a Sail rule that wants parity has three behaviours to encode, not
one: parent-first evaluation of foldable subtrees (which DataFusion's
bottom-up `ConstEvaluator` does not do), leniency for every child of
the four conditional kinds, and eager failure elsewhere, with the
`VALUES` exception coming from the local-relation batch rather than
from the folding rule (§6.2). The DataFusion rule already fails eagerly
for `Cast(Literal)` and is lenient for everything else
(`expr_simplifier.rs:559–571`), which is neither of Spark's two
behaviours; the Sail rule should replace that special case rather than
stack on it.

### 6.15 `nvl2` lowering `e5605fd3a`, and where DataFusion's constant evaluator cannot be switched off (CF-0401)

**`nvl2`.** Spark's `Nvl2` is `RuntimeReplaceable` with replacement
`If(IsNotNull(expr1), expr2, expr3)` (`nullExpressions.scala:271–276`),
and `If` merges only `trueValue` and `falseValue` types
(`conditionalExpressions.scala:48–50`), so the tested argument never
takes part in coercion. Sail's resolver returned `expr_fn::nvl2`, a
DataFusion function that coerces all three, hence `nvl2('sentinel', 1,
2)` typed as string and array or boolean tests rejected. The candidate
(`e5605fd3a` on `226b0c1cf`) lowers the ordinary arm through the
existing `if_expr` with `value.is_not_null()`, keeping the dedicated
date/timestamp path, which is Spark's replacement verbatim. Tests: the
tested type does not reach the branches (string, boolean, binary, null
test), branch widening `Int32`/`Int64` to `Int64`, a failing cast in the
unreached branch skipped under `LiteralEvaluator`, the tested
expression evaluated once (volatile counter equals one), and a public
feature scenario with the integer schema for all four inputs. Verdict
when requested: accept.

**Constant evaluation.** Codex's claim that there is no public switch is
true: `ExprSimplifier` exposes only `with_guarantees`,
`with_canonicalize` and `with_max_cycles`
(`expr_simplifier.rs:319`, `:371`, `:424`), and
`simplify_with_cycle_count` constructs `ConstEvaluator::try_new`
unconditionally (`:213–216`). The callers that build their own
simplifier, each of which would run the `Cast(Literal)` plan-time
failure independently of the `SimplifyExpressions` rule:

- optimizer: `simplify_exprs.rs:123` (the rule), `decorrelate.rs:530`,
  `:565`, `:605`, `simplify_literal.rs:54`, `unwrap_cast.rs:632`,
  `udf_preimage.rs:181`;
- core: `session_state.rs:814` (the `create_physical_expr` path) and
  `:2013`, `context/mod.rs:1569`;
- Sail: `resolver/constant.rs` (the unwrapped catalog expression path,
  §6.2), `resolver/identifier.rs`, `resolver/expression/window.rs`,
  `sail-logical-optimizer/src/session_timestamp.rs`,
  `sail-common-datafusion/src/schema_evolution.rs`, and the Delta and
  Iceberg `datasource/expressions.rs`.

`datafusion-physical-expr-55.2.0` also carries a physical
`simplifier/const_evaluator.rs` (`simplify_const_expr`), exported but not
called from the core planner in this version.

Consequence for the folding design: the Spark rule cannot be installed
by replacing or disabling DataFusion's evaluator. It can be installed in
front of it. `ConstEvaluator` preserves every failing expression except
a bare `Cast`/`TryCast` of a literal (`:559–571`); the typed cast UDFs
(§6.8, §6.10) remove that exception from Sail's plans, after which
DataFusion is uniformly lenient. A Sail analyzer rule that runs once
before the optimizer and applies Spark's `constantFolding` (§6.14:
parent-first, lenient inside the four conditional kinds, eager
elsewhere) then supplies the eager failures Spark raises, and whatever
it leaves unfolded is, by construction, inside a conditional branch or
non-foldable, where DataFusion's leniency is the behaviour wanted. The
Sail-owned call sites above (constant contexts first) can call the same
rule directly. That is one rule and the existing cast UDFs; nothing in
DataFusion needs patching.

### 6.16 `nvl2` accepted; `NaNvl` is the next lazy conditional (CF-0403)

`e5605fd3a` is accepted as read in §6.15 (three paths; the Spark
replacement verbatim; the production-only revert control fails the new
tests). Codex's `NaNvl` observation is in the pin: `NaNvl.eval` returns
`null` for a null left, the left itself when it is not `NaN`, and
evaluates the right only otherwise (`nullExpressions.scala:368–378`),
with `alwaysEvaluatedInputs = left` and `branchGroups = Seq(children)`
(`:361`, `:367`), so `right` is a conditional branch for folding (§6.14)
and for execution. Sail lowers `nanvl` to `expr_fn::nanvl`
(`function/scalar/conditional.rs:282`), DataFusion's `NanvlFunc`, an
`Immutable` scalar (`datafusion-functions-55.2.0/src/math/nanvl.rs:58`,
`:97`) whose two arguments DataFusion evaluates before invocation. A
failing right (an ANSI division by zero or a malformed cast) therefore
errors in Sail on rows where Spark never evaluates it, and a failing
foldable right is folded eagerly where Spark leaves it.

Two shapes fix it, and only one is correct for a volatile left:

- `CASE WHEN l IS NULL THEN NULL WHEN NOT isnan(l) THEN l ELSE r END`
  gives per-row laziness for `r` (DataFusion's `CaseExpr` evaluates each
  branch on its selected rows) and places `r` in a conditional branch for
  the folding rule, but it names `l` three times, and DataFusion
  evaluates a volatile `l` once per occurrence (§2.6's CSE fixture),
  where Spark evaluates `left` exactly once.
- The ordered component already built for division (§2, §5):
  `SparkDivModLazy` is "evaluate the first thunk once, decide per row
  from its value, evaluate the second thunk only on the selected rows,
  then the operation". `NaNvl` is that shape with the predicate "is a
  non-null `NaN`" instead of "is a non-null non-zero divisor" and the
  operation returning the chosen value. Generalising the component's
  predicate, or adding a sibling with the same three-lambda contract,
  gives `NaNvl` single evaluation of the left, laziness of the right,
  and the §6.6 vocabulary for free.

Codex's "classification alone will not fix it" is therefore right, and
so is the implication for the admitted-body list: `nanvl` as lowered
today is not a lazy conditional and must not be treated as one.
