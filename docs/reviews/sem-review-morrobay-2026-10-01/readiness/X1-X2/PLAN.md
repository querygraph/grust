Written UTC: 2026-10-02T01:00:54.538234+00:00.

Source/evidence audit SHA-256: `76cb6f7f276160a68f1b1fc3d6a52b3670502c2643bfe232141a6c298ec20318`.

# X1/X2 readiness: initiating faults, historical scope and supervised controls

Status: **X1 open; X2 open**. Read-only review of current Grust `AGENTS.md`, section 9 of `docs/SEM-REVIEW-2.md`, exact Sail Git objects, the prepared handoff and small retained receipts/logging controls. No remote message, SSH command, VM/container action, benchmark, build, source mutation or live lock action was performed. Root continues the serial B8 campaign. This plan neither changes that queue nor grants standing resource admission.

## 1. Evidence locations and qualification

Governing repo: `/Users/alexy/src/grust`. Board X1 is the Argentea two-host scale-24 failure; X2 is the historical relational stream loss described in `docs/STREAM-LOSS-STATUS.md`. Both are still marked running/open; neither is resolved by the later one-host passing campaigns.

The two-host handoff is local at:

`/Users/alexy/src/sail-extensions-gates/argentea-two-host-debug-20261001-handoff/`

Its `morrobay-handoff.json` SHA-256 is `60b97b06c151fb8564a6f1e8387472f65e2e8bc52d558d54579656667ecd104e`; `reproduce.py` is `44388257318dd01f9ce0308fd9ad22737fe8a8520df65ce7650d30966ea8a3e7`. All twelve members of `handoff-bundle.json` were independently rehashed and matched. The handoff was prepared at 2026-10-01T14:57Z; its then-active capacity PID/VM/container, ports, resource observations and ownership instructions are **historical**, not current admission or live-process findings.

The handoff explicitly says the root retains ownership pending an ACK; the reproducer is intended to run from a durable Capitola owner, with Morrobay managing its own worker and evidence. No large replay or boundary watcher was executed by this debugging pass. The small `logging-control02` passed with the unchanged old binary, but its scope is one host and two local workers with a deliberately induced failure. It qualifies driver typed-cause DEBUG visibility and its cleanup control, not Argentea, LAN transport or scale-24 completion. The initial parser failure remains preserved.

The original Capitola case's paths and expected hashes are in the handoff; their remote bytes were **not** accessed in this task. The separately retained `docs/reviews/sail-graphs-2026-09-30/two-host-log-observations.json` binds the historical merged log hash `f1b15fc009f53e1d97a44f6f94a10cd60987a95b3908bb46666c605266146298`. It records first FAILED at line 2305, 06:12:10 UTC, worker1/job37/stage22/partition26; the h2 reset-limit warning is line 2748 at 06:12:11 after 443 FAILED entries. There are 651 failures overall. Seconds-resolution merged records and an untagged h2 warning do not establish the initiating peer or cause.

The source/evidence audit JSON preserves exact paths, bytes, SHA-256 and before/after identities. All selected local evidence was unchanged. No physical graph, archive or complete historical sample stream was read or rehashed.

## 2. Source/runtime parity

Git objects were checked in the common source repository navigated at `/Volumes/Apo/graph-tests/workspaces/sem-review-20261001/pecan-f3b3ef8fc`; no pin is inferred from that directory name.

| Role | Source commit / artifact |
| --- | --- |
| Historical runtime/native | `ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73` |
| Prepared X1 source HEAD | `837a8ecf5c2c3b8ad24e044c72c1cb69d9fc71f4` |
| First bounded diagnostic runtime | `2894a962076d3cc404dd72ec736ebeb9239901f6` |
| Current retained compact runtime | `56194b170155301ba91077f0ba3df31fe2c78b6b` |
| Current Pecan controller | `f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a` |
| Current loaded Python harness | `6ae2e43a903c2cee02da170465c922c72b76198e` |
| Historical X1 macOS x86 runtime binary | SHA `fc1d87dccedee016a032638f3aee999f6387fd5770a541fdf8e56ba7db77691a` |
| Historical X1 macOS native library | SHA `0b54774417a3bdb9a6974f909bec4fce015b4885d89c12794534147c580e4579` |
| Historical X2 gate3 Linux binary | SHA `516cb3e5aecd89e954edff7934be439e63f2257e08c5ba45f09219261a173226` |
| Diagnostic289 Linux binary | SHA `40a78182a420152e8e3651f9cdb38a4196eaf8bc7aead092d10e258a17ac3497` |
| Compact561 Linux binary | SHA `5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec` |

