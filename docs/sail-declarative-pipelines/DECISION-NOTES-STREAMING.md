# Decisions for durable streaming and ordered changes

Streaming tables append new rows. Change capture maintains current records from
ordered updates and deletes. Sail's continuous flow events provide the foundation;
recovery must preserve their meaning through execution and durable publication.

These optional notes compare mechanisms within required guarantees: ordered
changes, safe control events, recoverable effects, bounded resources and fencing
for every admitted durable target. Each note supplies context for one mechanism
choice; its label is an optional reference identifier.

## S6. What must recover together

A flow is one computation feeding a target. A checkpoint fixes input boundaries
and their required writes. Recovery must preserve that association.

Suppose two append tables skip transaction identifiers already committed. One
commits before a crash. Reusing its identifier for replay plus new arrivals
loses new rows there; assigning the entire replay a new identifier duplicates
old rows. Preserve each prepared interval and each write outcome until completion.

Prefer independently recoverable flows over cross-flow coordination. For keyed
changes, prefer atomically publishing user rows and a reference to durable
key/version/deletion state when the target supports it. Separate state and target
tables are viable but require recovery of partially completed effects. Recovery
does not provide atomic visibility across tables.

Which target representation preserves ordinary table reads at acceptable cost?
Interrupt publication, introduce new input and recover every original effect
before claiming the selected scope works.

## S1. Where checkpoint coordination belongs

A checkpoint fixes input boundaries and tracks their durable effects. Its owner
must reach every participating execution task. Sail's local job runner executes
in the session process; cluster execution reconstructs source scans on workers.
A planning-time source object cannot control those fresh scans.

Prefer job-runner ownership for recovery within one job. Register control
endpoints with running task attempts, route requests through existing execution
ownership and reject acknowledgements from replaced attempts. Keep query
registration and cancellation in the existing lifecycle manager.

Broader coordination is justified only by recovery spanning jobs. Adding a local
driver merely for uniform placement increases machinery without supplying durability.

Can the existing runner own the selected recovery scope? Trace requests and
acknowledgements through actual local and cluster execution, including worker
replacement and restart with stable flow identity.

## S2. How a source participates

Recovery needs more than an offset. A source descriptor identifies the broker
or storage location, stream and partition incarnation. An incarnation distinguishes
recreation with reused offsets. Sail's source interface supplies scans but not
these recovery guarantees.

Prefer optional typed recovery capabilities over pretending every source can
resume. Require exact position meaning, replay availability, coordinated end-bound
capture and pinned participants for each prepared interval. Define discovery and
bootstrap of new partitions separately; earliest retained data is not automatically
a complete history.

Preserve source provenance outside user projection, or require an admitted event
envelope. Replacement-event identity can derive from source incarnation, key under
declared equality rules and complete per-key order; a broker identifier is optional.

Which source satisfies these contracts? Test recreation, retention loss, partition
addition and overlapping requests. Unsupported sources remain usable for narrower
operations, but cannot claim durable recovery.

## S4. How control markers traverse execution

A checkpoint marker identifies an ordered boundary. A durable prepared record
must associate it with source positions, state and effects before it supports
recovery. Marker isolation from data expressions is required, not a selectable
policy.

Use flow-aware operators that evaluate data only. At every admitted exchange,
route markers to all required participants and establish a consistent boundary
before snapshotting or forwarding. Ordinary asynchronous fan-in and payload-based
hash routing do not provide that contract.

Alignment pauses faster inputs. Recording rows still in transit can avoid that
pause but adds recovery state and complexity. Prefer alignment initially while
measuring slow-input effects. Preserve latency, watermark, checkpoint and terminal
marker ordering explicitly.

Should the first admitted exchanges align inputs or record in-flight rows?
Exercise real projections, filters, unions and exchanges locally and across
workers. Encoding tests alone do not qualify a distributed execution graph.

## S9. How bounded execution finishes

