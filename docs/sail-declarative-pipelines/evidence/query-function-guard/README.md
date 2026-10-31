# Eager work during pipeline definition

Sail dea8e10fb4c6ff4c258cd747e2a4b14b2c960daa (parent 15272ec0a) honors PipelineAnalysisContext. Before this, Sail ignored the extension, so `spark.sql("DROP VIEW v")` inside a query function really executed.

## Contract (Spark 617618396)

The guard is server-side: PipelineAnalysisContextUtils, SparkConnectPlanExecution:73, SparkConnectAnalyzeHandler:69, SparkConnectPlanner:3035-3041, PipelinesHandler.blockUnsupportedSqlCommand.

| Request | Execution | Analysis | spark.sql |
| --- | --- | --- | --- |
| No context | allowed | allowed | runs |
| Context, no flow name (definition) | allowed | allowed | side effects blocked, others run |
| Context with flow name (query function) | only SqlCommand; otherwise ATTEMPT_ANALYSIS_IN_PIPELINE_QUERY_FUNCTION | always ATTEMPT_ANALYSIS_IN_PIPELINE_QUERY_FUNCTION | side effects blocked, others return their relation unrun |

Both errors carry SQLSTATE 0A000. Only flow_name marks a query function; flow_identifier does not. The statement policy is default-deny with Spark's ten allowlisted classes. pipelines/query_function_guard.rs holds it.

**Analysis means every AnalyzePlan.** That includes the DdlParse RPC PySpark sends for `createDataFrame(data, "id BIGINT")` and for `StructType.fromDDL`, so a DDL string schema is rejected inside a query function. Use a StructType built directly.

## Qualification of the exact candidate

- fmt, strict Clippy, 125 Plan and 245 Connect library tests: gates/library-02.log.
- Frozen 300 selected public and 67 upstream, with the migrated harness: gates/frozen-public-receipt.json.
- New test_query_function_guard.py, a port of the PythonPipelineSuite grids: 61 passed on Spark 4.2.1 and 61 on Sail. Focused set 155 of 155; the entire pipelines test directory 535 of 535.
- Control: the same 61 tests on the 15272ec0a binary give 32 failed, 29 passed.

## Retained failure and fixture migration

The first candidate 4edade9ad failed the frozen regression, 2 failed and 298 passed: gates/frozen-initial-failure-*. Both tests passed a DDL string to createDataFrame inside a query function. Run unchanged on real Spark 4.2.1, the same two fail with the same condition (gates/spark-original-fixtures-pytest.log), so they had passed only because Sail had no guard. Each fixture now passes a StructType; no assertion changed; they pass on Spark (gates/spark-corrected-fixtures-pytest.log). harness/guard-migration.json binds the two changed hashes. The harness is a copy with only preparation.json changed, and the unresolved-flow-reporting packet is untouched.

## Open items

- SHOW CREATE TABLE is allowed by Spark but unimplemented in Sail's parser, so `spark.sql("SHOW CREATE TABLE t")` fails on Sail where Spark succeeds. Those two grid cases are not ported.
- The two writeStream grid cases are not ported. The in-function case is covered natively by the same arm through a WriteOperation command; the at-definition case needs the rate source and memory sink.
- The `command` parameter is measured for the eleven statements in the grid. Other commands keep Sail's node name, which is unmeasured and can differ from Spark's class name.
- `DESCRIBE TABLE t col` is denied from the source reading (DescribeColumn is not allowlisted), not measured.
- Whether a statement Sail parses as a query is a Command in Spark, or the reverse, is not audited beyond the grid.
- No original Scala-suite acceptance or inventory promotion is claimed.
