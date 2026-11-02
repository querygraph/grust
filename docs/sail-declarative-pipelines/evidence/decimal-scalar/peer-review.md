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