Prepared837 differs from historicalffcf only in `examples/extensions/argentea/python/qualify.py`: nine added lines permit/record extra `SAIL_*` settings. This Python source change is not a rebuilt runtime. The prepared adapter intentionally requires the historical macOS binary/native wheel; the currently retained Linux561 binary cannot be substituted and called a matched two-host historical replay.

Across the six reviewed pins, `Cargo.lock` is byte-identical: SHA `46121478d56b0d911d4f295f428b2816bd4a976d22265994afc2a5378bb00546`. Relevant locked versions are h2 0.4.15, hyper 1.11.0, hyper-util 0.1.20, Tokio 1.53.1 and Tonic 0.14.6. Shared dependency versions do not establish feature/build flags or executable identity.

First-fault logging was introduced at diagnostic289. The following entire files are byte-identical between diagnostic289 and actual compact561:

| File relative to source checkout | SHA-256 |
| --- | --- |
| `crates/sail-execution/src/diagnostics.rs` | `25ea6431b187f80230a12778b375f9802db81b76017caecc92b981c015dbf43a` |
| `crates/sail-execution/src/stream/service/client.rs` | `257aadfbf2a9d5e20d1e233020809a47722ec7a23927b6a8f92bcd057f2c980b` |
| `crates/sail-execution/src/stream/service/server.rs` | `2e9f48344c629855af1619870d7e425f0c3e021cdf43e7e5f0ba57927a308ac9` |
| `crates/sail-execution/src/task_runner/actor/handler.rs` | `5654729d444b2ca637de0d1e58a92480881d492a1c02a81fafad0489814f55de` |

Historicalffcf has no `diagnostics.rs`; its Flight/task logging files differ. Compact561 carries the bounded cause/peer hooks, but this does not give the old X1 binary those hooks or qualify new execution. JSON retains all nineteen files at all six pins, including absences.

Important preserved behaviors:

- `diagnostics.rs:14–20` logs PID and bounded error sources before conversion; Flight client/server hooks retain stream task key, peer and phase. Text is bounded to 4096 bytes, source traversal to 32 errors, with truncation marked. This is not a durable global first-cause ledger or connection-ID trace.
- `task_runner/actor/handler.rs:116–130` logs worker/session/task identity and message/cause before reporting. The old binary can instead print full decoded `ReportTaskStatusRequest` at `sail_execution::driver::server=debug`, demonstrated by the small logging control. Capturing the driver response alone can still show a propagated cancellation rather than its origin.
- `stream/error.rs:39–53` still maps ordinary Tonic status to its message unless it contains the special serialized task-stream cause. First-boundary logs remain needed. `job_scheduler/core.rs:586–609` chooses a returned cause by failure multiplicity then stage/partition order; it is not first-in-time selection.
- Shared `rpc.rs` client construction applies the 128-MiB decode limit to Flight as well as driver/worker clients. It does not retain a separate default 4-MiB limit on worker-to-worker Flight. Any other size hypothesis needs its actual source and batch size.
- `server/builder.rs` is unchanged across these pins (SHA `9b5589a5fefec2286349e22bd180d477f2edc40498d2989359512fb44bfab37c`): default HTTP2 interval 60 seconds, timeout 10 seconds, adaptive window on, with fork environment knobs. The one-host harness configures timeout120; the historical X1 qualifier did not explicitly set it.
- The **actual Argentea** launcher is `examples/extensions/argentea/python/launch_worker.py` (SHA `5b39f888bb1c4f849f75f7fd837f43c20d58556d97c71ce40adee2fed2790647`), not the plain `scripts/two_host_worker.py` entry point. It forwards ordinary pool/native quota/thread settings, cluster/execution settings and RUST_LOG; it omits experimental HTTP2 interval/timeout. Remote inherited values may still exist. Source/default inference is not a live effective-setting observation.
- `ExecutionGuard::drop` cancels a shared native context if incomplete; `nutmeg/src/argentea/input.rs:26` then lets sibling reads return cancellation. These files are identical at historicalffcf/diagnostic289/compact561. Cancellation while reading input can be secondary. Nativeffcf is still the loaded wheel in the relevant historical/compact cells; newer native fixes cannot be credited to them.

