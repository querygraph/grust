# Live source control: Research findings

Sail needs to address the source partitions that are actually running before it can coordinate recoverable input boundaries. The smallest useful increment is an attempt-scoped control path that wakes a live reader, emits an ordered checkpoint marker and returns a precisely qualified acknowledgement. Capability declarations alone do not establish that path.

This report records source inspection and recommendations. I ran no builds, tests, source programs or benchmarks. The saved request, AGENTS.md, LAKESAIL.md, SHEHAB.md, CLARITY.md, WRITING-RULES.md and applicable Sail Copilot, development and Rust-review instructions were reread. No source changes, rebases, environment changes or upstream communications were made.

## Inspected versions

| Boundary | Pin |
| --- | --- |
| Detached implementation worktree | `/Users/alexy/src/sail/tmp/source-control-20261106-b6d73d6a` |
| Starting HEAD | `b6d73d6a644dc04b1e6749e171100808c874d788` |
| Merge base with fetched main | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Separately inspected upstream main | `ae21b2ef7f6a306f530fad2f3c9e603c9742dc5a` |
| DataFusion execution source | Cargo registry version `55.2.0` |
| Spark source | clean `v4.2.1`, `617618396087429b5627a86ce933bb0f5d6645cb` |

The Sail worktree had clean tracked source and untracked review logs when inspected. Local DuckDB and Polars sources were absent at the prescribed `sail/opt` locations. No claims about their implementations are made. Their optimizer techniques would not resolve this source-lifetime and command-routing boundary; no broad literature search was needed.

## Existing execution paths

Crate paths below are relative to `crates/` in the pinned Sail worktree. Shorter paths identify files inside the named crate.

| Existing component | Verified behavior and integration consequence |
| --- | --- |
| `sail-common-datafusion/src/streaming/source.rs:15–44` | `StreamSource` provides schema, filter support and planning-time `scan`. It provides no recovery descriptor or live endpoint. |
| `sail-session/src/planner.rs:452–466` | Planning calls `source.scan`, then optionally renames its result. The logical source object is not the worker reader. |
| `sail-execution/src/proto/codec.rs:1325–1371,2890–2921` | Rate and socket plans serialize options, original schema and projection. Decode constructs fresh executable plans. There is no serialized source-control address. |
| `sail-execution/src/job_runner.rs:63–81,117–139` | Local execution calls `execute_stream` directly with a session task context. Cluster execution sends the plan and task context to the driver. Local mode has no driver to receive new controls. |
| `sail-execution/src/task_runner/actor/handler.rs:57–81` | Admission deduplicates attempts, then prepares a fresh executable plan for each `TaskKey`. Shared descriptions are not shared running readers. |
| `sail-execution/src/task_runner/preparation.rs:39–89` | Preparation knows the exact job, stage, partition and attempt, decodes the plan, installs shuffle endpoints and executes the task partition. This is the cluster context-injection seam. |
| `sail-execution/src/worker/server.rs:42–89`; `worker/actor/core.rs:124` | A worker supplies its session task context to multiple admitted tasks. That shared context must not acquire mutable per-attempt state in place. |
| `sail-execution/src/task_runner/monitor.rs:40–58,144–171` | Execution and cancellation compete; termination drops the stream. Preparation also has cancellation and abandoned-result ownership in `preparation.rs:163–198`. Registrations must respect both lifetimes. |
| `sail-execution/src/id.rs:105–138`; `task_runner/registry.rs:10–77` | `TaskKey` distinguishes attempts. Admission history rejects exact repeats, canceled attempts and closed jobs. It does not identify durable sources or fence storage commits. |

`TaskAssigner` already retains task-to-placement history in `driver/task_assigner/mod.rs:24–31`; worker clients and `WorkerService` already route task-specific operations. Reuse those owners with a typed control request and reply. A historical placement lookup alone is insufficient: validate that the addressed attempt is still current and live when accepting its acknowledgement.

## Smallest coherent implementation