A bounded run fixes an end position for each participating source. Independent
bounds are not an atomic snapshot of all sources. Capturing bounds concurrently
with readers requires coordination so consumption cannot pass an uninstalled bound.

Fixed ranges, source identity and participants define the bounded run. Choose
how its owner coordinates capture and installation. Define new-partition discovery
separately. An input's end marker and later closure count once. Ended inputs retain
their assigned checkpoint acknowledgements until the protocol releases them.

Input exhaustion, cancellation, failure and durable success are different outcomes.
Sail's query lifecycle and bounded adapters need that distinction; a closed stream
or consumed error cannot establish successful writes.

Which existing execution owner confirms completion? Stagger input endings, close
a channel unexpectedly and fail the final write. Success must wait for every
required durable effect, with failures visible to the caller.

## S3. When checkpoints start

A checkpoint prepares a recoverable input interval. Frequent checkpoints reduce
replay distance but increase snapshot and commit work. A bounded run can need
several checkpoints before its final one.

Prefer time or byte-volume triggers plus final completion, with one outstanding
request initially. A final request must not overwrite an ordinary request awaiting
acknowledgements. The trigger is an operational choice, not a business ordering rule.

Cadence alone does not bound memory. Account for transport, operator state,
prepared output and snapshot workspace across tasks. Reuse Sail's memory pools,
backpressure and bounded spill. Preserve ordered control progress; replacing
unbounded fan-out buffers with blocking queues can deadlock.

Which limits fit the workload? Run a large backlog against a slow target and
request completion during a pending checkpoint. Verify bounded resources,
termination and unchanged results under different checkpoint grouping.

## S5. How operator state is stored

Stateful operators retain information between batches. Their recovery snapshot
must match an exact input boundary. A manifest names the immutable files composing
that snapshot and its operator configuration.

Reuse Arrow files and durable object storage for state sizes where full snapshots
are practical. Partitioned or incremental snapshots cost more implementation work
but may be necessary at larger cardinalities. An embedded key-value store remains
an option, not a prerequisite.

Restore the recorded snapshot, never simply the newest file. Check semantics and
configuration as well as schema. Retain all artifacts needed by pending effects
and valid restart points. A newer source-position record does not authorize
cleanup. Temporary spill is not durable recovery storage.

What state-size envelope is required? Interrupt publication and cleanup, restore
shrinking state, and measure snapshot cost with stalled progress before selecting
the storage implementation.

## S7. What a watermark promises

