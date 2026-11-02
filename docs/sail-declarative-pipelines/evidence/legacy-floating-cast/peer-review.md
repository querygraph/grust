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
