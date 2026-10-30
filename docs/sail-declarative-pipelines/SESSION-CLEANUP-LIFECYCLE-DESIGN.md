# Session cleanup and shutdown design checkpoint

Recorded 2026-10-30T06:16:11.349749+00:00. Source baseline is Sail
`ec8e74d57de51149a774cd4f9048d82039704d0c`; Spark reference is 4.2.1 at
`617618396087429b5627a86ce933bb0f5d6645cb`. This extends the
[local stream ownership design](LOCAL-STREAM-OWNERSHIP-DESIGN.md).
The user was notified before this phase. The audit establishes requirements and
selects a manager-specific architecture; it does not qualify an implemented
session/storage/cluster shutdown barrier. Effect ownership still has an explicit
unresolved design boundary below.

## Evidence that changes the next action

The independent source audits at the recorded baseline are
[deletion state](evidence/session-cleanup-design/deletion-state-audit.md),
[manager/transport shutdown](evidence/session-cleanup-design/manager-shutdown-audit.md),
[checkpoint effects](evidence/session-cleanup-design/checkpoint-effect-audit.md),
and [operation ownership](evidence/session-cleanup-design/operation-ownership-audit.md).
Their proposed schedules are source-derived, not executed fault reproductions.

LocalJobRunner now waits for its owned stream and registered supervisors, but:

- Explicit/idle deletion still marks DELETED and acknowledges before the cleanup
  helper finishes. A failed cleanup is logged and its context is discarded.
- A newly constructed context can live only in an activation task or queued
  CompleteSessionCreation message. Sweeping Running sessions misses it.
- Actor shutdown closes but retains a mailbox while its stop hook runs. A queued
  GetDriver request can hold a gateway reply that gateway shutdown is awaiting.
- Both server entrypoints drain the transport before invoking manager shutdown.
  An active response that needs runner cancellation can prevent that call.
- RuntimeAwareObjectStore owns spawned PUT/multipart operations whose callers
  can disappear while mutation continues. Neither checkpoint writer nor these
  operations currently register a resource barrier visible to local stop.
- At that baseline, registry insertion checked open before locking, and storage
  cleanup cleared descriptors even on storage failure. The independent registry
  prerequisite below now fixes this loss of in-memory cleanup metadata.

Therefore adding a Deleting enum variant and awaiting the current helper is not
sufficient to claim that checkpoint objects cannot reappear after deletion.

## Selected ownership and state boundary

Keep the lifecycle policy in sail-session and preserve the actor architecture.
Do not drain ActorContext's generic JoinSet: it also owns idle timers and sends
that need the same actor. Do not rewrite the common actor framework merely to
support this manager.

As soon as the runner factory returns an allocated runner, retain a staged owner
before invoking the context factory, which may fail or panic after taking it.
A shared JobService passed into the existing factory seam is a candidate minimal
change; the exact public factory input adjustment still needs a caller audit.
Attach the constructed context before any asynchronous activation/completion
handoff. A cleanup record owns its
context/JobService, checkpoint registry, runtime, current phase and shared terminal
outcome. An RPC waiter or completion message is only an observer/notification.
The same record must serve explicit deletion, idle deletion, failure disposition
and manager shutdown; those paths may not start duplicate namespace deletion.

| Session state | Admission and retained ownership |
| --- | --- |
| Creating | Retain context and activation disposition, as well as waiters; no successful creation after manager Closing |
| Running | Existing context lookup and activity tracking |
| Deleting | Reject context lookup; retain exactly one cleanup record and attempt identity; later delete callers observe it |
| DeletionFailed | Keep unavailable; retain typed outcome and cleanup ownership; no implicit retry/resurrection |
| Deleted | Known successful deletion tombstone; reject recreation and acknowledge repeated release |
| Failed | Keep unavailable and retain any created context/cleanup record; do not overwrite or lose an active deletion |

The smallest explicit-delete unit may retain today's rejection while Creating;
accepting cancellation during activation is a separate behavior change. Global
shutdown nevertheless must own and dispose Creating contexts. Session IDs remain
nonreusable after known closure. A checked deletion-attempt token fences stale
completion notifications; no new incarnation/reconnect feature is introduced.

Spark's ReleaseSession handler explicitly treats a never-seen session as a no-op.
That public request should succeed without adding a tombstone, so it does not
prevent later creation of an ID that was never present. Known Deleted sessions
retain their tombstones. The pinned original double-release test is useful for
idempotency; its eventual cancellation assertions do not prove a storage join at
RPC acknowledgement. The deletion-state audit records exact reference paths.

## Cleanup operation and errors

Move state out of Running before starting asynchronous cleanup. Record ownership
before spawn, run foreign cleanup outside actor state mutation, and publish the
shared outcome before sending a completion notification. Fan out typed shared
errors; dropping all RPC receivers does not cancel or erase the record.

