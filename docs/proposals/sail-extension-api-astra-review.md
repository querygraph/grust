# Sail extension API — Astra architecture review

## Verdict

Proceed with the small, explicitly experimental scalar-UDF proof of concept. Do not freeze the proposed manifest or describe Stages 1–2 as production-ready yet. The direction—Python packaging, DataFusion FFI, Sail-owned registration and distributed integration—is sound. The missing contracts are execution semantics, not just more registration hooks.

The most important changes are:

1. Preserve physical input requirements and host execution resources, or reject plans that need them.
2. Define session instances, stable component ownership, worker compatibility and configuration snapshots before implementing stateful extensions.
3. Specify retry/commit semantics for Nutmeg writes and end-to-end cancellation for reads.
4. Make the join and data-source contracts concrete; neither is completely represented by the proposed manifest.
5. Qualify the design in separate worker processes, not only `local-cluster`.

This is a source-level design review, not an implementation verdict. Failure scenarios below are deductions from the inspected contracts unless explicitly described as source observations. No extension prototype, cluster deployment, benchmark or Rust test suite was run.

## Baselines and scope

The [proposal](sail-extension-api.md) was reviewed at Grust `4966548db3bca4ec593ba4bb2434116dfb0ee536`; its SHA-256 was `c8618d29e358e6d7e88a16c59affd7d15dbc637ca40113e10a5ec346cd8546de`.