Put common source-control types and the endpoint registry in `sail-common-datafusion`. Both source implementations and execution already depend on it, and it already has Tokio and Futures. Keep execution-specific `TaskKey` routing in `sail-execution`, avoiding a reverse dependency.

Use a fresh context extension for each execution attempt. DataFusion's public [`TaskContext::new` and getters](https://docs.rs/datafusion-execution/55.2.0/src/datafusion_execution/task.rs.html) preserve the session ID, all four function registries and `RuntimeEnv`. Clone `SessionConfig` and attach an opaque typed extension through [`with_extension`](https://docs.rs/datafusion-execution/55.2.0/src/datafusion_execution/config.rs.html). `TaskContext` itself is not `Clone`. Rebuilding it from defaults would lose configured functions and services. These public APIs suffice; copying DataFusion implementation is not justified here.

The registry must distinguish a source occurrence within the prepared plan, source partition and execution attempt. Serialize occurrence addresses with the plan. The existing `SourceOccurrence(Arc<()>)` in `sail-logical-plan/src/streaming/source_wrapper.rs:15–43` only protects in-process logical equality. Its pointer cannot become a wire or restart identity. A runtime occurrence address also cannot substitute for the future durable source descriptor, partition incarnation or stable pipeline identity.

Register an endpoint with the running stream, reject duplicate registration, and revoke it on drop, failure, exhaustion or cancellation. An obsolete registration must not remove a replacement. Late preparation after cancellation must not publish a usable endpoint. Local execution needs the equivalent per-execution owner without introducing a driver.

Use a bounded command mailbox and a reply channel. Integrate command polling with the reader so idle sources wake without waiting for data. Serialize checkpoint requests initially. Define duplicate request handling explicitly so a lost reply cannot cause a second, different boundary under the same checkpoint identifier. Reject unsupported, unready, stale and stopped addresses explicitly.

A source produces the marker and any position receipt at the same serialized boundary. A generic wrapper can inject a marker but cannot infer a replay position from emitted row counts, especially after filtering or projection. Keep capability admission explicit: marker injection, recoverable position capture and exact replay are different contracts.

The acknowledgement proves only the specified source-side action. It does not prove that downstream operators consumed the marker, sinks committed, a checkpoint became durable or stale writers are fenced. An accepted task launch does not prove source readiness. An empty registry must not satisfy expected participation: `LIMIT 0` intentionally does not execute its source.

`JobRunner::execute` currently returns only a batch stream, as defined in `sail-common-datafusion/src/session/job.rs:11–17`. Select an explicit internal execution/control handle so the caller can reach this live path. Avoid hiding a second execution owner in query metadata. The existing lifecycle manager should continue to own query registration and cancellation.

## Native source limits and required decisions

Rate execution resets its offset to zero and generates timestamps with `Utc::now`, at `sail-data-source/src/formats/rate/reader.rs:206–258,309–339`. It is not exact replay. Its zero-rate branch sleeps without data, making it a useful control-wakeup test. Socket execution creates a fresh TCP connection and deliberately has no retry or reconnection, at `formats/socket/reader.rs:184–245`. Neither should advertise durable replay merely because it accepts control messages.

Before implementation, settle:

1. Whether this increment establishes live marker control only, or also implements a concrete replayable source. The former is meaningful progress only with real local and remote execution controls, not just descriptors or mocked planner handles.
2. The source-occurrence address and participant manifest, including repeated identical source references and plans decoded on workers.
3. The exact acknowledgement point, duplicate request semantics, and handling of cancellation while a reply is pending.
4. The caller-visible internal handle and readiness contract. A registry must not silently turn omitted or unstarted participants into success.

If replayable rate data is included, specify stable time origin, partition layout, exclusive resume-position meaning and source incarnation first. That would intentionally change the current nondeterministic timestamp contract; it should not be smuggled into generic command plumbing.