Close session/operation admission and request cancellation of every admitted
operation and physical job before awaiting their coordinated disposition. An
operation may itself await a job: joining that operation before requesting job
stop would deadlock. Drain registered supervisors and qualify mutable checkpoint
effects before deleting the session prefix and clearing its retained metadata;
only then publish successful deletion. The operation-owner audit identifies
execution preparation, removed/paused executors, pipeline producers and streaming
tasks that need retained ownership;
it also confirms that pipeline table materialization commands already pass through
the runner. Do not move SparkSession into sail-session: use a protocol-neutral
lifecycle/factory seam consistent with the current dependency direction. An
already-admitted TRUNCATE spawn_blocking is another effect supervisor prerequisite.
This inventory must be implemented before the order is activated. A context clone
returned earlier is not revoked by changing a map entry.

Use DataFusion Context/Shared/Collection and the existing SessionError conversion.
Keep query failure distinct from cleanup failure, and preserve a later
CommitStateUnknown cause. At an admitted externally visible publication/commit
boundary, an unobserved outcome must retain the existing nonretryable unknown-commit
classification. Before effect admission, ordinary failures retain their original
classification. Cleanup-only uncertainty blocks destructive deletion, but does not
by itself prove a target commit; each operation must establish its replay contract
before retries are enabled. The exact effect-stage classification remains part
of the pending adapter design. Join all cleanup siblings and aggregate their
errors; an early `?`/try_join must not abandon other sessions. JobRunner.stop
currently has no general drain-qualification result, so Err cannot justify
discarding its owner.

Choose one owned-operation implementation before coding the record: a retained
shared future with a designated driver, or an independently driven task with a
pre-spawn interruption guard and immutable watch outcome. The latter matches the
existing managed-stream observer pattern, but that component is not itself a
session/actor join primitive. Failure records must remain reachable from manager
shared state after actor termination while SessionManager handles remain alive.
Observer cancellation differs from forced destruction of ActorSystem/runtime;
forced destruction must produce interruption, never a successful cleanup claim.

Stop failures remain sticky and do not authorize checkpoint deletion on a later
ordinary release. A future manager/API-level checkpoint-only cleanup retry must
retain phase information and cannot skip an unconfirmed stop. Retained checkpoint
metadata is session-local in-memory state, not durable CDC recovery state.

## Manager Closing and transport ordering

Select Open → Closing → terminal manager lifecycle. The first accepted Shutdown
seals session admission but keeps the actor receiving messages. Continue handling
GetDriver and late lifecycle completions while session owners, child drivers and
the gateway need them. Reject every get/create context lookup, including existing
Running sessions, and avoid new idle probes. Previously returned clones still need
the shared operation
admission seal; the manager state alone cannot revoke them.

Retain manager completion outside the mailbox, shared by every SessionManager
handle. A requester canceled before its bounded send succeeds must not strand a
one-time started flag. After acceptance, caller loss is harmless; repeated callers
can observe the same terminal result even after the send channel closes.

A manager-owned coordinator can take the child ActorSystem after admission closes,
request all relevant operation/job/driver cancellation before awaiting dependent
cleanup records and child-driver joins, then stop/join the gateway while the
manager still services lookup messages. Constructing an async stop future is not
itself a cancellation request: the coordinator must actually drive those requests.
Driver lookup handles remain available until no gateway request needs them.
Only then may an internal
completion transition terminate the actor. The exact coordinator/record ownership
must be covered by interruption and bounded-mailbox tests before activation.

Manager completion denotes the retained cleanup/coordinator disposition published
from the final actor stop path. It does not claim that the actor future has been
joined: the entrypoint still performs that join separately. Mailbox closure or
receipt of an internal completion message is neither barrier. Relevant actor
failures already discarded by reap cannot be reconstructed from a final join.

Start manager shutdown concurrently with transport graceful draining on the
external signal. Also shut the manager down if transport exits with an error.
Both Spark Connect and Flight entrypoints must always join their actor system,
even when shutdown returns Err, and retain both transport and cleanup failures.
The whole serve future still owns the ActorSystem; canceling that owner is a
separate boundary from canceling a shutdown observer.

Existing driver shutdown, ActorSystem.reap/join and gateway stop swallow some
failures. A result signature does not repair that history. Retaining/returning
those failures and confirming worker effects are separate granular units. Local
success must not be represented as a universal cluster cleanup certificate.

## Checkpoint effects: unresolved implementation choice

The [runtime baseline](evidence/checkpoint-effect-baseline/README.md) now observes
late publication at Sail `36525a06f8d6da69a5c968a0630968690602ad71`: a held
multipart completion republishes a deleted checkpoint object after its caller
has been canceled and joined. All 17 object-store tests and the focused optimized
CPU-load test pass. This is a controlled InMemory provider observation, distinct
from the earlier source-derived schedules. The test changes no production
behavior and does not implement the adapter below.