Event time is a row's timestamp. Sail's [watermark marker](https://github.com/lakehq/sail/blob/85c6cca01cd521dd778bc200c987a34edf141de1/crates/sail-common-datafusion/src/streaming/event/marker.rs#L18)
promises that no later row has an older timestamp. Observed timestamps minus a
delay do not alone establish that promise because late rows can arrive afterward.

Preserve this contract. Handle excluded late rows before they enter
the downstream stream, including arrivals after emission. A distinct threshold
marker with downstream admission rules is an alternative requiring explicit
semantics, not a silent reinterpretation.

Specify progress for every input, including missing watermarks, termination and
reactivation. Idleness alone proves no completeness. Restore the progress needed
to preserve those rules; checkpoint placement must not determine lateness.

What late-data policy does the workload need? Test delayed arrivals and restart
under changed input interleavings. Define window closure and permitted updates
from that policy before admitting window aggregation.

## S8. Which operators belong in the first scope

Sail's streaming rewriter admits a narrow operator set. Preserving the event
encoding does not make ordinary operators safe for markers or retractions,
which cancel previously emitted rows.

Start with marker-safe stateless transformations and durable append. Add ordered
whole-row replacement and deletion when required by the user scenario. Their
per-interval reduction and durable current versions do not require retaining
all historical events in a streaming operator.

Windows and duplicate removal require independently qualified state recovery
and resource bounds. Joins, aggregates and partial-row patches also need explicit
output identity and composition contracts; they must not inherit replacement-event
semantics accidentally. Reject unsupported shapes during planning.

Which operators make the first capability useful? For each admitted shape,
verify optimizer transformations, marker handling, recovery and resource growth.
A smaller scope can defer capabilities but cannot waive correctness within it.

## S10. Apache Iggy as a source

Apache Iggy is a partitioned message broker. Its offsets locate messages but
need broker, stream, partition and incarnation identity to support safe recovery.
Offsets across unrelated partitions do not automatically order business changes.

Keep the broker client in an optional crate. Check replay availability and
identity throughout reading and end-bound capture. Pin checkpoint participants;
new partitions need an explicit discovery and bootstrap policy. Preserve message
provenance through decoding or require an event envelope carrying equivalent
identity and ordering information.

Broker acknowledgements and durable pipeline progress are separate contracts.
Client dependency changes also require their own build assessment; a feature
flag does not resolve incompatible dependency versions.

Is this broker needed initially? Test retention loss, recreation, partition
addition and concurrent end-bound capture. Select it only after source correctness
and dependency compatibility are demonstrated independently.

## S11. How ordered changes are validated

A normalized change contains a key, complete per-key order, stable identity,
whole-row upsert or delete, and payload. Greater orders win for both actions.
Equal order with identical action and logically equal payload is a duplicate;
different content is a conflict. Retain deleted keys' winning orders.

Evaluate normalized values once, validate every original row, then reduce.
Require deterministic normalization by default. Other computations need separately
persisted immutable normalized input. Saving winners stabilizes retries but cannot
repair an initially schedule-dependent winner.

Default verification covers conflicts within the prepared interval and against
the durable current version, including identity consistency within retained scope.
It does not detect every contradictory superseded event in history. Exhaustive
verification requires an explicit retention horizon and resource budget.

This deliberately replaces Spark 4.2.1's [undefined ties and action-dependent equality](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/Scd1BatchProcessor.scala#L80).
Is verification against current state sufficient, or is budgeted historical
conflict detection needed? Test invalid losing rows, conflicting equals, delete resurrection, retries
and regrouped checkpoints with exact normalized values.

## S12. How identity changes and rebuilds work

Changing entity keys or ordering semantics changes the meaning of durable state.
A rebuild must not reuse unrelated positions, validation evidence or write tags.
A declaration reorder that preserves identity need not force rebuilding.

Prefer explicit migration into a new fenced generation, meaning a separately
identified version of the flow and target state. Resolve pending effects before
switching authority. Publish the new generation atomically where the target
supports it; otherwise specify interrupted-reset recovery and reader visibility.

A consistent authoritative snapshot plus a log frontier can establish a baseline.
Physical offset zero is not universally required. Verify that the available
baseline and retained changes can reconstruct the requested state before destructive
work. Missing deletion versions or discarded ties cannot be inferred afterward.

Which migrations are needed initially? Interrupt initialization, publication and
cleanup, including with unavailable history. Define schema and table identity
behavior for external readers before choosing a representation.

## S13. How targets reject obsolete writers

A lease permits ownership takeover. A fence rejects obsolete ownership atomically
where a durable effect is accepted. Checking ownership before an ordinary table
commit is insufficient: a paused writer can resume after its successor.

Require fencing for every admitted durable target. Extend existing catalog and
format commit interfaces; build missing filesystem Delta, managed Delta and
Iceberg adapters. Cover creation, reset, schema changes and maintenance as well
as data writes. Every permitted external writer must use the same authority or
an enforced protocol that prevents bypass.

Prefer an existing authoritative catalog. A new commit service is justified only
if it can enforce publication. Exact bytes accepted before takeover may finish
publication; the obsolete owner cannot authorize new effects. Reconcile uncertain
outcomes by their original identity.

Which authority can enforce each target? Pause writers across takeover and test
all commit paths with authenticated worker access. Until adapters enforce the
contract, targets remain unadmitted; external single-writer assurances are no substitute.
