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
