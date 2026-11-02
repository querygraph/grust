# Streaming tables

Sail `c8594db27` (parent `4f37aef98`) runs streaming tables as triggered append flows, in `pipelines/append.rs`. Before it, any graph with a streaming table was refused at execution, which blocked much of the unmapped Spark suites.

Native: 125 Plan + 430 Connect, fmt, strict Clippy. Frozen 300 + 67. Test results are in `gates/`. `test_streaming_tables.py` has 15 cases. Spark: 13 passed, 2 skipped (the Sail-only replay case and the two-flow case below). Sail: 15 of 15, and all 15 fail on the `4f37aef98` binary. `gates/probe.py` and `obs.json` are the Spark measurement the behaviour comes from.

**Measured on Spark 4.2.1.** An empty rerun adds nothing. A later run reads only new files. `INSERT OVERWRITE` on a source adds only its new rows and keeps the old ones. A full refresh truncates and starts checkpoint `n + 1`. An aggregate without a watermark fails with `STREAMING_OUTPUT_MODE.UNSUPPORTED_OPERATION`.

**Intentional difference.** In the Spark run, two flows into one table fail on a concurrent commit, one retries, and its rows are absent from the result. Sail runs flows one at a time and keeps both.

**Limits.**
- Recovery is at-least-once: a crash after a batch is recorded replays it, and the replay duplicates rows in a plain file table. Spark's file sink avoids this.
- Each flow runs one batch per run; there is no `maxFilesPerTrigger`, and no concurrency between flows.
- Refused, not read wrongly: partitioned sources, Delta and Iceberg sources, catalog views as streams, stateful operators (aggregation with a watermark, deduplication, stream-stream joins, sort, limit, window), `readStream.format(...)` data sources.
- `schema_stream.rs` projection was not exercised at execution; the run reads the table's catalog schema, and whether that matches analysis for every type was not tested.
- Once flows and sinks are not implemented. Unadmitted AutoCDC graphs stay refused. Flow lifecycle events for these runs were not added.
- No distributed run. No original Scala suite was run and the inventory is unchanged.
