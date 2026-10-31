# Original temporary-view qualifier rejection

Two source commits:

- 60a5f290c1e019e4d01d24f140d224b583f0698f moves the dependency-free
  StructuredSparkError payload and diagnostic identifier formatter to sail-common.
  DataFusion callers retain their wrapper/re-export APIs; the struct is an exact
  blob move. Cargo.lock/dependencies are unchanged.
- db650c40e7605658b047fafac2fc721a395c4a0c applies Spark's query-defined
  temporary-view name policy and preserves structured errors through SQL,
  planner, Connect and pipeline preparation.

The pin is617618396087429b5627a86ce933bb0f5d6645cb. SparkSqlParser's query-view
path calls normalizeTempViewIdentifier (:809): bare name, SESSION.name or
SYSTEM.SESSION.name with Java case-insensitive comparison. Other qualifiers
produce ParseException/INVALID_TEMP_OBJ_QUALIFIER/42602 and the three
objectType/objectName/qualifier parameters. Existing Sail JDK17 comparison and
identifier parsing are reused, including long-s/dotted/dotless-I and diagnostic
dotted-name quirks. Malformed diagnostic names preserve
INVALID_ATTRIBUTE_NAME_SYNTAX/42601 but are reclassified as ParseException,
matching the parser boundary.

This closes the public assertion port for SqlPipelineSuite:599–615: pipeline SQL
CREATE TEMPORARY VIEW some_database.tv raises ParseException with the original
condition. Valid session-qualified direct and private views execute correctly.
Native tests also prove error metadata through direct/planner conversion and
whole-draft rollback after an earlier valid materialized-view declaration.

Validation:

- Shared move:33 common+140 common-DataFusion library tests, fmt/strictClippy.
- Behavior:29 analyzer+123 plan+185 Connect tests, fmt/strictClippy.
- Two production-only controls retain exact test blobs and fail0/1 each.
- Fresh final CLI:300 selected public and67 upstream Python executions.
- Identical19 focused tests pass on Spark4.2.1 and Sail.
- Fresh30 API/name cases match acceptance/rows or exception type, condition,
  SQLSTATE and parameters30/30, versus parent4/30. Full message origins/Java
  hierarchy rendering are not claimed equivalent by that comparison.

The first public preflight stopped before build because its frozen source hashes
predated the reviewed8e5 test-only commit. The failed receipt is retained.
Source refresh changes exactly conftest.py/test_sql_namespace.py hashes to their
8e5 blobs; selected300 identifiers, pre-existing assertions, input assets and
harness code are unchanged. Old/new preparation/manifest snapshots are retained;
the refreshed gate passes.

CREATE USING remains on its existing distinct path; qualified CREATE/DROP of
persisted views is unchanged and tested. The Spark helper's DROP docstring is
misleading: actual call sites are CREATE TEMP TABLE, local CREATE TEMP VIEW
USING and query CREATE VIEW; the grammar has no DROP TEMPORARY VIEW statement.
No new DROP syntax, dependency, streaming/provider/replay activation or general
SQL-parity prerequisite is introduced.

manifest.json hashes retained evidence; verify.py checks pins, source blobs,
native/public/paired results, counterfactuals, source-snapshot refresh and the
single original-registration inventory delta. Original Scala execution remains
false. Counts become63 partial/399 unmapped,97 reviewed/462 static sites.
Fabled262bcbf/2075e56b accept the two units.
