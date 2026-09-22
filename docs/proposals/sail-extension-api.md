# A Sail extension API, tested against SedonaDB and Nutmeg

A design proposal for [lakehq/sail discussion #2001](https://github.com/lakehq/sail/discussions/2001).
Draft; not yet posted. Fourth revision, after an external architecture review whose
findings reshaped it: the earlier revisions described which closed places in Sail
an extension must reach; this one also states the contracts an admitted object must
satisfy for its execution to stay correct through Sail's job graph, retries, worker
reconstruction and cancellation. The two are different problems, and the second was
missing.

Every claim is anchored to a public source: a quoted comment with its link, or a
file and line at a named commit. Sail is read at `main` `51b57bc2` (2026-09-22),
`datafusion-ffi` and `datafusion-physical-plan` at the published 55.1.0 crates,
SedonaDB at `main` `a115fc3f`, Apache Sedona at `master` `86fbb82b`, Nutmeg at
`work/streaming-reads` `96816e5`, datafusion-python at `main` `516d20d`. Where a
claim is reasoning rather than something read or run, it says **inferred**.

## 1. In one paragraph

Extensions are Python packages discovered through an entry-point group, as
`pysail.datasources` is today. Each hands Sail one small, versioned, `repr(C)`
manifest through a `PyCapsule`. Every component in the manifest is a
`datafusion-ffi` object that DataFusion 55.1.0 already carries. Sail's work has two
halves. The first is reaching the places where those objects must be consulted and
today are not: the name resolver, the worker sessions, the remote-execution codec
and stage placement. The second, which is larger, is holding a foreign object to
the contracts Sail's own nodes satisfy implicitly: who owns it, which session and
query it belongs to, where it may run, what its children must provide, which
resources it uses, how another process reconstructs it, and what happens on
cancellation or retry. A first release answers those questions for a few
capabilities, restrictively, rather than designing a universal extension system.
It begins with a proof of concept that needs no new ABI, because that is where most
of the value is and where the maintainers asked to start.

## 2. Increment A: an explicitly experimental function proof of concept (C4)

SedonaDB already exports its `ST_*` scalar functions over the DataFusion FFI as
`__datafusion_scalar_udf__` (`python/sedonadb/src/udf.rs:83`). Sail's expression
resolver never consults DataFusion's session UDF registry
(`crates/sail-plan/src/resolver/expression/function.rs:74-236`). Those two facts
make the smallest possible experiment:

1. Pin a SedonaDB build to DataFusion 55.1.0 (it is on 54.1.0 today), and pin the
   exact `datafusion-ffi` version and build tuple on both sides; the FFI's own
   `version()` reports only the major (§5), so the pin is the guarantee, not the check.
2. Register its capsules into a Sail session through a `pysail` call.
3. Add one lookup to the scalar resolver: the session's `udf` registry, at a
   position fixed by the precedence matrix in §7.3.
4. Run the unmodified `apache-sedona` PySpark client against Sail in `local` mode.

Over Spark Connect that client sends `Column(UnresolvedFunction(function_name,
expressions))` (`python/sedona/spark/sql/connect.py:40`, selected by `is_remote()`
at `dataframe_api.py:69`), so on the wire its contract is function names.

**Pass condition:** `ST_*` calls resolve by name, and queries whose geometry stays on
the server (`ST_Intersects` filters, `ST_AsText` projections, counts, aggregates)
return results equal to an independent oracle. **Not a pass condition, and not
achievable:** collecting a geometry column. Sedona's client type is a
`UserDefinedType` over `BinaryType` (`python/sedona/spark/sql/types.py:47-51`) with
Sedona's own preamble byte format
(`python/sedona/spark/utils/geometry_serde_general.py:250-293`), while Sail emits
Spark 4.1 `GEOMETRY` (`crates/sail-plan/src/resolver/data_type.rs:329-366`). No
client-compatibility or performance claim is made from this increment.

Then, in the same increment: an independently compiled FFI fixture with a scalar,
an aggregate and a window function, so that `DISTINCT`, `FILTER`, `ORDER BY`, null
handling and partial/final aggregation are qualified now, without waiting for
SedonaDB to export an aggregate; a separate-wheel build of the fixture, so the
capsule crosses a real package boundary; the codec path in `local-cluster`; and a
separate-process worker smoke test, because `local-cluster` workers are actors in
the server process (§7.5) and prove less than a separately started worker.

That is most of a Sedona user's notebook and a pull request of a few hundred
lines. Everything after this section is what it takes to go further, and none of
it should be frozen until this increment has run.

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

§10 checks the design against each, with the strongest case that it fails.

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
  scalars are exported over the FFI. These counts are from the pinned survey, not
  re-certified here.
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
  Neither is integrated by anything in this proposal (§8).
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
  would find nothing. The name-keyed store is a multi-tenancy defect in Nutmeg, to be
  fixed there by scoping it to a session; what Sail must supply for that fix is a
  stable, host-issued session identity and lifetime (§6.2).
- **Its writes have no retry contract.** `StageWriter::write_all` stages batches and
  commits in `finish()`; an append retains existing rows, adds the new batches and
  increments the graph revision (`nutmeg-sail/src/lib.rs:240`, `nutmeg-graph/src/lib.rs:1563`).
  The writer reads no task context and carries no operation or attempt identity.
- **Cluster mode fails today:** staging at `unsupported data sink node`
  (`crates/sail-execution/src/proto/codec.rs:2517`), reads at `unsupported physical
  plan node` (`:2889`). A codec alone would not fix it: the node would run on a worker
  without the graph. Driver placement is a hard-coded list of Sail's own nodes
  (`crates/sail-execution/src/job_graph/planner.rs:460-472, 606-617`).
- **What it uses from a session:** table functions (already resolved from the
  DataFusion session, `crates/sail-plan/src/resolver/query/read.rs:421`); a
  `DataSource` for `format("nutmeg")` with read options (`crates/nutmeg-sail/src/lib.rs:87-117`)
  and write options (`:133-165`) whose writer is an `insert_into` over a table
  provider returning `DataSinkExec` (`:174-180, 222-237`); a typed `SessionConfig`
  extension selecting the read path (`nutmeg-graph/src/lib.rs:2648-2654`, with an
  environment fallback); cancellation by stream drop, which signals a detached
  kernel thread that keeps its resources until it exits (`:2776, 2816-2824`).

### 4.3 The alternative C6 points at, and what it gives up

A Nutmeg *service*, a separate process holding the graphs and reached from a
Python data source, would need nothing from Sail: the reader runs on workers and
cancels when its generator closes. What it gives up is that every kernel's input
and output cross a process boundary and a second deployable exists. In-process
residency has two reasons: Arrow batches pass from the engine to the kernel and
back without a copy, and there is nothing to deploy beyond `pip install`. That is a
trade a maintainer may reasonably decline to support; §10's C6 row says so. The
mechanism proposed for it (§7.5) is the one Sail already uses for its own commit
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
| mutation | none | append and overwrite, with a revision |

## 5. What DataFusion's FFI carries at 55.1.0

Sail pins DataFusion 55.1.0 and arrow 59.2.0 (`Cargo.toml:165,194`) and uses no
`datafusion-ffi` and no `PyCapsule` today. At 55.1.0, verified in the published crates:

**Carried:** table providers and factories, catalog and schema providers, table
functions, scalar, aggregate and window UDFs (with Arrow field metadata, so extension
types survive), physical expressions, execution plans and plan properties, physical
optimizer rules, a query planner, session config and extension options, record batch
streams, statistics and metrics, both extension codecs.

**Not carried:** `LogicalPlan::Extension` nodes and logical optimizer or analyzer
rules (`src/proto/logical_extension_codec.rs:382,386`), `ExtensionPlanner`, file
formats (`:435,443`), physical-expression codecs, `DataSink`, object stores, and the
host `RuntimeEnv`: a foreign `TaskContext` is rebuilt with `RuntimeEnv::default()`
and a `SessionConfig` carrying only `ConfigOptions`, falling back to defaults on
error (`src/execution/task_ctx.rs:193-242`, `src/session/config.rs:137-139`;
[datafusion#24733](https://github.com/apache/datafusion/pull/24733), open, head
`f509f500` when checked).

**Not forwarded, which is different from not carried:** `ForeignExecutionPlan`
implements the minimum of `ExecutionPlan` (`src/execution_plan.rs:451-556`). It does
not forward `required_input_distribution`, `required_input_ordering` or the newer
`input_distribution_requirements()` (DataFusion 55.1.0 `datafusion-physical-plan`
`src/execution_plan.rs:194-221`), so the host sees DataFusion's defaults: unspecified
distribution, no required ordering. `FFI_PlanProperties` carries output properties
only and rebuilds equivalences from orderings (`src/plan_properties.rs:160-190`).

Sail has 26 `UserDefinedLogicalNodeCore` implementations and no
`LogicalExtensionCodec`, so a foreign query planner could never see Sail's plans;
that is why `FFI_QueryPlanner` is not the join hook (§7.7).

**Five properties that shape the design:**

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
   library becomes an opaque `ForeignExecutionPlan` (`src/query_planner.rs:29-35`).
   The marker is the address of a library-local static (`src/lib.rs:64-88`): it
   identifies a library instance, not a manifest, session or component.
3. **Options cross as strings.** Every `ConfigExtension` is flattened to a string map
   (`src/config/mod.rs:42-78`) and recovered by type only where a `Default` can be
   parsed from strings (`:81-101`). A typed extension holding an `Arc` does not cross.
4. **A foreign codec's task context can be rebound.** `FFI_PhysicalExtensionCodec::new`
   rebinds an imported codec to the supplied task-context provider
   (`src/proto/physical_extension_codec.rs:292-317`, regression test at `:731`). So
   per-session binding of a codec is a supported mechanism; it does not restore the
   host runtime (property 5).
5. **No panic protection.** No `catch_unwind` in the crate; a panic across
   `extern "C"` aborts the process.

## 6. The contracts a foreign object must satisfy

Opening the closed places (§7) admits an object. These contracts are what make its
execution correct afterwards. Each names the Sail or DataFusion mechanism that
would otherwise break it, and the increment (§11) in which it must be met.

### 6.1 Ownership and identity (increment B)

A library marker identifies a library, not an extension: two manifests may share a
provider library, a glue manifest may list objects from another library (§2 is that
case), and a provider may return a plan another library made. So ownership is an
explicit identity attached at every plan-producing boundary: Sail wraps a foreign
plan in a Sail-owned adapter carrying the extension and component identity, and
the wire envelope (§7.5) carries the same. Markers stay an FFI optimisation for
unwrapping, never a wire identity. In v1, conflicting ownership at load, two
manifests claiming one component, is a rejected load rather than a resolved one;
mixed-owner children under a foreign parent are recorded per child.

### 6.2 Session binding and configuration snapshots (increment B)

Discovery is a process event; a session is an instance. Sail's server factory
receives `ServerSessionInfo` with session and user identity
(`crates/sail-session/src/session_factory/server.rs:31`); the worker factory takes
`()` and builds a default config (`session_factory/worker.rs:34`). A DataFusion task
or session id is not the Spark session identity. The contract: a host-issued session
identity and incarnation, an explicit close and expiry, per-session component
handles, and a configuration snapshot (per-session enablement, `SET` values,
exported-UDF options) carried to task decoding and execution, so that driver and
worker execute one query under one effective configuration. A query planned before
a concurrent `SET` keeps its snapshot. Codecs are bound per session through the
rebinding in §5.4. Nutmeg's session-scoped store rests on this identity.

### 6.3 Placement, covering functions as well as nodes (increment B)

A foreign scalar can sit inside an ordinary projection or filter with no foreign
plan node above it, and the job graph places stages by walking plan nodes
(`crates/sail-execution/src/job_graph/planner.rs:254, 606, 881`), including barrier
and root-preservation paths. So placement cannot be decided from foreign nodes
alone. v1 rule: a `DriverOnly` extension may not export scalar, aggregate or window
functions; only table functions, providers and plans, whose nodes the placement
walk sees. Every task carries a required-extension descriptor: extension and
component identity, wire-format version, build tuple, and configuration identity,
validated before scheduling or decoding, so a missing worker package or a mismatched
version fails with both identities named rather than at execution. Exact package
equality across the deployment is the v1 policy.

### 6.4 Physical input requirements (increment B for the adapter; D for joins)

Because `ForeignExecutionPlan` does not forward input requirements (§5), a host
optimizer cannot enforce what it cannot see: a foreign operator needing one
partition, sorted input or co-partitioned inputs can receive incompatible children,
and the answer changes, not only the plan. The `DataSinkExec` case in §7.6 is one
instance of the category. Contract: the Sail-owned adapter (§6.1) carries the
foreign node's declared input requirements, distribution and ordering per child and
relationships between children, and Sail validates them through child replacement,
optimizer passes, encoding and decoding, and task preparation. In v1 the adapter
accepts only documented execution shapes, single-partition and unspecified, and
rejects others. `build_side` (§7.7) and a coalesce before a sink are instances of
this contract, not substitutes for it.

### 6.5 Runtime fidelity (increment B, gated; not deferred)

A foreign parent executes Sail's children through a rebuilt task context with
`RuntimeEnv::default()` (§5): no configured memory pool or spill policy, no
object-store registry, no caches, no typed session services (Sail's runtime factory:
`crates/sail-session/src/runtime.rs:42`). The foreign node itself gets the same
defaults for its own memory. Contract: host-resource fidelity is a capability with
four parts, memory, temporary disk, object stores and typed services, each either
provided across the boundary or refused with an explicit unsupported error; never
silently defaulted. Until [datafusion#24733](https://github.com/apache/datafusion/pull/24733)
or an equivalent lands, a foreign parent over a Sail child is accepted only where
every part it needs is either unused (a `ShuffleReadExec` child, which reads only
`batch_size()`, `plan/shuffle_read.rs:98`) or declared as the extension's own
independent budget. Nutmeg's kernels have their own admission; that covers the
kernels, not the Sail operators or transfer buffers around them.

### 6.6 Distributed scan invariant (increment C for formats)

Task preparation rewrites native file scans to disable process-local sibling work
sharing, because in cluster mode each partition is an isolated task and would
otherwise scan every file (`crates/sail-execution/src/task_runner/preparation.rs:58-65`).
A provider-created scan that stays an opaque foreign node never matches that
downcast. Contract: a foreign scan declares its partition semantics through the
adapter, or is restricted to the driver. Local-file readability proves nothing about
this.

### 6.7 Mutation, retry and commit (increment C)

Sail's scheduler retries task regions and cancels other attempts in a failed one
(`crates/sail-execution/src/driver/job_scheduler/core.rs:150-175`). A driver-side
write that commits before a downstream task or acknowledgement fails can be replayed;
for Nutmeg an append would apply twice, and an overwrite is not automatically safe
under concurrent writes or read-visible revisions. This scenario is deduced from the
scheduler, not fault-injected. Contract: mutation is specified separately from
residency. v1 policy for Nutmeg: at-most-once, no retry, with an explicit
indeterminate outcome reported when a write's acknowledgement fails; a retried read
pins the graph revision it started on, or discloses that it may observe a newer one.
A prepare/commit pattern keyed by session incarnation and logical operation identity
is the later design.

### 6.8 Cancellation end to end (increment C)

Spark distinguishes interrupt, release and reattachment
(`crates/sail-spark-connect/src/service/plan_executor.rs:566`, `executor.rs:359`);
a stream drop across the FFI is one signal among those. Nutmeg's drop cooperatively
cancels a detached kernel thread that keeps its resources until it exits. Contract:
cancellation is tested through the Spark client operation, during computation and
while blocked on a full output channel, under `LIMIT` and early consumer stop,
session expiry, driver shutdown and task-region cancellation; the evidence is
kernel termination and accounting release, not receipt of a request. Exported
Arrow batches held past the drop remain valid until the last consumer releases them.

## 7. The design, by increment

### 7.1 The manifest (increment B; C1, C5.1)

The capsule holds a Sail-owned `#[repr(C)]` manifest of `datafusion-ffi` objects.
It is producible from Rust, since its components carry `stabby` containers; it is
not a C API. It is the only ABI Sail defines, and in v1 it is deliberately small.

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
    pub kind: SailComponentKind,
    pub name: *const c_char,         // the function, format or catalog name
    pub object: *mut c_void,         // the datafusion-ffi struct for that kind
}
```

**v1 support table.** Every kind names its exact payload type, ownership transfer,
lifetime and threading; a kind not in the table is not in v1.

| kind | payload | ownership |
| --- | --- | --- |
| `ScalarUdf`, `AggregateUdf`, `WindowUdf` | `FFI_ScalarUDF` etc. | Sail takes the object; released with the manifest |
| `TableFunction` | `FFI_TableFunction` | same |
| `TableProvider` | `FFI_TableProvider` | same; named for `format("name")` reads |
| `TableProviderFactory` | `FFI_TableProviderFactory` | same; named for `format("name")` reads and writes (§7.6) |
| `PhysicalExtensionCodec` | `FFI_PhysicalExtensionCodec` | rebound per session (§5.4) |
| `ExtensionOptions` | `FFI_ExtensionOptions` | registered into the session config |

`JoinExtension` (§7.7) and a Spark Connect plugin (§7.8) are not `datafusion-ffi`
objects and have no payload the FFI defines; they enter the table only when their
own ABI is specified, and are not reserved as undefined tags.

The capsule's owner is retained until every callback, stream and buffer it produced
is released. Placement is per extension (§6.3). An installed native package is
trusted in-process code; per-session disablement is a configuration, not a security
boundary.

**Breaking changes (C5.1).** Two numbers are checked before any component is touched;
a mismatch is an error naming both sides. The version is the first field so a layout
mismatch cannot fault before the check runs, the gap datafusion-python describes in
its own check (`crates/util/src/lib.rs:195-198`: "`version` is not the first field on
any of these types, so a sufficiently different layout can fault before this ever
runs"). `datafusion_major` is kept in the manifest because most FFI structs carry no
`version` field: only about a dozen do, and none of the UDF kinds,
`FFI_TaskContext`, `FFI_PlanProperties`, `FFI_SessionConfig`, `FFI_ExtensionOptions`
or `FFI_RecordBatchStream` does. The check rejects known-incompatible manifests; it
does not validate arbitrary pointers, and it does not establish that every
FFI-plus-protobuf combination within a major is compatible. So v1 pins and tests one
exact DataFusion FFI version and build tuple, and the descriptor in §6.3 carries it.
What cannot be promised is independence from DataFusion's major: an extension
releases on its own schedule within a pinned build and rebuilds when Sail moves.
C1 is met to that extent. SedonaDB's maintainer prefers "version-independence from
DataFusion", which his C ABI has and `datafusion-ffi` does not; §9 records that as
an open trade.

### 7.2 Discovery and session binding (increment B; C3, C8)

An entry point in the group `pysail.extensions`, mirroring `pysail.datasources`
(`crates/sail-data-source/src/formats/python/discovery.rs:28`), resolves to an
object with one method, `__sail_extension__(self) -> PyCapsule`, capsule name
`sail_extension`. Distribution is PyPI; discovery is `importlib.metadata`; Sail
`dlopen`s nothing. This would be Sail's first `PyCapsule` unwrap, and the `unsafe`
surface is the `datafusion-ffi` call surface, the same one datafusion-python has.
A duplicate extension name is refused at load; a manifest with an unsupported tag,
an incorrect capsule name or a missing required component is rejected through the
bootstrap header, never by dereferencing an incompatible component.

Discovery yields process-level objects. Binding them to a session is a separate
step with the contract in §6.2, performed by Sail's session factories, not by the
mutator.

### 7.3 Reaching the resolver: three insertions and one precedence matrix

Sail resolves an expression through the session `CatalogManager` (which holds
`ScalarUDF` only, `crates/sail-catalog/src/manager/function.rs:17-28`), then its
built-in tables, never DataFusion's registries. Table functions are the exception
(`resolver/query/read.rs:421`).

- **Scalar:** consult the session's `udf` registry. This is the §2 change.
- **Aggregate:** a different path. Aggregates resolve through
  `get_built_in_aggregate_function` with `AggFunctionInput { distinct, ignore_nulls,
  filter, order_by, .. }` (`function.rs:177, 212-229`); a catalog `ScalarUDF` is
  rejected when `FILTER` or `ORDER BY` appears (`:118-120`) and `is_distinct` is not
  carried (`:150-153`). A foreign `AggregateUDF` needs an `Expr::AggregateFunction`
  construction with those modifiers, qualified by the fixture in §2.
- **Window:** `resolver/expression/window.rs:31-148` accepts a catalog function only
  if it is a PySpark window UDF (`:106-119`); a foreign `WindowUDF` needs a
  `WindowFunctionDefinition::WindowUDF` construction.

**Precedence matrix**, one for all three paths, enforced at registration and at
resolution: Spark built-ins first; then Spark user-defined functions registered
through the catalog, so their existing precedence is unchanged; then extension
functions, in extension load order. An extension shadows a built-in only under a
session opt-in (`sail.extensions.override`), and the built-in stays reachable under
a qualified name. Two extensions registering one name is a load error. Names are
matched after Spark's case normalisation; aliases register as names. Workers
reconstruct the implementation the driver chose, identified by the descriptor in
§6.3, not merely one with the same name.

### 7.4 Reaching the workers (increment B)

Worker sessions are built by `WorkerSessionFactory` with `with_default_features()`,
no mutator and no data-source registry
(`crates/sail-session/src/session_factory/worker.rs:15-54`); the `sail` binary
initialises a Python interpreter for every subcommand (`crates/sail-cli/src/main.rs:11-38`)
and Kubernetes pods run `["sail", "worker"]` (`sail-execution/src/worker_manager/kubernetes.rs:380-381`),
so discovery can run there. It does not today: `register_external_data_sources` is
reached only from the server factory (`session_factory/server.rs:113`). Python data
sources reach workers by a different route, a pickled reader whose module must be
importable (`codec.rs:1748-1767`).

Change: worker sessions run discovery as a new step, register every component of
every `AnyWorker` extension, and bind the session snapshot from §6.2. `DriverOnly`
extensions are not registered on workers, and by §6.3 export nothing that could
reach one. `local-cluster` workers are actors cloned from one context in the server
process (`sail-execution/src/worker_manager/local.rs:22`,
`session_factory/job_runner.rs:99`); a separately started worker with its own
Python and native modules is the qualification that counts.

### 7.5 The codec, the envelope and placement (increment B)

`RemoteExecutionCodec` is a closed downcast chain
(`crates/sail-execution/src/proto/codec.rs:1825-2889`), hard-wired at
`driver/job_scheduler/mod.rs:37`. For an unknown UDF it writes an empty buffer
(`:3690-3691`), and `datafusion-proto` then resolves by name from the decoding
session's registry (`physical_plan/from_proto.rs:296-300`); the TODO at `:2899-2921`
notes Sail's own non-empty `Standard` marker defeats that fallback for Sail's
functions. Driver stages round-trip through the codec too
(`driver/actor/handler.rs:607-720` → `task_runner/preparation.rs:59`).

**Encoding.** Sail defines an envelope for foreign nodes: the owning extension and
component identity (§6.1), the wire-format version, and the bytes the extension's
`PhysicalExtensionCodec` produced. `FFI_PhysicalExtensionCodec` carries no
discriminator (`try_encode(plan)`, `try_decode(buf, inputs)`,
`src/proto/physical_extension_codec.rs:51-59`), so the envelope is Sail's, and
decoding is by identity, order-independent. The adapter's declared input
requirements (§6.4) travel in the envelope. Foreign UDFs are not name-only on the
wire: the task's descriptor (§6.3) names the extension, version and configuration
identity the driver used, validated before decode.

**Placement.** The adapter's identity, not a marker, tells `job_graph/planner.rs`
who owns a node. Classification is centralised so that the main placement walk, the
barrier paths and root preservation agree. A `DriverOnly` owner forces a driver
stage, as `DeltaCommitExec` does since [#2192](https://github.com/lakehq/sail/pull/2192).
The final-stage rule (`planner.rs:59`) is unchanged: a driver-only read is followed
by a worker stage that forwards its output. Sail's driver stages today are commit
and metadata nodes (`planner.rs:606-617`); a driver stage that ingests a shuffle is a
new pattern, and it should be named as one.

**The cost for Nutmeg, stated plainly:** every row of a staged graph passes through
the Spark Connect server process on write, and a read's rows pass driver → worker →
driver → client. A `DriverOnly` extension pays that for residency.

### 7.6 Data sources: a narrow format adapter (increment C)

Sail's format entry point is its `DataSource` trait
(`crates/sail-common-datafusion/src/datasource.rs:221, 461-487`): `SourceInfo`
carries several paths, an optional schema, constraints, partition, bucket and sort
metadata, layered options and case sensitivity; `SinkInfo` carries the input and
write metadata. The FFI has `FFI_TableProvider` with `scan` and
`insert_into(session, input, InsertOp)` (`src/table_provider.rs:131-135`),
`FFI_TableProviderFactory::create` taking a protobuf `CreateExternalTable`
(`src/table_provider_factory.rs:59, 147-155`), and no `DataSink`. A
`CreateExternalTable.location` is one string, not a path list.

v1 is therefore a narrow adapter, not a general bridge. For a
`TableProviderFactory` component named `n`:

- `spark.read.format("n").options(o)` → `create` with `o` as
  `CreateExternalTable.options` (precedence and case handling specified: layered
  options flatten last-wins, keys matched after Spark normalisation), one path as
  `location`, the requested schema when the read gives one and an empty schema
  meaning "infer" otherwise, `n` as `name` and `file_type`. Zero paths and several
  paths, partitioning, bucketing and sort metadata are refused with a named error,
  not discarded.
- `df.write.format("n").mode(m).options(o)` → the same factory, then `insert_into`
  with `m` mapped to `InsertOp` (`overwrite` → `Overwrite`, `append` → `Append`;
  `errorifexists` and `ignore` refused, as Nutmeg refuses them today), the write's
  input schema propagated.
- **Sail coalesces the input before any foreign `insert_into`**, as an instance of
  §6.4. `DataSinkExec` requires a single input partition and executes only partition 0
  (`datafusion-datasource-55.1.0/src/sink.rs:277-287, 344-348`); in-process
  `EnsureRequirements` inserts the coalesce, across the FFI the requirement is
  invisible, and a multi-partition write would stage partition 0 and report success.
- A foreign scan declares its partition semantics or is `DriverOnly` (§6.6); scan
  pushdown exactness, projection and limit contracts are the provider's and are
  validated, separately from creation.
- A typed `SessionConfig` extension cannot cross; Nutmeg's read-path selector moves
  to a read option.

This is the one place the FFI is used for a leaf source, which C6 says a Python data
source usually serves better. The reason is placement, not performance; §10's C6
row treats it as the strongest case against. Generic catalog providers are out of
v1: Sail's named-table resolver asks `CatalogManager`, not DataFusion's registry
(`crates/sail-plan/src/resolver/query/read.rs:30`), so an imported DataFusion
catalog would be invisible to Spark SQL until a bridge into Sail's catalog model is
specified (§8).

### 7.7 The join extension: one Sail-owned hook, with its own ABI (increment D)

Logical nodes and rules do not cross the FFI, and a foreign physical rule cannot
inspect Sail's join nodes (§5, property 2). SedonaDB's maintainer described the
options: "either Sail would have to hard-code some of the logical planning that
identifies a logical and/or KNN join and have a specific extension point for
'spatial join' (which could resolve the FFI version of the executionplan), or
implement some general 'join extension' (where it passes the join condition to an
extension which can optionally return an FFI execution plan if it applies). This
would be ambitious" ([#2001](https://github.com/lakehq/sail/discussions/2001#discussioncomment-17818136)).

Proposed: the general form, seated where Sail can see the join, and specified as a
versioned request/response ABI of its own rather than as a manifest tag.

- The hook is a Sail-owned physical optimizer rule at a fixed position: after
  `JoinReorder`, `JoinSelection`, `FilterPushdown` and `WindowTopN`, and before
  `EnsureRequirements` (`crates/sail-physical-optimizer/src/lib.rs:48-58`). It
  downcasts two shapes Sail can produce: `NestedLoopJoinExec` with a filter, and
  `FilterExec` over `CrossJoinExec`, which Sail's `JoinReorder` reconstructs
  (`join_reorder/reconstructor.rs:584` for the nested-loop shape; `:600` builds the
  cross join and `:1010` the filter over it). `JoinReorder` decomposes only
  `HashJoinExec` regions, so a nested-loop join the planner produced survives it.
- **The request** carries the join kind; the physical `JoinFilter` as DataFusion
  carries it, its expression, its intermediate schema and its side-and-index map
  (`datafusion-physical-plan` 55.1.0 `src/joins/join_filter.rs:27-33, 47-49, 66-71`), because
  the expression's column indices are not indices into the concatenated children;
  both child schemas and the output schema; and the children as `FFI_ExecutionPlan`s.
  A predicate claim is bound to the registered component whose function the resolver
  actually selected, not to a name.
- **The response** is an `FFI_ExecutionPlan` or a refusal, with `build_side: Left |
  Right | None`, the declared input requirements of §6.4, and the output schema,
  which Sail validates against the join's. A recognised predicate inside a larger
  condition does not authorise dropping residual predicates or moving them across an
  outer join; residual predicates stay with Sail. v1 accepts inner joins and a narrow
  predicate grammar; outer, semi, anti and KNN forms are declined without changing
  their results. Two extensions claiming one join is deterministic by registration
  order in v1, and the doc says so.
- **Build-side reuse.** `SpatialJoinExec` reads every build partition in every task
  (`exec.rs:466-480`); Sail marks a build side `Shared` for `HashJoinExec` in
  `CollectLeft` mode and for the nested-loop, cross and piecewise-merge joins it
  downcasts (`job_graph/planner.rs:292-296, 316-326`), and an unknown node inherits its
  parent's usage (`:365`). The declared `build_side` travels through the adapter and
  the envelope so Sail treats the build child as a `CollectLeft` build side. A
  reusable shuffle means several consumers may read the produced build stream; it is
  not proof that all tasks share one in-memory index, and the evidence records both
  shuffle production and per-task materialisation.

**Which queries reach it.** A predicate in an `ON` clause is the join's filter
directly. The cross-join-with-`WHERE` form the #2001 post names reaches it because
Sail installs DataFusion's default logical rules with two of its own added and one
dropped (`crates/sail-session/src/optimizer.rs:9-15`,
`sail-logical-optimizer/src/lib.rs:24-40`), lowers a cross join through
`LogicalPlanBuilder::cross_join` (`resolver/query/join.rs:90`), DataFusion's
`push_down_filter` folds the predicate into the join (DataFusion 55.1.0
`push_down_filter.rs:431-434, 502`) and the physical planner plans a filter-only join
as `NestedLoopJoinExec` (`physical_planner.rs:1693-1694`). That chain is read, not
run; increment D runs it. SedonaDB's `MergeSpatialFilterIntoJoin`, `KnnJoinEarlyRewrite`
and query-side pushdown are not covered and wait for §8.

**What execution under a foreign join requires.** §6.5 in full: the extension
executes Sail's children through a default runtime, and `SpatialJoinExec` itself
gets a default memory pool and default options, so it does not spill and does not
see the session's settings. The join is accepted in v1 only where its children are
`ShuffleReadExec` or local files and its own budget is declared as independent; it
does not claim ordinary Sail resource semantics until fidelity is provided.

**Rules in Sail's pipeline that will walk over the opaque node** and treat it
generically (the first two are DataFusion's, the last two Sail's):
`EnsureRequirements` (which now sees the adapter's declared requirements rather
than defaults), the post-optimization `FilterPushdown` (`lib.rs:71`),
`RewriteCollectLeftHashJoin` and `EnforceBarrierPartitioning` (`:73-74`).

Physical optimizer rules as extension components are deferred: neither reference
extension ships one, and the only rule in this design is Sail's.

### 7.8 Spark Connect plugins (increment E; C5.2)

Spark Connect carries opaque `google.protobuf.Any` extension messages for relations,
expressions and commands; GraphFrames asked for that route (Discussion
[#2002](https://github.com/lakehq/sail/discussions/2002),
[#1062](https://github.com/lakehq/sail/issues/1062#issuecomment-3557419148)); Sail
rejects such messages today (`crates/sail-spark-connect/src/proto/plan.rs:1339`).
Neither reference extension needs it. linhr placed the work in the resolver: "I
guess the extension would fit into this process, and the core logic to mimic
GraphFrames would be in the second step (plan resolver)"
([#2002](https://github.com/lakehq/sail/discussions/2002#discussioncomment-17083597)).
When it is specified, it is a function from an `Any` message to a logical plan,
seated in the resolver, with its own ABI; it is not a reserved tag in v1. C5.2's
answer: a second entry point into the same extension, not a second extension system.

### 7.9 The session mutator (C2, C7)

Nothing here registers through `ServerSessionMutator`; Sail discovers, binds and
registers extensions itself, in server and worker factories. Nutmeg moves from the
mutator to a manifest and stops compiling against Sail's crates.

## 8. Boundaries of the first release

- **Logical plan transformation is out.** The FFI cannot carry it, and nobody has
  proposed that it should; SedonaDB's C structs, which its maintainer vaguely plans
  to propose upstream, cover kernels, plans and expressions, not logical nodes.
  Making `ExtensionPhysicalPlanner` return `Ok(None)` for unknown nodes
  (`crates/sail-session/src/planner.rs:540`, the prerequisite #2001's author named)
  is worthwhile composability work; it does not make foreign logical nodes
  representable and is not counted as doing so.
- **DataFusion coupling stays** (§7.1), and v1 pins an exact FFI build.
- **Options.** `SET k=v` already reaches a registered `ConfigExtension` through
  DataFusion (`crates/sail-plan/src/resolver/command/variable.rs:20-22` →
  `execute_logical_plan` → `ConfigOptions::set`, `datafusion-common-55.1.0/src/config.rs:2018-2056`),
  and an unregistered prefix is routed to `FFI_ExtensionOptions` when the
  `datafusion_ffi` namespace is present (`:2044-2052`), so `SET sedona.x` reaches an
  extension's options once the manifest registers them; the snapshot rule in §6.2
  says which queries see it. `spark.conf.set` does not: it stays in a Spark-side
  string map (`sail-spark-connect/src/config.rs:145-151`). What blocks Sedona is on
  its side: kernels read options baked at export (§4.1), not per call (§9).
- **File formats cross as table providers**, not `FileFormat`; Sail's parquet reader
  gains no GeoParquet handling, and SedonaDB's parquet replacement and dynamic
  object-store catalog are not integrated by anything here.
- **Generic catalogs are out** until a bridge into Sail's catalog model is specified.
- **Object stores and the host runtime do not cross**; §6.5 governs what is accepted.
- **Panics abort.** Extensions catch their own.
- **Type mapping is not extensible**, and the geometry mapping accepts three CRSs.
- **Sedona's client geometry UDT is not emitted by Sail** (§2).
- **Zero-copy across the FFI is not zero-copy across the shuffle.** No universal
  speed claim follows from the FFI's buffer sharing.

## 9. Open questions

1. **Aggregates from SedonaDB** need an FFI export on their side; Sail's aggregate
   path is qualified by the §2 fixture regardless.
2. **Options per call.** Sedona kernels must read `SedonaOptions` from the call's
   `ConfigOptions` through `local_or_ffi_extension` rather than bake them at export.
3. **Version independence.** This design gives up what SedonaDB's C ABI has. If the
   maintainers weigh that above C1's FFI basis, the manifest could carry SedonaDB's
   structs instead of `datafusion-ffi`'s; that is a different proposal.
4. **Mutation protocol beyond at-most-once** (§6.7): whether Sail's prepare/commit
   pattern for lakehouse commits is the right shape for an extension's writes.
5. **Version alignment for §2.** SedonaDB is on DataFusion 54.1.0, Sail on 55.1.0.

## 10. Check against the constraints, with the case against

| | Met by | Strongest case against |
| --- | --- | --- |
| C1 | every component is a `datafusion-ffi` object; the manifest is the only Sail ABI | independence holds only within a pinned DataFusion build |
| C2 | nothing registers through the mutator | the reference extension uses the mutator today (§4.2) |
| C3, C8 | Python packages, entry points, capsules, no `dlopen` | the `unsafe` surface is the whole `datafusion-ffi` call surface |
| C4 | §2, with a pass condition that can be met and no compatibility claim | server-side results only, because of the client's UDT |
| C5.1 | two checked versions, first-field layout, an exact build pin | none found |
| C5.2 | a defined seat in the resolver, its ABI deferred | not built in the first release |
| C5.3 | the join hook has a fixed position; claimant precedence is by registration order | logical ordering is deferred with the logical layer |
| C6 | the FFI is used for plan transformation and for one leaf source | the leaf source is justified by residency, which no maintainer has endorsed (§4.3) |
| C7 | Sail stays a Python-distributed server | the reference extension compiles against Sail's crates today; this is how it stops |

## 11. Increments, each with the evidence that ends it

| | Deliverable | Evidence that ends it |
| --- | --- | --- |
| **A** | §2: scalar capsule registration, exact build pin, the precedence matrix, the aggregate and window fixture | exact results through Spark Connect; separate wheels; the codec path in `local-cluster`; a separate-process worker smoke test; no client-compatibility or performance claim |
| **B** | §7.1 to §7.5 with §6.1 to §6.5: the manifest and its support table, session binding and snapshots, ownership identity, task descriptors, the adapter carrying input requirements, the envelope, centralised placement | mismatch, lifecycle and ownership tests: two manifests from one module, a glue manifest importing another module's objects, a delegated foreign plan, a missing worker package, a version mismatch; foreign fixtures needing single-partition, sorted and co-partitioned input give exact output over uneven and empty partitions and after post-decode child replacement; memory pressure and spill exhaustion under a foreign parent produce an explicit unsupported error, never a silent default |
| **C** | Nutmeg, constrained: session-scoped store, streaming read, the narrow format adapter, driver placement, at-most-once writes with indeterminate outcomes | a four-partition write stages every row; fault injected after mutation and before acknowledgement gives the specified outcome and count; concurrent append and overwrite; a refused write leaves the previous graph intact; cancellation through the Spark client during computation, on a full channel, under `LIMIT`, on expiry and driver shutdown, with kernel termination and accounting release observed; two sessions using one graph name see their own data; in `local-cluster` and with a separately started worker |
| **D** | the join ABI, a codec for `SpatialJoinExec` on the Sedona side, options per call, declared requirements and build reuse | differential tests against an unoptimised oracle over nulls, empty inputs, duplicate matches, reordered and projected columns, a spatial predicate with a residual; several probe tasks and unequal build and probe partition counts; both shuffle production and per-task materialisation recorded; resource and object-store gates; unsupported shapes decline without changing results |
| **E** | generic catalogs and formats, physical rule components, logical transformation, Connect plugins, type mapping, the Sedona client UDT | each with its own representable contract and tests |

Every test receipt names the Sail, DataFusion, extension and client revisions, the
wheel and build identities, the execution mode and process layout, the effective
options and the input partition counts, and keeps unsupported, mismatch, timeout,
refusal and error outcomes separate from passes. `EXPLAIN` and diagnostics expose
extension identity and version, configuration identity, owner, placement, stage and
attempt, and codec identity; Sail's tracing wrapper walks the physical tree
(`crates/sail-telemetry/src/execution/physical_plan.rs:60`), and the adapter must not
hide operators from it.

## 12. What is asked of others

- **SedonaDB:** a DataFusion 55 build for §2; an aggregate export over the FFI;
  options read per call; eventually a codec for `SpatialJoinExec`.
- **DataFusion:** nothing for A; for B and D, host-runtime sharing across the FFI
  ([#24733](https://github.com/apache/datafusion/pull/24733) or equivalent) is what
  lifts the restrictions in §6.5; E waits on logical nodes crossing the FFI.
- **Sail:** for A, one resolver lookup and a `pysail` registration call; for B, the
  five closed places reopened, the resolver, the worker factory, the codec, the
  placement list and the physical planner's error, plus the adapter, the descriptor
  and the session binding that make what they admit correct.
- **Nutmeg:** a Rust `cdylib` Python package (today `python/nutmeg` is pure Python
  and no crate exposes a module); a `PhysicalExtensionCodec` for its nodes (none
  exists); a session-scoped store; an at-most-once write policy with reported
  indeterminate outcomes; a pinned graph revision for reads; and acceptance of the
  driver cost in §7.5.
