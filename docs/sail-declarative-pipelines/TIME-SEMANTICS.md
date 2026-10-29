# Shared Spark TIME semantics

Spark reference: **4.2.1**, source `617618396087429b5627a86ce933bb0f5d6645cb`.
This records the shared type decision reached during the announced ORC temporal
checkpoint. TIME is a Sail type-system concern; neither pipeline-specific schema
patching nor a LakeCat adapter can preserve it through arbitrary nested fields.

The [scalar reference](evidence/time-semantics/reference/README.md) retains 23
operations, including 12 expected rejections, and 191 source/result checks. The
[nested reference](evidence/time-semantics/nested-reference/README.md) retains ten
successful Spark operations and 50 checks. Installed jar hashes and source pins
are recorded separately; the jars are not claimed to have been built from the
source checkout. These are Spark reference observations, not Sail verdicts.

## Representation and compatibility

Add `spec::DataType::Time { precision }` for Spark precision 0 through 6, default
6 at protocol/parser boundaries. Resolve every precision to Arrow
`Time64(Nanosecond)` and carry declared precision in the existing internal
`SAIL::spark::time` field metadata. Preserve raw Arrow `Time32` and `Time64`
variants and their existing unit mappings. A semantic typed-null literal retains
both its precision and nanosecond storage. Resolve nested list/map/struct fields
through the same field-aware path, including literal construction.

Arrow storage units cannot reconstruct declared precision. Arrow-to-Connect
output and Connect-to-spec input must preserve the logical type so that pipeline
schema analysis can use the normal shared conversion. Spark `StructType.merge`
accepts equal TIME precisions with merged nullability, and rejects different
precisions recursively. Do not add widening merely because the physical storage
types match. Internal precision metadata must remain hidden from user metadata.

## Cast values are independent of storage units

The reference value `12:34:56.123456` is 45,296,123,456,000 nanoseconds.
String-to-TIME casts retain that value for every declared precision. A TIME cast
to the same declared precision also retains it, including extra fractional bits
under a declared TIME(0). A cast to a different precision `q` truncates to
`10^(9-q)` nanoseconds. This applies even when `q` is greater than the source
precision; a declared TIME(0) to TIME(1) cast truncates to tenths.

The rule recurses into array elements, struct fields and map keys/values. Only
changed leaves truncate; identical leaves retain their bits. Preserve container
nulls, slices and positional struct casts. A plain Arrow cast between equal
nanosecond types loses this semantic operation.

Implement direct scalar precision changes with existing integer/Arrow
expressions where possible. For nested values, a focused field-aware TIME
precision transform may prepare an intermediate array before the normal cast.
It must preserve source shape and non-TIME leaves, so existing name and type
conversion behavior still belongs to Sail's shared cast path. Carry source and
target fields through the existing worker codec; nested metadata is part of
that contract. Do not alter the metadata-only struct-renaming helper to perform
hidden value changes.

## Review units and activation gate

1. Shared semantic type, typed-null and nested field/literal preservation.
   This unit does not change Connect's inbound TIME mapping or SQL parsing.
2. Precision transform and worker codec, with actual scalar/array execution,
   nested null/slice preservation and decoded-worker behavior.
3. Planner cast wiring and Connect schema activation, including optimized
   execution over columns, schema roundtrips and schema-merge errors. Activate
   only after direct and recursive precision changes have correct values.
4. Remaining SQL type/literal, non-null Connect literal, formatting/functions
   and configuration parity in separately reviewed shared units.

The existing SQL analyzer and non-null Connect literal paths use storage-unit
conventions and require their own corrections. JSON/CSV/XML schema converters
also need field-aware handling before switching SQL type analysis. Existing
TIME functions returning microseconds are not an implementation of nanosecond
precision casts. Normal Spark runtime defaults TIME disabled, while the source
default is conditional on `Utils.isTesting`; keep configuration integration
separate from the representation decision.

The ORC bridge must preserve encoded TIME nanoseconds and declared precision
without truncating values simply because a field declares a lower precision.
This checkpoint does not complete SQL TIME parity, ORC source registration or
any streaming/CDC runtime work.

## Qualified implementation

Recorded: 2026-10-29T21:05:59.836586+00:00. Sail `6bba6817b52c53d532e8019421293b5e20619905` implements review unit 1. Its [receipt](evidence/time-semantics/core/gate.json) records 17 common and 28 planner library tests, formatting and strict all-target/all-feature Clippy on the exact detached candidate. The Connect mapping and cast changes are deliberately outside this commit. The test link step emitted the retained macOS unwind-table size warning; all tests completed successfully. No CLI or public SDP verdict was produced.

## Qualified cast and Connect units

Recorded: 2026-10-29T21:36:49.540828+00:00. The [activation archive](evidence/time-semantics/activation/provenance.json) retains four separately gated commits:

| Sail commit | Boundary | Full library tests |
| --- | --- | --- |
| `2f5192d50a` | Recursive precision transform and worker UDF payload. | 390 function / 155 execution |
| `aacea1ecfb` | Scalar and recursive cast activation; nested type display. | 37 planner |
| `dce4bd7514` | Sliced arrays, signed truncation and physical worker expression execution. | 394 function / 156 execution |
| `39e63d6863` | Connect schemas, typed/non-null literals and pipeline schema merging. | 60 Connect |

All four pass formatting and strict all-target/all-feature Clippy on their exact detached candidates. The first transform candidate failed to compile a codec test because of an unavailable direct Arrow import; the correction and failed logs are retained. These counts are overlapping library suites, not additional SDP assertions.

The planner runs the recursive TIME transform before its existing positional rename and ordinary leaf casts. Optimized column tests preserve identity bits, changed precision, nested nulls and mixed numeric casts. The worker test serializes, decodes and evaluates an actual physical column expression. Connect now accepts every declared precision 0 through 6, preserves nanoseconds in non-null literals, validates day bounds, and honors an explicit root literal type. Typed-null root precedence is corrected in the shared literal converter.

Remaining shared work includes SQL type/literal lowering, TIME-specific string parsing, configuration admission, field-aware schema converters and enclosing-type propagation for container literals. Native ORC timezone conversion and Sail ORC registration remain separate. No full SDP, streaming or CDC verdict follows from these units.

## Public runtime qualification

Recorded: 2026-10-29T21:42:25.105752+00:00. Sail `1e1d3760ab23ce61d2f8eb3b9a7a272b4f0a4564` passes **285 selected pytest cases and 67 upstream Python executions** on a freshly built CLI. The [runtime archive](evidence/time-semantics/public/provenance.json) records the binary hash, exact candidate, commands, environment and raw results. Eight new shared TIME checks pass unchanged on installed Spark4.2.1; the previous Sail CLI passes one and fails seven. They cover all49 scalar precision pairs, declared schemas, fractional values, null/day boundaries, nested arrays/maps/renamed mixed structs, and a Python TIME literal.

The first new Sail launch passed281 and failed4 during `createDataFrame` configuration lookup because it lacked the established Python environment. Restoring `PYTHONPATH` and `VIRTUAL_ENV` fixed the focused control and full run without changing the binary or assertions. The initial failed gate is retained alongside a corrected Spark-runner port setup failure. The canonical462 SDP registrations,97 assertion reviews and59 partial ports remain unchanged; these shared-type regressions do not close additional upstream SDP assertions by themselves.
