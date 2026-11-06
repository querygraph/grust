# Control running streaming sources through their execution owners

Streaming pipelines need to request an ordered input boundary from sources that
are already running. Acknowledgement must identify the exact source partition and
execution that produced the boundary. Build this control path on Sail's job runners,
task attempts and flow-event markers. A live boundary alone does not establish
replay, checkpoint alignment, target fencing or durable completion.

## Planning describes a source; execution owns its reader

Sail's StreamSource interface describes a schema and creates a physical scan plan.
The live reader is created later by that plan's execute method. LocalJobRunner
executes directly in the session process. Distributed execution reconstructs a
physical plan for each TaskKey, which identifies a job, stage, partition and attempt.
The worker currently shares a base TaskContext across tasks.

A planning descriptor therefore cannot hold a worker's live control handle. A
session-wide map would mix attempts and allow stale cancellation or acknowledgements
to affect replacements. Attach a fresh control scope through a cloned session
configuration in a reconstructed TaskContext. Preserve its runtime, function
registries, session identity and existing configuration. Public DataFusion APIs
support this; dependency ownership is unnecessary here.

| Existing component | Addition | Guarantee |
| --- | --- | --- |
| StreamSource and physical source planning | Truthful live-barrier capability and an explicit physical source binding | Planned participants remain distinguishable before execution |
| Physical-plan codec | Preserve the binding identifier and capability | Worker reconstruction addresses the same compiled occurrence |
| Job runner or task-attempt owner | Own, expose and revoke a fresh runtime scope | Session state and replacement attempts cannot share live endpoints |
| Native source polling loop | Register its actual partition and accept a bounded command | Idle readers wake without waiting for data |
| Flow-event encoder | Encode the source's marker before acknowledging its handoff | An accepted command is distinct from an emitted boundary |

The physical binding uses a fresh opaque identifier created for one compiled source
occurrence and preserved by cloning and serialization. It is not derived from a
provider pointer or display name. Reusing a compiled plan creates a fresh runtime
scope. Neither identifier is a restart-stable source incarnation or durable position.
Those require a separate replay contract tied to the pipeline definition.

## Expose a usable control path

Add an explicit controlled-execution entry point to JobRunner returning both output
and a SourceController. Ordinary execute retains its existing behavior. The
controller carries the expected source-partition manifest and addresses individual
live sources; an empty registry never means a checkpoint succeeded. A source below
LIMIT 0 is NotReady while its execution remains live and becomes Closed when output
completion or drop revokes the scope.

First qualify the shared contract and an actual local rate-source path. This
settles marker ordering, cancellation and request semantics before encoding them in
driver and worker protocols. Controlled cluster execution must return a named refusal
until task-attempt routing implements the same contract. The physical binding codec
is included now so ordinary cluster plans remain reconstructible. Distributed
routing remains required, not waived by local qualification.

In distributed integration the existing driver selects the current TaskKey, and
worker/task actors route to that exact active scope. Admission history is not
readiness: admitted task records can outlive execution. Revoke on cancellation,
terminal status, job closure and output drop. Acknowledgements include runtime
registration identity, and the owner must reject replies from revoked attempts.
Local execution uses its job runner instead of introducing a driver.

A hidden global mailbox would lack execution ownership. Passing commands through
the data stream would make an idle or backpressured reader unreachable. A separate
checkpoint service would duplicate existing actors before their seams are used.
An owner-exposed scope and typed TaskContext extension keep the contracts together.

## Bound requests and make uncertain outcomes explicit

Each source partition retains only its current operation, either pending or completed.
Beginning a greater identifier retires the controller's previous cached result;
previously returned receipt handles keep their historical result.
The request identifier is the FlowMarker checkpoint identifier. Repeating that
identifier observes the same operation and never emits another marker. A different
identifier while pending returns Busy. Once completed, a greater identifier may
advance the source; older identifiers return Stale. Bound expected participants
before starting the job rather than growing an unlimited registry.

Acquire an opaque handle for the current registered source before sending a request.
Requests and cleanup compare its registration token, so a retry cannot target a
replacement reader accidentally. A request returns a receipt handle immediately. Waiting is separate from polling
output. Dropping or timing out that wait does not cancel or rename the operation;
the caller can retry its original identifier while that operation remains current.
The controller never interprets uncertainty as permission for a new durable effect.
NotReady, Unsupported, Busy, Stale and Closed are distinct refusals.

