# Path sinks and watermarked windows

Three commits: Sail `2db6921dd` (path sinks, storage root validation, the once refusal), `31ac33f65` (watermarked tumbling windows, persisted view alias failure, and the rest of SqlPipelineSuite, ViewSuite and SystemMetadataSuite), and `19d7137eb` (a lint fix).

**Gate failure.** `31ac33f65` landed with its native gate failing: strict Clippy refused a collapsible `if`, so fmt passed but library tests never ran on that commit. The landing step checked only that trees matched. No behavior was wrong. `19d7137eb` fixes the lint, and `gates/land.sh` now refuses unless the native gate and the frozen receipt both passed on the exact commit. An earlier version of this README wrongly said native passed on both commits.

On `19d7137eb`: fmt, strict Clippy, library tests for sail-plan, sail-spark-connect, sail-sql-analyzer and sail-sql-parser; frozen 300 + 67; pipelines directory 651 of 651. `2db6921dd` passed native and frozen itself. Spark 4.2.1: `test_python_api_suite.py` plus `test_sql_views_metadata.py`, 47 of 48 on the first run; the failure was my persisted-view expectation, corrected from `gates/pv.py`; the views file then ran 14 of 14, on the candidate before the lint fix. On the prior binaries, new tests fail: 7 of 34 for sinks and 2 of 14 for windows.

The watermark test's third run, which checks that a closed window is not repeated and an open one is not lost, is my extension of the Spark test, and Spark passes it.

**Limits.** Tumbling windows on the watermark column only; one stream source; sliding windows, watermarked deduplication and stream-stream joins are refused. `withWatermark` outside a pipeline stays unimplemented. Retained rows are not bounded and are rewritten each batch. A crash replay is at-least-once. Sinks need a `path`, so memory, console and Kafka sinks are refused. `CREATE_PERMANENT_VIEW_WITHOUT_ALIAS` omits Spark's `<attr>` text and inspects only the query's top Project, through Sort and Filter.
