# NVL2 conditional lowering and branch types

Sail `982877d859bed7b7e82662d6873a6b7f88eb04a3`, parent
`226b0c1cfc9ac72dadc3ec8a81667f7acc3aacec`, normalizes NVL2 through
Sail's IF builder, then applies the analyzer's existing CASE coercion helper
before resolver type introspection. Only the two result branches determine the
common type. The date/timestamp conversion path remains and receives the same
final branch coercion. The shared helper's implementation is unchanged; it is
now exposed to the resolver. No dependency or worker protocol changes.

Spark 4.2.1 pin `617618396087429b5627a86ce933bb0f5d6645cb` defines Nvl2 as
RuntimeReplaceable with `If(IsNotNull(expr1), expr2, expr3)` in
`sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/expressions/nullExpressions.scala:271–282`.
The previous DataFusion NVL2Func coercion included the test's type. Fresh16
Spark and exact parent CLI cases show wrong string values for a string test,
rejection of boolean/array tests, and wrong widened/decimal result types.

Validation:

- Detached formatting and strict Clippy; 119 plan and 51 logical optimizer tests
  pass. One existing logical optimizer test remains ignored.
- Two focused tests cover test-type exclusion, Int64/Decimal common types before
  analysis, skipped failing branches and one evaluation of a volatile test.
- A production-only revert preserves those tests and fails both (0/2).
- Fresh built CLI: 300 selected public cases and 67 upstream Python cases pass.
  These are selections, not the complete Spark SDP suite.
- Six NVL2 feature scenarios pass, including temporal conversion, existing
  common-type behavior and the new integer-schema and typeof cases.
- Fresh16 SQL comparisons match all Spark row values. The verifier reports the
  12/16 schema match count and retains all remaining mismatches.

The first candidate `e5605fd3a4b1cf61c8ff72cc4f4f1fe0eadff303` passed native119
and public300+67, but the broader NVL2 feature selection failed (4pass/1fail):
CASE types were observed before analyzer coercion. It is retained under
`attempt-01`, including native/public/probe receipts. The revision tests types
before analysis rather than relying on the analyzer to hide that gap. The
intermediate `45ad3f5c10bfe280dac894cea72c1cc7677e1ee7` is a qualified native
checkpoint; the final commit only reattaches an adjacent NULLIF documentation
comment to its function, and is gated independently.

`manifest.json` hashes raw evidence; `verify.py` checks hashes, exact source and
CLI pins, native/public/feature results, unchanged-test control, baseline
mismatches, and retained failures. Run it with the pinned Python3.12 interpreter.
The raw observations stringify Python Decimal values in both engines.

This unit does not install a folding rule or activate the decimal SQL caster.
Existing cast/CASE nullability gaps remain explicit in the16-case comparison.
Ordinary IF/CASE early type introspection is checked separately as a possible
follow-up. Source-dependent folding, VALUES evaluation order, NaNvl laziness,
original Scala SDP suites, streaming and CDC remain required work.

The separate follow-up oracle confirms8/8 mismatches for ordinary IF/CASE
common-type introspection: Spark returns bigint or decimal(11,1), Sail reports
int, under both ANSI settings. This is the next shared-coercion implementation
unit. It is retained as failing conformance evidence, not counted as a pass.