Registration belongs to the returned source stream. Reject duplicate active
registration, mint a distinct registration token and compare that token on cleanup.
An old stream cannot unregister its replacement. Scope revocation closes pending
receipts, including dequeued commands, and prevents late registration or acknowledgement.
New requests after revocation return Closed, even duplicates. Already successful
receipt handles retain their historical handoff, identified by their original scope
and registration; they never authorize a replacement attempt. Output errors and drops
must settle requests explicitly, without manufacturing EndOfData or durable success.
No actor handler should wait for source polling while holding its actor turn.

Commit an operation's immutable outcome while holding the scope lock, then release
the lock before notifying waiters, sending commands or dropping channel owners.
Waking a task can re-enter control code synchronously. Keep cancellation and success
atomic without running those callbacks inside the ownership lock.

## Put the cut inside the source

Only the source knows its input position. A generic wrapper cannot reconstruct it
from rows remaining after a filter. The native rate reader will process commands
in the same serialized loop that generates its batches. It encodes the matching
checkpoint marker before acknowledging the handoff and reports its exclusive
emitted-row ordinal for that live partition. No later data may overtake the marker.
A ready data deadline must retain fair progress when barriers arrive repeatedly.

The rate source currently resets its counter for every execution and derives
batch timestamps from the wall clock. Socket input has no replay or reconnect
contract. Both therefore remain nonrecoverable. The live ordinal is not a replay
position. Rate can opt into live barriers; socket and unsupported adapters receive
named refusals rather than fabricated positions. Exact replay will need a saved
origin, incarnation, partition interpretation and deterministic rows, or immutable
prepared output where that is sufficient for the admitted recovery protocol.

A zero-rate source must wake for commands even though it emits no data. A
backpressured source cannot acknowledge marker handoff until its output is polled.
Reaching EOF, cancellation and EndOfData remain different events. Repairing the
bounded-source adapter's final-checkpoint lifecycle and full completion protocol
remains separate work; it cannot be admitted as a recoverable participant here.

## Keep normal execution and Arrow behavior intact

Use a thin physical binding with complete child properties and schema. Without a
control scope it forwards the original execution stream directly. Native rate keeps
its ordinary path when no live registration is requested. Controls do not evaluate
user expressions or change payload projection. Extract a reusable event encoder
from the existing encoding implementation so the controlled reader can encode before
acknowledging, preserving all Arrow fields and existing encoding oracles.

The plan codec already carries child plans. Store only binding identity and capability
in the extension payload and reuse its one supplied child when decoding. Embedding
the child again would duplicate serialization and reconstruction work for every scan.

This introduces no durable store, new scheduler, expression framework or replacement
for Sail's flow events. Source routing is outside per-row computation. Measure
normal execution and controlled polling separately, retaining residual costs and
resource limits. A finite local corpus cannot establish production throughput.

Binding occurs once when execution opens and owns no operator metrics. Keep the
binding node in the tracing traversal, trace its child operators, and omit a separate
per-batch tracing wrapper and operator number for the binding itself. This preserves
the real operators' identities and metrics without adding polling work for metadata.
The binding's dedicated span is omitted; measure its context setup separately.
Verify actual exported child metrics as well as values, since correct output alone
cannot detect accidentally disabling all child instrumentation.

## Review three connected contracts

Review the ownership protocol first: bounded requests, registration replacement,
immutable receipts and cancellation. Then review identity preservation through the
task context, physical binding, optimizer and codec. Finally review the native reader
and local runner together, where marker handoff and output lifetime become observable.
These are distinct review boundaries within one working path. Keeping the ownership
state machine together makes its races easier to assess than splitting it across
connectors. Each boundary needs its own discriminating tests and the combined path
needs integration tests. Distributed routing and durable recovery add further contracts.

## Verify the contract before building recovery on it

Exercise the real local runner, planned binding, native rate reader and output
polling together. Check markers among exact data, zero-rate wakeup, zero-column
projection, duplicate requests, Busy, stale identifiers, missing participants,
invalid partitions, source errors, cancellation and drop. Verify distinct scans of
one provider, separate jobs using one compiled plan, and replacement registration.
Codec roundtrips must retain binding identity, capabilities and complete fields.
Preserve all task-context function registries and runtime/configuration extensions.

Use synchronization and controlled polling rather than deadline races as the primary
oracles. Run necessary concurrent lifecycle stress in an optimized build under load.
The preceding implementation and ordinary public queries remain controls. Retain
failed invocations separately from executed behavior, then qualify the cumulative
source on an immutable commit.

Does this owner-exposed control contract provide an ordered live boundary without
claiming replay or durable completion? Local end-to-end and lifecycle evidence
settles the first increment. Distributed task replacement, transport alignment,
replay, prepared effects and mandatory commit-time target fencing must settle
recovery before any durable pipeline is admitted.
