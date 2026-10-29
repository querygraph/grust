# Nested Spark TIME casts

One classic Spark 4.2.1 `local[1]` process ran ten cases. All ten retained the
expected schemas and nanosecond values. The process used 512 MiB driver/executor
settings, one shuffle partition, UTC, ANSI mode and whole-stage code generation.
TIME was initially disabled and was explicitly enabled before these cases.

`probe.py` and `runtime.log` retain the exact run. `results.json` records SQL,
Spark schema JSON/DDL, Arrow schemas, integer TIME values, optimized plans,
configuration, installed jar hashes and source receipts. Input strings derive
from `range`, so these cases exercise nonconstant input. Nested TIME leaves are
serialized directly as integer nanoseconds, without Python datetime conversion.
All failures would be retained; this run produced none. No Sail build or runtime
execution occurred, and no repository files were edited by this probe.

## Results

All source TIME(0) values come from the string `12:34:56.123456` and contain
**45296123456000 ns**, despite their declared precision. A changed target
precision of 3 yields **45296123000000 ns**. An identity cast preserves the
original value.

| Case | Result |
|---|---|
| Array TIME(0) → TIME(3) | Element truncates; null element remains null. |
| Array TIME(0) → TIME(0) | Fractional bits remain; null remains null. |
| Struct fields → TIME(3), TIME(0) | First field truncates; second retains fractional bits. |
| Struct identity | Both fields retain fractional bits. |
| Map STRING → TIME(3) values | Time value truncates; null value remains null. |
| Map value identity | Fractional bits remain. |
| Map TIME(0) → TIME(3) keys | Time key truncates. |
| Map TIME(0) key unchanged, value → TIME(3) | Key retains bits; value truncates. |
| Array of mixed structs | Changed leaf truncates; unchanged leaf and null struct are preserved. |
| Struct with renamed fields | Conversion is positional; only changed leaf truncates. |

The schemas preserve each declared leaf precision. All TIME leaves still export
as Arrow `time64[ns]`.

## Source and Sail impact

Pinned Spark source is `617618396087429b5627a86ce933bb0f5d6645cb`.
`Cast.scala:1225–1265` recursively casts array elements, map keys/values and
positional struct fields. Each leaf reaches the ordinary cast dispatch;
`:1268–1272` preserves structurally identical Spark types. The TIME branch at
`:828–837` truncates different-precision TIME casts. Corresponding generated-code
paths are retained at `:1348–1358`, `:1497–1529` and `:2284–2392`.

Three Sail working-file snapshots are retained with hashes and their HEAD at
capture. They include uncommitted work and are **source observations only**:

- `sail-expression-cast-working.rs:116–130` recognizes the special precision
  conversion only for a top-level `spec::DataType::Time`. Nested targets reach
  ordinary casts at `:370–371`, or the structural rename path. A scalar-only
  precision fix therefore leaves a separate nested conversion boundary.
- `sail-type-resolver-working.rs:131–134,313–317` resolves every semantic TIME
  precision to nanosecond storage and carries precision on fields. Different
  nested precision metadata cannot be implemented by changing Arrow units.
- `sail-recursive-array-cast-working.rs:111–114,240–251,308–328` is a separate
  schema/array adaptation helper, not the SQL expression-cast dispatcher. Its
  recursive calls pass child DataTypes and short-circuit equal storage types;
  using it unchanged would relabel TIME precision without truncating values.
  ORC schema adaptation must preserve incoming bits, so globally changing that
  helper to truncate by metadata would conflate reading with SQL CAST semantics.

The concrete implementation requirement is a recursive semantic SQL cast that
compares source and target TIME precision at each leaf, preserves identity
leaves, transforms only changed leaves, and handles map keys and positional
struct renaming. Until implemented, reject unsupported nested precision changes
explicitly rather than silently reporting the target schema with old values.
Such a guard is a temporary unsupported boundary, not Spark parity. This oracle
contains no claim that current Sail executed or failed these cases.

Installed artifacts identify themselves as Spark 4.2.1. Their hashes are recorded,
but they are not asserted to have been built from the exact pinned source commit.
`audit.py` checks retained results and source receipts without launching Spark.
