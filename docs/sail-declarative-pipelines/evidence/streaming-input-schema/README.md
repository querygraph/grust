# Streaming read schema of materialized virtual inputs

Sail 7a32efd2a62e3668a64e21e87c3f9dc0938e1912 (parent ba0d692c6) adds pipelines/schema_stream.rs, the single definition of the schema a STREAM read of a virtual table exposes. Batch reads, final inferred schemas, publication and command reanalysis do not use it.

## Measured contract (Spark 4.2.1 at 617618396, framework default false)

| Property | STREAM read | Evidence |
| --- | --- | --- |
| Field metadata | Dropped at top level and inside structs, arrays and maps; batch retains it | observations-01 metadata_real, a real run |
| Names, nullability | Retained at top level and nested | observations-02 nullable_*, with discriminating controls |
| Intervals | Widen to the full family, both framework modes, both map sides | observations-01 types_* |
| TIME | TIME(6) unless the framework is on, including map keys | observations-01 types_* |
| Declared CHAR/VARCHAR | UNSUPPORTED_DATA_TYPE_FOR_ENCODER unless spark.sql.preserveCharVarcharTypeInfo | observations-01, observations-03 char_* |
| Inferred CHAR/VARCHAR | STRING, or CHAR(n) when preserved | observations-03 char_* |
| Setting precedence | flow over graph over session | observations-01 precedence_* |
| View contribution | Reaches the read through the merged second call | observations-03 second_call_* |

**This corrects the earlier scoped-read-mode README and handoff, which said to preserve metadata.** ExpressionEncoder.scala:215 rebuilds top-level fields from name, type and nullability, and CreateNamedStruct takes metadata only from named expressions, which the RowEncoder serializer's If/AssertNotNull fields are not. The measured real run confirms the source reading.

**Method limit.** observations-02 view_second_call_* are invalid as second-call evidence: sqrt(TIME) fails the first call, so the merged call never runs and the result follows the session. They are retained. observations-03 replaces them with a declared consumer, which passes the first call and discriminates only at schema validation.

## Qualification of the exact candidate

- fmt, strict Clippy, 125 Plan and 237 Connect library tests: gates/library-02.log.
- Frozen 300 selected public and 67 upstream: gates/frozen-public-receipt.json, outcome passed.
- New test_streaming_input_schema.py: 58 pass on Spark 4.2.1 (exit 0) and 58 pass on the candidate binary. Spark's run used -q -q, so that log carries no count.
- Control: the same tests on the ba0d692c6 binary give 40 failed, 18 passed.
- Spark and Sail run the same test bytes. Failures retained below.

## Retained failures and open items

- First candidate 6d2b11085: 57 of 58 on Sail. Its one failure came from Sail's named_struct reporting nested fields nullable for literals, while struct() is correct. The fixture was changed to struct(1 AS x), keeping the assertion. **The named_struct nullability gap is real, general and unfixed.**
- An earlier compile failure on quoted_type visibility was masked as exit 0 by a pipe into tail; later runs use pipefail.
- Metadata and CHAR-preserved behavior are covered natively; a dry run cannot observe metadata publicly.
- Collated strings are unmeasured: all collation cases were accepted or blocked by a Spark flow-type check, and no type was observed. Sail has no collation contract here.
- Computed IDENTIFIER targets still bypass the projection through the late-bound path. Spark paired coverage of STREAM(IDENTIFIER(...)) has not been run.
- Public streaming execution stays disabled. This is analysis-only, not original Scala-suite acceptance.
