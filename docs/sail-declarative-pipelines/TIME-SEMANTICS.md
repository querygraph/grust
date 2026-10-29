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