Locked h2 controls show ordinary response cancellation does not consume the protocol-error reset cap. The local exact-version Tonic control shows `tonic::transport::server=debug` exposes a deliberately induced keepalive timeout without hyper tracing. Those are diagnostic controls, not a diagnosis of an existing Sail loss. Default hyper logging feature closure must not be assumed from `RUST_LOG`; use Tonic's verified target. A late GO_AWAY(NO_ERROR) or reset storm is not sufficient causal evidence.

## 3. Latest retained zero-event losses versus later replays

These are the two latest retained gate3 relational loss receipts in the historical roots inspected by the independent metadata review. Both have producer `error`, the h2 body-read error, no correctness result, no outer timeout, zero max/oom/oom_kill/group-kill counters before and after, Docker `OOMKilled=false`, stopped exit1/attach1 and successful container remove. These observations mean **no recorded cgroup OOM event**, not a general exclusion of memory refusal, host pressure or uncaptured mechanisms.

| Case | Retained metadata and result |
| --- | --- |
| Scale25 Pecan BFS reference, finished 2026-09-30T11:31:10.835672Z | `~/src/sail-extensions-gates/graph-nuts-gate-next/decide3-gate3/cells/decide-pecan-s25-bfs-r1-scale25-pecan-bfs-reference/artifacts/receipt.json`, SHA `9a23e9309d167157a1fb86f283dd3c1bad1fa81c60d4eaaaca4b6f504c7fd57b`; sampled execute PSS 43,706,977,280 bytes; cgroup peak61,129,412,608 bytes /100GiB. Outer transport errors empty. No post-shutdown staging inventory. |
| Scale24 Pecan SSSP delta_star, finished 2026-09-30T08:24:08.852074Z | `~/src/sail-extensions-gates/graph-nuts-gate-next/decide-gate3/cells/decide-pecan-s24-sssp-r1-scale24-pecan-sssp-delta_star/artifacts/receipt.json`, SHA `ba808d6b1bcdebd8b90a1607f4106438aab844641feb68e31803003f0898eb59`; sampled execute PSS69,806,754,816 bytes; cgroup peak82,117,808,128 bytes /100GiB. Outer record retains `required artifact copy failed: artifacts`; archive closure is incomplete. No post-shutdown staging inventory. |

Both pin runtime/harness/nativeffcf, 32 CPUs, one100GiB/no-extra-swap Linux container, two workers, P32/32threads, configured96GiB pool per process and80GiB native settings. Those caps are configured intent and do not bound whole-container physical consumption; pool/reservation/quota/PSS/cgroup are distinct observations. `cleanup_errors=[]` with explicitly uncertain write/deferred cleanup is not deletion proof.

The status table preserves twelve historical zero-event relational failures; thirteen zero-event body-read failures were found if the separate confounded Argentea scale25 attempt is included. Do not fold that native case into the relational category.

Later evidence answers different questions:

- `logging01`: an exact100GiB-cgroup kernel victim and one disappeared worker; namespace-to-host victim role association remains an inference because it was not captured live. OOM explains that replay.
- `logging02`: exact same-boot cgroup kernel kills of both live-mapped workers, followed by worker2 Flight broken pipe, `oom_kill=2`. This is an explained OOM replay, not a no-OOM initiating fault. The first-fault analysis/clock/sample-window limitations remain preserved.
- `logging03` at compact561 passes the producer and independent physical-output scan; later local A3 passes also contain no loss. They do not establish that the original no-OOM mechanism was reproduced or repaired. Newer next-capacity Pecan25 is a pass, not another retained loss.

