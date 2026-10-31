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
