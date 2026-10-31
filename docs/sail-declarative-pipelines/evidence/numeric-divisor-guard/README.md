# Numeric divisor evaluation evidence

Sail candidate `b857dabb74da0484b781c096f9a9cd6a78daaa5c`, parent
`5a1142bcd90b97385314610f1342e1a9a4879690`; Spark 4.2.1 source
`617618396087429b5627a86ce933bb0f5d6645cb`. This packet qualifies a
single-evaluation numeric divisor guard. It does not qualify complete arithmetic
parity or the original Scala SDP suites.

The unary `SafeNumericDivisor` checks an already evaluated numeric/Null value,
returns its original datatype and metadata, preserves nulls and nonzero values,
recognizes both floating zero signs, and either raises the existing structured
arithmetic exception (ANSI) or replaces zeros with typed nulls (legacy). Numeric
arithmetic keeps its native kernels and coercion. Four stateless StandardUdf
names encode kind/mode; legacy nullary error decoding remains supported. No new
protobuf or dependency is introduced. Nonnumeric fallback still uses the old
comparison/CASE or NULLIF; intervals/durations keep their existing path.

## Why the expression changed

The old ANSI CASE duplicates its divisor. Independently, pinned DataFusion 55.2.0
`CaseExpr::nullable` evaluates predicates on a dummy batch without checking
volatility (`case.rs:1255–1304,1506–1524`). Backtraces and counter stages establish
this cause; no registry source was modified. Dependency file hashes and Cargo.lock
blob are in [dependency-source.json](dependency-source.json). Fable corroborated
the stages in Grust review `9a99e28e` and reviewed this candidate in `2b6c00cb`.

The stable-callback stage probes are test-only, unadvanced commits. Lowering and
DataFrame construction make zero calls in both runs. Collection counts:

| Expression | Parent | Candidate |
| --- | ---: | ---: |
| Volatile UDF | 1 | 1 |
| abs(UDF) | 1 | 1 |
| Explicit duplicated CASE | 6 | 6 |
| Sail guarded division | 7 | 1 |

The explicit CASE remains an executable generic dependency failure. The source
regression uses an alternating nonzero/zero volatile divisor, asserts one call,
and returns the first value's quotient. Restoring only the old production
expression makes this unchanged test fail. Removing only the four codec decode
entries makes the unchanged codec test fail. Both controls are 0 passed/1 failed;
test blob equality and single-file production mutations are verified.

## Qualified results and limits

- Detached formatting, strict all-target/all-feature Clippy, and 913 libraries:
  execution230, function396, plan107, SparkConnect180. Numeric scalar widths,
  decimal types, nulls, signed zeros, NaN/infinity, sliced arrays and field metadata
  are covered; four codec variants execute after decoding.
- Fresh exact-source CLI: 300 selected public cases and 67 upstream Python
  executions pass; owned server exits0 and listeners are empty.
- [Previous core corpus](../deferred-arithmetic/README.md): all40 outcomes,
  metadata/raw error fields, and33 successful schemas still match Spark.
  Existing phase48 stays33 behavior/13 metadata; arithmetic14 stays10/7;
  provenance20 observations remain identical. Directive phase output paths differ
  only by this run's output directory. Empty raw-error lists in older probes
  are not proof of meaningful wire parity.
- Runtime12 retains six failures (ANSI null-input/volatile-null/window-null/pmod).
  Floating DIV retains two domain failures. These are required work, not accepted
  deviations. Right-first evaluation and conditional dividend evaluation remain
  unresolved by a unary divisor guard.
- The added22 decimal/CASE/string cases compare rows, schemas, exceptions and raw
  errors with fresh Spark and a clean, rebuilt parent CLI. All22 rows/errors match the parent; two legacy decimal remainder schemas improve
  from decimal(10,2) to Spark decimal(5,2), including a zero divisor. All other
  observations remain identical. Full additional-corpus parity is not implied.
  Spark comparison:16 outcomes,20 metadata/raw comparisons,7 successful schemas
  match. Decimal division precision/scale, CASE result nullability and string
  arithmetic domains remain required. Two string-literal operands are rejected with BINARY_OP_WRONG_TYPE in ANSI
  mode and accepted in legacy mode. A mixed numeric/string pair is accepted in
  both modes. Do not infer a blanket string-to-double coercion rule.

The initial additional recorder failed serializing Decimal values for both
engines; logs are retained and owned servers stopped. The corrected recorder
serializes Decimal as strings while recording exact schemas. This is a recorder
failure, not an engine verdict. The first candidate's Clippy failure (missing
ColumnarValue test import) is retained in attempt-01 and never advanced.

The parent-only extra build is qualified for22 probes, not a new full public
suite. After it, gate HEAD is restored to candidate but its CLI remains the
parent binary. Do not reuse that binary with the candidate's public receipt.
All archived runtime receipts name the exact source and binary used at execution.

## String-mode correction (CF-0351–0352)

The first prose summary misread the original22-case comparison as rejecting
strings under both modes. Raw observations and16/20/7 comparison counts were
correct throughout: only ANSI rejects the two-string rows. Fable0a276ae9 caught
the prose error. A fresh16-row Spark Connect audit records effective settings,
true/false/true/false toggles, identical SQL and mode-specific comments; it
corroborates ANSI rejection, legacy3.5/NULL and mixed7/'2'→3.5 in both modes.
There is no observed query-reuse or configuration failure. Raw original evidence
is unchanged; the reporting error is corrected, with append history retained.

## Verification and replay

Run `python verify.py` with Python3.12 from this directory. It validates manifest
hashes, source/test pins, exact gate counts, controls, phase counters, runtime
receipts, unchanged observations and required gaps. Grust/Sail Git objects and
sibling historical evidence packets must be available. SHA256.json covers every
other file. Scripts preserve original absolute paths as historical commands;
replaying requires fresh output paths and exact detached source/binary ownership.
The ordinary SDP coverage inventory remains462 sites,97 reviewed,61 partial,
401 unmapped; no full original Scala-suite acceptance is claimed.
