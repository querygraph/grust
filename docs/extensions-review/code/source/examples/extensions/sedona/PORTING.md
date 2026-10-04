# Port scope and retained findings

The source pin is Apache SedonaDB
`0a1993d9be8bcf52150593ad08fc6a3412d50f29`. Its unmodified workspace declares
DataFusion 54.1.0 and Arrow 58.3.0. The independent Sail wheel uses DataFusion
55.1.0 and Arrow 59.3.0; the patch changes those dependency declarations and
the one accumulator needed by the native scalar crate.

An exploratory `cargo check -p sedona-spatial-join -p sedona-geos` after changing
DataFusion/Arrow versions reported these concrete compiler failures:

- `sedona-functions/src/st_envelope_agg.rs`: `GroupsAccumulator::merge_batch`
  changed from five parameters to four; `convert_to_state` became required.
- `sedona-geo/src/st_convexhull_agg.rs`: the same two accumulator changes.
- `sedona-query-planner/src/probe_shuffle_exec.rs` and
  `raster_batch_budget.rs`: required `ExecutionPlan::apply_expressions` missing.
- `sedona-query-planner/src/query_planner.rs`: `QueryPlanner` now receives
  `&dyn Session`, replacing `&SessionState`.
- `sedona-query-planner/src/spatial_join_physical_planner.rs`: the extension
  planner receives an additional `PhysicalPlanningContext`; physical expression
  construction also requires that context.

The delivered patch ports only the envelope accumulator because the standalone
wheel does not depend on the convex-hull crate or spatial planner. Merge never
reapplies the aggregate filter: DataFusion applies it during partial updates.
The new bypass conversion builds one intermediate bounds state per input row
through the existing update path, preserving its null and filter behavior.
The rest of the spatial migration remains explicit follow-up work, with further
compiler failures possible after the listed planner failures are resolved.

Initial forced-FFI scalar tests exposed two fixture assumptions, not differing
geometric answers: FFI materializes one-row arrays instead of preserving
`ColumnarValue::Scalar`, and Sedona emits `POINT(1 2)` without a space before the
parenthesis. The final tests assert one result row and compare exact typed
values, preserving the point-in-polygon, WKT, and null expectations.

The host collision check found five existing Sail names. Exporting all 133
native Rust/GEOS UDFs would be refused. The final package exports 128 and keeps
the host's collision refusal intact; the README names every omitted UDF.

This port qualifies the native scalar dependency closure. It is not evidence
that the full SedonaDB workspace builds or passes its upstream test suite on
DataFusion 55, and it is not an indexed-spatial-join implementation.
