# JVM `StructType.merge` oracle for the pipeline schema merge

Pins the raw merge failure Spark's last validation phase (`DataflowGraph.inferredSchema`,
`DataflowGraph.scala:174–182`) raises unwrapped, and the pair of types it reports.

- Oracle: `MergeOracle.java` over the Spark 4.2.1 jars in Sail's
  `.venvs/fable-spark-4.2.1` (hashes in `provenance.txt`), JDK 17.0.8, calling the
  `private[sql]` instance method `left.merge(right, caseSensitive = true)`, which is
  what `SchemaMergingUtils.mergeSchemas` delegates to.
- Cases: `cases.txt` to `cases4.txt` (64 pairs: scalars, nested structs, arrays, maps,
  decimals and their defaults, intervals, time, variant, void, quoted names, `NOT NULL`,
  SMALLINT and CHAR/VARCHAR lengths at every nesting depth).
- Raw output: `merge-oracle*.out`.

Findings carried into Sail (`pipelines/schema_merge.rs`, `pipelines/schema.rs`):

- Class `org.apache.spark.SparkException`, condition
  `CANNOT_MERGE_INCOMPATIBLE_DATA_TYPE`, SQLSTATE `42825`, parameters `left` and
  `right` as the `.sql` rendering in double quotes, no cause.
- The reported pair is always the **top-level** field's types, whatever the depth
  of the mismatch (`STRUCT<b: STRUCT<x: INT>>` against `STRUCT<b: STRUCT<x: STRING>>`
  reports the outer structs; arrays and maps likewise), because each struct level
  rethrows with its own field types (`StructType.scala:610–626`).
- Accepted merges: same-scale decimal precision widening, year-month and day-time
  interval unit union, nullability union, field-order and extra-field union; no
  integer, float or string-length widening. Sail's kernel already matched every
  case; only the reported pair changed (innermost → top-level).
- Parameter parity: `schema::sql_type_name` renders `toSQLType` from the retained
  spec types (Sail `b61da2c98`, per CF-0089), so every `left`/`right` string in the
  64 cases matches the JVM byte for byte, including `SMALLINT`, `CHAR(n)`/`VARCHAR(n)`
  in nested positions, `TIME(6)` and `DECIMAL(10,0)` defaults and `VOID`. The public
  `toDDL` renderer (which prints `SHORT`, pinned by `test_toddl.py`) is untouched.
  Schema acceptance (the `Ok` rows) is compared after both sides pass through Sail's
  DDL renderer and is a separate property from string parity.
