# A Sail extension API, tested against SedonaDB and Nutmeg

A design proposal for [lakehq/sail discussion #2001](https://github.com/lakehq/sail/discussions/2001).
Draft; not yet posted.

Every claim is anchored to a public source: a quoted comment with its link, or a
file and line at a named commit. Sail is read at `main` `51b57bc2` (2026-09-22),
`datafusion-ffi` at the published 55.1.0 crate, DataFusion at 55.1.0, SedonaDB at
`main` `a115fc3f`, Apache Sedona at `master` `86fbb82b`, Nutmeg at
`work/streaming-reads` `96816e5`. Where a claim is reasoning rather than something
read or run, it says **inferred**.

## 1. In one paragraph

Extensions are Python packages discovered through an entry-point group, as
`pysail.datasources` is today. Each hands Sail one small, versioned, `repr(C)`
manifest through a `PyCapsule`. Every component in the manifest is a
`datafusion-ffi` object that DataFusion 55.1.0 already carries: functions, table
providers and table functions, catalog providers, physical plans, extension codecs
and options. Sail's work is to reach the places where those objects must be
consulted and today are not: the name resolver, the worker sessions, the
remote-execution codec and stage placement. An extension declares whether its
components may run on any worker or only on the driver, so a stateless geospatial
library and a stateful graph-analytics service are served by one mechanism. Two
things the FFI cannot carry, logical plan nodes and logical optimizer rules, are the
boundary of the first release, not designed around; one Sail-owned hook covers the
spatial join. The proposal starts with a proof of concept that needs none of the
new ABI, because that is where most of the value is and where the maintainers asked
to start.

## 2. Start here: a proof of concept with no new ABI (C4)

SedonaDB already exports its `ST_*` scalar functions over the DataFusion FFI as
`__datafusion_scalar_udf__` (`python/sedonadb/src/udf.rs:83`). Sail's expression
resolver never consults DataFusion's session UDF registry
(`crates/sail-plan/src/resolver/expression/function.rs:74-236`). Those two facts
make the smallest possible experiment:

1. Pin a SedonaDB build to DataFusion 55.1.0 (it is on 54.1.0 today).
2. Register its capsules into a Sail session through a `pysail` call.
3. Add one lookup to the scalar resolver: the session's `udf` registry, after the
   `CatalogManager` and before the built-ins.
4. Run the unmodified `apache-sedona` PySpark client against Sail in `local` mode.

Over Spark Connect that client sends `Column(UnresolvedFunction(function_name,
expressions))` (`python/sedona/spark/sql/connect.py:40`, selected by `is_remote()`
at `dataframe_api.py:69`), so on the wire its contract is function names.

**Pass condition:** `ST_*` calls resolve by name, and queries whose geometry stays on
the server (`ST_Intersects` filters, `ST_AsText` projections, counts, aggregates)
return correct results. **Not a pass condition, and not achievable:** collecting a
geometry column. Sedona's client type is a `UserDefinedType` over `BinaryType`
(`python/sedona/spark/sql/types.py:47-51`) with Sedona's own preamble byte format
(`python/sedona/spark/utils/geometry_serde_general.py:250-293`), while Sail emits
Spark 4.1 `GEOMETRY` (`crates/sail-plan/src/resolver/data_type.rs:329-366`).

Then repeat in `local-cluster`, which needs two more things: worker sessions that
load the same capsules (§6.4), and the codec's existing empty-buffer path for
unknown UDFs (§6.5). Pass condition: the same queries, with the plan encoded on the
driver and decoded on a worker.

That is most of a Sedona user's notebook, it proves the FFI path end to end with
nothing invented, and it is a pull request of a few hundred lines. Everything after
this section is what it takes to go further.

## 3. The constraints

All from the maintainers, quoted verbatim.

| | Constraint | Source |
| --- | --- | --- |
| C1 | "since DataFusion has an FFI, we won't use Rust trait as the API, but we'll have an extension FFI built on top of DataFusion so that we won't need to recompile the extension on every Sail version or Rust version change. This allows Sail and the extension to release under different schedule." | linhr, [#2001](https://github.com/lakehq/sail/discussions/2001#discussioncomment-17083578) |
| C2 | "The session mutator is something not very stable and I'd consider it a deep implementation detail, so we need to think more around the best way to alter session config." | same |
| C3 | "Using Python package for distribution and the discovery mechanism make sense to me." | same |
| C4 | "I would love to see end-to-end proof of concept around FFI." | same |
| C5 | Open questions: "1. How do we handle breaking changes to the extension API? 2. How does this fit into Spark Connect's existing plugin mechanism? 3. How to specify optimizer and planner orders? (This is mentioned in the proposal already.)" | same |
| C6 | "The FFI extension would shine the most for *transformation* of existing query plans. For connecting with external data systems, since the query plan is the leaf node without input, I feel the Python data source is powerful and performant already, and it avoids the complexity of working with FFI. But the FFI extension can definitely be used to support data source if there are reasons for particular use cases." | linhr, [#1062](https://github.com/lakehq/sail/issues/1062#issuecomment-3573403774) |
| C7 | "There is no plan to publish it as Rust crates for use in other Rust projects." | linhr, [#1991](https://github.com/lakehq/sail/discussions/1991#discussioncomment-17062283) |
| C8 | Shared-library loading "does not seem mature. (I'm sure we'll need to deal with a lot of `unsafe` code.)"; a Python library "looks promising ... It allows sharing functionalities between native modules using `PyCapsule` as the bridge." | linhr, [#1062](https://github.com/lakehq/sail/issues/1062#issuecomment-3561587467) |

§9 checks the design against each, with the strongest case that it fails.

## 4. The two reference extensions

Chosen because they pull in opposite directions.

### 4.1 SedonaDB: stateless, wide, worker-resident

- **Types.** Geometry is `geoarrow.wkb` field metadata over `Binary`, `LargeBinary`
  or `BinaryView` (`rust/sedona-schema/src/datatypes.rs:193,228-250`); Sail stamps
  the same metadata. Sail's Spark boundary accepts only `OGC:CRS84`, `EPSG:3857` and
  `SRID:0` (`crates/sail-spark-connect/src/proto/data_type_arrow.rs:31-40`) and fails
  the whole schema on any other CRS; SedonaDB writes any CRS's JSON
  (`datatypes.rs:485-500`).
- **Functions.** 141 `ST_*` scalars, 7 `ST_*` aggregates, 58 `RS_*`, as DataFusion
  UDFs with multi-kernel overloading (`rust/sedona-expr/src/scalar_udf.rs:69`). Only
  scalars are exported over the FFI.
- **Config.** `SedonaOptions`, a `ConfigExtension` with prefix `sedona`
  (`rust/sedona-common/src/option.rs:262`), holding an `Arc`'d CRS engine
  (`:40-55`); `spatial_join.enable` defaults to true (`:122-124`). Three of the four
  spatial-join rules return early when the options are absent from the session or
  disabled (`rust/sedona-query-planner/src/optimizer.rs:199-205, 248-254, 379-385`).
  Before a kernel crosses SedonaDB's own C ABI, the exporting session's options are
  baked into it (`c/sedona-extension/src/scalar_kernel.rs:388-427`).
- **Spatial join.** Four logical rules, three inserted before DataFusion's
  `push_down_filter` and one appended (`optimizer.rs:81-121`), a vendored replacement
  of `push_down_leaf_projections` (`:40-58`), a `UserDefinedLogicalNode`, an
  `ExtensionPlanner`, and `SpatialJoinExec` (`rust/sedona-spatial-join/src/exec.rs:361`),
  which reads every build-side partition in each task (`:466-480`), reserves build
  memory from the task's pool with spilling (`prepare.rs:215-220`) and reads
  `SedonaOptions` from the session config, defaulting when absent
  (`prepare.rs:99-101`, `stream.rs:159-161`). No `PhysicalExtensionCodec` exists for
  it. The form the #2001 opening post names is "spatial filters on cross-joins",
  merged by `MergeSpatialFilterIntoJoin` (`optimizer.rs:115-117`).
- **Also installed by `SedonaContext`:** a replacement for the `parquet` format
  (`rust/sedona/src/context.rs:272`) and a dynamic object-store catalog (`:298-302`).
- **Its own C ABI.** `c/sedona-extension/` defines version-agnostic C structs for
  kernels, plans and table providers, with expressions as DataFusion protobuf
  ([sedona-db#407](https://github.com/apache/sedona-db/pull/407),
  [#1004](https://github.com/apache/sedona-db/pull/1004),
  [#1094](https://github.com/apache/sedona-db/pull/1094)). Its maintainer: "I'm
  vaguely planning to propose them to DataFusion as well"
  ([paleolimbot, #2001](https://github.com/lakehq/sail/discussions/2001#discussioncomment-17818136)).
- **Versions.** DataFusion 54.1.0, arrow 58.3.0; Sail is on 55.1.0 and 59.2.0.

### 4.2 Nutmeg: stateful, narrow, driver-resident

Nutmeg embeds Grust's graph kernels in a Sail server. A client stages a graph from a
DataFrame (`df.write.format("nutmeg")`), runs a kernel
(`spark.read.format("nutmeg").option("algorithm", "pagerank")`, or
`nutmeg_pagerank('g')` in SQL) and reads a DataFrame back. Today it compiles against
Sail's crates by path (`Cargo.toml:44-48`) and embeds the server through
[#2630](https://github.com/lakehq/sail/pull/2630) (`crates/nutmeg-server/src/main.rs:44-67`);
under this proposal it would ship as an extension package instead.

- **State lives in one process.** Staged graphs are a process-global store keyed by
  graph name (`crates/nutmeg-graph/src/lib.rs:1109-1118`). A worker in another pod
  would find nothing. The name-keyed store is a multi-tenancy defect in Nutmeg,
  to be fixed there by scoping it to a session; nothing here asks Sail to accommodate
  it.
- **Cluster mode fails today:** staging at `unsupported data sink node`
  (`crates/sail-execution/src/proto/codec.rs:2517`), reads at `unsupported physical
  plan node` (`:2889`). A codec alone would not fix it: the node would run on a worker
  without the graph. Driver placement is a hard-coded list of Sail's own nodes
  (`crates/sail-execution/src/job_graph/planner.rs:460-472, 606-617`).
- **What it uses from a session:** table functions (already resolved from the
  DataFusion session, `crates/sail-plan/src/resolver/query/read.rs:421`); a
  `DataSource` for `format("nutmeg")` with read options (`crates/nutmeg-sail/src/lib.rs:87-117`)
  and write options (`:133-165`) whose writer is an `insert_into` over a table
  provider returning `DataSinkExec` (`:174-180, 222-237`); a `SessionConfig`
  extension selecting the read path (`nutmeg-graph/src/lib.rs:2648-2654`, with an
  environment fallback); cancellation by stream drop (`:2816-2824`).

### 4.3 The alternative C6 points at, and what it gives up

A Nutmeg *service*, a separate process holding the graphs and reached from a
Python data source, would need nothing from Sail: the reader runs on workers and
cancels when its generator closes. What it gives up is that every kernel's input
and output cross a process boundary and a second deployable exists. In-process
residency has two reasons: Arrow batches pass from the engine to the kernel and
back without a copy, and there is nothing to deploy beyond `pip install`. That is a
trade a maintainer may reasonably decline to support; §9's C6 row says so. The
mechanism proposed for it (§6.5) is the one Sail already uses for its own commit
nodes, and Nutmeg is its first customer rather than its only conceivable one.

### 4.4 Where they differ

| | SedonaDB | Nutmeg |
| --- | --- | --- |
| scalar and aggregate functions by name | required | no |
| table functions | nice | required |
| data source, read and write | file formats, important | required |
| custom execution plan | spatial join | streamed algorithm read |
| plan transformation | required | no |
| config extension | important | one, small |
| where components run | **workers** | **driver only** |
| state | none | process-resident |

## 5. What DataFusion's FFI carries at 55.1.0

Sail pins DataFusion 55.1.0 and arrow 59.2.0 (`Cargo.toml:165,194`) and uses no
`datafusion-ffi` and no `PyCapsule` today. At 55.1.0, verified in the published crate:

**Carried:** table providers and factories, catalog and schema providers, table
functions, scalar, aggregate and window UDFs (with Arrow field metadata, so extension
types survive), physical expressions, execution plans and plan properties, physical
optimizer rules, a query planner, session config and extension options, record batch
streams, statistics and metrics, both extension codecs.

**Not carried:** `LogicalPlan::Extension` nodes and logical optimizer or analyzer
rules (`src/proto/logical_extension_codec.rs:382,386`), `ExtensionPlanner`, file
formats (`:435,443`), physical-expression codecs, `DataSink`, object stores, and the
host `RuntimeEnv`: a foreign `TaskContext` is rebuilt with `RuntimeEnv::default()`
and a `SessionConfig` carrying only `ConfigOptions` (`src/execution/task_ctx.rs:193-231`,
`src/session/config.rs:137-139`; [datafusion#24733](https://github.com/apache/datafusion/pull/24733), open).

Sail has 26 `UserDefinedLogicalNodeCore` implementations and no
`LogicalExtensionCodec`, so a foreign query planner could never see Sail's plans;
that is why `FFI_QueryPlanner` is not the join hook (§6.6).

**Four properties that shape the design:**

1. **Version coupling.** `version()` returns the crate's major (`src/lib.rs:64-68`)
   and nothing in the crate checks it. The README recommends the same version on both
   sides "but this is not strictly required" (`README.md:38-40`); stabilisation is
   open ([#17374](https://github.com/apache/datafusion/issues/17374)). SedonaDB's
   maintainer: "my main complaint with the DataFusion FFI is that the major version
   is not part of the FFI, so you get a crash if you try to mix datafusion-python
   versions with whatever your extension was compiled against but you could work
   around that here" ([#2001](https://github.com/lakehq/sail/discussions/2001#discussioncomment-17083581)).
2. **Identity survives within a library and is lost across one.** A handle that
   returns to the library that made it unwraps to the original `Arc`
   (`src/execution_plan.rs:418-419`, by `library_marker_id`, a public field at `:114`);
   a handle from another library becomes an opaque `ForeignExecutionPlan`
   (`src/query_planner.rs:29-35`). Neither side can inspect the other's nodes.
3. **Options cross as strings.** Every `ConfigExtension` is flattened to a string map
   (`src/config/mod.rs:42-78`) and recovered by type only where a `Default` can be
   parsed from strings (`:81-101`). A typed extension holding an `Arc` does not cross.
4. **No panic protection.** No `catch_unwind` in the crate; a panic across
   `extern "C"` aborts the process.

## 6. The design

### 6.1 The manifest (C1, C5.1)

The capsule holds a Sail-owned `#[repr(C)]` manifest of `datafusion-ffi` objects.
It is producible from Rust, since its components carry `stabby` containers; it is
not a C API. It is the only ABI Sail defines.

```rust
#[repr(C)]
pub struct SailExtension {
    pub sail_ext_abi_version: u32,   // first field: layout of this struct
    pub datafusion_major: u64,       // must equal Sail's, or refused with a message
    pub name: *const c_char,         // "sedona", "nutmeg"
    pub version: *const c_char,      // the extension's own
    pub placement: SailPlacement,    // AnyWorker | DriverOnly, for the whole extension
    pub n_components: u32,
    pub components: *const SailComponent,
    pub release: unsafe extern "C" fn(*mut SailExtension),
}

#[repr(C)]
pub struct SailComponent {
    pub kind: SailComponentKind,     // ScalarUdf, AggregateUdf, WindowUdf, TableFunction,
                                     // TableProvider, CatalogProvider, PhysicalExtensionCodec,
                                     // ExtensionOptions, JoinExtension, ConnectPlugin
    pub name: *const c_char,         // the function, format or catalog name
    pub object: *mut c_void,         // the datafusion-ffi struct for that kind
}
```

Placement is per extension. Nutmeg needs every component on the driver and Sedona
every component on workers; a per-component flag would add only a way to be
inconsistent. Planning happens on the driver whatever an extension's placement, so
a `ConnectPlugin` (§6.8) runs there without a flag.

**Breaking changes (C5.1).** Two numbers are checked before any component is touched;
a mismatch is an error naming both sides. The version is the first field so a layout
mismatch cannot fault before the check runs, the gap datafusion-python describes in
its own check (`crates/util/src/lib.rs:195-198`: "`version` is not the first field on
any of these types, so a sufficiently different layout can fault before this ever
runs"). `datafusion_major` is kept in the manifest rather than read from each object
because three FFI types carry no version (`FFI_TaskContextProvider`,
`FFI_TableProviderFactory`, `FFI_ExtensionOptions`). Arrow data crosses as the Arrow
C Data Interface, which is version-independent; expressions and plans cross as
DataFusion protobuf, which rides the DataFusion-major check. Proposed: while Sail is
0.x, `sail_ext_abi_version` changes only with a Sail minor, and one Sail minor
accepts one DataFusion major. What cannot be promised is independence from
DataFusion's major: an extension releases on its own schedule within a DataFusion
major and rebuilds when Sail moves to the next. C1 is met to that extent. SedonaDB's
maintainer prefers "version-independence from DataFusion", which his C ABI has and
`datafusion-ffi` does not; §8 records that as an open trade.

### 6.2 Discovery and loading (C3, C8)

An entry point in the group `pysail.extensions`, mirroring `pysail.datasources`
(`crates/sail-data-source/src/formats/python/discovery.rs:28`), resolves to an
object with one method, `__sail_extension__(self) -> PyCapsule`, capsule name
`sail_extension`. Distribution is PyPI; discovery is `importlib.metadata`; Sail
`dlopen`s nothing. This would be Sail's first `PyCapsule` unwrap, and the `unsafe`
surface is the `datafusion-ffi` call surface, the same one datafusion-python has.
A duplicate extension name is refused at load; function-name collisions are §8.

### 6.3 Reaching the resolver: three insertions

Sail resolves an expression through the session `CatalogManager` (which holds
`ScalarUDF` only, `crates/sail-catalog/src/manager/function.rs:17-28`), then its
built-in tables, never DataFusion's registries. Table functions are the exception
(`resolver/query/read.rs:421`).

- **Scalar:** consult the session's `udf` registry after the `CatalogManager` and
  before the built-ins. This is the §2 change.
- **Aggregate:** a different path. Aggregates resolve through
  `get_built_in_aggregate_function` with `AggFunctionInput { distinct, ignore_nulls,
  filter, order_by, .. }` (`function.rs:177, 212-229`); a catalog `ScalarUDF` is
  rejected when `FILTER` or `ORDER BY` appears (`:118-120`) and `is_distinct` is not
  carried (`:150-153`). A foreign `AggregateUDF` needs an `Expr::AggregateFunction`
  construction with those modifiers. Untestable until SedonaDB exports an aggregate
  (§8).
- **Window:** `resolver/expression/window.rs:31-148` accepts a catalog function only
  if it is a PySpark window UDF (`:106-119`); a foreign `WindowUDF` needs a
  `WindowFunctionDefinition::WindowUDF` construction.

Built-ins keep precedence; shadowing one is a session opt-in (§8).

### 6.4 Reaching the workers

Worker sessions are built by `WorkerSessionFactory` with `with_default_features()`,
no mutator and no data-source registry
(`crates/sail-session/src/session_factory/worker.rs:15-54`); the `sail` binary
initialises a Python interpreter for every subcommand (`crates/sail-cli/src/main.rs:11-38`)
and Kubernetes pods run `["sail", "worker"]` (`sail-execution/src/worker_manager/kubernetes.rs:380-381`),
so discovery can run there. It does not today: `register_external_data_sources` is
reached only from the server factory (`session_factory/server.rs:113`). Python data
sources reach workers by a different route, a pickled reader whose module must be
importable (`codec.rs:1748-1767`).

Change: worker sessions run discovery as a new step and register every component of
every `AnyWorker` extension. `DriverOnly` extensions are not registered on workers,
so a stray reference fails with a named error. The extension's distribution must be
installed on workers, as a Python data source's module must be.

### 6.5 The codec and placement

`RemoteExecutionCodec` is a closed downcast chain
(`crates/sail-execution/src/proto/codec.rs:1825-2889`), hard-wired at
`driver/job_scheduler/mod.rs:37`. For an unknown UDF it writes an empty buffer
(`:3690-3691`), and `datafusion-proto` then resolves by name from the decoding
session's registry (`physical_plan/from_proto.rs:296-300`); the TODO at `:2899-2921`
notes Sail's own non-empty `Standard` marker defeats that fallback for Sail's
functions. Foreign UDFs take the empty-buffer path, so with §6.4 a worker's
`ctx.udf(name)` finds them. Driver stages round-trip through the codec too
(`driver/actor/handler.rs:607-720` → `task_runner/preparation.rs:59`).

**Encoding.** Sail defines an envelope for foreign nodes: the owning extension's
name plus the bytes its `PhysicalExtensionCodec` produced. `FFI_PhysicalExtensionCodec`
carries no discriminator (`try_encode(plan)`, `try_decode(buf, inputs)`,
`src/proto/physical_extension_codec.rs:51-59`), so the envelope is Sail's, and it
makes decoding order-independent. A foreign codec decodes against its own task
context provider (`:94`), not the worker's; and a UDF with state baked at export
(§4.1) is reconstructed on a worker from that worker's export, which may differ
from the driver's. Both are stated limits.

**Identifying the owner.** Not by trial encoding, and not by a marker in the
manifest, because a manifest and the components it lists may come from different
libraries: in §2, SedonaDB's UDF capsules come from `sedonadb._lib` while a glue
package would produce the manifest. Instead, at load Sail calls `library_marker_id()`
on every plan-producing component (`FFI_ExecutionPlan`, `FFI_TableProvider`, codec)
and builds a marker→extension map itself; one extension may map to several markers.
A foreign node's marker is read off its handle (`src/execution_plan.rs:337-339`)
before any encoding, which is when stage placement needs it. UDFs carry no marker
(`FFI_ScalarUDF` has none) and are owned by name.

**Placement.** `job_graph/planner.rs` consults the owner's manifest before its
hard-coded list (`:460-472`). A `DriverOnly` owner forces a driver stage, as
`DeltaCommitExec` does since [#2192](https://github.com/lakehq/sail/pull/2192). The
final-stage rule (`planner.rs:59`) is unchanged: a driver-only read is followed by a
worker stage that forwards its output. Sail's driver stages today are commit and
metadata nodes (`planner.rs:606-617`); a driver stage that ingests a shuffle is a
new pattern, and it should be named as one.

**The cost for Nutmeg, stated plainly:** every row of a staged graph passes through
the Spark Connect server process on write, and a read's rows pass driver → worker →
driver → client. A `DriverOnly` extension pays that for residency.

### 6.6 The join extension: one Sail-owned hook

Logical nodes and rules do not cross the FFI, and a foreign physical rule cannot
inspect Sail's join nodes (§5.2). SedonaDB's maintainer described the options:
"either Sail would have to hard-code some of the logical planning that identifies a
logical and/or KNN join and have a specific extension point for 'spatial join'
(which could resolve the FFI version of the executionplan), or implement some
general 'join extension' (where it passes the join condition to an extension which
can optionally return an FFI execution plan if it applies). This would be ambitious"
([#2001](https://github.com/lakehq/sail/discussions/2001#discussioncomment-17818136)).

Proposed: the general form, seated where Sail can see the join.

- A `JoinExtension` component names the functions it treats as join predicates.
- The hook is a Sail-owned physical optimizer rule, at a fixed position: after
  `JoinReorder`, `JoinSelection`, `FilterPushdown` and `WindowTopN`, and before
  `EnsureRequirements` (`crates/sail-physical-optimizer/src/lib.rs:48-58`), so the
  returned node's requirements are still enforced. It downcasts two shapes Sail can
  produce: `NestedLoopJoinExec` with a filter, and `FilterExec` over `CrossJoinExec`,
  which Sail's `JoinReorder` reconstructs (`join_reorder/reconstructor.rs:584, 600`).
  When the filter contains a declared predicate it offers the extension the join
  type, the condition as DataFusion protobuf (SedonaDB's C ABI's own choice,
  `sedona-db#1094`) and the children as `FFI_ExecutionPlan`s, and receives an
  `FFI_ExecutionPlan` or a refusal.
- The reply declares `build_side: Left | Right | None`. `SpatialJoinExec` reads
  every build partition in every task (`exec.rs:466-480`); Sail marks a build side
  `Shared` for `HashJoinExec` in `CollectLeft` mode and for the nested-loop, cross and
  piecewise-merge joins it downcasts (`job_graph/planner.rs:292-296, 316-326`), and an
  unknown node inherits its parent's usage (`:365`), which would make each task
  re-read a single-consumption shuffle. The declaration lets Sail treat the build
  child as a `CollectLeft` build side. It is a Stage 2 pass condition.

**Which queries reach it.** A predicate in an `ON` clause is the join's filter
directly. The cross-join-with-`WHERE` form the #2001 post names reaches it because
Sail installs DataFusion's default logical rules minus one
(`crates/sail-session/src/optimizer.rs:9-15`), lowers a cross join through
`LogicalPlanBuilder::cross_join` (`resolver/query/join.rs:90`), DataFusion's
`push_down_filter` folds the predicate into the join (DataFusion 55.1.0
`push_down_filter.rs:431-434, 502`) and the physical planner plans a filter-only join
as `NestedLoopJoinExec` (`physical_planner.rs:1693-1694`). That chain is read, not
run; Stage 2 runs it. SedonaDB's `MergeSpatialFilterIntoJoin`, `KnnJoinEarlyRewrite`
and query-side pushdown are not covered and wait for §7.

**What execution under a foreign join loses.** The extension executes Sail's
children through a task context Sail's side rebuilds with `RuntimeEnv::default()`
and a bare config (§5): a Sail `DataSourceExec` over object storage cannot resolve
its store, `RepartitionExec` falls back to a default buffer
(`crates/sail-physical-plan/src/repartition.rs:244-248`), and nodes needing a Sail
config extension fail. On the extension's side, `SpatialJoinExec` gets a default
unbounded memory pool and default options, so it does not spill and does not see
the session's settings. Under `ShuffleReadExec`, which reads only `batch_size()`
(`plan/shuffle_read.rs:98`), and over local files, the hook is safe; beyond that it
waits on [datafusion#24733](https://github.com/apache/datafusion/pull/24733).

**Sail rules that will walk over the opaque node** and treat it generically:
`EnsureRequirements` (`required_input_distribution` unspecified, equivalences
rebuilt from orderings only, `src/plan_properties.rs:178-180`), the post-optimization
`FilterPushdown` (`lib.rs:71`), `RewriteCollectLeftHashJoin` and
`EnforceBarrierPartitioning` (`:73-74`). Expect a redundant repartition or two.
Not fatal; stated.

Physical optimizer rules as extension components are deferred: neither reference
extension ships one, and the only rule in this design is Sail's.

### 6.7 Data sources: `format("name")` over an FFI table provider

Sail's format entry point is its `DataSource` trait
(`crates/sail-common-datafusion/src/datasource.rs:461-487`). The FFI has
`FFI_TableProvider` with `scan` and `insert_into(session, input, InsertOp)`
(`src/table_provider.rs:131-135`), `FFI_TableProviderFactory::create` taking a
protobuf `CreateExternalTable` (`src/table_provider_factory.rs:59, 147-155`), and no
`DataSink`. Mapping, for a `TableProvider` component named `n`:

- `spark.read.format("n").options(o)` → the factory's `create`, with `o` as
  `CreateExternalTable.options`, the read's paths as `location`, an empty schema
  meaning "infer" as `ListingTableFactory` treats it, and `n` as `name` and
  `file_type`. The provider's `scan` becomes the source.
- `df.write.format("n").mode(m).options(o)` → the same factory, then `insert_into`
  with `m` mapped to `InsertOp` (`overwrite` → `Overwrite`, `append` → `Append`;
  `errorifexists` and `ignore` refused, as Nutmeg refuses them today).
- **Sail coalesces the input before any foreign `insert_into`.** `DataSinkExec`
  requires a single input partition and executes only partition 0
  (`datafusion-datasource-55.1.0/src/sink.rs:281-287, 344-353`); in-process,
  `EnsureRequirements` inserts the coalesce, but across the FFI the requirement is
  invisible, and a multi-partition write would stage partition 0 and report success.
  A four-partition write staging every row is a Stage 1 pass condition.
- A `SessionConfig` extension cannot cross; Nutmeg's read-path selector moves to a
  read option.

This is the one place the FFI is used for a leaf source, which C6 says a Python data
source usually serves better. The reason is placement, not performance, and §9's C6
row treats it as the strongest case against.

### 6.8 Spark Connect plugins (C5.2)

Spark Connect carries opaque `google.protobuf.Any` extension messages for relations,
expressions and commands; GraphFrames asked for that route (Discussion
[#2002](https://github.com/lakehq/sail/discussions/2002),
[#1062](https://github.com/lakehq/sail/issues/1062#issuecomment-3557419148)); Sail
rejects such messages today (`crates/sail-spark-connect/src/proto/plan.rs:1339`).
Neither reference extension needs it. linhr placed the work in the resolver: "I
guess the extension would fit into this process, and the core logic to mimic
GraphFrames would be in the second step (plan resolver)"
([#2002](https://github.com/lakehq/sail/discussions/2002#discussioncomment-17083597)).
The manifest reserves a `ConnectPlugin` kind, a function from an `Any` message to a
logical plan, seated in the resolver; it is out of the first release. C5.2's answer:
a second entry point into the same extension, not a second extension system.

### 6.9 The session mutator (C2, C7)

Nothing here registers through `ServerSessionMutator`; Sail discovers and registers
extensions itself, in server and worker factories. Nutmeg moves from the mutator to
a manifest and stops compiling against Sail's crates.

## 7. Boundaries of the first release

- **Logical plan transformation is out.** The FFI cannot carry it, and nobody has
  proposed that it should; SedonaDB's C structs, which its maintainer vaguely plans
  to propose upstream, cover kernels, plans and expressions, not logical nodes.
- **DataFusion major coupling stays** (§6.1).
- **Options.** `SET k=v` already reaches a registered `ConfigExtension` through
  DataFusion (`crates/sail-plan/src/resolver/command/variable.rs:20-22` →
  `execute_logical_plan` → `ConfigOptions::set`, `datafusion-common-55.1.0/src/config.rs:2018-2056`),
  and an unregistered prefix is routed to `FFI_ExtensionOptions` when the
  `datafusion_ffi` namespace is present (`:2045-2051`), so `SET sedona.x` reaches an
  extension's options once the manifest registers them. `spark.conf.set` does not:
  it stays in a Spark-side string map (`sail-spark-connect/src/config.rs:145-151`).
  What blocks Sedona is on its side: kernels read options baked at export (§4.1),
  not per call (§8).
- **File formats cross as table providers**, not `FileFormat`; Sail's parquet reader
  gains no GeoParquet handling.
- **Object stores and the host runtime do not cross**; extensions carry their own
  clients until [datafusion#24733](https://github.com/apache/datafusion/pull/24733).
- **Panics abort.** Extensions catch their own.
- **Type mapping is not extensible**, and the geometry mapping accepts three CRSs.
- **Sedona's client geometry UDT is not emitted by Sail** (§2).

## 8. Open questions

1. **Name collisions.** Sail has three implemented `ST_*` built-ins and two stubs
   (`crates/sail-plan/src/function/scalar/geo.rs:10-14`); Sedona on Spark overwrites
   Spark's own `ST_*` on purpose (`apache/sedona` `AbstractCatalog.scala:90-96`).
   Proposed: no shadowing of a built-in without a session opt-in; two extensions
   colliding is a load error.
2. **Per session.** The opening post asked "should there be a way to opt in/out per
   session (e.g. `SET sail.extensions = 'sedona,comet'`)?". Proposed: loaded always,
   enabled per session by config, default all, so worker registries match the
   driver's.
3. **Aggregates from SedonaDB** need an FFI export on their side and the aggregate
   resolver path (§6.3) on Sail's.
4. **Options per call.** Sedona kernels must read `SedonaOptions` from the call's
   `ConfigOptions` through `local_or_ffi_extension` rather than bake them at export.
5. **Version independence.** This design gives up what SedonaDB's C ABI has. If the
   maintainers weigh that above C1's FFI basis, the manifest could carry SedonaDB's
   structs instead of `datafusion-ffi`'s; that is a different proposal.
6. **Version alignment for §2.** SedonaDB is on DataFusion 54.1.0, Sail on 55.1.0.

## 9. Check against the constraints, with the case against

| | Met by | Strongest case against |
| --- | --- | --- |
| C1 | every component is a `datafusion-ffi` object; the manifest is the only Sail ABI | independence holds only within a DataFusion major |
| C2 | nothing registers through the mutator | the reference extension uses the mutator today (§4.2) |
| C3, C8 | Python packages, entry points, capsules, no `dlopen` | the `unsafe` surface is the whole `datafusion-ffi` call surface |
| C4 | §2, with a pass condition that can be met | server-side results only, because of the client's UDT |
| C5.1 | two checked versions, first-field layout, mismatch is an error | none found |
| C5.2 | a reserved `ConnectPlugin` kind in the resolver | not built in the first release |
| C5.3 | the join hook has a fixed position; rule components are deferred | logical ordering is deferred with the logical layer |
| C6 | the FFI is used for plan transformation and for one leaf source | the leaf source is justified by residency, which no maintainer has endorsed (§4.3) |
| C7 | Sail stays a Python-distributed server | the reference extension compiles against Sail's crates today; this is how it stops |

## 10. Stages after the proof of concept

**Stage 1.** Manifest and discovery (§6.1, §6.2); worker loading (§6.4); codec
envelope and marker map (§6.5); the coalesce before foreign `insert_into` (§6.7);
`ExtensionPhysicalPlanner` returns `Ok(None)` for unknown nodes instead of
`internal_err!` (`crates/sail-session/src/planner.rs:540`, the prerequisite #2001's
author named); Nutmeg as the `DriverOnly` reference. Pass conditions, in
`local-cluster`: Nutmeg stages and reads with its nodes on the driver; a
four-partition write stages every row; dropping a read's stream cancels the kernel
across the FFI (`FFI_RecordBatchStream` release drops the inner stream,
`src/record_batch_stream.rs:95-100, 211-214`), verified rather than assumed.

**Stage 2.** The join hook (§6.6) with a codec for `SpatialJoinExec` on the Sedona
side; options per call. Pass conditions, in `local-cluster`: an `ST_Intersects` join
in an `ON` clause and the cross-join-with-`WHERE` form both plan as
`SpatialJoinExec`; the build side is shuffled once and read by every task.

**Stage 3.** Logical plan transformation, when something carries it; `ConnectPlugin`;
type mapping; the Sedona client UDT.

## 11. What is asked of others

- **SedonaDB:** a DataFusion 55 build for §2; an aggregate export over the FFI;
  options read per call; eventually a codec for `SpatialJoinExec`.
- **DataFusion:** nothing for §2 through Stage 2; Stage 3 waits on logical nodes
  crossing the FFI and on [#24733](https://github.com/apache/datafusion/pull/24733).
- **Sail:** for §2, one resolver lookup and a `pysail` registration call; for
  Stage 1, five changes, each reopening one closed place: the resolver, the worker
  factory, the codec, the placement list, the physical planner's error.
- **Nutmeg:** a Rust `cdylib` Python package (today `python/nutmeg` is pure Python
  and no crate exposes a module); a `PhysicalExtensionCodec` for its nodes (none
  exists); a session-scoped store; and acceptance of the driver cost in §6.5.
