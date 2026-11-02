# Delta sources for append flows

Product commit `be0881c80`, on `d4c7a45eb`. A streaming table reads a Delta table by name or by path.

Oracle: Spark 4.2.1 with `delta-spark_4.2_2.13` 4.4.1 and `delta-storage` 4.4.1 from Maven Central. Delta's `DeltaSource.scala` at tag v4.4.1 was read as the reference for its rules.

`probe.py` runs one script on either engine. `diff.py` compares observations. The JSON files are the last full runs: 109 cases on Spark, 113 on Sail (four schema cases ran separately on Spark), 86 of 109 identical.

The 23 differences:

- 9 come from file layout. Spark writes two files for a two-row insert and Sail writes one, so the same statement is a file delete on one and a rewrite on the other. The same rule gives a different outcome. `layout_*` forces one row per file and those cases all agree.
- `dv_layout`: Sail's DELETE of a whole one-row file keeps the file with a deletion vector, where Spark removes the file. The stream rule then sees a change, not a delete. The stream is right; the difference is in DELETE.
- 3 are probe statements Sail refuses or rejects: a `VACUUM` retention check, and an `INSERT` with too few columns.
- `stream_static_join`: `collect()` on `INSERT` into a parquet table fails after the write. This predates this work and is separate from Delta.
- `graph_delta_mv`, `graph_delta_streaming_table`, `delta_target`: Spark 4.2.1 fails the second run with DELTA_CANNOT_CHANGE_PROVIDER, which is Spark's own defect with a Delta target. Sail runs them.
- `batch_time_travel_option`, `batch_timestamp_option`: same condition, but Spark fails during analysis, so its target does not exist, and Sail leaves an empty one.
- `mapped_rename`: same condition, but Sail's failed run has already added the renamed column to the target.
- `not_delta`, `plain_parquet_dir`: both fail. Sail reports a failed flow, not DELTA_SCHEMA_NOT_SET.
- `window_path` was a real defect, fixed before landing.

Tests: `test_delta_sources.py`, 57 cases. Sail 57 passed. Spark with Delta 56 passed through a Connect server (`on-jvm.py`), after one test was corrected for layout; the other is `test_a_delta_target_runs_twice`, the Spark defect above. Negative control on `d4c7a45eb`: 57 failed.

Gate at `be0881c80`: 15 crates native, frozen 300 + 67, pipelines 906 passed, 17 skipped, 13 strict expected failures, Delta suite 875 outcomes unchanged from `delta-root`.

Not covered: a catalog-managed Delta table is refused. Rate limits are validated and have no other effect, since a run reads to the end of the log in one batch. `schemaTrackingLocation` and the `allowSourceColumn*` options are not read. A watermark over a projection of a stream is still refused.
