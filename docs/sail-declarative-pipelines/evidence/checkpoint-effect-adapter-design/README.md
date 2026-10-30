# Owned checkpoint effects: implementation checkpoint

This extends the [session lifecycle design](../../SESSION-CLEANUP-LIFECYCLE-DESIGN.md)
after the [observed late-publication baseline](../checkpoint-effect-baseline/README.md).
It selects ownership boundaries, while leaving the concrete hook API and provider
qualification incomplete. No new storage or shutdown guarantee is implemented here.

## Selected boundaries

Own effects per checkpoint operation/task, never by mutating the globally cached
store. DynamicObjectStoreRegistry caches by scheme/authority/session fingerprint;
concurrent execution scopes can share that same store. A shared store therefore
cannot carry one mutable current-job owner. Custom registered stores and local
filesystem stores also need interception: registration can bypass the dynamic
runtime wrapper, and the default file store is registered without it.

Retain the existing TaskResourceScope as the execution admission/drain owner.
Keep storage mechanics in sail-object-store; keep TaskContext, Spark error policy
and checkpoint namespace policy in their current higher layers. Prefer a narrow
owner hook implemented by a TaskResourceScope adapter over importing an entire
Grust/LakeCat service. No existing reviewed module supplies this complete contract.
The exact trait/error API remains to be chosen; no new dependency edge is approved
merely by this note. The current common-datafusion manifest depends on the external
object_store crate, not sail-object-store, so assess actual edges rather than
assuming a cycle or importing another crate to avoid an unverified cycle.

Register a multipart lifetime supervisor before starting provider creation.
That supervisor owns the provider upload, parts and final complete/abort disposition.
The consumer receives a command/result handle; it must not own the raw provider
upload whose Drop could launch unobserved cleanup. Keep provider/runtime affinity
and part-index assignment order from RuntimeAwareMultipartUpload. Cancellation
closes new data admission, requests part cancellation, and drives all admitted
parts and provider settlement to a known outcome. Retain one shared terminal
outcome independent of consumer waiters and completion notifications.

Complete and abort commands must serialize. Once complete has been admitted,
caller loss cannot retract an already-started commit. Wait for its result; on
known success, do not abort it again. On failure, apply the provider's cleanup
contract and preserve both typed causes. Cancellation before creation returns
must still dispose an upload returned after its consumer disappears.

Settlement belongs to the existing lifetime supervisor. It cannot depend on a
new TaskResourceScope.spawn after the job scope has sealed. The lower-level
lifetime must support settling already-admitted work while rejecting new data;
sealing every nested spawn indiscriminately would prevent the necessary abort.
A timeout or queued abort may bound observation, but cannot become clean drainage.
Runtime/task loss must leave an interrupted/uncertain result and retain the prefix.

A plain PUT likewise needs retained ownership before provider invocation, with
its actual completion joined through caller cancellation. Do not abort its owner
merely because a result receiver goes away. Completed result values and cleanup
ownership are separate: successful publication can outlive an observer, while a
resource-bearing creation result still needs explicit disposal.

## Routing the writer without changing other jobs

The checkpoint ParquetSink resolves its store again from TaskContext.runtime_env;
wrapping only the earlier explicit store variable does not intercept sink writes.
The same operation owner must reach those lookups, metadata reads and compensating
cleanup. Do not mutate the session's shared RuntimeEnv registry.

Use a private operation registry overlay as the routing direction to investigate.
DataFusion55.2 RuntimeEnvBuilder.from_runtime_env preserves the memory pool and
disk manager, carries the existing caches into a cache configuration, and preserves
the encryption factory registry when its upstream feature is enabled. Its
with_object_store_registry hook can select the overlay. This creates a new
RuntimeEnv/CacheManager container; it does not preserve their Arc identity.
Verify cache contents and underlying cache sharing rather than asserting identity
of the newly built manager. Avoid a hand-maintained RuntimeEnv struct literal,
which can lose upstream feature-dependent fields.

Construct the derived TaskContext with the parent's task/session IDs, complete
session configuration/extensions and all four function maps. Keep the existing
resource scope; creating another ScopedTaskContext would create another scope
and misroute drainage. Keep the default ScopedTaskContext behavior unchanged.
Any shared context-construction helper must preserve the current nonempty-function
regressions and gain an overlay isolation test before checkpoint integration.

This overlay is routing, not effect qualification. An opaque cached store may
already be a RuntimeAwareObjectStore. An outer forwarder awaiting its future
cannot observe its detached inner completion or Drop abort after cancellation.
The owned-mode hook must reach that wrapper's actual spawned work, or replace the
relevant path with a fully owned equivalent. Explicit owner propagation versus an
operation-local contextual bridge remains an API decision. Do not select ambient
session-global state. Prove nested-wrapper and custom-store cases before activation.

## Writer and error obligations

ParquetSink has internal child tasks and early-error exits. Starting the whole
sink in one owned task does not by itself join those children. Seal mutation
admission at terminal failure, settle every admitted upload, and prevent a late
writer from starting another mutation. Qualification of remaining operator tasks
and memory is still required for complete session shutdown; a storage fence alone
does not prove those tasks joined. Preserve downstream-driven input polling and
do not introduce a forwarding task that keeps reading after demand disappears.

Keep original provider and DataFusion errors as typed causes. A commit result
whose visibility is unknown needs the existing nonretryable unknown-commit
classification; failure before mutation admission does not establish a commit.
Cleanup uncertainty blocks namespace deletion, while keeping target-commit
classification dependent on the actual stage. In particular, commit_checkpoint
currently flattens simultaneous query and relation-cleanup errors into an Internal
string; preserve both causes before using that path for owned-effect recovery.

## Reviewable implementation and proof order

1. Preserve typed simultaneous checkpoint/cleanup errors independently.
2. Add an operation-owner seam and held PUT ownership test, without global-store
   mutation or claims about multipart lifetime. Admission must precede invocation.
3. Add the whole multipart lifetime supervisor, including abandoned creation,
   synchronous part ordering, retained complete and confirmed abort/part joins.
4. Route the checkpoint sink through the isolated registry/context, proving all
   resource/configuration preservation and sibling-job isolation.
5. Integrate failure/stop drainage with checkpoint publication and cleanup. The
   existing late-publication schedule must now hold deletion until settlement.
6. Qualify provider-specific blocking work, runtime loss and distributed workers;
   activate the full session barrier only after its declared boundary is proved.

Use held futures/channels, not sleeps as ordering evidence. Include cancellation
before first poll, during creation, part upload, complete and abort; dropped
observers; simultaneous complete/abort; provider failure; nested runtime wrappers;
custom stores; empty input; sibling scopes; panic/runtime loss; and late child-task
admission after sealing. Preserve every failure. Run optimized concurrency tests
under CPU load and exact combined library/public gates for runtime integration.
A temporary refusal after unqualified cleanup is honest but remains an unfinished
capability. The goal still includes successful batch, streaming/Iggy, CDC and all
original Spark SDP acceptance, not only these lifecycle components.