The old evidence is under `~/src/sail-extensions-gates`, not the new Apo typed/SEM campaign archive. This task created no archive migration. Absolute metadata paths and hashes are in the audit JSON.

## 4. Current blockers

1. **No fresh two-host ownership/admission.** Prepared ownership/resource facts are stale. Current B8 remains the one heavy gate job. A future X1 operator must explicitly claim the Capitola driver/client/store and Morrobay worker/supervisor roles and a common fresh experiment ID after the active queue closes. No host CPU/RAM/disk/network/process observation was performed here.
2. **Prepared X1 helper is not a qualifying supervisor.** Its docstring and receipts expressly omit full payload rehash, CPU/RAM/disk admission/watchdogs, result export, independent BFS certificate and independent remote closure. It pins a manifest only, records inferred inherited keepalive rather than actual launched settings, and requires an external durable outer owner. `qualified_completion` in that adapter means old completion/placement/identity criteria; it must not be promoted to full correctness or archive/resource closure.
3. **Namespace scope is incomplete.** The adapter overrides GraphUtils root only on the driver; remote host storage env files remain unchanged, and the worker allowlist does not forward that root. Before any cleanup, bind actual per-host roots and immutable input/output ownership. No broad store/prefix removal is authorized by an apparently fresh driver namespace.
4. **Historical X1 runtime lacks new worker/Flight diagnostics.** Driver DEBUG is useful and tested, but a source-parity diagnostic runtime for the macOS x86 hosts has not been built/qualified here. Substituting Linux561/native artifacts changes platform/path. A diagnostic-only fork backport/new binary must have its own exact gate and declared source differences before a large run.
5. **The original no-OOM X2 path has not been reproduced with complete first-boundary evidence.** The later instrumented frontier/delta-star cells OOMed, and compact replay passed. Neither closes X2. Current32GiB A1 admission is not admission for the old32CPU/100GiB experiment; even logged compact24's33.05GiB peak exceeds32GiB. A smaller control can validate logging/oracle/cleanup but cannot replace the missing large-case observation.
6. **Full BFS/SSSP oracle and archival closure must be added.** The custom X1 helper lacks an exported full BFS output and edge/parent oracle. The latest SSSP loss also retains a copy failure; final staging inventories are missing in both losses. Current exact cit-Patents positive-ID oracle is not the Graph500 ID contract: these generated graphs include vertex0 and use an undirected tuple adapter.

The blockers are concrete prerequisites for a new job, not a request to stop B8, change a VM, contact a peer or start a rebuild in this task.

## 5. Minimal supervised plan

### Common admission and evidence contract

Before launch, freeze a new plan/config/helper manifest and source/binary/native/interpreter/package pins. Use source-parity diagnostic changes only for the initial causal replay; a later controller/native optimization is a separate profile. Keep every original failure and copy/observer/timeout outcome, no automatic failed-ID retry.

Fresh per-host admission must record actual machine/platform/translation, host memory available/pressure/compressor/swap, active authorized workloads, CPU budget, pool/quota environment, disk/inodes for original inputs+references+peak scratch+failed outputs+archive copies, PID/FD budgets, deadline/grace and LAN route/advertised endpoints. The Capitola driver/store/worker and Morrobay worker share physical hosts differently; sum process budgets by actual host. Do not apply one100GiB container's accounting to two macOS processes/hosts. PSS/cgroups are unavailable on a native macOS path unless a supported observer is provided; retain RSS and host-specific pressure/kernel records as their own metrics, not fake PSS or a zero-OOM proof.

