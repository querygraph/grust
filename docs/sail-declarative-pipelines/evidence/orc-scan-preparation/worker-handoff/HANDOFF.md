# Worker file-scan preparation handoff

The candidate fixes loss of decoded checkpoint output partitioning when worker preparation rebuilds a file scan. It also qualifies the existing preserve-order isolation for ordinary ORC sources with separately decoded task plans.

## Production scope

Only `crates/sail-execution/src/task_runner/preparation.rs` changes production behavior. `rewrite_file_scans` becomes a private associated function because it uses no actor/session state. `execute_plan` invokes that same function. After building the config with preserve-order and the existing Parquet adapter policy, a new `DataSourceExec` retains the original decoded node output partitioning. File groups, projection, and runtime source binding remain intact.

This is a property-preservation fix, not repartitioning. DataFusion 55.2.0 `source.rs:456-470` forwards the supplied partition index directly to its source; `with_partitioning` at 665-667 only changes cached plan properties. Sail checkpoint commit adjusts partition counts to the observed descriptor partitions (`crates/sail-physical-plan/src/remote_checkpoint.rs:668-670,802-818`); session planning builds one file group per descriptor partition, including empty partitions (`crates/sail-session/src/planner.rs:289-314`). The rewrite preserves that layout. A previously malformed override with a mismatched count is not repaired or newly validated in this unit.

## Regression tests

New `preparation/file_scan_tests.rs` contains two tests:

1. Encode and decode a Parquet checkpoint with three file groups (including an empty group), reordered output columns, and `Hash(id at output index 1, 3)`. The decoded base config alone is unknown-partitioned, making the separate execution-node property necessary. Preparation preserves the hash expression/count, full output schema, exact file metadata/ranges/partition values, and decoded Parquet adapter Arc. Repeating preparation retains the adapter and hash property.
2. Put the retained Spark-written ORC TIME fixture at three independent in-memory paths, read its integer ID with a projected file partition value, and group the files as one/empty/two. Explicitly enable work stealing. A freshly decoded unprepared empty task actually consumes all three files; its baseline rows are sorted because no order is promised. Then create a separate context and decode for each task, invoke the production rewrite, and execute only that task partition. Exact ordered rows are asserted per group, including no rows for the empty group; combined rows contain each file once. Exact ObjectMeta and partition values survive. Worker reservations are released after collection.

The ORC fixture is reused unchanged from `sail-data-source/tests/fixtures/orc/time_precisions.orc`; no native dependency or new binary fixture is added.

## Suggested immutable gates (root-owned)

- `cargo +nightly fmt -p sail-execution -- --check`
- `cargo test -p sail-execution --lib task_runner::preparation`
- `cargo clippy -p sail-execution --lib --tests -- -D warnings`
- `cargo test -p sail-execution --lib`

Author ran only nightly rustfmt and whitespace/source checks, not cargo builds/tests/gates. Source and exact file hashes are recorded in `source-state.json`. Other worktree changes belong to root/other agents and are outside this candidate.
