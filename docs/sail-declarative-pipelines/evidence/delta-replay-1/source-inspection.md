# Delta replay design source evidence

Inspected, without builds or runtime tests:

- Source-control worktree parent `b6d73d6a644dc04b1e6749e171100808c874d788`;
  Delta files unchanged from that parent. Under `crates/sail-delta-lake/src`,
  `table/mod.rs:817` loads read state; `datasource/scan.rs:245` constructs scans,
  `:401` adds physical row numbers, and `:505` collects unordered file groups.
  `physical_plan/scan_by_adds_exec.rs:412` repartitions files and `:469` executes
  their merged output. `physical_plan/log_replay_exec.rs:55` documents spill-capable
  snapshot reconstruction. `spec/actions.rs:268` defines Add and `:523` constructs
  ObjectMeta without object version/ETag. `snapshot/mod.rs:333` skips refresh when
  the version is unchanged; `session_extension.rs:19` keys cached tables without ID.
- Bounded runtime `99dc47788941daf28eec847527949a4cadafdbd2`:
  `crates/sail-delta-lake/src/stream.rs:203` defines version-only offsets;
  `:354`, `:516` and `:604` select ranges and read with the latest snapshot schema.
  `crates/sail-spark-connect/src/pipelines/append.rs:894` reuses saved ranges.
  `python/pysail/tests/spark/pipelines/test_delta_sources.py:232` pins the current
  empty `latest` behavior. That is a Sail source observation, not a Spark execution.
- Spark 4.2.1 source `617618396087429b5627a86ce933bb0f5d6645cb`, inspected through
  Git objects in `/Users/alexy/src/spark-sdp-4.2.1`: `ContinuousStream.java` and
  `ContinuousPartitionReader.java` separate planned partitions from reader-owned
  offsets. They support the distinction; they do not establish Delta semantics or
  require adopting Spark's execution model.
