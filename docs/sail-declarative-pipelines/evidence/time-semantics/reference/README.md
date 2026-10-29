# Spark 4.2.1 TIME semantic reference

This standalone oracle ran one installed Spark 4.2.1 classic session with `local[1]`,
512 MiB driver/executor settings, one shuffle partition, UTC and ANSI enabled.
It does not execute or qualify Sail. Spark source excerpts are pinned to
`617618396087429b5627a86ce933bb0f5d6645cb`. The report records installed jar hashes;
it does not assert that those jars were built from that exact source commit.

`probe.py` generated `results.json` and `runtime.log`. There are 23 cases:
11 successful operations and 12 retained expected rejections. Each rejection has
its full traceback. `audit.py` verifies the retained observations and source
excerpts without running Spark. `validation.json` records 191 passing checks.
`files.json` hashes every retained regular file except itself. Spark scratch and
warehouse paths contain no retained evidence files.

## Observed contract

- The initial normal-runtime `spark.sql.timeType.enabled` value was `false`.
  Both the initial default and explicit `false` reject SQL typed-null TIME casts
  with `UNSUPPORTED_TIME_TYPE`. All subsequent cases explicitly enable TIME.
  The pinned configuration default is **`Utils.isTesting`**, so it is not an
  unconditional `false` in Spark test environments (`SQLConf.scala:7435–7441`).
- SQL `TIME(0)` through `TIME(6)` retain their exact precision in schema JSON.
  Unparameterized `TIME` produces `time(6)`. Typed nulls have the corresponding
  nullable TIME schema and a null Arrow value. Precisions 7 and 9 reject with
  `UNSUPPORTED_TIME_PRECISION` (SQLSTATE `0A001`).
- Every precision exports as Arrow `time64[ns]`. Precision is a separate logical
  property; the Arrow storage unit alone cannot reconstruct it.
- `CAST('12:34:56.123456' AS TIME(p))` yields **45296123456000 nanoseconds** for
  every `p=0..6`, including `TIME(0)`. The dynamic string expression gives the
  same result. Declared precision therefore does not imply those lower bits are
  absent, and a schema or ORC bridge must not truncate them by inference alone.
- For a TIME value created from that string, casting **to the same precision**
  preserves those bits. Casting **to a different precision q** truncates to
  `floor(nanoseconds / 10^(9-q)) * 10^(9-q)`. Both constant and dynamic 7×7 cast
  matrices confirm this distinction. For example, declared TIME(0)→TIME(1)
  produces 45296100000000 ns, while TIME(0)→TIME(0) preserves 45296123456000 ns.
  TIME(6)→TIME(3)→TIME(6) remains 45296123000000 ns.
- JVM `StructType.merge(other, true)` merges equal TIME precisions and ORs field
  nullability. Different TIME precisions reject with
  `CANNOT_MERGE_INCOMPATIBLE_DATA_TYPE` (SQLSTATE `42825`) at top level and inside
  arrays, maps and structs. Distinct field names retain their separate types.
  TIME(3) versus VOID also rejects. This is the JVM schema-merge contract, not
  SQL UNION/type-coercion or Python `_merge_type` behavior.

## Paired source

`results.json.source_evidence` and `source-supplement.json` record exact paths,
line spans, Git blob IDs, whole-source hashes and excerpt hashes. All 14 excerpts
were checked against pinned Git objects.

| Behavior | Pinned source span |
|---|---|
| Valid precision/default/type name | `sql/api/.../types/TimeType.scala:23–59` |
| SQL default precision | `sql/api/.../parser/DataTypeAstBuilder.scala:352–364` |
| Config default/gating | `sql/catalyst/.../internal/SQLConf.scala:7435–7442`; `sql/catalyst/.../util/TypeUtils.scala:137–148` |
| Arrow nanoseconds | `sql/api/.../util/ArrowUtils.scala:64–75` |
| String and TIME cast branches | `sql/catalyst/.../expressions/Cast.scala:828–837,1497–1529` |
| Same-type identity | `sql/catalyst/.../expressions/Cast.scala:1268–1286,1348–1373` |
| Truncation and string parsing | `sql/api/.../util/SparkDateTimeUtils.scala:158–185,711–786` |
| JVM schema merge | `sql/api/.../types/StructType.scala:477–488,597–701` |

The source string-parser comment mentions microseconds, while its implementation
constructs `LocalTime` and returns `localTimeToNanos`; observed Arrow integers
and the explicit Arrow mapping establish nanosecond storage. Preserve the source
comment as evidence rather than silently correcting the excerpt.

## Implications for Sail acceptance tests

Retain declared precision separately from nanosecond storage through parsing,
resolved types, typed nulls, nested schemas and metadata roundtrips. Check both
schema equality and integer values. Equal-unit Arrow casts alone cannot implement
cross-precision TIME casts because every precision uses the same Arrow unit.
Keep identity casts separate from different-precision truncation, and do not
silently widen different TIME precisions during Spark-compatible schema merge.
These are source-backed design requirements; this artifact contains no Sail test
results. Config-gating behavior remains a separate integration decision.