The selected requirement is admission before each mutable effect and retained
completion/abort ownership through caller cancellation. Sealing blocks new
mutations, but abort and compensating cleanup belonging to an already-admitted
operation must remain possible inside its existing supervisor. They cannot rely
on spawning another supervisor after TaskResourceScope has sealed. All admitted
effects must reach a known disposition, or cleanup reports uncertainty and forbids
prefix deletion. A canceled awaiter, queued abort, 15-second timeout, or dropped ParquetSink
future is insufficient evidence. Input consumption must remain demand-driven.

Reuse TaskResourceScope for supervisor admission/drainage and typed outcomes.
Reuse RuntimeAwareObjectStore's required runtime affinity and serialized multipart
completion/abort rather than bypassing them. The existing wrapper is not already
a session effect tracker; its detached operations need an owner visible to the
cleanup boundary. Arbitrary explicitly registered stores can bypass that wrapper
and must also be covered by the selected adapter contract.

Before choosing an adapter/extraction, prove the exact boundary for PUT,
multipart creation/parts/complete/abort, compensating deletes, provider blocking
operations and the Parquet sink's internal task/error paths. Spawning the whole
sink in a scope alone cannot qualify its early-error paths. A temporary
fail-closed qualifier can expose unsupported cleanup honestly, but it is not the
requested finished implementation or a substitute for owned completion.

Grust/LakeCat's earlier [reuse inventory](evidence/local-lifecycle-reuse/README.md)
found notification and ownership patterns, not this complete contract. Do not add
whole service/catalog imports. Any extracted small module needs concrete callers
and a contract that both can preserve; Spark error and session policy stay in Sail.
Fable's pure CDC validation/corrections remain independent of this checkpoint.

## Reviewable implementation order and proof

1. Registry correctness prerequisite: completed at Sail
   `cba833ae08a4844afcb4e5edef0cc894231d0d82`. Seal/publication share one lock;
   storage failure retains closed metadata, get hides it, and only success clears
   it. Typed errors and explicit registry cleanup retry are preserved. The partial
   deletion fixture fails on unchanged production source and passes after the
   fix. [Separate evidence](evidence/checkpoint-registry-recovery/README.md)
   records 51 library tests, 4 optimized stress tests, 300 public cases and 67
   upstream Python executions. This is not an effect fence or manager retry API.
2. Effect ownership baseline and adapter: first reproduce a delayed PUT or
   multipart commit after caller cancellation/stop; then require held cleanup or
   explicit uncertainty until its owned work completes. Include provider abort
   failure and runtime loss. Do not activate a full deletion guarantee beforehand.
3. Retained creation/operation/cleanup records, shared typed outcome and attempt
   notification. Prove lost requesters, constructor/cleanup panic and pending
   creation cannot lose ownership. Keep new machinery private until wired.
4. Explicit/idle deletion states and raw ReleaseSession outcomes. The destructive
   cleanup path requires an explicit qualified effect barrier for its runner.
   Until distributed cleanup supplies that qualification, clustered cleanup must
   return an explicit unconfirmed-cleanup failure and retain the prefix/owner;
   existing ClusterJobRunner.stop Ok cannot authorize it. This is a temporary
   incomplete capability, not the finished cluster implementation. Test concurrent
   waiters, unknown/known-deleted idempotency, unavailable context lookup, status
   timestamps, typed failures and unchanged checkpoint storage on stop failure.
5. Manager Closing plus server entrypoint ordering. Exercise all local sessions,
   in-flight deletion/creation, queued gateway lookup, a long idle timer, concurrent
   shutdown observers, sibling failures and active transport streams. Always join.
6. Fallible retained actor/gateway outcomes and full distributed worker/effect
   qualification. These must not be inferred from local or library-only tests.

Each executable unit uses a detached immutable gate, appropriate Rust/Clippy/fmt
checks, deterministic latches and optimized CPU-load stress for concurrency.
Public runtime changes also rerun the selected 300-case/67-execution regression
baseline. Full Spark SDP Scala/Python acceptance, public ORC writing, Iggy and CDC
execution remain the goal; these lifecycle tests do not replace their assertions.

## Current upstream and review status

Origin/main advanced from4454d8369 to d803e13f0 during the fetch for this checkpoint.
Its two intervening commits do not change the session-manager, actor or checkpoint
registry files audited here. This source pin was not silently rebased or merged;
any integration needs its own combined gate. The original active Sail checkout
and Fable worktrees were not edited.

The manager architecture above is selected for review. The source audits retain
their `ec8e74d57de5` baseline; the registry prerequisite has since completed as
recorded above. Operation admission, the concrete effect adapter, the exact
cleanup-driver choice and manager Closing implementation remain pending. This
checkpoint does not establish an effect or session-cleanup barrier.
