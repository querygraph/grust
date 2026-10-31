# Conditional expressions and constant folding: Fable's review record (continued)

Continues `OPERAND-EVALUATION-REVIEW.md` (§1–§6.18). Same rules: every
claim about Spark cites the pin `617618396` at
`/Users/alexy/src/spark-sdp-4.2.1`, every claim about DataFusion cites
the 55.2.0 crates Sail builds against, every Sail claim cites the commit
read, and nothing here edits Sail.

## 1. `CASE` nullability: the missing `else_expr` (CF-0411, before the IF/CASE unit lands)

Codex has reported "four cast/CASE nullability gaps" against Spark since
the `nvl2` work (CF-0410) and is now gating a unit that routes `IF` and
`CASE` through the analyzer's coercion helper at lowering. One of those
gaps has a mechanical cause in the same file, so it is recorded before
the unit is final.

- Sail lowers a SQL `CASE … ELSE x END` through the `when` function
  (`sail-sql-analyzer/src/expression.rs:750–795`, the `ELSE` value is
  appended as a trailing lone argument), and the `case` builder in
  `sail-plan/src/function/scalar/conditional.rs:28–52` turns that lone
  trailing argument into a `(lit(true), value)` branch and sets
  `else_expr: None`.
- DataFusion decides nullability of a `CASE` from the reachable nullable
  `THEN` branches, then the `ELSE`, and when there is no `else_expr`
  returns `true` unconditionally, with the comment "CASE produces NULL
  if there is no `else` expr" (`datafusion-physical-expr-55.2.0/src/expressions/case.rs`,
  `fn nullable`, final arm; the logical rule in
  `datafusion-expr-55.2.0/src/expr_schema.rs:315–345` has the same
  shape). The predicate pre-evaluation in that function can prove a
  branch unreachable, but nothing in it recognises `WHEN true` as making
  the missing `ELSE` unreachable.