The original X1 settings to preserve initially are scale24 V16,777,216 / input tuples268,435,456, source13507776, undirected reference BFS, cap8, P32, eight threads/process,48task slots/worker,32GiB ordinary pool/process,16GiB native quota settings, stream creation900s and idle86400s. Actual launched selected nonsecret environment must be captured on all three Sail processes. HTTP2 settings are initially inherited/default under the original contract; measure them. Explicitly forwarding changed settings is a later declared control. Host resource refusal is distinct from a runtime fault. A heterogeneous Capitola/Rosetta–Morrobay path is functional qualification, not homogeneous scaling.

Outside engine timing, rehash every original Parquet file on both hosts against the exact historical generation; verify schema/rows/unique ID domain and endpoint validity once, preserving duplicate/self-loop/undirected tuple semantics. Pin an independent directed/undirected reference appropriate to each selected cell and its exact source. Do not regenerate a graph from seeds and call it the same physical input; do not substitute the official LDBC Graph500-24 pair currently being acquired for B8.

Retain separate boundaries for algorithm-ready, full raw output export, independent oracle and owned closure. Output must preserve actual schema/types without casts. For full BFS require all unique original IDs including0, source distance0, unreachable semantics, every exact unweighted distance, all reached-edge inequalities, and a rooted tight-predecessor witness. An independently generated BFS distance array plus a bounded full edge certificate suffices if raw output lacks parents; declared producer parent/hops fields require their own exact checks. For SSSP fix original weights/source/delta/cap and finite path contract, retain exact/tolerant distance policy and rooted tight witnesses; distance-row domain checks alone are not shortest-path proof. Prepare references once outside timers and record their own resource admission.

Each host has a durable local supervisor/PID/process-start identity and heartbeat lease. Record each owned child/group, command/source, stdout/stderr, wait result and forced cleanup. Both observers continue through failing writes and shutdown. Caller deadline stops only owned groups; queue never kills engines itself. Afterwards independently prove owned supervisor/worker/driver absence and exited state on each host, observe store ownership separately, retain final namespace inventory, and hash complete collected evidence/result artifacts to the archive before any disposable payload removal. Keep unrelated VMs, stores and process groups outside ownership scope. Preserve `uncertain_closure` and retain locks/payload on uncertainty.

### X1: one logging replay, then a cause-driven repair and one rerun

1. Build/gate only the required diagnostic runtime/adapter at an explicit new pin for the original architecture; source review must show unchanged algorithm/native/input contracts and identify every diagnostic/config change. A small two-host valid graph first proves actual Argentea work on both hosts, full output oracle, first-cause sentinel visibility and durable owned closure. Include signed/highbit IDs, duplicate edges, loops and an isolate; use BFS, not unqualified signed-ID randomized WCC. This control is separate from scale24 diagnosis.
2. Admit and run **one** original scale24 reference-BFS replay. Use the prepared handoff's parameters/input identities and a fresh fully owned namespace. Record the native phase initialization counts, producer/consumer progress, first complete typed failure before subsequent cancellation, worker task/peer mapping and per-host resources. Capture all failure events, not only a parser's first matching line.
3. Select one control/repair from the observed boundary: explicit keepalive forwarding, admission/queue behavior, store/transport issue, or another typed error. A reset-limit warning after a cancellation cascade is not sufficient evidence to change reset caps. If all observed failures are cancellation without an originating cause, outcome remains unexplained and bounded native cancellation-origin logging is the next prerequisite; no speculative repair verdict.
4. After the smallest justified repair, gate that exact source and run **one** matched new-ID scale24 rerun, with identical input/reference/profile and full oracle/closure. A pass alone is a completed scoped run; claim the cause repaired only when the recorded causal mechanism and changed control support it. No multi-host performance/scaling claim follows from these diagnostic single observations.

### X2: retain OOM cases; replay an original zero-event shape

