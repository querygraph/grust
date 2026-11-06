# Recoverable streaming tables on Sail’s flow events

Streaming tables append new rows without rebuilding the target. A crash or task
replacement must preserve both table effects and source progress. Build that guarantee
on Sail’s continuous flow events, with replayable input, durable preparation and
fenced commits that reject obsolete writers.

The first recovery domain is one flow: a declared computation feeding one target.
Begin with append output. Change capture adds keyed state to the same protocol;
general stateful operators and transactions across independent flows require further
contracts. Spark’s repeated bounded jobs are not the execution model.

A durable flow identity survives query and task attempts and process restarts.
Execution attempts are temporary owners of that identity; refresh creates a distinct
generation rather than silently reusing the old computation’s effects.

## Extend the components that already own execution

`StreamSource` describes a streaming scan. Sail’s rewriter lowers it into a plan
carrying flow events: data with retraction flags, or ordered latency, watermark,
checkpoint and end-of-data markers. A checkpoint marker identifies a boundary in
that ordered stream. Durable records must associate it with recoverable positions,
state and effects before it can support restart.

| Existing component | Addition or repair |
| --- | --- |
| Streaming rewriter and event encoding | Preserve exact Arrow schemas and row counts; evaluate user expressions only on data |
| Source planning and worker reconstruction | Declare replay capabilities and bind controls to the running source attempt |
| Fan-in, shuffle and replicas | Preserve input order and align checkpoint boundaries through the actual graph |
| Local job runner, driver and task actors | Coordinate within one job and reject commands or responses from obsolete attempts |
| Table writers and catalog commits | Publish immutable prepared effects with enforced ownership and reconcilable receipts |
| Memory pools and temporary storage | Account for transport, preparation and state, with spill or backpressure |

A dedicated flow-aware projection and changes to existing operators are alternative
ways to isolate expressions. The local reference uses flow-aware operators and
worker codec support. It preserves supported expression behavior, but mixed-marker
fragmentation remains costly. The choice must preserve markers before later data
that may fail, rather than evaluate a whole mixed batch and lose that ordering.

## Give sources a replay contract and a live control path

A planning descriptor cannot control a scan reconstructed on another worker. A
recoverable source declares stable identity, a versioned position format, retention
and bound capture. Each running partition registers controls under its source,
partition and task attempt. Route requests through the job runner and existing
cluster actors. Local mode needs no new driver; coordination across separate jobs
would justify a broader owner only when that capability is required.

Bind positions to the source incarnation, which distinguishes recreation from
continuation. Record the participating partitions and define how new partitions enter.
Detect missing retained input during every read. A bounded run captures identified
ends and reads exactly to them, including recreation checks for an empty end.
Several captured bounds are not automatically a simultaneous cross-source snapshot.

Native rate and socket sources do not provide this replay guarantee. A source that
can emit a checkpoint marker still needs a reproducible input boundary. Admit a
production source only after retention loss, recreation and task replacement tests
exercise its actual reader. Connector choice and dependency cost are delivery
questions; the replay contract is shared.

## Align boundaries without confusing closure with success

Initially allow one checkpoint in flight. Hold each participating input at its
marker until the others reach the same identifier. This avoids persisting rows
in transit but waits for the slowest participant. Queued requests or unaligned
checkpoints require additional saved state and a demonstrated reason for their cost.

Alignment must follow the actual transport graph, including shuffle and source
participation retained through optimization. A local merge is insufficient. Keep
ended input, closed transport, cancellation, failed execution and durable completion
distinct. A bounded source reaches its captured end and remains available for final
checkpoint completion. A bounded run succeeds only after its required effects finish.
Continuous execution uses the same protocol without captured ends.

## Prepare once, then recover those effects

Persist a prepared checkpoint before output commits. It binds exact source boundaries,
computation and normalized configuration identity, necessary state, output and effect
identifiers. Store immutable output chunks unless retained input and deterministic
computation prove identical replay. A source offset alone does not provide that proof.

For example, an append for rows through position 6 commits, but the response is lost.
Retrying with a fresh effect identifier can duplicate those rows. Reusing the original
identifier for rows through position 10 can lose the additional rows when the target
recognizes an already committed effect. Reconcile and finish the original effect
before advancing. An identifier must never acquire different content.

Delta’s application identifier and transaction version can recognize repeated appends.
They do not establish source replay or writer ownership. Each target must distinguish
accepted, rejected and unknown outcomes and reconcile the original identity. Where a
flow has several effects, record each completion separately. Recover partial progress
without claiming atomic visibility across tables.

Retain preparation and state while any pending effect or admitted restart point
needs them. Restore the state named by that point, not the newest file in storage.
Refresh prepares a new generation and resolves previously accepted work before
activating it. A successor may take ownership to finish that work. Missing
or corrupt recovery artifacts are explicit failures.

## Enforce ownership at acceptance

A fence rejects obsolete write authority where an effect is accepted. A lease merely
allows takeover: a paused owner can resume and reload the latest table head after
its lease expires. Ordinary table-version checks can then accept its stale authority.

The accepting authority must atomically check the owner epoch, a number that changes
on takeover, together with refresh generation, table incarnation, effect identity,
content and relevant table preconditions. Cover
creation, enrollment, schema changes, refresh, maintenance and worker writes. An effect
accepted before takeover may finish publishing its exact content; an old owner cannot
authorize new work. Authority failure must not enable an unfenced path.

Prefer an existing catalog that can enforce these checks. A commit service is an
alternative only where it controls every publication route, including permitted external
writers. A custom property honored only by Sail does not constrain another engine.
Build an enforced adapter for each admitted target. The first delivery can admit one;
managed Delta and Iceberg remain required adapter work before those paths are admitted.

## Bound costs and fix computation meaning

Account for transport queues, prepared chunks and operator state in bytes. Use Sail’s
memory pools and temporary-file facilities, with disk and retention limits. Whole-interval
buffering and periodic checkpoints do not establish bounded memory. Replacing an
unbounded replica queue with a blocking queue can deadlock fan-out; qualify progress
and total resource use together under slow consumers.

Normalize YAML, JSON and API input into one strict versioned type before dependent
planning. Reject unknown or duplicate keys, incorrect scalar types and conflicting
options, including within connector-specific typed schemas. Optional Dhall checks
authoring types and produces the same validated input; server validation remains
authoritative. Pin its compiler and bound imports and compilation resources; deployments
may accept rendered artifacts only. Bind the effective configuration into preparation
so a retry cannot silently change the computation.

Refuse unsupported output modes and retractions explicitly. Future event-time operators
must enforce Sail’s watermark promise that older timestamped data will not follow,
or propose a revised contract before relying on it. Window state and late-data policy
are separate decisions, not inherited consequences of checkpoint scheduling.

## Evidence needed for acceptance

The design requires real process and task restarts around preparation, acceptance,
publication and completion recording. Test unknown outcomes, stale owners, source
recreation and retention loss, actual transport alignment, final completion and resource
exhaustion. Component prototypes establish individual mechanisms; the integrated durable
path remains to be built.

The main implementation choices are the first source, enforcing target authority and
expression-isolation mechanism. Their recommendations and delivery dependencies are
in the review agenda and delivery plan. The [architecture reference](STREAMING-ARCHITECTURE.md)
and [fencing reference](FENCED-TABLE-COMMITS.md) provide optional contract detail.