| Source | Reviewed baseline | How it was used |
| --- | --- | --- |
| Local `~/src/sail` | `lakecat`, `9f6f8065dd810be8146995876acf872ea803adf0`; DataFusion 54 / Arrow 58 | Local architectural context and LakeCat/catalog-lifecycle notes; not mistaken for the proposal's target |
| Proposal's Sail target | `51b57bc2e3611aebcb6112ffa5470bd56fe25d04`; DataFusion 55.1.0 / Arrow 59.2.0 | Source snapshot from the local repository's Git objects; authoritative for Sail findings below |
| DataFusion | Published `datafusion-ffi` and `datafusion-physical-plan` 55.1.0 crate sources | Actual boundary implementation, not an assumption about the Rust traits |
| Nutmeg | `96816e511f70ba725084c6bc9d66af97f8dfcaaa`, the proposal's streaming-read pin | Staging, registry, physical execution, accounting and cancellation |
| Local Nutmeg | `3e2c640af5f46b327ea186d81fd5f16f4090ccc5` | Kept separate from the newer proposal pin |
| Grust requirements | Above Grust revision; [Arrow requirements](../goals/arrow-performance-parity.md) and [kernel design rules](../goals/graph-analytics-catalog.md#design-rules) | Buffer ownership, admission, semantics, determinism and recovery requirements |
| [Sail Rust Book](https://firstpair.org/read/sail-rust-book/) | Live published edition, consulted during this review | Architectural orientation and extension chapter; source pins take precedence |

Repository remotes were fetched before review. Existing uncommitted Sail notes/output and Nutmeg's lockfile were left untouched. Sedona-specific function counts, kernel implementations and Apache Sedona client compatibility are taken from the proposal's pinned survey, not independently certified by this review. The review independently checks the Sail/DataFusion contracts that the proposed Sedona integration would have to satisfy.

The architectural survey covers the query path end to end: front ends/spec conversion, resolution, session/catalog/data-source construction, logical and physical planning, physical optimization, job graphs, scheduling/retries, codecs, task preparation, shuffle, worker construction, runtime resources, execution telemetry and Spark operation lifetime. It is not a line-by-line audit of every SQL function, storage format or lakehouse implementation.

## Architectural fit

Sail is not a DataFusion `SessionContext` with a different network endpoint. It supplies substantial semantics both before DataFusion planning and after DataFusion optimization. An extension must remain correct through those layers.

| Layer | Actual responsibility / evidence | Consequence for the proposal |
| --- | --- | --- |
| SQL and Spark Connect | Sail spec and resolver construct logical plans; Spark operations have their own execution/release lifecycle | Registering a DataFusion object does not automatically expose the corresponding Spark behavior |
| Server sessions | `ServerSessionFactory` installs Sail registries, custom planner/rules, runtime, activity and job services; it deliberately does not install DataFusion default catalogs/features [S1] | Discovery must feed specific Sail adapters, with per-session ownership |
| Catalogs and data sources | Named tables go through Sail `CatalogManager`; format reads/writes go through `DataSourceRegistry` [S2] | DataFusion catalog registration and table factories are not drop-in replacements |
| Logical/physical planning | Sail-owned extension nodes are lowered by its planner; its physical optimizer has explicit pre/post requirement-enforcement phases [S3] | Keeping the existing planner and making unknown-node handling composable is appropriate |
| Job graph | Physical trees become stages with partition usage, barriers, subqueries and placement [S4] | An opaque physical node needs scheduling metadata as well as an execute callback |
| Task execution | Both driver and worker tasks decode plans, rewrite scans/shuffles, add tracing and then execute [S5] | Driver placement does not eliminate codecs, child replacement or runtime reconstruction |
| Runtime/storage | Sail configures object-store registry, memory pool, disk policy and caches [S6] | Replacing the runtime with a default is a change to the execution contract |
| Worker deployment | Local-cluster uses worker actors in the same process; Kubernetes workers start separately [S7] | Both modes are useful tests, but they prove different properties |
| Reliability and observability | Scheduler retries task regions; Spark supports interruption and reattachment; tracing walks the physical tree [S8, S9] | Side effects, cancellation, buffer lifetime and operator identity must survive all these layers |

The book's extension chapter is particularly useful on collision policy, versioned codec payloads and driver/worker symmetry. Its example Rust traits are design sketches, not an alternative stable ABI. The proposal is right to follow the maintainers' FFI direction instead of exporting Rust trait objects. [Book](https://firstpair.org/read/sail-rust-book/), [maintainer discussion](https://github.com/lakehq/sail/discussions/2001#discussioncomment-17083578).

## Findings

Severity: **P1** means resolve before the affected capability is accepted as supported; **P2** means an important contract, qualification or scope correction. These are findings against a draft, not claims of deployed vulnerabilities.

### F1 — P1: Missing input requirements can change answers, not merely add repartitions

**Proposal:** §6.6 characterizes the opaque-plan losses as possible redundant repartitioning and not fatal; §6.7 separately recognizes partition loss in a sink.

**Observed:** `ForeignExecutionPlan` does not forward input distribution or ordering requirements. DataFusion 55's defaults are unspecified distribution and no required ordering. Its newer `input_distribution_requirements()` also supports relationships between children; merely copying the deprecated method would not cover the entire interface. FFI plan properties describe outputs and reconstruct only limited equivalence information. [D1, D2]

**Consequence:** a host optimizer cannot enforce requirements it cannot see. A foreign operator requiring one partition, sorted input or co-partitioned inputs can receive incompatible children. The proposal's `DataSinkExec` example is already a concrete instance of this category. Losing equivalences conservatively can cost optimization; losing required input properties can cost correctness. Those must not be grouped together.

**Required revision:** either extend the FFI with the necessary physical contract or introduce a Sail-owned adapter that explicitly carries and validates that contract. For an initial restricted API, accept only documented execution shapes and reject others. Preserve the metadata through child replacement, optimizer passes, encoding/decoding and task preparation. `build_side` and a blanket sink coalesce are not a general replacement.

**Gate:** independently built foreign fixtures requiring single-partition, sorted and co-partitioned input; verify exact output over uneven partitions, empty partitions and post-decode child replacement. Assert final physical requirements, not just the presence of a coalesce before insertion.

### F2 — P1: Runtime fidelity is a Stage 1/2 prerequisite, not a Stage 3 enhancement

**Proposal:** §§5 and 6.6 correctly identify `RuntimeEnv::default()`, but §6.6 calls shuffle/local-file cases safe and §11 asks DataFusion for nothing through Stage 2.

**Observed:** cross-library `FFI_TaskContext` conversion creates a new default runtime; conversion of session config also falls back to defaults on error. Sail's runtime contains configured memory and temporary-disk limits, object-store resolution and caches. [D3, S6]

**Consequence:** a local file being readable does not establish that a join or its child subtree respects the configured resource envelope. A shuffle source needing little context does not repair the foreign join's own memory/spill policy. Crossing back into Sail children can reconstruct another default context; returning an execution-plan handle to its originating library does not by itself return the original task context. Nutmeg's separate admission accounting helps its kernels, not every Sail operator or transfer buffer around them.

**Required revision:** make host-resource fidelity an explicit gate for general foreign plans and spatial joins. A restricted experiment can proceed with disclosed independent extension budgets, constrained children and fail-closed capability checks; it must not claim ordinary Sail resource semantics. Treat object stores, memory, temporary disk and typed session services as separate capabilities. A runtime bridge need not restore every typed extension.

DataFusion [PR #24733](https://github.com/apache/datafusion/pull/24733) was still open when checked; its head was `f509f500641ad1e81f3b21ad6f8007fae3d8dd10`. It is a candidate dependency, not evidence that 55.1.0 already satisfies this gate.

**Gate:** force memory pressure and configured spill exhaustion, exercise a registered non-default object store, and invoke a Sail child requiring a typed extension through a foreign parent. Require an explicit unsupported error where fidelity is unavailable; no silent defaulting.

### F3 — P1: Discovery is not a session lifecycle or configuration protocol

**Proposal:** §§6.2, 6.4 and 8 suggest globally discovered objects, worker registration and per-session enablement. Nutmeg is separately told to scope its graph store to a session.

**Observed:** the manifest supplies component objects and one manifest release callback, but no defined session-instantiation/closure contract. Sail supplies `ServerSessionInfo` including session and user identity, while `WorkerSessionFactory` takes `()` and constructs its own default DataFusion config. Nutmeg's store is process-global, and its read selector currently uses a typed session extension. [S1, S7, N1]

**Consequence:** scoping Nutmeg state is rightly Nutmeg's job, but Sail must provide a stable, scoped identity and lifetime on which that implementation can rely. A DataFusion task/session ID must not be assumed to equal the Spark session identity. Rediscovering identical packages also does not propagate per-session enablement, `SET` values, exported-UDF options or subsequent configuration changes.

**Required revision:** distinguish process discovery from session binding and query execution. Specify either a session factory or an equivalent ownership protocol: trusted host-issued session identity, session incarnation, explicit close/expiry behavior, per-session component handles, and configuration snapshots carried to task decoding/execution. Decide whether an already planned query keeps its option snapshot after a concurrent `SET`. Document ephemeral graph behavior across expiry, reconnection and driver restart.

A useful correction to §6.5: the foreign codec's captured context is **not wholly immutable in 55.1.0**. `FFI_PhysicalExtensionCodec::new` explicitly rebinds an imported codec to the supplied task-context provider; the crate contains a regression test for it. Use that supported mechanism for per-session binding rather than accepting exporter context as unavoidable. It does not solve F2. [D4]

**Gate:** two simultaneous sessions use the same graph name with different data/options; expiry closes only the appropriate state; an old decoded plan cannot attach to a recreated session; driver and worker report the same effective query options.

### F4 — P1: A library marker is not an unambiguous extension owner

**Proposal:** §6.5 derives physical-plan ownership from a marker→extension map, while explicitly allowing two extensions from one library and components supplied by other libraries.

**Observed:** DataFusion's marker is the address of a library-local static, intended to recognize objects returning to their own library. It identifies a library instance, not a manifest, codec, session or component. [D5]

**Consequence:** two manifests using one provider/codec library can claim the same marker but require different codecs or placement. A provider may also return plans manufactured by another library. Discovering markers on the originally listed objects does not establish ownership of every returned plan. A marker map cannot select the right owner in those cases; using registration order would silently reintroduce order dependence.

**Required revision:** attach an explicit extension/component identity to plan-producing boundaries and preserve it in Sail-owned wrappers and wire envelopes. Specify mixed-owner child handling and ownership after a join replacement or provider call. Alternatively, make unique producer-library ownership a restrictive v1 rule and reject conflicting markers at load time; remove the contradictory composition promise. Keep library markers as an FFI identity optimization, never as wire identity.

**Gate:** two manifests from one native module, one glue manifest importing another module's objects, and a producer returning a delegated foreign plan. Placement and codec choice must be deterministic or rejected explicitly.

### F5 — P1: Placement and wire compatibility must cover functions as well as physical nodes

**Proposal:** placement is per extension; only foreign physical-node ownership is consulted by the scheduler; unknown UDFs can serialize as an empty buffer and re-resolve by name. The custom-plan envelope carries extension name and bytes.

**Observed:** the job graph traverses execution plans. A foreign scalar can live inside a normal Sail/DataFusion projection or filter, with no foreign plan at the root. The proposal deliberately does not register `DriverOnly` extensions on workers. Driver-stage recognition is also used in barrier/root-preservation paths, not just the main placement downcast chain. [S4]

**Consequence:** a permitted `DriverOnly` UDF can resolve successfully but reach a worker inside a native node and fail there. Meanwhile, name-only reconstruction of an `AnyWorker` UDF can select a different implementation/configuration on a worker. Checking DataFusion major at package loading does not establish extension wire-payload compatibility or semantic agreement across a rolling deployment.

**Required revision:** for v1, either prohibit driver-only scalar/aggregate/window functions or analyze their ownership and force/reject appropriate enclosing plans. Centralize placement classification across ordinary nodes, cooperative wrappers, barriers and subqueries. Define a required-extension descriptor for every task, including function-only tasks: extension/component identity, wire format version, supported ABI/capabilities and effective configuration identity. Validate before scheduling or decoding. Exact package equality is a reasonable initial policy; broader compatibility can be declared later.

**Gate:** a driver-only scalar under a normal projection; the same node beneath a barrier; a missing worker package; equal function names from mismatched package versions; an incompatible codec payload. Fail before execution with the required and actual identities.

### F6 — P1: Nutmeg writes need an explicit retry/commit contract

**Proposal:** §6.7 maps append/overwrite to `insert_into`; Stage 1 checks partition completeness but not replay.

**Observed:** Sail retries task regions, canceling other attempts in a failed region. Nutmeg's `StageWriter::write_all` stages batches and commits via `finish()`. For append, `swap_into` retains existing rows and appends the new batches; it increments the graph revision. The writer ignores the task context and carries no operation/attempt deduplication key. [S8, N2]

**Inferred failure scenario:** the driver-side write commits, but a downstream task or acknowledgement fails before the region is considered complete. If the write is retried, append can apply again. Overwrite is not automatically safe either when concurrent writes or read-visible revisions matter. This scenario was not fault-injected; the source establishes the missing contract, not a reproduced duplicate write.

**Required revision:** define mutation execution separately from residency. Choose an initial at-most-once/no-retry policy with explicit indeterminate outcomes, or a transaction/idempotency protocol keyed by session incarnation and logical operation identity. If adopting Sail's prepare/commit pattern, specify the commit boundary rather than assuming driver placement provides it. Pin the graph revision for retried reads, or explicitly disclose when retries can observe a new snapshot.

**Gate:** inject failure after graph mutation but before task/operation acknowledgement; verify final rows, revision, returned count and retry outcome. Also test a refused/canceled write, concurrent append/overwrite and read-versus-update behavior. Admission failure must leave the previous graph intact.

### F7 — P1: The spatial join request omits information needed to preserve SQL semantics

**Proposal:** §6.6 sends join type, a protobuf condition and child plans; a declared function name triggers an offer to the extension, which returns a plan and build side.

**Observed:** a DataFusion physical `JoinFilter` includes the expression, an intermediate schema and a side/index map. Its expression's column indices are not simply indices into concatenated original children. [D6] Sail's scheduling additionally distinguishes reusable build input from single-consumption input. [S4]

**Consequence:** serializing only the expression is ambiguous without a specified normalization/remapping contract. A recognized spatial predicate inside a larger condition does not authorize dropping residual predicates or moving them outside an outer join. Projected/reordered inputs and duplicate column names make name-based reconstruction unsafe. Function-name claims also need to respect the resolver's actual selected implementation.

**Required revision:** define a versioned join request/response ABI with child schemas, filter schema and side/index mapping (or a canonical equivalent), projection/output schema, supported join kinds, residual predicate semantics and refusal behavior. Bind predicate claims to registered component identity. Validate the returned schema, child arity, partitioning and output contract. Define deterministic selection or reject overlap when multiple extensions claim one join.

Start with inner joins and a narrow predicate grammar; reject unsupported outer/semi/anti/KNN forms without changing their results. Carry build-side reuse metadata through F1's adapter and wire codec. Reusable shuffle means multiple consumers may read a produced build stream; it is not proof that all tasks share one in-memory spatial index.

**Gate:** compare against an unoptimized exact oracle for nulls, empty inputs, duplicate matches, swapped/reordered/projected columns and a spatial predicate combined with a residual predicate. Exercise multiple probe tasks and unequal build/probe partition counts. Record both shuffle production and per-task build materialization.

### F8 — P1: The manifest does not yet define the ABI it claims to define

**Proposal:** §6.1 says every component is an existing DataFusion FFI object and the manifest is the only new ABI. It lists `JoinExtension` and `ConnectPlugin`, but §6.7 needs a table-provider factory.

**Observed:** DataFusion's existing objects do not implement the proposed Sail join callback or a Spark `Any`→logical-plan callback. `TableProvider` and `TableProviderFactory` are distinct FFI types; the latter is absent from the kind list. The manifest sketch leaves object ownership, clone/release relationships, pointer validity and callback lifetime unspecified.

**Consequence:** two implementers cannot independently construct compatible extensions from this definition. A first-field version check helps reject known valid manifests with unsupported layouts; it does not validate arbitrary pointers, prove that a glue package's components match its declared DataFusion version, or establish same-major compatibility for every FFI/protobuf combination.

**Required revision:** publish a deliberately small v1 support table: component tag, exact payload type, ownership transfer, lifetime, thread safety, callback/error behavior and supported build tuple. Add a distinct factory kind. Remove unsupported kinds from v1 rather than assigning them undefined payloads. Specify the join ABI separately when it exists. Use an explicitly laid-out bootstrap header/tags with defined unknown-value handling and extension-size/capability negotiation, or document an exact-layout rejection policy. Retain the module/capsule owner until all callbacks, streams and buffers are released.

Pin and test the initial DataFusion FFI minor/patch/build combination; do not promise compatibility throughout a major merely because `version()` reports only the major. Make the same safety check explicit in the no-new-manifest PoC. Installed native packages are trusted in-process code, not sandboxed plugins; per-session disablement is not a security boundary.

**Gate:** independently built wheels, incorrect capsule name, unsupported manifest/tag/version, missing required component, duplicate registration, partial load failure and balanced release after shutdown with outstanding Arrow output. Invalid layouts must be rejected through a valid bootstrap, not probed by dereferencing incompatible component structs.

### F9 — P2: Catalog and format integration are underspecified and should be narrowed

**Proposal:** catalog providers are supported manifest objects; §6.7 maps format reads to `CreateExternalTable` with paths as `location` and an empty schema for inference.

**Observed:** Sail deliberately manages its own catalogs. Its named-table resolver asks `CatalogManager`, not the DataFusion catalog registry. `SourceInfo` includes multiple paths, optional schema, constraints, partition/bucket/sort metadata, layered options and case sensitivity. `SinkInfo` likewise carries input and write metadata. A `CreateExternalTable.location` string cannot directly represent arbitrary path lists. [S1, S2]

**Consequence:** a successfully imported DataFusion catalog may still be invisible to Spark SQL. A generic factory adapter can lose requested schema or write semantics. A convention used by `ListingTableFactory` is not a universal obligation of every foreign factory. These are gaps even before supporting transactions, DDL and lakehouse commits.

There is also a distributed scan invariant to preserve: task preparation rewrites native file scans to disable process-local sibling work sharing, because independently deserialized tasks must not each scan every file. A provider-created scan that remains an opaque foreign node will not match that native downcast. It therefore needs an equivalent partition contract; local-file accessibility alone does not prove safe distributed scanning. This is a source-derived risk, not a reproduced duplicate scan. [S5]

**Required revision:** defer generic catalog support or specify an explicit bridge into Sail's catalog model. For Nutmeg, define a narrow format adapter with an allowed option/schema/mode contract and reject unsupported paths, partitioning, bucketing and sorting rather than discard them. Specify option precedence/case handling and propagate the write input schema. Distinguish scan pushdown semantics from factory creation and preserve provider filter exactness/projection/limit contracts.

Do not imply that a factory adapter makes Sedona's Parquet replacement or dynamic object-store catalog integrate with Sail's lakehouse/catalog machinery. Those need their own capability decisions. The existing local catalog-lifecycle notes are relevant design context, but their older observations are not asserted as current upstream bugs here.

**Gate:** explicit read schema, zero/one/multiple paths, unknown/conflicting options, empty writes, append/overwrite and rejected modes; SQL lookup of any claimed catalog; multi-file, multi-task scans return each expected row exactly once. Unsupported metadata must produce a named error.

### F10 — P2: Local-cluster and stream-drop tests are necessary but insufficient qualification

**Proposal:** the distributed pass conditions use `local-cluster`; cancellation is framed as dropping a read stream across the FFI.

**Observed:** `LocalWorkerManager` spawns worker actors in the same process with a cloned worker context. This exercises Sail's codec/staging machinery but not independently installed worker packages or process-global separation. Nutmeg stream drop signals cooperative cancellation to a detached kernel thread, which retains its resources until it exits. Spark execution separately distinguishes interrupt/release from reattachment. [S7, S9, N3]

**Required revision:** keep local-cluster as a fast gate, then add separate-process workers with independently initialized Python/native modules. Test Spark cancellation through the actual client operation, not only by releasing a Rust stream. A transient disconnect for a reattachable query is not the same action as cancellation.

Test interruption during computation and while blocked on a full output channel; `LIMIT`/early consumer stop; session expiry; driver shutdown; and task-region cancellation. Observe kernel termination and accounting release, not merely receipt of a cancel request. Also hold exported Arrow batches past stream drop: buffer ownership/admission must remain valid until the last consumer releases them. Do not equate FFI zero-copy eligibility with end-to-end zero-copy through the network shuffle.

### F11 — P2: Resolver precedence is contradictory, and aggregate qualification need not wait for Sedona

**Proposal:** §§2 and 6.3 insert session functions before built-ins, then §6.3 says built-ins retain precedence and §8 makes overriding opt-in. It also calls aggregate integration untestable until Sedona exports aggregates.

**Observed:** Sail has distinct scalar, aggregate and window construction paths. Existing catalog resolution is not a uniform DataFusion registry lookup. [S10]

**Required revision:** specify one precedence/collision matrix and enforce it during registration and resolution, including aliases, normalization and namespace qualification. Define how a non-overridden built-in remains reachable and how existing Spark user-defined-function precedence is retained. Ensure workers reconstruct exactly the implementation chosen by the driver, not merely something with the same name.

A tiny independently compiled FFI fixture can test aggregate `DISTINCT`, `FILTER`, `ORDER BY`, null handling and partial/final aggregation now; a similar fixture can cover windows and table functions. Sedona's export is needed for Sedona integration, not for qualifying Sail's registry plumbing. This also keeps the first PR's correctness tests independent of a large external project's release schedule.

## Revised delivery sequence

| Increment | Deliverable | Required evidence / stop condition |
| --- | --- | --- |
| A — experimental functions | Scalar capsule registration, explicit build pin, coherent collision policy; tiny fixture plus the proposed Sedona server-side queries | Exact results through Spark Connect; separate wheels; local-cluster codec path; separate-process worker smoke test; no geometry-client compatibility or performance claim |
| B — extension foundation | Minimal versioned manifest, process/session separation, component ownership, task dependency descriptors, registry-aware codec at every encode/decode site | Mismatch and lifecycle tests; no arbitrary foreign physical plans until their requirements and resource policy are explicit |
| C — constrained Nutmeg | Session-scoped graph state; streaming read; narrow staging adapter; driver placement; replay policy | Complete multipart input, snapshot semantics, fault-injected write outcome, end-to-end cancellation and admission/buffer-lifetime tests in local and real cluster execution |
| D — constrained spatial join | Separately specified join ABI; codec; physical requirements; build reuse; effective options; qualified runtime support | Exact differential join tests, resource/spill/object-store gates and multi-worker execution; unsupported shapes decline safely |
| E — expansion | Generic catalogs/formats, richer physical rules, logical transformation and Connect plugins | Each obtains its own representable contract and tests; a reserved enum value is not an implementation |

Changing Sail's extension planner to return `Ok(None)` for unknown logical nodes is worthwhile composability work. It does not make foreign logical nodes representable, and it should not be counted as solving that ABI problem. Likewise, choose a fixed join-rule position initially, but define precedence between multiple claimants rather than relying on Python entry-point enumeration.

## Acceptance evidence to retain

Every test receipt should name the Sail, DataFusion, extension and client revisions; exact wheel/build identities; execution mode and process layout; effective options; and input partition counts. Retain unsupported, mismatch, timeout, refusal and error outcomes separately from successful results.

For Grust/Nutmeg, verify the existing requirements rather than introduce an extension-specific weaker contract:

- Exact graph rows, multiplicity, isolates, orientation, weights and deterministic outputs under the declared algorithm semantics.
- Admission before allocation where required; bounded work/cancellation latency; no retained scratch after termination; honest accounting for retained Arrow buffers.
- Clear projection/snapshot/revision ownership and transactional staging behavior under error, retry and concurrency.
- End-to-end measurement boundaries covering planning, staging/transfer, projection, kernel work and result consumption. Report copies and materialization at each boundary; make no universal speed claim.

Expose extension identity/version, effective configuration identity, owner, placement, stage/attempt and codec identity in diagnostics or `EXPLAIN`. Sail already wraps execution trees for tracing; check that ownership wrappers and foreign child replacement preserve observability without hiding operators. [S5, S9]

## Bottom line

Keep the small UDF experiment and the FFI/Python distribution choice. Revise the claim that five closed integration points are the remaining problem: opening those points admits objects, but does not establish that their execution remains correct.

The production boundary must cover **who owns an object, which session/query it belongs to, where it may run, what its children must provide, which resources it uses, how another process reconstructs it, and what happens on cancellation or retry**. A restricted first release can answer those questions for a few capabilities without designing a universal extension system. That is the strongest route to an upstreamable API and a dependable Nutmeg integration.

## Source anchors

Sail links below are pinned to the proposal's target, not the older local LakeCat checkout. DataFusion links name the published 55.1.0 source. Nutmeg links name the proposal's streaming-read revision. Line anchors identify the entry point; the associated implementation was read beyond that line where needed.

- **S1 — session composition:** [server factory](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-session/src/session_factory/server.rs#L31), [session-manager API](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-session/src/session_manager/mod.rs#L50).
- **S2 — catalog/source routing:** [named-table resolver](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-plan/src/resolver/query/read.rs#L30), [source/sink contracts](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-common-datafusion/src/datasource.rs#L221).
- **S3 — planning phases:** [physical optimizers](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-physical-optimizer/src/lib.rs#L48), [extension planner](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-session/src/planner.rs#L540).
- **S4 — job-graph semantics:** [child partition usage](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-execution/src/job_graph/planner.rs#L254), [driver classification](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-execution/src/job_graph/planner.rs#L606), [driver-stage creation](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-execution/src/job_graph/planner.rs#L881).
- **S5 — execution round trip:** [task preparation](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-execution/src/task_runner/preparation.rs#L51), [driver task dispatch](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-execution/src/driver/actor/handler.rs#L607), [physical codec](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-execution/src/proto/codec.rs#L1825).
- **S6 — host resources:** [runtime factory](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-session/src/runtime.rs#L42).
- **S7 — worker environments:** [worker session factory](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-session/src/session_factory/worker.rs#L34), [local worker manager](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-execution/src/worker_manager/local.rs#L22), [job-runner construction](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-session/src/session_factory/job_runner.rs#L99).
- **S8 — retries:** [scheduler task-region policy](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-execution/src/driver/job_scheduler/core.rs#L155).
- **S9 — operation lifetime and telemetry:** [interrupt/reattach/release](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-spark-connect/src/service/plan_executor.rs#L566), [executor pause](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-spark-connect/src/executor.rs#L359), [tracing traversal](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-telemetry/src/execution/physical_plan.rs#L60).
- **S10 — function paths:** [scalar/aggregate resolver](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-plan/src/resolver/expression/function.rs#L74), [window resolver](https://github.com/lakehq/sail/blob/51b57bc2e3611aebcb6112ffa5470bd56fe25d04/crates/sail-plan/src/resolver/expression/window.rs#L31).
- **D1 — foreign plan surface:** [`execution_plan.rs`](https://docs.rs/crate/datafusion-ffi/55.1.0/source/src/execution_plan.rs), especially the FFI struct and `impl ExecutionPlan for ForeignExecutionPlan` at line 449.
- **D2 — required versus output properties:** [physical-plan trait](https://docs.rs/crate/datafusion-physical-plan/55.1.0/source/src/execution_plan.rs), lines 188–223; [FFI output properties](https://docs.rs/crate/datafusion-ffi/55.1.0/source/src/plan_properties.rs), lines 160–190.
- **D3 — task context reconstruction:** [`task_ctx.rs`](https://docs.rs/crate/datafusion-ffi/55.1.0/source/src/execution/task_ctx.rs), lines 193–242.
- **D4 — codec rebinding:** [`physical_extension_codec.rs`](https://docs.rs/crate/datafusion-ffi/55.1.0/source/src/proto/physical_extension_codec.rs), constructor at line 280 and `ffi_physical_extension_codec_rebind_adopts_task_ctx_provider` at line 731.
- **D5 — marker semantics:** [`lib.rs`](https://docs.rs/crate/datafusion-ffi/55.1.0/source/src/lib.rs), lines 64–88.
- **D6 — physical join filter:** [`join_filter.rs`](https://docs.rs/crate/datafusion-physical-plan/55.1.0/source/src/joins/join_filter.rs), lines 27–34 and accessors at lines 78–91.
- **N1 — state:** [Nutmeg global store](https://github.com/querygraph/nutmeg/blob/96816e511f70ba725084c6bc9d66af97f8dfcaaa/crates/nutmeg-graph/src/lib.rs#L1109), [read execution selection](https://github.com/querygraph/nutmeg/blob/96816e511f70ba725084c6bc9d66af97f8dfcaaa/crates/nutmeg-graph/src/lib.rs#L2648).
- **N2 — mutation:** [staging sink](https://github.com/querygraph/nutmeg/blob/96816e511f70ba725084c6bc9d66af97f8dfcaaa/crates/nutmeg-sail/src/lib.rs#L240), [finish/swap/revision](https://github.com/querygraph/nutmeg/blob/96816e511f70ba725084c6bc9d66af97f8dfcaaa/crates/nutmeg-graph/src/lib.rs#L1563).
- **N3 — streaming cancellation:** [algorithm stream and detached-thread lifetime](https://github.com/querygraph/nutmeg/blob/96816e511f70ba725084c6bc9d66af97f8dfcaaa/crates/nutmeg-graph/src/lib.rs#L2776).
