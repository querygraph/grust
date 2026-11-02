# Explicit CASE ELSE and nullability

Sail e18c7a81ae0c5a933c518ef8ca47727753ff8aa8, parenta51bef4ce, preserves
the trailing ELSE argument as else_expr instead of a synthetic WHEN true arm.
ELSE remains among all branch values during string/temporal normalization and
is separated only afterwards. Missing ELSE stays absent. The preceding
conditional-types unit already shares analyzer coercion among IF/CASE/NVL2.

Spark4.2.1 pin617618396087429b5627a86ce933bb0f5d6645cb and the parent CLI
agree on all16 row results, but only6 schemas. Final Sail matches all16 complete
results. Native123, formatting, strictClippy pass; restoring the parent's
production file with the exact new test blob fails0/1. Fresh final CLI passes
300 selected public cases and67 upstream Python executions. All18 selected
conditional feature scenarios pass on Spark and Sail, including temporal cases
and the existing literal CASE schema assertion. Its @sail-bug marker is removed;
the expected decimal(11,1)/nullable=false assertion is unchanged.

The candidate8403829d9 checkpoint and its passing native/public/feature receipts
are retained. An extra probe exposed that one new Rust fixture encoded an
oversimplified CASE nullability rule: it expected nullable=true for literal
WHEN true THEN1 ELSE NULL. Spark instead reports false. The fixture now selects
a NULL ELSE with a false predicate, testing a genuinely nullable ELSE. Production
code and Python features are unchanged between840 and final; final source is
independently gated. The Spark18 run at840 uses the identical final Python
tree/feature hash, which the verifier proves explicitly.

Additional required failures are preserved under unreached-null: all4 rows match
but all4 schemas differ across two ANSI modes. Spark reports false for
CASE WHEN TRUE THEN1 ELSE NULL and true for CASE WHEN FALSE THEN NULL ELSE2;
Sail reports the opposite. Spark CaseWhen.nullable has a TrueLiteral special
arm (conditionalExpressions.scala:191–201) that considers only branches through
the first true condition, while retaining preceding false branches. Its common
type still includes every branch. DataFusion folding/field inference is not
equivalent. This unit does not claim to close those cases or the older four
NVL2 cast/nullability gaps.

manifest.json hashes raw evidence; verify.py checks exact source/CLI receipts,
all tests, identical control test blob,16-case parity, parent6/16 baseline,
checkpoint equivalence, and the retained4/4 schema failures. Selections are not
full original Scala SDP acceptance. No folding rule, decimal SQL routing,
worker protocol, replay, provider or streaming activation is introduced.