The cheapest convincing checks exercise the actual execution path: two partitions and repeated source occurrences; an idle reader; marker/data ordering with a filtered-to-zero result; request replay after a lost reply; an obsolete attempt after replacement; cancellation before and during preparation; and stream drop while a command is pending. Round-trip the physical plan and exercise worker request routing. Retain a control where registration or command polling is removed and the corresponding check fails. These are proposed checks, not executed results.

## Reference semantics and upstream constraints

Spark 4.2.1 separates partition planning from continuous readers and their partition offsets in [`ContinuousStream`](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/catalyst/src/main/java/org/apache/spark/sql/connector/read/streaming/ContinuousStream.java#L30-L70) and [`ContinuousPartitionReader`](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/catalyst/src/main/java/org/apache/spark/sql/connector/read/streaming/ContinuousPartitionReader.java#L31-L39). Its queued reader captures the starting offset before reader threads start and sequences data and epoch markers through one queue. Its epoch coordinator waits for reader offsets and writer commits before committing an epoch, at `EpochCoordinator.scala:147–164`. This supports distinguishing source boundaries from durable completion. It does not prove Sail's proposed protocol or require copying Spark's threads or epoch architecture. No Spark execution was performed.

Upstream [Delta commit `cebc9513b`](https://github.com/lakehq/sail/commit/cebc9513b241e543e90eaf8a0a98f48fb0a1a8f6) changes `DefaultLogStore::write_commit_entry`: after `AlreadyExists`, it reads the complete existing log and compares exact bytes. Matching bytes succeed; different bytes retain the collision policy; inability to verify yields nonretryable `CommitStateUnknown`. The transaction-module delta contains tests, not another production retry algorithm. This reconciles a specific attempted publication. It supplies neither source checkpoint coordination nor commit-time ownership fencing. Preserve unknown-outcome propagation before allowing source retry to trigger sink replay.

Upstream [Iceberg commit `60b788c41`](https://github.com/lakehq/sail/commit/60b788c4162fd5129dd23f4073be80f641688a21) adds per-write snapshot properties. Its nine added codec lines are entirely a writer round-trip test; the options use existing serde transport. These properties can carry attribution, but a tag alone does not enforce ownership. The later REST view replacement commit is a separate catalog change. None was merged into this worktree.

## Selected source fingerprints

SHA-256, measured from the pinned bytes:

| Source | SHA-256 |
| --- | --- |
| StreamSource trait | `8ad95175cc7e9bc1c7f54cf80c0dfcf975d6f95f3023dfd2ee26022b084ede2d` |
| Rate reader | `a91d82e2ab0b253d15283020806ae0242a392afff58354153429aad214442a09` |
| Task preparation | `14c37991b12e0878bf562ff17f791d6e228f6128a551542932bfd71040cd4ca6` |
| Task-runner handler | `8aba87e07dd83ff1a7c5672f1d3f152095c204dcc778a6b950c898d198fe4d8a` |
| Worker server | `a90f36952543976b2a30052cbc4a1a7e38b354e2c95ce4e7ecc5249563c8ff3a` |
| Job runners | `872745b3bfee1d542fd14118631ad9188e94e29a5cc15f1d9ac0cfcf1a4b972d` |
| DataFusion `src/task.rs` | `4c29a992167ac93c7be62c2f889558c1f485394ed3ce91391cdcafa9fec28ffc` |
| DataFusion `src/config.rs` | `5c90a468bb0c7e244e0972ac1ce569f71c0bd056b271e17330efae75ea836c29` |
| Delta `git show --format= --binary cebc9513b` | `e076e4693ce44d40fca26ad2ea00efa3921da3cc283de408b27d06783282ad76` |
| Iceberg `git show --format= --binary 60b788c41` | `b628a1e48e6d5cf2ee26097c11012efcd63832103e61ae05bc3ea96bf6f5233e` |

The broader SDP, Extensions, Comet, typed-configuration and fencing objective remains incomplete. This report establishes a source-based integration recommendation, not runtime qualification.

Recorded: 2026-11-06T10:16:04.639805+00:00
