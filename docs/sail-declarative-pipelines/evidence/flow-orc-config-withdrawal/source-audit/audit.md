# ORC flow-configuration candidate: source audit

Spark source pin: `617618396087429b5627a86ce933bb0f5d6645cb` (4.2.1). Sail comparison baseline: `71f24a87a2f2b5b38bd012388e3ce6589c7c6d46`. This packet contains read-only source analysis, not a new runtime result. `sources.json` records the exact repository paths, full Git blob IDs, full-source SHA-256 hashes, and inclusive line ranges for every verbatim excerpt in `windows/`.

The candidate's proposed ORC merge behavior is not justified by the cited Spark configuration tests. The reference probe shows a direct ORC read retains its registration-time schema even with graph/flow `mergeSchema=true`. Changing Sail to merge that schema would diverge from this observed Spark 4.2.1 path. Withdrawing the candidate avoids claiming parity from an invalid oracle. This conclusion does not establish that every candidate helper is intrinsically incorrect, or decide future writer behavior.

## Registration

- `python/pyspark/pipelines/api.py:270–297` passes `spark_conf or {}` when creating the materialized-view flow. `spark_connect_graph_element_registry.py:113–134` serializes that map directly as `DefineFlow.sql_conf`; it does not copy ambient session settings.
- `sql/connect/server/src/main/scala/org/apache/spark/sql/connect/pipelines/PipelinesHandler.scala:211–219` preserves the graph default map. Its `384–396` window calls `transformRelationFunc(relation)` while constructing the flow, before registering/merging the flow configurations.
- `sql/connect/server/src/main/scala/org/apache/spark/sql/connect/planner/SparkConnectPlanner.scala:1671–1711` leaves named-table reads unresolved but eagerly obtains `reader.load(...).queryExecution.analyzed` for direct batch data-source reads. This fixes the direct ORC schema before per-flow analysis configuration is installed.
- `sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/graph/GraphRegistrationContext.scala:61–63` merges `defaultSqlConf ++ flowDef.sqlConf`; a colliding flow key wins. The failure is not reversed map precedence.

## Analysis

- `sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/graph/FlowAnalysis.scala:42–86` clones the session configuration and installs a private configuration with `SQLConf.withExistingConf`. Its stated scope is the analyzer's reads through `SQLConf.get`, while sharing the session/catalog.
- `sql/core/src/main/scala/org/apache/spark/sql/execution/datasources/orc/OrcUtils.scala:209–219` constructs `OrcOptions` using `sparkSession.sessionState.conf`. `OrcOptions.scala:62–69` gives an explicit `mergeSchema` option precedence over that object's `isOrcSchemaMergingEnabled` value. This path is not an assertion that all data-source defaults read the analyzer's thread-local configuration.
- SQL registration can defer the source relation, but our probe did not qualify it as a replacement fixture: the initial destination schema was `struct<id:int>` and execution reanalysis produced `struct<id:int,extra:int>`, causing a column-count error.

## Execution

- `sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/graph/FlowExecution.scala:268–292` runs synchronous `graph.reanalyzeFlow(flow)` inside `SparkSessionUtils.withSqlConf`; it then creates a `Future` whose body constructs the writer and calls `saveAsTable`.
- `sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/util/SparkSessionUtils.scala:24–40` temporarily sets values on `spark.conf` and restores them in `finally`. This is a different mechanism from analysis's private thread-local configuration. The excerpt alone does not prove which configuration every asynchronous writer operation observes; this audit makes no writer-default parity claim.

## What the original assertions cover

All following windows are in `sql/pipelines/src/test/scala/org/apache/spark/sql/pipelines/graph/ConnectValidPipelineSuite.scala`:

- `625–662`: at `655` the observer sees `flowValue` through `SQLConf.get`; at `657–659` the run session does not contain that value during analysis; at `661` it remains absent afterwards.
- `664–721`: eight synchronized analysis threads each observe their own value (`714–717`), and the run session remains unchanged (`720`).
- `723–763`: an unresolved consumer `SELECT Foo FROM src` resolves under the case-insensitive baseline (`741`), fails with its explicit case-sensitive configuration (`752`), reports `UNRESOLVED_COLUMN.WITH_SUGGESTION` (`756–758`), and leaves the parent configuration false (`761`).
- `460–493`: resolved flow configuration maps preserve graph defaults and give explicit flow keys precedence (`481–491`). These are map assertions, not ORC file-source assertions.
- `264–337`: configuration fusion, materialization boundaries, and duplicate equal values have their own map assertions. These do not broaden the isolation assertions into an ORC guarantee.

`SqlPipelineSuite.scala:345–384` checks SQL `SET` values captured on successive flow definitions. Sail already mirrors those expected maps in `crates/sail-spark-connect/src/pipelines/sql/tests.rs:136–183`, also checking reset for the next SQL file. Sail's public `python/pysail/tests/spark/pipelines/features/sql.feature:286–312` checks timezone-dependent results and next-file defaults. These existing tests do not require new ORC configuration semantics.

## Smallest later assertion

A small test-only follow-up can port the graph-default/flow collision assertion from `ConnectValidPipelineSuite.scala:488–491`: graph default `default.conf=value`, flow override `default.conf=other-value`, expected stored flow map containing only `default.conf=other-value`. Including the independent-default case at `481–485` in that same unit would preserve the original test's full precedence contract.

Sail baseline `crates/sail-spark-connect/src/pipelines/graph.rs:232–233` already implements the expected merge order, so this is a targeted coverage addition, not an identified missing feature. The existing SQL configuration test starts from empty graph defaults. `coverage-search.json` records the limited source search supporting the absence of an explicit precedence assertion; it does not claim exhaustive absence of indirect coverage. No test, implementation, or additional Spark process was started for this audit.

Runtime evidence remains separate: `/tmp/sail-sdp-flow-config-reference/reference.json` is the root's failed original reference; `/tmp/sail-sdp-flow-config-probe-24c4d43eb7934af0a64435e7a7548035/probe.json` records direct graph-default and explicit-flow `id:int` schemas with captured protocol maps, plus the SQL schema mismatch. The fourth named-path probe was interrupted and has no usable outcome. It must not be counted as passing or failing reference evidence.
