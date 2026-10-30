# Retained multipart lifetime

Implemented component: Sail `4cb9aec14cd8aa8725e79326c968a5672dc4dd0e`.
This continues the [effect ownership checkpoint](evidence/checkpoint-effect-adapter-design/README.md).
[Exact component evidence](evidence/owned-multipart/README.md) covers the new module;
checkpoint routing, nested wrappers and the complete session barrier remain open.

## Layer and admission

Storage mechanics live in sail-object-store::owned_multipart. There is no dependency
on sail-common-datafusion and no new crate dependency. The existing common
TaskResourceScope remains the execution owner. The new component prepares an
unstarted MultipartSupervisor and a Creation observer, spawning nothing itself.
The higher layer registers the complete lifetime before awaiting Creation:

```rust
let (supervisor, creation) = prepare(provider_factory, max_parts);
resources.spawn(move |canceled| async move {
    supervisor.run(canceled).await.map_err(
        sail_execution::owned_multipart::execution_error
    )
})?;
let mut upload = creation.wait().await?;
```

Sail `beebb83d0df5aff947bd1e20e0a69626c98c14bc` now implements this adapter in
sail-execution::owned_multipart::create, with execution_error preserving original
typed Complete failures alongside nonretryable unknown-commit classification.
[Actual scope/adapter evidence](evidence/execution-owned-multipart/README.md).
The adapter is not installed into checkpoint routing. Its layer already depends
on both crates; sail-session and sail-cache also have both edges. Do not make
common-datafusion depend on the object-store service merely to exercise it. A failed registration must drop
the supervisor and observer without calling the provider. An abandoned observer
before the first poll also avoids creation. Cancellation/observer loss during
creation does not drop the provider future: a returned upload is explicitly aborted
and joined. Abort errors survive even when the creation observer is gone.

The retained owner must run on the provider's required runtime. If it bridges to
a separate I/O runtime, retain and join that actual task; no detached forwarding
or fresh independent resource scope. Keep that runtime alive through settlement.
The component's separate-runtime test checks creation, synchronous provider part
invocation, part future polling, and both complete/abort on the selected owner
runtime while command/result callers use another runtime.

## Commands, capacity and part ordering

The consumer receives a MultipartHandle, never the raw upload. put_part is a
synchronous, fallible command admission. It reserves one part permit before
queueing; capacity rejection invokes no provider. One non-Clone mutable handle
serializes submissions, and the single supervisor invokes provider put_part in
FIFO order. Actual provider invocation is deferred to that supervisor, unlike the
legacy runtime wrapper's immediate invocation in its caller. No task scheduling
order decides provider part indices. Only the returned futures are multiplexed
concurrently in a retained FuturesUnordered.

The observer future does not carry the provider future. Dropping it never cancels
the admitted part. The permit remains held until that provider future completes
and is released before notifying its result observer, so an awakened producer
can reuse capacity immediately. The result receiver carries only completion/error,
not the payload. An unbounded channel is used internally but at most max_parts
queued/active part commands plus one terminal command can be submitted: permits
bound parts and the admission state bounds terminal commands. This is a count
bound, not a byte budget; caller byte/memory admission is still required.
Capacity above Tokio's supported semaphore maximum is refused before creation.

## Terminal transitions

Admission is Open, Completing or Closed. complete synchronously transitions Open
to Completing before returning a shared result observer. It rejects further data.
Explicit abort and cancellation serialize against that transition under the same
mutex. Cancellation rechecks the current state rather than acting on a stale Open
snapshot; it cannot retract a completion that has since been admitted.

Notifications happen after unlocking. A channel waker can reenter the supervisor;
sending under the mutex would expose a deadlock. The deterministic notification
control fails with the old send placement and passes with the identical test after
the fix. The tests do not depend on a sleep or scheduler timing to detect this.

Before completion admission, cancellation or explicit abort closes data admission.
Queued parts not yet invoked are rejected and their payloads/permits released.
Already-created provider part futures are joined, then provider abort is awaited.
The generic MultipartUpload trait provides no cancellation-and-join primitive for
an opaque part. This component therefore waits for it instead of dropping it and
assuming cancellation stopped effects. Provider-specific cancellable joins are a
later qualification. A stuck provider keeps drainage pending; there is no timeout
that converts pending work into clean disposal.

After completion admission, the supervisor processes prior part commands, joins
all their futures, then invokes provider complete if no part failed. Consumer loss,
explicit abort or later cancellation observes the same result; it cannot start a
competing abort. A known committed upload is never aborted again. If a part fails,
complete is not invoked: join siblings, abort, and retain both kinds of cause.
Empty completion and explicit abort each have exactly one provider disposition.

## Typed outcomes and uncertainty

A shared terminal observer yields Committed(PutResult), Aborted, or MultipartError.
It does not keep command admission open. Creation and part observers, terminal
observers and the retained owner preserve original object-store errors in Arcs.
Provider errors carry Create/Part/Complete/Abort stage, and causes() retains every
observed failure. Error::source exposes the first cause; siblings remain available
without string parsing. Tests compare the original error Arc and shared aggregate
identity across observers and owner.

A complete error has unknown visibility under the generic provider contract. The
component retains that typed Complete error and does not blindly call abort, whose
behavior after a possibly committed upload is implementation-defined. A provider-
qualified recovery rule, including any required cleanup, remains necessary before
activation. The enclosing checkpoint protocol must apply its nonretryable unknown-
commit classification; this lower component does not manufacture a clean abort.

Task panic/runtime loss drops observers as Interrupted; the retained task owner must
also retain its real JoinError. Neither result means clean settlement. Error-return
paths may drop a provider whose own Drop spawns work; they remain failures rather
than cleanup-qualified success. The adapter must distinguish operation failure from
confirmed disposal if it later wants to permit safe compensation after successful
abort of failed parts. The initial generic TaskResourceScope mapping conservatively
retains those errors; a successful abort does not erase a failed operation.

## Limits and next units

The legacy RuntimeAwareMultipartUpload implementation is unchanged. Its abort waits
up to 15 seconds for its tracked parts, ignores timeout, and Drop can spawn an abort.
An outer wrapper alone cannot qualify that nested lifetime. Raw/custom/local stores
and nested runtime wrappers need explicit held-effect qualification. No checkpoint
writer is routed into this new API, no public success/Deleted/RPC acknowledgement is
changed, and the incremental/sink execution guard remains.

The execution-owner adapter is done at the stated component boundary. Next
reviewable units are provider/runtime-wrapper ownership hooks (including runtime-
loss uncertainty); isolated registry/context routing with
config/function/cache preservation and sibling-scope isolation; actual checkpoint
publication and failure cleanup; then session/cluster drainage. Each combined tree
needs its own gate. The existing late-publication baseline must become a real
integration regression before deletion is authorized after stop. ORC memory/writer
admission and durable streaming/Iggy/CDC effects remain separate unfinished work.

The component gate is 33 object-store library tests, formatting, strict all-target/
all-feature Clippy, and 16 optimized multipart tests under ten CPU-load workers.
Those workers were joined and the tested binary hash checked. This is not a full
Spark SDP suite, provider matrix, public CLI or session shutdown verdict.
