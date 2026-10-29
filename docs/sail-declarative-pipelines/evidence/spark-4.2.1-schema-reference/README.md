# Spark 4.2.1 schema and lifecycle reference

These probes ran with PySpark 4.2.1 and its bundled JVM jars on macOS arm64,
using Java 20.0.2. `pipeline.py` starts a local Connect server; `append.py`
uses a classic local session. Both use temporary warehouses. The matching
source tag is `617618396087429b5627a86ce933bb0f5d6645cb`.

Run each script with the pinned PySpark environment. They clear Connect routing
environment variables, use `local[2]`, stop their sessions, and write raw JSON
under `/tmp`. The checked-in JSON and logs retain the original results and
exception stack traces. Temporary absolute paths are evidence of the run,
not requirements for another machine.

| Probe | Expected result observed on Spark 4.2.1 |
| --- | --- |
| Unknown output format, dry run | Success; table absent |
| Missing nullable top-level column, dry run | Success; table absent |
| Missing nullable top-level column, real run | `_LEGACY_ERROR_TEMP_1161`; table exists |
| Wider declared decimal, real run | Success; one row and declared precision |
| Missing nested nullable field, dry run | Success; table absent |
| Missing nested nullable field, real run | `INCOMPATIBLE_DATA_FOR_TABLE.CANNOT_FIND_DATA`; table exists |

`pipeline.py` creates a fresh graph for each attempt. The earlier probe reused
the dry-run graph for a real run and received
`SPARK_CONNECT_ILLEGAL_STATE.EXECUTION_STATE_EXECUTE_HOLDER_ALREADY_EXISTS_GRAPH`.
Its raw results are retained in `reused-graph.json`; its superseded script was
not retained. Do not interpret those lifecycle errors as schema-write results.

Source anchors: `PipelineExecution.dryRunPipeline` only calls graph resolution;
`startPipeline` materializes datasets before starting triggered execution;
`FlowExecution.BatchTableWrite` uses ordinary append/saveAsTable. The ordinary
append probe independently reproduced the column-count and nested-field errors.
These are targeted reference observations, not a run of Spark's full SDP suite.
