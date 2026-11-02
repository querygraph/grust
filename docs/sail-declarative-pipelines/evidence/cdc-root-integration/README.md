# CDC root integration

Sail `2eae921c5` fast-forwards the batch root `dea8e10fb` with the CDC chain the peer offered in CF-0570: 21 commits, 76 files. This packet qualifies the union only. It is not a review of the CDC design and not a CDC acceptance claim.

| Gate, on the exact candidate | Result |
| --- | --- |
| fmt, strict Clippy, library tests for sail-plan, sail-spark-connect, sail-sdp-control, sail-delta-lake, sail-execution, sail-common, sail-common-datafusion, sail-sql-analyzer | pass; 125, 430, 60, 347, 244, 34, 140, 64 tests |
| Frozen regression, harness from evidence/query-function-guard | 300 selected + 67 upstream |
| Whole pipelines test directory on Sail | 575 of 575 |
| Delta Python suite, root binary against candidate binary | 875 identical outcomes, 0 changed |
| Public AutoCDC run on the candidate binary | refused with `incremental pipeline execution`; no target table |

The peer's Delta baseline was the pre-root `28515224e`, so this was re-measured on `dea8e10fb`. Both binaries give 12 failed and 12 errors. They are pre-existing, not caused by this chain, and not diagnosed as product defects:

- 8 failed: `test_native_delta_command_keeps_relative_string_target_as_path`, which depends on the client and server sharing a working directory; this harness runs an external server.
- 4 failed: `test_create_table_as_select_result_can_be_collected`, `test_greek_final_sigma_resolves_to_the_canonical_schema_column` and two `test_cast_aggregates_preserve_order_and_null_counts` cases. These match the peer's count of 4.
- 12 errors: fixtures that start a classic JVM Spark session with delta-spark. The gateway exits at setup, and no Delta jars are in the local Ivy cache; the cause was not confirmed. So the delta-spark interoperability tests were **not exercised** on either binary.

`gates/delta-root-unpinned-parallelism.xml` is a first baseline retained as a harness error: 97 failed, because the external server lacked `SAIL_EXECUTION__DEFAULT_PARALLELISM=4` and plan snapshots changed. `gates/guard-run.xml` is a failed activation probe that named a catalog Sail does not have; `guard-run-2.xml` is the valid run.

Limits: the ordinary-write review of `commit_exec.rs` was by reading. Fenced commits, the Turso authority and durable runs are covered only by the peer's tests. `sail-spark-connect` now depends on Turso unconditionally, adding 82 lockfile packages. No CDC is publicly reachable, because no production code registers `BoundedSources`.
