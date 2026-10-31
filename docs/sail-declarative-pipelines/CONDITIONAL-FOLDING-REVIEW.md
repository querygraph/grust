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
