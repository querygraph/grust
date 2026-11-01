# Path sinks and watermarked windows

Two units: Sail `2db6921dd` (path sinks, storage root validation, the once refusal) and `git log` tip of this packet, parent `2db6921dd` (watermarked tumbling windows, persisted view alias failure, and the rest of SqlPipelineSuite, ViewSuite and SystemMetadataSuite).

Native and frozen 300 + 67 pass on both exact commits. Spark 4.2.1: `test_python_api_suite.py` plus `test_sql_views_metadata.py`, 47 of 48 on the first run; the failure was my persisted-view expectation, corrected from `gates/pv.py`; the views file then ran 14 of 14. Sail 651 of 651 on the candidate before the final commit, whose only change is one native test call site. On the prior binaries, the new tests fail: 7 of 34 for sinks and 2 of 14 for windows.

The watermark test's third run, which checks that a closed window is not repeated and an open one is not lost, is my extension of the Spark test, and Spark passes it.

**Limits.** Tumbling windows on the watermark column only; one stream source; sliding windows, watermarked deduplication and stream-stream joins are refused. `withWatermark` outside a pipeline stays unimplemented. Retained rows are not bounded and are rewritten each batch. A crash replay is at-least-once. Sinks need a `path`, so memory, console and Kafka sinks are refused. `CREATE_PERMANENT_VIEW_WITHOUT_ALIAS` omits Spark's `<attr>` text and inspects only the query's top Project, through Sort and Filter.
