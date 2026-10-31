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