1. Qualify the already-delivered diagnostic hooks on a small local two-worker real exchange at the **chosen** binary pin, with a full answer oracle and an induced typed peer/task failure control. Retain all logs and cleanup. It does not close the large-case loss.
2. The minimal original zero-event shape proposed by the status record is scale24 Grenada BFS reference (historical failure about108s into iteration2, roughly42.8GiB sampled peak), rather than repeating the frontier shape that later OOMed. Pin that original receipt's actual controller/native/runtime/config/dataset before execution. Use a diagnostic-only backport onto that source/profile if preserving historical work is required; a compact561/f3 rerun is explicitly a different-profile observation. It is not a memory promise or a10-minute runtime guarantee.
3. Freshly admit the original encompassing resource envelope and capture namespace mappings/kernel/cgroup counters while live. If only32GiB is available, retain `not_admitted`; do not silently shrink pools or switch algorithm/input and call it a reproduction. Record pool refusal, OOM, timeout, nonconvergence, transport error and observer/archive failure separately.
4. Run the one logged zero-event-shape cell; the independent oracle remains required if it completes. A recorded OOM explains only this new replay; it does not retroactively diagnose original no-OOM losses. Choose the next single discriminating control from its initiating fault, keeping keepalive/partition changes isolated and explicitly recorded. No broad matrix or automatic retries.

### First-fault collection

Use existing bounded worker/Flight hooks and the verified Tonic logger on **every** process. Preserve the driver decoded task request as supporting typed-cause evidence. A practical declared filter can combine:

`info,sail_execution::diagnostics=warn,sail_execution::task_runner::actor::handler=debug,sail_execution::driver::server=debug,tonic::transport::server=debug,h2::proto::connection=debug,h2::proto::streams=warn,h2::frame::go_away=trace,h2::frame::reset=trace,h2::frame::ping=trace,h2::proto::ping_pong=trace`

Keep DATA/WINDOW_UPDATE tracing excluded. This diagnostic logging changes cost; its elapsed values are not added to A2/A3/B8 performance cells. Bind each log to host, PID/start identity and endpoints; h2 connection prefixes alone may omit these. Record client operation/job/stage/partition/attempt/worker and native operation/owner/phase where available, plus first native admission/refusal/cancellation reason. Retain raw logs when structured extraction fails.

For two physical hosts, monotonic values have different kernel origins. Generate UTC and monotonic timestamps locally, record clock offsets/uncertainty and suspend/boot identities before/after, and correlate messages/IDs. Do not sort seconds-resolution merged UTC lines and call the first line a proven causal root. Distinguish original socket/typed error, native guard cancellation, subsequent task cancellation and session teardown. The scheduler's chosen returned error is not an authoritative first-fault timestamp.

## 6. Required future receipt fields

Use typed records for `FilePin`, `SourcePin`, `HostAdmission`, `ProcessOwner`, `EffectiveEnvironment`, `InputGeneration`, `Reference`, `EngineOutcome`, `FirstFaultObservation`, `Correctness`, `HostClosure` and `ArchiveProof`.

- `InputGeneration`: every actual original file identity, schemas/counts/domain, separate host copies and preserved tuple adapter; whole generation hash before/after.
- `Reference`: independent algorithm/source/direction/weight policy, arrays or certificate identities and preparation resource receipt.
- `HostAdmission`: observed timestamps/host platform/CPU/RAM/disk/network, actual per-host process caps, resource watchdog thresholds and explicit unavailability.
- `FirstFaultObservation`: raw host/log offset/hash, task/worker/native/peer identity, complete bounded typed cause, timing uncertainty and classification as initiating/cascade/unexplained.
- `Correctness`: raw physical schema/result identities, complete unique coverage, source/unreachable and every expected value, full edge/witness proof; missing output means unverified, not mismatch.
- `HostClosure`: every owned process wait/state/absence, final OOM/pressure/kernel evidence, namespace inventory and shared-store ownership. No `cleanup_errors=[]` shortcut.
- `ArchiveProof`: exact final evidence inventory/file hashes, verified copy, root-controlled payload disposition and released locks. Preserve original collection failures.

No X1/X2 DONE claim is supported by this readiness audit. Root can now prepare the missing supervisor/oracle/diagnostic parity and coordinate fresh ownership/admission after the serial gate queue; execution remains a separate authorized phase.