- Spark's `CaseWhen.nullable` is `branches.exists(_._2.nullable) ||
elseValue.map(_.nullable).getOrElse(true)`, so `CASE WHEN c THEN 1
ELSE 2 END` is not nullable.

Consequence: every Sail-built `CASE` with an `ELSE` whose branches are
all non-nullable is reported nullable, and so is `IF` only when lowered
through this builder (`if_expr` sets `else_expr`, `conditional.rs:62–66`,
so plain `IF` is already right). The fix is local to the builder: when
the trailing lone argument exists, place it in `else_expr` instead of
synthesising a `WHEN true` branch. That also hands the `ELSE` value to
`coerce_case_expression` as an `else`, which is how the analyzer
expects to see it. It belongs in the IF/CASE unit Codex is gating, or
in the next one; either way it should close at least the `CASE` member
of the four gaps, with a public schema scenario for `CASE … ELSE` over
non-nullable branches as the proof.

## 2. IF and CASE through the shared coercion, candidate `a51bef4ce` on `982877d85` (CF-0412)

Three paths. `case` and `if_expr` now return through
`coerce_conditional_case`, which applies the analyzer's
`coerce_case_expression` with the captured session time zone after the
existing string/temporal normalisation; `nvl2` delegates to `if_expr`
and its private wrapper from §6.18 is gone, so there is one coercion
site for the three functions and it is the analyzer's own
implementation. Raw SQL `CASE` reaches `case` through the `when`
function (§1), so it is covered.

Tests: for both builders, both branch orders, `Int32`/`Int64` and
`Int32`/`Decimal(2,1)` widening are asserted on the lowered expression
before any analyzer runs and again after `TypeCoercion`, with the
`true`/`false`/`NULL` conditions evaluated through `LiteralEvaluator`;
a `CASE` without `ELSE` coerces all branches, stays nullable and yields
a typed `NULL` when nothing matches; multiple branches with a trailing
`ELSE` take the common type; an `Immutable` throwing branch is invoked
zero times during coercion and when skipped, once when selected. The
public feature pins `typeof` for `IF` and `CASE` (`bigint`,
`decimal(11,1)`) under both ANSI settings and evaluates coerced
branches over nullable conditions, including a `no_else` `NULL` row.

Verdict: accept, read-only, pending the public gate. Two notes:

- The `else_expr` finding of §1 is not in this candidate (the two
  crossed); the `case` builder still emits `(lit(true), value)` with
  `else_expr: None`, so `CASE … ELSE` over non-nullable branches stays
  reported nullable. Carry it as the next change in the same file.
- Coercion failures now surface while the expression is resolved, not
  in the analyzer, so for a projection with several expressions the
  first error a client sees may change order relative to, say, an
  unresolved column in a later expression. Spark raises both in
  analysis as well, so this is a precedence detail to watch in the
  public comparison, not a defect.

## 3. The other nullability direction: ANSI string casts inherit their input's nullability (CF-0415)

Codex's four retained `nvl2` mismatches run the other way from §1: Sail
reports `nullable = false` where Spark reports `true`, on cases that
already lower through `IF` with a real `else_expr` and involve casts.
The cause is in the cast, not the conditional:

- `SparkAnsiStringCast::return_field_from_args` copies the input field
  and changes only its name, type and metadata, with the comment "Match
  type-only Cast's source nullability"
  (`sail-function/src/scalar/spark_ansi_string_cast.rs:109–129` at
  `982877d85`). A non-nullable string input, a literal or a non-null
  column, therefore yields a non-nullable cast.
- Spark's `Cast.nullable` for a non-`TRY` cast is `child.nullable ||
forceNullable(from, to)`, and `forceNullable` is `true` for any cast
  from `StringType` to a non-string, non-binary type, in every mode
  (`Cast.scala:630–631`, `:433`; pinned in §6.8 of the operand review).
  `TRY_CAST` is nullable too (`:632–640`).
- Sail's legacy `SparkCastStringToInt32` already forces `nullable = true`
  and tests it (`spark_cast_string_to_int32.rs:221–232`), and
  `SparkStringToDecimal` does the same (§6.10), so the ANSI primitive
  caster is the odd one out.

Fix: `with_nullable(true)` in the ANSI caster's return field, matching
its two siblings; the "match type-only Cast" comment describes
DataFusion's `Cast`, which is the wrong reference for a Spark cast from
string. This should close the four `nvl2` cases and the twenty ANSI
`CAST` schema mismatches Codex counted at CF-0378, and it is independent
of the `else_expr` change in §1; the two together are the two
directions of the schema gap.

## 4. Explicit `ELSE` preserved, candidate `8403829d9` on `a51bef4ce` (CF-0417)

Thirteen product lines in the `case` builder: a trailing lone argument
sets `has_else` instead of synthesising a `WHEN true` arm; all values
including the `ELSE` go through `coerce_string_temporal_values`
together, as before, and the `ELSE` is popped afterwards into
`else_expr`; with no trailing argument `else_expr` stays `None`. The
`CASE x WHEN a …` form reaches the same builder after the SQL analyzer
rewrites it to comparisons (`expression.rs:771–773`), so it is covered.

Tests pin, on the lowered expression before any analyzer: `CASE WHEN
TRUE THEN 1 ELSE 2 END` non-nullable with value `1`; no `ELSE` nullable
with a typed `NULL`; a `NULL` literal in either branch nullable; three
arms with `ELSE` taking `Int64` and non-nullable. The public scenario
runs `with_else`, `without_else` and `nullable_branch` over a nullable
condition under both ANSI settings, with the schema `false`/`true`/`true`,
which is Spark's `CaseWhen.nullable`. The old `@sail-bug` tag is dropped
with its assertion unchanged.

Verdict: accept, read-only, pending the public gate. This closes the §1
direction; the §3 direction (ANSI string cast return field) remains the
separate change.
