# A Sail extension API, tested against SedonaDB and Nutmeg

A design proposal for [lakehq/sail discussion #2001](https://github.com/lakehq/sail/discussions/2001).
Draft for review; not yet posted. Second revision, after an adversarial review that
found the first one overclaiming in several places; §11 lists what changed.

Every claim is anchored to a public source: a quoted comment with its link, or a
file and line at a named commit. Sail is read at `main` `51b57bc2` (2026-09-22),
`datafusion-ffi` at the published 55.1.0 crate, DataFusion at 55.1.0, SedonaDB at
`main` `a115fc3f`, Apache Sedona at `master` `86fbb82b`, Nutmeg at
`work/streaming-reads` `96816e5`. Where a claim is reasoning rather than something
read or run, it says **inferred**.

## 1. What this proposes, in one paragraph

Extensions are Python packages discovered through an entry-point group, the way
`pysail.datasources` works today. Each package hands Sail one small, versioned,
`repr(C)` manifest through a `PyCapsule`. The manifest lists components, and every
component is a `datafusion-ffi` object that DataFusion 55.1.0 already carries:
functions, table providers and table functions, catalog providers, physical plans and
physical optimizer rules, extension codecs and options. Sail's work is to reach the
places where those objects must be consulted and today are not: the name resolver,
the worker sessions, the remote-execution codec, the physical planner and stage
placement. An extension declares whether its components may run on any worker or
only on the driver, so a stateless geospatial library and a stateful graph-analytics
service are served by one mechanism. Two things the FFI cannot carry, logical plan
nodes and logical optimizer rules, are named as the boundary of the first release,
not designed around; one Sail-owned hook covers the spatial join. The proposal begins
with a proof of concept that needs no new ABI at all, because that is where most of
the value is and where the maintainers asked to start.

## 2. The constraints this design must satisfy

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

Section 9 checks the design against each, including the strongest case that it fails.

## 3. The two reference extensions

Chosen because they pull in opposite directions. A design that fits both without a
special case is likelier to fit the extension nobody has named yet.

### 3.1 SedonaDB: stateless, wide, worker-resident

- **The client contract is function names.** Over Spark Connect, Sedona's PySpark
  DataFrame API emits `Column(UnresolvedFunction(function_name, expressions))`
  (`python/sedona/spark/sql/connect.py:40`), selected by `is_remote()`
  (`dataframe_api.py:69`). The docs: "Spark Connect runs SQL functions in the remote
  server process." ([cluster.md:55](https://github.com/apache/sedona/blob/86fbb82b33ef22a0e19fcd62eac7eb20a103e91f/docs/setup/cluster.md)).
- **But the client's geometry type is not Spark's.** Sedona's `GeometryType` is a
  `UserDefinedType` over `BinaryType` (`python/sedona/spark/sql/types.py:47-51`)
  whose bytes are Sedona's own preamble format, not WKB
  (`python/sedona/spark/utils/geometry_serde_general.py:250-293`). Sail emits Spark
  4.1 `GEOMETRY` (`crates/sail-plan/src/resolver/data_type.rs:329-366`). So an
  unmodified Sedona client can run `ST_*` queries against Sail **only where the
  geometry stays on the server**: filters, aggregates, `ST_AsText`, `ST_AsBinary`.
  Collecting a geometry column to the client needs either a Sedona client change or a
  Sail shim that emits the UDT. This limits the proof of concept (§10) and is stated
  there.
- **Storage types agree; CRS mapping is narrow.** SedonaDB stores geometry as
  `geoarrow.wkb` metadata over `Binary`, `LargeBinary` or `BinaryView`
  (`rust/sedona-schema/src/datatypes.rs:193,228-250`), and so does Sail. But Sail's
  Spark boundary accepts only `OGC:CRS84`, `EPSG:3857` and `SRID:0`
  (`crates/sail-spark-connect/src/proto/data_type_arrow.rs:31-40`) and fails the whole
  schema on any other CRS, while SedonaDB writes any CRS's JSON
  (`datatypes.rs:485-500`). `ST_Transform` to another CRS, collected, is an error
  today (§7).
- **Functions:** 141 `ST_*` and 7 `ST_*` aggregates, 58 `RS_*`, as DataFusion
  `ScalarUDF`s with multi-kernel overloading (`rust/sedona-expr/src/scalar_udf.rs:69`).
  SedonaDB exports scalar functions over the DataFusion FFI as
  `__datafusion_scalar_udf__` (`python/sedonadb/src/udf.rs:83`), and exports nothing
  else that way: no aggregate, table provider or plan.
- **Config:** `SedonaOptions`, a `ConfigExtension` with prefix `sedona`
  (`rust/sedona-common/src/option.rs:262`), holding among other things an `Arc`'d CRS
  engine (`option.rs:40-55`). Three of the four spatial-join rules return early unless
  `spatial_join.enable` is set (`rust/sedona-query-planner/src/optimizer.rs:199-205,
  248-254, 379-385`). SedonaDB bakes the exporting session's config into each kernel
  before it crosses its own C ABI (`c/sedona-extension/src/scalar_kernel.rs:388-427`).
- **Spatial join:** four logical rules inserted at named positions among
  DataFusion's, three before `push_down_filter` and one appended
  (`optimizer.rs:81-121`), plus a vendored replacement of `push_down_leaf_projections`
  (`:40-58`); a `UserDefinedLogicalNode`; an `ExtensionPlanner`; and
  `SpatialJoinExec` (`rust/sedona-spatial-join/src/exec.rs:361`), which reads every
  build-side partition inside each task (`exec.rs:466-480`), reserves build memory
  from the task's pool with spilling enabled (`prepare.rs:215-220`), and reads
  `SedonaOptions` from the session config with `.unwrap_or_default()`
  (`exec.rs:449`). No `PhysicalExtensionCodec` exists for it. The join form the
  #2001 opening post names is "spatial filters on cross-joins", handled by
  `MergeSpatialFilterIntoJoin` (`optimizer.rs:107-115`).
- **Also installed by `SedonaContext`:** a replacement for the `parquet` file format
  (`rust/sedona/src/context.rs:272`) and a dynamic object-store catalog (`:298-302`).
- **Its own C ABI.** `c/sedona-extension/` defines version-agnostic C structs for
  scalar kernels, execution plans and table providers, with expressions crossing as
  DataFusion protobuf ([sedona-db#407](https://github.com/apache/sedona-db/pull/407),
  [#1004](https://github.com/apache/sedona-db/pull/1004),
  [#1094](https://github.com/apache/sedona-db/pull/1094)). Its maintainer: "I'm
  vaguely planning to propose them to DataFusion as well"
  ([paleolimbot, #2001](https://github.com/lakehq/sail/discussions/2001#discussioncomment-17818136)).
- **Versions:** DataFusion 54.1.0 and arrow 58.3.0, against Sail's 55.1.0 and 59.2.0.

### 3.2 Nutmeg: stateful, narrow, driver-resident

Nutmeg embeds Grust's graph kernels in a Sail server. A Spark client stages a graph
from a DataFrame (`df.write.format("nutmeg")`), runs a kernel
(`spark.read.format("nutmeg").option("algorithm", "pagerank")`, or
`nutmeg_pagerank('g')` in SQL) and gets a DataFrame back.

- **A disclosure.** Nutmeg today compiles against Sail's crates by path
  (`Cargo.toml:44-48`: `sail-common`, `sail-common-datafusion`, `sail-telemetry`,
  `sail-session`, `sail-spark-connect`) and embeds Sail's server
  (`crates/nutmeg-server/src/main.rs:44-67`) through the session-factory hook merged
  as [#2630](https://github.com/lakehq/sail/pull/2630), by the author of this
  proposal. That is exactly what C7 rules out and what C2 calls a deep implementation
  detail. This proposal is how Nutmeg stops doing it.
- **Its state lives in one process.** Staged graphs are a process-global store keyed
  by graph name (`crates/nutmeg-graph/src/lib.rs:1109-1118`). A worker in another pod
  would find nothing. A name-keyed global store is also a cross-session visibility
  problem in a multi-tenant server; that is Nutmeg's defect to fix by scoping the
  store to a session, and nothing here asks Sail to accommodate it.
- **Cluster mode fails today**: staging at `unsupported data sink node`
  (`crates/sail-execution/src/proto/codec.rs:2517`), reads at `unsupported physical
  plan node` (`:2889`). A codec alone would not fix it, because the node would then run
  on a worker without the graph. Driver placement is a hard-coded list of Sail's own
  nodes (`crates/sail-execution/src/job_graph/planner.rs:460-472, 606-617`).
- **What it uses from a session:** table functions (already resolved from the
  DataFusion session, `crates/sail-plan/src/resolver/query/read.rs:421`), a
  `DataSource` for `format("nutmeg")` with read options (`algorithm`, `columnNames`,
  limits; `crates/nutmeg-sail/src/lib.rs:87-117`) and write options (`mode`, `part`,
  column mapping; `:133-165`) returning a `DataSinkExec` (`:222-237`), a
  `SessionConfig` extension selecting the read path (`nutmeg-graph/src/lib.rs:2649-2654`,
  with an environment fallback), and cancellation by stream drop (`:2816-2824`).

### 3.3 The alternative that needs nothing from Sail, and why it is not enough

A Nutmeg with no resident state, whose graphs are persisted to Delta and reloaded
by a kernel running in one worker partition, could be a `pysail.datasources` package
today, with no manifest, no placement and no codec. It would serve one-shot
workloads well. What it cannot do is what a graph-analytics session is for: run
ten algorithms on one staged graph without rebuilding the projection ten times,
keep an index that costs seconds to build and milliseconds to query, and cancel a
running kernel from the client. Those are the reasons Neo4j's Graph Data Science
keeps a projection in memory, and they are the reason Nutmeg holds state. The
argument for driver placement is that any extension with process-resident state
needs it, and the mechanism proposed for it (§5.5) is the one Sail already uses for
its own commit nodes. Nutmeg is the first customer, not the only conceivable one.

### 3.4 Where they differ

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

Placement is the axis of disagreement, so it is a declared property of an extension.

## 4. What DataFusion's FFI carries at 55.1.0, and what it does not

Sail pins DataFusion 55.1.0 and arrow 59.2.0 (`Cargo.toml:165,194`) and uses no
`datafusion-ffi` and no `PyCapsule` today. At 55.1.0, verified in the published crate:

**Carried:** table providers and factories, catalog and schema providers, table
functions, scalar, aggregate and window UDFs (with Arrow field metadata, so extension
types survive), physical expressions, execution plans and plan properties, physical
optimizer rules, a whole query planner, session config and extension options, record
batch streams, statistics and metrics, both extension codecs.

**Not carried:** `LogicalPlan::Extension` nodes and logical optimizer or analyzer
rules (`src/proto/logical_extension_codec.rs:382,386`:
`not_impl_err!("FFI does not support decode of Extensions")`), `ExtensionPlanner`,
file formats (`:435,443`), physical-expression codecs, `DataSink`, object stores, and
the host `RuntimeEnv`: a foreign `TaskContext` is rebuilt with `RuntimeEnv::default()`
(`src/execution/task_ctx.rs:231`) and a `SessionConfig` carrying only `ConfigOptions`
(`src/session/config.rs:137`), so no host memory pool, object-store registry or
config extension crosses ([datafusion#24733](https://github.com/apache/datafusion/pull/24733), open).

Logical plans themselves do cross as protobuf (`FFI_SessionRef::optimize` and
`create_physical_plan`, `src/session/mod.rs:106-130`); what does not is the
`Extension` variant. Sail has 26 `UserDefinedLogicalNodeCore` implementations and no
`LogicalExtensionCodec`, so a foreign query planner cannot see Sail's plans. That is
why `FFI_QueryPlanner` is not the join hook (§5.7).

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
   (`src/execution_plan.rs:418-419`, by `library_marker_id`); a handle from another
   library becomes an opaque `ForeignExecutionPlan` that cannot be downcast
   (`src/query_planner.rs:29-35`). So Sail can downcast its own nodes under a foreign
   parent, and an extension can identify its own; neither can inspect the other's.
3. **Options cross as strings.** Every `ConfigExtension` is flattened to a string map
   (`src/config/mod.rs:42-78`) and recovered by type only where a `Default` can be
   parsed from strings (`:81-101`). A typed extension holding an `Arc` does not cross.
4. **No panic protection.** No `catch_unwind` in the crate; a panic across
   `extern "C"` aborts the process.

## 5. The design

### 5.1 Discovery and loading (C3, C8)

An extension is a Python package with an entry point in the group
`pysail.extensions`, mirroring `pysail.datasources`
(`crates/sail-data-source/src/formats/python/discovery.rs:28`). The entry point
resolves to an object with one method:

```python
def __sail_extension__(self) -> PyCapsule   # capsule name "sail_extension"
```

Distribution is PyPI; discovery is `importlib.metadata`; Sail `dlopen`s nothing.
This would be Sail's first `PyCapsule` unwrap; the `unsafe` surface is the
`datafusion-ffi` call surface, the same one datafusion-python has, not a smaller
one. First registration wins on a duplicate extension name, as the data-source
registry does today (`discovery.rs:163`), and the duplicate is logged. Function-name
collisions are §8.

### 5.2 The manifest (C1, C5.1)

The capsule holds a Sail-owned `#[repr(C)]` manifest of `datafusion-ffi` objects.
It is not a C API: its component fields are `datafusion-ffi` structs with `stabby`
containers, producible from Rust. It is the only ABI Sail defines.

```rust
#[repr(C)]
pub struct SailExtension {
    pub sail_ext_abi_version: u32,     // first field: layout of this struct
    pub datafusion_major: u64,         // must equal Sail's, or refused with a message
    pub name: *const c_char,           // "sedona", "nutmeg"
    pub version: *const c_char,        // the extension's own
    pub placement: SailPlacement,      // AnyWorker | DriverOnly, for the whole extension
    pub library_marker_id: usize,      // datafusion_ffi::get_library_marker_id()
    pub n_components: u32,
    pub components: *const SailComponent,   // kind tag + datafusion-ffi object
    pub release: unsafe extern "C" fn(*mut SailExtension),
}
```

Component kinds: `ScalarUdf`, `AggregateUdf`, `WindowUdf`, `TableFunction`,
`TableProvider` (named, for `format("name")`; §5.8), `CatalogProvider`,
`PhysicalOptimizerRule` with a position (§5.6), `PhysicalExtensionCodec`,
`ExtensionOptions`, `JoinExtension` (§5.7).

Placement is per extension, not per component. Nutmeg needs every component on
the driver; Sedona needs every component on workers; no extension in view needs a
mixture, and a per-component flag would only add a way to be inconsistent.

**Breaking changes (C5.1).** Two numbers are checked before any component is touched,
and a mismatch is an error naming both sides, not a crash. The version is the first
field so that a layout mismatch cannot fault before the check runs, the reason
datafusion-python gives for its own check being only a diagnostic
(`crates/util/src/lib.rs:195-198`: "`version` is not the first field on any of these
types, so a sufficiently different layout can fault before this ever runs"). Arrow
data crosses as the Arrow C Data Interface, which is version-independent, so no
arrow version is checked. Sail's promise: `sail_ext_abi_version` changes only with a
Sail major, and one Sail major accepts one DataFusion major. What Sail cannot
promise is independence from DataFusion's major. An extension releases on its own
schedule within a DataFusion major and rebuilds when Sail moves to the next. That is
the FFI's limit, and C1 is met to exactly that extent. SedonaDB's maintainer prefers
"version-independence from DataFusion"
([#2001](https://github.com/lakehq/sail/discussions/2001#discussioncomment-17818136)),
which his C ABI has and this design, by resting on `datafusion-ffi`, does not. That
is a real trade and §7 records it.

### 5.3 Reaching the resolver: three insertions, not one

Sail's expression resolver consults the session `CatalogManager`, then its built-in
tables, and never DataFusion's `udf`, `udaf` or `udwf` registries
(`crates/sail-plan/src/resolver/expression/function.rs:74-236`); `CatalogManager`
holds `ScalarUDF` only (`crates/sail-catalog/src/manager/function.rs:17-28`).
Table functions are the exception (`resolver/query/read.rs:421`), which is why
Nutmeg's SQL functions already work.

- **Scalar:** after `CatalogManager` and before the built-ins, consult the session's
  `udf` registry. This is the change that makes Sedona's names resolve.
- **Aggregate:** a separate path. Aggregates resolve through
  `get_built_in_aggregate_function` with `AggFunctionInput { distinct, ignore_nulls,
  filter, order_by, .. }` (`function.rs:177, 212-229`). A foreign `AggregateUDF` needs
  an `Expr::AggregateFunction` construction that carries those modifiers; today a
  catalog `ScalarUDF` is rejected as soon as `FILTER` or `ORDER BY` appears
  (`:118-120`) and `DISTINCT` is dropped (`:156-159`). This path cannot be tested until
  SedonaDB exports an aggregate over the FFI (§8).
- **Window:** a third path (`resolver/expression/window.rs:31-148`), which accepts a
  catalog function only if it is a PySpark window UDF (`:106-119`). A foreign
  `WindowUDF` needs a `WindowFunctionDefinition::WindowUDF` construction.

Spark's built-ins keep precedence; an extension shadows one only by session opt-in (§8).

### 5.4 Reaching the workers

Worker sessions are built by `WorkerSessionFactory` with `with_default_features()`,
no mutator and no data-source registry
(`crates/sail-session/src/session_factory/worker.rs:15-54`), for local-cluster
(`session_factory/job_runner.rs:107-110`) and the Kubernetes worker
(`crates/sail-cli/src/worker/entrypoint.rs:20`). The `sail` binary initialises a
Python interpreter for every subcommand (`crates/sail-cli/src/main.rs:11-38`), and
Kubernetes pods run `["sail", "worker"]` (`sail-execution/src/worker_manager/kubernetes.rs:380-381`)
from a Python base image, so discovery can run there. It does not run there today:
`register_external_data_sources` is reached only from the server factory
(`session_factory/server.rs:113`). Python data sources reach workers by a different
route, a pickled reader whose module must be importable
(`codec.rs:1748-1767`).

Change: worker sessions run discovery (§5.1) as a new step and register every
component of every `AnyWorker` extension. `DriverOnly` extensions are not registered
on workers, so a stray reference fails with a named error rather than an empty
registry. The extension's distribution must be installed on workers, as a Python
data source's module must be.

### 5.5 The codec and placement

`RemoteExecutionCodec` is a closed downcast chain
(`crates/sail-execution/src/proto/codec.rs:1825-2889`), hard-wired at
`driver/job_scheduler/mod.rs:37`. For an unknown UDF it writes an empty buffer
(`:3690-3691`); `datafusion-proto` then resolves by name from the decoding session's
registry, which the TODO at `:2899-2921` notes Sail's non-empty `Standard` marker
currently defeats for its own functions. Foreign UDFs take the empty-buffer path, so
with §5.4 a worker's `ctx.udf(name)` finds them. Driver stages round-trip through the
codec too (`driver/actor/handler.rs:607-720` → `task_runner/preparation.rs:59`).

**Encoding.** Sail defines an envelope for foreign nodes: the owning extension's
name plus the bytes its `PhysicalExtensionCodec` produced. `FFI_PhysicalExtensionCodec`
has no discriminator of its own (`try_encode(plan)`, `try_decode(buf, inputs)`), so
the envelope is Sail's, and it makes decoding order-independent. Each extension's
codec is asked only for its own nodes.

**Identifying the owner.** Not by trial encoding. A foreign node's handle carries the
`library_marker_id` of the library that created it (`FFI_ExecutionPlan::new` on a
`ForeignExecutionPlan` returns the inner handle, `src/execution_plan.rs:337-339`), and
each manifest carries its marker. The match is exact and deterministic, and it is
available before any encoding, which stage placement needs.

**Placement.** `job_graph/planner.rs` consults the owner's manifest before its
hard-coded list (`:460-472`). A `DriverOnly` owner forces a driver stage, as
`DeltaCommitExec` does since [#2192](https://github.com/lakehq/sail/pull/2192). The
final-stage rule (`planner.rs:59`) is unchanged: a driver-only read is followed by a
worker stage that forwards its output, as Sail's own driver stages are today.

For Nutmeg this means: manifest says `DriverOnly`; table functions and the streamed
read are FFI components; its nodes are placed by the rule that places Sail's own
commits. A cost it must accept: `DataSinkExec` takes a single input partition, so a
`DriverOnly` write funnels every partition of a cluster job through the driver.

### 5.6 Physical optimizer rules, with a position (C5.3)

The FFI carries `FFI_PhysicalOptimizerRule`. Sail's physical rules are a fixed list
of 25 (`crates/sail-physical-optimizer/src/lib.rs:41-76`), which at DataFusion 55.1.0
includes `EnsureRequirements` (`:58`), the rule that replaced the separate
`EnforceDistribution` and `EnforceSorting`, and Sail's own `JoinSelection`,
`HashJoinBuffering`, `RewriteCollectLeftHashJoin` and `EnforceBarrierPartitioning`
around it. A rule appended through the mutator runs last with no control
(**inferred** from builder semantics).

Change: a rule declares a phase, named for what Sail guarantees rather than for a
rule that may be renamed: `BeforeRequirements` (before partitioning and ordering
requirements are enforced) or `AfterRequirements`. Rules in one phase run in
extension load order. Replacing one of Sail's rules is not offered; SedonaDB
replaces `push_down_leaf_projections` in its own engine (`optimizer.rs:40-58`), and
that is the kind of thing an extension does not get to do to its host.

### 5.7 The join extension: one Sail-owned hook

Neither logical nodes nor logical rules cross the FFI, and a foreign physical rule
cannot inspect Sail's `NestedLoopJoinExec` (§4.2). So the spatial join cannot be
expressed through the FFI as it stands. SedonaDB's maintainer described the options:
"either Sail would have to hard-code some of the logical planning that identifies a
spatial and/or KNN join and have a specific extension point for 'spatial join'
(which could resolve the FFI version of the execution plan), or implement some
general 'join extension' (where it passes the join condition to an extension which
can optionally return an FFI execution plan if it applies). This would be ambitious"
([#2001](https://github.com/lakehq/sail/discussions/2001#discussioncomment-17818136)).

Proposed: the general form, seated where Sail can see the join.

- A `JoinExtension` component names the functions it treats as join predicates
  (`st_intersects`, `st_dwithin`, ...).
- Sail never constructs join nodes itself; it uses `DefaultPhysicalPlanner` with
  extension planners (`crates/sail-session/src/planner.rs:83-113`) and rewrites joins
  afterwards. So the hook is a **Sail-owned physical optimizer rule** in the
  `BeforeRequirements` phase. It downcasts `NestedLoopJoinExec` (Sail's own node,
  which it can) and, when the filter contains a declared predicate, offers the
  extension the join type, the condition as DataFusion protobuf (the representation
  SedonaDB's own C ABI chose, `sedona-db#1094`), the two children as
  `FFI_ExecutionPlan`s, and receives an `FFI_ExecutionPlan` or a refusal.
- The reply declares `build_side: Left | Right | None`. `SpatialJoinExec` reads every
  build partition in every task (`exec.rs:466-480`); Sail's stage planner marks a
  build side `Shared` only for `HashJoinExec` in `CollectLeft` mode and the other join
  types it downcasts (`job_graph/planner.rs:271-336`), and an unknown node inherits
  its parent's usage (`:365`), which would make each task re-read a single-consumption
  shuffle. The declaration is what lets Sail treat the build child as it treats a
  `CollectLeft` build side. It is a Stage 2 pass condition, not a footnote.

**Which queries reach it.** A predicate in an `ON` clause reaches
`NestedLoopJoinExec::filter` directly. The form the #2001 post names, a spatial
filter over a cross join, reaches it only if DataFusion's `push_down_filter` moves
the predicate into the join first (DataFusion 55.1.0 `push_down_filter.rs:502`,
`join.filter = conjunction(join_conditions)`). Whether that happens for the exact
query in Sail is **not verified** and is the first thing Stage 2 checks. SedonaDB's
`MergeSpatialFilterIntoJoin`, `KnnJoinEarlyRewrite` and query-side filter pushdown
are not covered; they wait for §6.

**What execution under a foreign join loses, today.** The extension executes Sail's
children through an `FFI_TaskContext` that Sail's side rebuilds with
`RuntimeEnv::default()` and a bare `SessionConfig` (§4). So under the foreign node a
Sail `DataSourceExec` over object storage cannot resolve its store, `RepartitionExec`
falls back to a default buffer size
(`crates/sail-physical-plan/src/repartition.rs:244-248`), and nodes that require a
Sail config extension fail (`remote_checkpoint.rs:652`, `catalog_command.rs:107`).
On the extension's side, `SpatialJoinExec` gets a default, unbounded memory pool and
default `SedonaOptions`, so it does not spill and does not read the session's
settings. The hook is therefore safe in cluster mode, where the children are
`ShuffleReadExec`, and for local files in local mode, and it is not correct beyond
that until [datafusion#24733](https://github.com/apache/datafusion/pull/24733) shares
the host runtime across the boundary. Stage 2 says so in its pass condition.

**Foreign nodes under `EnsureRequirements`** are handled generically but lossily:
`ForeignExecutionPlan` implements the minimum of the trait
(`src/execution_plan.rs:451-556`), so `required_input_distribution` is unspecified
and equivalence properties are rebuilt from orderings only
(`src/plan_properties.rs:178-180`). Expect a redundant `RepartitionExec` or two
around the join. Not fatal; stated.

### 5.8 Data sources: `format("name")` over an FFI table provider

Sail's format entry point is its `DataSource` trait
(`crates/sail-common-datafusion/src/datasource.rs:461-487`): `create_source(session,
SourceInfo { paths, schema, options, .. })` returns a logical table source, and
`create_writer(session, SinkInfo { mode, options, .. })` returns a `LogicalPlan`. The
FFI has `FFI_TableProvider` with `scan` and `insert_into(session, input, InsertOp)`
(`src/table_provider.rs:131-135`), `FFI_TableProviderFactory::create` taking a
`CreateExternalTable` (`src/table_provider_factory.rs:59`), and no `DataSink`.

Mapping, for a `TableProvider` component named `n`:

- `spark.read.format("n").options(o)` → the factory's `create` with `o` as
  `CreateExternalTable.options` and the read's paths as its location; the resulting
  provider's `scan` becomes the source. Read-side options such as Nutmeg's
  `algorithm` and `columnNames` travel that way.
- `df.write.format("n").mode(m).options(o)` → the same factory, then
  `insert_into` with `m` mapped to `InsertOp` (`overwrite` → `Overwrite`, `append` →
  `Append`; `errorifexists` and `ignore` are refused, as Nutmeg refuses them today).
  Nutmeg's `part` and column-mapping options travel as `CreateExternalTable.options`.
  The write is a foreign `insert_into` plan with a Sail child, so it inherits §5.7's
  runtime caveat; for a `DriverOnly` extension in cluster mode the child is a
  `ShuffleReadExec`, which is the safe case.
- A `SessionConfig` extension cannot cross the FFI. Nutmeg's read-path selector
  (`nutmeg-graph/src/lib.rs:2649-2654`) moves to a read option or stays on its
  environment fallback.

This is the one place the design uses the FFI for a leaf source, which C6 says is
usually better served by a Python data source. The reason is placement: a Python
data source's reader runs on workers, and Nutmeg's reader has nothing there. §9
treats this as the strongest case against C6 compliance.

### 5.9 Spark Connect plugins (C5.2)

Spark Connect carries opaque `google.protobuf.Any` extension messages for relations,
expressions and commands. GraphFrames asked for that route (Discussion
[#2002](https://github.com/lakehq/sail/discussions/2002), and
[#1062](https://github.com/lakehq/sail/issues/1062#issuecomment-3557419148)); Sail
rejects such messages today (`crates/sail-spark-connect/src/proto/plan.rs:1339`).
Sedona does not need it, since its client sends names; Nutmeg does not either.

linhr placed the work in the resolver: "I guess the extension would fit into this
process, and the core logic to mimic GraphFrames would be in the second step (plan
resolver)" ([#2002](https://github.com/lakehq/sail/discussions/2002#discussioncomment-17083597)).
This layer is out of the first release; the manifest reserves a `ConnectPlugin` kind
for it, a function from an `Any` message to a logical plan, seated in the resolver
as he suggested. It is inherently `DriverOnly`. C5.2's answer: the plugin mechanism
is a second entry point into the same extension, not a second extension system.

### 5.10 What the session mutator becomes (C2, C7)

Nothing here registers through `ServerSessionMutator`. Sail discovers and registers
extensions itself, in both server and worker factories. The mutator stays what linhr
called it, a detail of embedding the server in a binary, and Sail stays a
Python-distributed server. Nutmeg migrates from the mutator to a manifest, and stops
compiling against Sail's crates.

## 6. Boundaries of the first release

- **Logical plan transformation is out.** The FFI cannot carry it, and nobody has
  proposed that it should. SedonaDB's maintainer vaguely plans to propose his C
  structs for kernels, plans and expressions upstream; logical nodes are not among
  them. Until something carries logical nodes, SedonaDB's filter merging, KNN rewrite
  and pushdown rules do not run in Sail.
- **DataFusion major coupling stays.** §5.2.
- **`SedonaOptions` does not reach the kernels** across the FFI, and Sail has no
  route from `SET` or `spark.conf.set` to a `ConfigExtension` today
  (`crates/sail-plan/src/resolver/command/variable.rs:8-23` reaches
  `ConfigOptions::set`, which rejects unknown namespaces; `spark.conf.set` stays in a
  Spark-side string map, `sail-spark-connect/src/config.rs:145-151`). Stage 2's
  options work depends on SedonaDB reading options from `ScalarFunctionArgs.config_options`
  rather than freezing them at export (§8).
- **File formats cross as table providers**, not as `FileFormat`, so Sail's own
  parquet reader does not gain GeoParquet metadata handling; SedonaDB's replacement
  of the `parquet` format (`context.rs:272`) does not apply.
- **Object stores and the host runtime do not cross.** An extension carries its own
  clients until [datafusion#24733](https://github.com/apache/datafusion/pull/24733).
- **Panics abort.** Extensions catch their own; Sail documents it.
- **Type mapping is not extensible**, and the existing geometry mapping accepts three
  CRSs. Anything else needs a `TypeMapping` component later.
- **The Sedona client's geometry UDT is not emitted by Sail** (§3.1). Server-side
  geometry works; client-side collection of geometry columns does not.

## 7. Trade-offs made on purpose

- Resting on `datafusion-ffi` buys the maintainers' C1 and costs paleolimbot's
  version independence. A Sail-owned C ABI would invert that. This design takes the
  maintainers' side and says so.
- Per-extension placement is simpler than per-component and covers both references.
- One Sail-owned hook, the join, rather than a general plan-transformation API the
  FFI cannot support.

## 8. Open questions, as questions

1. **Name collisions.** Sail has three implemented `ST_*` built-ins and two stubs
   (`crates/sail-plan/src/function/scalar/geo.rs:10-14`); SedonaDB overwrites Spark's
   own `ST_*` on purpose (`AbstractCatalog.scala:90-96`). Proposed: no shadowing of a
   built-in without a session opt-in; two extensions colliding is a load error.
2. **Enable per session.** The opening post raised "per-session opt-in (e.g. `SET
   sail.extensions = 'sedona,comet'`)" as a question. Proposed: loaded always,
   enabled per session by config, default all, so worker registries match the driver.
3. **Aggregates from SedonaDB.** Needs an aggregate export over the FFI on their side,
   and the aggregate resolver path (§5.3) on Sail's.
4. **Options across the FFI.** Needs SedonaDB to read `SedonaOptions` from the call's
   `ConfigOptions` via `local_or_ffi_extension` rather than baking them at export.
5. **Version alignment for the proof of concept.** SedonaDB is on DataFusion 54.1.0,
   Sail on 55.1.0.

## 9. Check against the constraints, with the case against

| | Met by | Strongest case against |
| --- | --- | --- |
| C1 | every component is a `datafusion-ffi` object; the manifest is the only Sail ABI | independence holds only within a DataFusion major; SedonaDB's maintainer wants more (§7) |
| C2 | nothing registers through the mutator | the reference extension uses the mutator today, widened by #2630 from the same author; disclosed in §3.2 |
| C3, C8 | Python packages, entry points, capsules, no `dlopen` | the `unsafe` surface is the whole `datafusion-ffi` call surface, not a single unwrap |
| C4 | §10 is a proof of concept with a pass condition that can actually be met | the condition is server-side results only, because of the client's UDT |
| C5.1 | two checked versions, first-field layout, mismatch is an error | none found |
| C5.2 | a reserved `ConnectPlugin` kind in the resolver | not built in the first release |
| C5.3 | named phases for physical rules | logical ordering is deferred with the logical layer; replacement is refused |
| C6 | FFI is used for plan transformation (§5.7) and for one leaf source | Nutmeg's leaf source uses the FFI because of a design choice, resident state, that §3.3 argues for but no maintainer has endorsed |
| C7 | Sail stays a Python-distributed server | the reference extension compiles against Sail's crates today; this proposal is how it stops |

## 10. Staged plan, with a proof of concept first

**Stage 0, proof of concept (C4), no new Sail ABI.** Pin a SedonaDB build to
DataFusion 55.1.0. Register its existing `__datafusion_scalar_udf__` exports into a
Sail session through a `pysail` call, add the scalar resolver change (§5.3), and run
the unmodified `apache-sedona` PySpark client against Sail in `local` mode. Pass
condition: `ST_*` calls resolve by name, and queries whose geometry stays on the
server (`ST_Intersects` filters, `ST_AsText` projections, counts) return correct
results. Not a pass condition: collecting a geometry column, which the client cannot
consume from Sail. Then repeat in `local-cluster` with worker discovery (§5.4) and the
empty-buffer UDF fallback (§5.5). Pass condition: the same queries, and the plan
encodes and decodes on a worker. This is most of a Sedona user's notebook, and it
proves the FFI path end to end with nothing invented.

**Stage 1.** Manifest and discovery (§5.1, §5.2); worker loading (§5.4); codec
envelope and marker-based placement (§5.5); `ExtensionPhysicalPlanner` returns
`Ok(None)` for unknown nodes instead of `internal_err!`
(`crates/sail-session/src/planner.rs:540`, the prerequisite #2001's author named);
Nutmeg migrated off the mutator as the `DriverOnly` reference. Pass conditions:
Nutmeg stages and reads in `local-cluster` with its nodes on the driver; dropping a
read's stream cancels the kernel across the FFI (`FFI_RecordBatchStream` release
drops the inner stream, `src/record_batch_stream.rs:95-100, 211-214`), verified rather
than assumed.

**Stage 2.** Physical rule phases (§5.6); the join hook (§5.7) with a codec for
`SpatialJoinExec` written on the Sedona side; options over the FFI once SedonaDB
reads them per call. Pass conditions, in `local-cluster`: an `ST_Intersects` join in
an `ON` clause plans as `SpatialJoinExec`; the cross-join-with-`WHERE` form does or
does not, and the answer is recorded; the build side is shuffled once and read by
every task.

**Stage 3.** Logical plan transformation, when something carries it; `ConnectPlugin`;
type mapping; the Sedona client UDT.

## 11. What is asked of others

- **SedonaDB:** a DataFusion 55 build for Stage 0; an aggregate export over the FFI;
  options read per call rather than frozen at export; eventually a codec for
  `SpatialJoinExec`.
- **DataFusion:** nothing for stages 0 to 2. Stage 3 waits on logical nodes crossing
  the FFI and on [#24733](https://github.com/apache/datafusion/pull/24733).
- **Sail:** the five stage-1 changes, each reopening one closed place: the resolver,
  the worker factory, the codec, the placement list, the physical planner's error.
- **Nutmeg:** scope its store to a session; move off the mutator; accept the
  driver-funnelled write.

## 12. Changes from the first revision

An adversarial review of the first draft found twenty-six issues. The material ones:
the proof of concept claimed an unmodified Sedona client would work, without noting
its geometry UDT; the join hook cited a query the #2001 post does not contain and
excluded the form it does; rule positions were anchored to `EnforceDistribution`,
which Sail does not have at 55.1.0; placement was identified by codec claiming rather
than by library marker; the resolver change was described as one insertion rather
than three; `SedonaOptions` was assumed to cross the FFI; Nutmeg's use of Sail's
crates and of #2630 was not disclosed; a claim that `pysail` already unwraps
capsules was false; a quote said "steals" where the source says "takes"; and
"intends to propose" was stronger than "vaguely planning to". All are corrected
above.
