# PythonPipelineSuite graph tests

Sail `99fa8cad0` (parent `35e8d4fb3`) ports the suite's graph tests to `test_python_api_suite.py` and closes the gaps they found: partitioned streaming sources, eager analysis of `spark.sql()` queries during definition, and Spark's `TABLE_OR_VIEW_NOT_FOUND` wording.

Native 125 + 430 + sail-catalog 20, fmt, strict Clippy. Frozen 300 + 67. Pipelines directory 630 of 630. New file 27 of 27 on Spark 4.2.1 and on Sail; 3 of 27 fail on the `35e8d4fb3` binary, since the earlier units covered the rest.

The port checks what a client can see, not the Scala resolved graph: a dry run's verdict and a real run's rows. So it does not establish `inputs` or `df.isStreaming` per flow. Event source locations are not ported. The `rate` source is exercised only by dry runs. Sinks are only registered, not run. AutoCDC and guard tests are covered by other files.

**Pre-existing, unrelated.** `dml/test_features.py::test_explain_create_table_as_select_shows_physical_plan_with_catalog_command` fails under this external-server harness on this binary and on `2eae921c5`. It was not diagnosed.

Eager analysis applies only to definition requests. Spark analyzes ordinary `spark.sql()` eagerly too; Sail's ordinary path is unchanged.
