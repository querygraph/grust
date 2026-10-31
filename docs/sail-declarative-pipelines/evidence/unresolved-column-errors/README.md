# Structured unresolved-column errors

This is general Sail resolver/error support used by SDP. It closes the five
structured-error differences in the thirteen-case flow configuration packet,
without changing successful name binding or introducing a pipeline translator.
Original Scala suites and broader SDP acceptance remain unqualified.

## Review units

- `abadcd8b068d10429ca550dcb51c9a36bf3f42c6`: add a boxed shared
  StructuredSparkError to PlanError and preserve it through SparkError's existing
  Connect codec. The existing full-metadata transport test also exercises this
  planner branch. Exact fmt, strict Clippy and 88 Plan +176 Connect tests pass.
- `7b5667c1fef901c5f6768fd5af222beeed453f15`: after native attribute and outer
  lookup fail, construct UNRESOLVED_COLUMN.WITH_SUGGESTION or WITHOUT_SUGGESTION,
  SQLSTATE42703, objectName and optional proposal. User-facing field names come
  from existing resolver state, not internal field IDs; hidden fields are omitted.
  Shared qualifiers are stripped before stable Levenshtein ordering; comparison
  uses Java UTF-16 units and escaped multipart names. At most five proposals are
  emitted. Existing matching, ambiguity, nested-field and plan-ID policies remain.
  Exact fmt, strict Clippy and 91 Plan +176 Connect tests pass.

Both reuse Sail's existing shared error representation and transport. No dependency
or provider/lifecycle behavior was added. The native test uses real parsed SQL,
not direct calls to the diagnostic constructor. SDP failure-order assertions now
require the structured condition, state and column/proposal details.

## Independent reference and runtime evidence

`reference-source.json` pins Spark source files for unresolved error construction,
qualifier trimming, identifier quoting and UnresolvedAttribute.sql. The ordinary
Connect oracle ran installed Spark/PySpark4.2.1, with the source pin recorded
separately. This is not execution of those source Scala suites against Sail.

- `spark-ordinary/` and `spark-ordinary.log`: twelve independent reference cases,
  eleven errors and one case-insensitive success. The reference session stopped;
  an explicit listener check confirms15002 is free.
- `sail-ordinary/`: same twelve inputs against the exact rebuilt Sail CLI.
  Condition, SQL state, exception type and all message parameters match for all
  eleven errors. The successful case's rows match too. Inputs include joins,
  qualifier stripping, stable ties, five proposals, dots/backticks and Unicode.
- `sail-config/`: identical thirteen inputs from the historical flow-config-fusion
  reference packet. All error-condition/success-row outcomes now match, improved
  from3/13 at163b and8/13 at1bc. The five missing-column first-line messages also
  match Spark exactly. Duplicate-flow parameter/provenance equivalence is not
  established by this comparison; the fixture uses different default catalogs.
- `public/`: fresh exact-source CLI build,300 selected public tests and67 upstream
  Python executions, all passing. Every owned Sail server stopped exit0 and left
  no listeners. These selections are not full SDP acceptance.
- `native-control/`: unchanged native SQL test fails when only the final attribute
  failure sites are restored to their old implementation. Two helper tests pass,
  one native-resolution test fails (exit101). Its test source blob is unchanged.

`comparison.json` records the exact scope and matching observations. `compare.py`
rechecks inputs, identities, raw hashes, metadata, rows and message comparisons.
`run-probe.py OUTPUT COMMIT PUBLIC_RECEIPT ordinary|config` uses a qualified immutable
CLI and refuses source/binary drift; use fresh output directories.

## Retained failures and fixture changes

`attempt-01/` passed91 Plan tests but failed one of176 Connect tests: the SQL
function golden test still expected the old unstructured dimension_col failure.
The exact expected error was updated in agg.json. `attempt-02/` then exposed two
remaining old failure strings in predicate.json (91 Plan pass,175 Connect pass /
1 fail). The official SAIL_UPDATE_GOLD_DATA=1 filtered function test generated
those two updates. `golden-generation/` preserves its successful run and diff.
Only three error-output strings across two fixtures changed; inputs, success rows
and failure outcomes are unchanged. No error assertion was loosened. The final
immutable full gate ran without the update environment variable.

Remaining generic errors from nested extraction, ambiguity and special plan-ID
validation are separate work; this unit covers final unresolved attributes.
Configured dynamic/WithRelations binding, Parquet metadata case handling, captured
preparation/admission, SDK lifetime/shutdown, streaming/Iggy/CDC durability and full
original Scala acceptance remain. See the current native binding design and
FABLE-HANDOFF.md. The goal remains active.

Run `verify.py` for packet hashes, exact library/public receipts, the unchanged
control, golden input preservation and both comparisons.
