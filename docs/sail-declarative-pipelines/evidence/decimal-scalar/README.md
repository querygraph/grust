# Callable Spark decimal string cast component

Sail `8a7bf8ca4d98d43437eb005dde5db5b1f024e13c`, parent63f5bd3b3.
This unit adds an unregistered SparkStringToDecimal ScalarUDF for Spark's
Decimal128 precision1..38 domain, a private scanner/rescaler and native fixtures.
It extracts the primitive caster's existing malformed-string factory for reuse;
primitive error behavior is covered by the unchanged existing function tests.
No dependency, resolver routing, worker codec, arithmetic mode or SQL folding
policy changed. Existing extended Decimal256 paths remain unchanged.

The immutable UDF captures precision, scale, fail_on_error and input negative-
scale policy. Legacy and TRY_CAST share fail_on_error=false. The last flag is
orthogonal: even a positive-scale target has different overflow error kinds
when Spark permits parsed negative scales. A fresh32-case Spark4.2.1 Connect
oracle records that difference and exact structured parameters. Negative target
refusal remains a resolver/config decision; the pure UDF accepts Arrow's valid
negative-scale types. Captured policy/wire support is required before SQL use.

The parser follows Java BigDecimal's UTF-16 char grammar, ASCII-control trim,
exponent and resulting i32-scale bounds. Zero is returned after grammar/scale
validation. Integral-range checks precede bounded HALF_UP rescaling to i128;
no exponent-sized integer or string is built. Overflow rendering follows Spark's
plain parsed-value display except scales below-1000, which use scientific form.
Malformed22018, unsupported-range22003 and target-overflow22003 are distinct.
Only data errors become NULL in null-on-error mode; type/arity errors remain
errors. Scalar and array adapters use one value conversion, preserving scalar
representation and original array order/slices. Fields are nullable in all modes,
clear Arrow extension annotations, and retain ordinary source metadata.

## Qualification

- All410 sail-function libraries, formatting and strict Clippy pass.
- Four production-only controls alter rounding, Java trim, captured-policy
  plumbing and field nullability. Each fails the same unchanged test0/1.
  Test/fixture blobs and exact source patches are pinned.
- The original192-cell Spark oracle is losslessly reduced to96 distinct
  decimal policies/inputs. Fresh32 policy cases extend it. Each128 native case
  runs as scalar and one-row array in all three Arrow string layouts; class,
  condition, SQLSTATE and complete error parameters are checked.
- Additional tests cover null/mixed/sliced/empty batches and first-error row,
  HALF_UP carry/38-digit boundaries, extreme exponents, canonical overflow
  values, negative target scales, type-only fields and ordered LiteralEvaluator
  skipping a strict failing decimal thunk under rightNULL.
- Independently generated JDK20.0.2 Character.digit(char,10) mapping checks all
  65536 Java char values:37 BMP ten-digit blocks. Native tests compare every
  valid Rust BMP char and reject supplementary digit surrogate pairs, circled
  and superscript digits. Spark policy32 independently confirms three such
  supplementary rejections and Arabic digit acceptance.

This is native callable-component evidence. The public CLI remains qualified at
parent63f5; no fresh public300/67 run or SQL use of this new class is claimed.
Full message/origin/public transport equivalence and exhaustive Java grammar
coverage are not established by these samples. Original Spark SDP suite coverage
and the source-dependent folding failures remain required, as do streaming/CDC.

Two failed test drafts are preserved: initial unused import/serde error conversion
compilation, then a fixture policy field not passed into the constructor. The
intermediate409-pass candidate is also retained. Assertions were not weakened.
All controls restored the clean exact component candidate before branch advance.

Next reviewable units: worker serialization for all captured policy; generic
Sail config/type policy and resolver routing; source/conditional-aware folding
before activation. New NUMERIC_* conditions must enter the audited raw error
vocabulary before a future fast path admits this class. No replay/default,
provider/streaming/ownership change, push or release was performed.

Run verify.py for source, hash, fixture and gate checks. The Spark192 source
oracle lives in the prior source-dependent-cast-folding packet; its original
assertions and mismatches are retained there. Archived launch/control helpers
use original absolute worktrees and /tmp paths; inspect before reuse.

Fable6b7fe4de independently [accepts the component](peer-review.md), with no
correctness findings. It confirms Java's UTF-16 char domain and the orthogonal range flag.
The same exhaustive mapping helper was also run on installed JDK17; its37 starts
are identical to JDK20, with the raw report and command/hash receipt retained.
