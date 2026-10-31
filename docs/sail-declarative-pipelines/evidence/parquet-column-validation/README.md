# Shared schema validation and Parquet metadata policy

Two review units improve Sail's general schema/file-source behavior. No LakeCat,
provider-lifetime or streaming policy is introduced. Full original Spark SDP/Scala
acceptance remains open.

## Review units

`52d4403c424542d598de70095b83c491c08c0bc4` extracts the existing
column_change::validate_field_names into a focused schema_validation module,
keeping the old import path as a reexport. Readers and schema changes share it.
It checks parent names before children, uses the accepted ROOT lowercase helper,
selects the UTF-16 lexical minimum duplicate, and preserves structured
COLUMN_ALREADY_EXISTS/42711 details. Its private diagnostic formatter follows
Spark's toSQLId(String) attribute syntax, including its dot/backtick behavior.
Arrays/maps recurse; Arrow's fixed-size array layout is covered too.

The independent Spark4.2.1 JVM SchemaUtils oracle has12 cases: one success,
ten COLUMN_ALREADY_EXISTS errors and one INVALID_ATTRIBUTE_NAME_SYNTAX error.
The native test checks the same conditions/states/parameters, including parent
precedence, multiple duplicates, quoted names, Unicode and UTF-16 ordering.
Exact gate: fmt, strict all-target/all-feature Clippy,139 common-datafusion +237
data-source +91 Plan +176 Connect tests (643 total).

`005fcb07826321693c937a23f362f2e0212aa441` validates supplied and inferred
schemas using SourceInfo.read_case_sensitive at the shared listing boundary.
The full schema is checked before partition fields can hide a duplicate. Directory
partition names are checked separately. Inferred data schemas now exclude fields
shadowed by partitions, using the same helper as supplied schemas. This preserves
partition values and removes duplicate logical columns.

Real in-memory Parquet footer tests cover root/nested case collisions independently
of parser normalization, supplied schemas, partition shadowing and duplicates
that shadowing must not hide. Exact gate: fmt, strict Clippy,139 common +240 data
source +91 Plan +176 Connect tests (646 total). No dependency was added; public
ORC writing and streaming/CDC effects remain disabled.

## Runtime and controls

- `spark-schemautils/`: actual JVM validation observations, source/runtime pins
  separate. `reference-source.json` names the relevant Spark source blobs.
- `spark-partition/`: six public Spark Parquet schema/row/error observations.
  Files contain p, P, or both; directory p supplies different values. Both case
  policies are tested. The mixed physical P/p schema still fails under false.
- `public/`: exact-source fresh CLI build,300 selected public tests +67 upstream
  Python executions. This selection is not original Scala-suite acceptance.
- `sail-partition/`: same six public schema/row/error cases against that CLI.
- `sail-external/`: seven pipeline +two direct mixed-case metadata controls from
  the historical external-read reference. The adaptation only copies its original
  Spark-produced input bytes instead of producing a new fixture with Sail. SQL,
  definitions, graph/flow settings and session policies are unchanged; URI paths
  are normalized in comparison. Original and adapted harnesses are both retained.
- `comparison.json`: six matching partition outcomes and seven matching metadata
  condition/row outcomes of nine. The two remaining differences are structured
  AMBIGUOUS_REFERENCE errors after metadata succeeds with base true/private false.
  Sail fails those queries at the right semantic stage but retains generic errors.
- `listing-control/`: removing only the three shared checks from source.rs fails
  all three unchanged integration tests (0 pass/3 fail, exit101). The test source
  blob is identical. The partition exclusion helper remains active in the control.

Owned runtime servers stop normally with no listeners. Direct control true reads
upper_value1/lower_value2 from the original Spark file; false rejects duplicate
foo. The five session-false pipelines reject metadata regardless of private true
settings. The session-true/private-false cases reach semantic ambiguity.

## Retained attempts

`listing-attempt-01/` (d7287234c) passed139 common and239 data-source tests, failing
one data-source test: inferred file p and partition p were exposed twice. Plan and
Connect tests were not reached. The assertion was preserved; schema preparation
was fixed. `listing-shadow-intermediate/` (0ad51a67a) passes646 tests, but predates
the expanded physical P/p test. The final candidate checks the full schema before
removing shadowed fields and extends that same test with the six observed cases.

`partition-attempt-01/` is a probe infrastructure failure, not a product failure:
input-p and input-P collided on the host's case-insensitive filesystem. Two cases
were retained. The corrected probe uses numbered directories and records all six.
No failed assertion or observation was replaced with a passing label.

## Limits and continuation

This establishes captured duplicate-name validation and the stated partition
cases. It does not establish every format's schema matching/evolution/inference
policy, complete partition type inference (the shared default remains STRING),
or arbitrary SDK metadata/cancellation/error ordering. Parquet inference across
multiple files and supplied-schema semantics need broader qualification.
General native structured ambiguity is the next concrete metadata-comparison gap.
Configured dynamic/WithRelations binding, CTE equivalence, captured preparation,
shutdown, streaming/Iggy/CDC durability and full original Scala acceptance remain.

Run verify.py for identities/counts/control/input hashes and comparisons.
run-probe.py OUTPUT COMMIT PUBLIC_RECEIPT external|partition requires a fresh output
directory and the qualified immutable CLI. compare.py preserves both differences.
