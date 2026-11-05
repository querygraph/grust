# Recoverable streaming tables on Sail’s flow events

Streaming tables append newly available rows without rebuilding the target.
Users need a crash or task replacement to preserve both data and source progress.
Build that guarantee on Sail’s existing continuous flow events and execution
ownership, with durable preparation and fenced table commits.

The first recovery domain is one flow, a computation feeding a target. Broader
multi-flow transactions and stateful operators are separate capabilities. Spark’s
batch scheduling is not the execution model or a constraint on correctness.

## Extend the existing foundation at its real boundaries

`StreamSource` describes a streaming scan. Its provider becomes a flow-event
source through Sail’s streaming rewrite. A flow event contains data, retraction
flags that cancel earlier rows, or a marker for latency, watermark, checkpoint
or end of data. The marker ordering is useful, but does not itself save progress
or commit output.

Native rate and socket sources demonstrate streaming; their current contracts
do not qualify them as replayable production sources. Add optional recovery
capabilities without forcing nonrecoverable sources to claim durability.

| Existing component | Required behavior |
| --- | --- |
| Rewriter, projection and filter paths | Evaluate expressions only on data; preserve control events without inventing user rows |
| Arrow event encoding | Preserve row counts, exact types, field/schema metadata and unambiguous control-column identity |
| Fan-in, shuffle and replicas | Preserve per-input order and align checkpoint markers through the actual graph |
| Job runner and cluster actors | Coordinate recovery inside one job and address live source task attempts |
| Table writers and catalog commits | Publish fixed prepared effects with enforced ownership and reconcilable receipts |
| Query lifecycle | Distinguish final durable success from closure, cancellation and failure |

Focused unchanged-module probes reproduced strict-cast errors on marker placeholders,
zero-column decode errors, decimal marker mismatches and schema metadata loss.
Source inspection found plain fan-in and an unbounded local replica overflow queue.
Repair these foundations before treating additional marker-aware operators as a
complete streaming system. A flow-aware adapter is preferable to guarding each
kind of user expression separately.

## Separate source descriptors from running controls

A source scan is reconstructed on a worker, so an object retained during planning
cannot control its runtime instance. A recovery-capable descriptor declares source
identity, position format, replay guarantees and bound capture. Running partitions
register control endpoints with source, partition and task-attempt identity.
Existing job and driver actors route commands and reject obsolete attempts.

Bind recoverable positions to the source descriptor and its incarnation, which
distinguishes recreation from continuation. Record the participating partition
set. Newly discovered partitions need an explicit bootstrap policy; starting them
silently at the earliest retained offset may omit required history.

A source must detect missing retained data on every read, including during a
run. A bounded run captures ends with their identities and reads exactly to them.
Capturing an empty end must not bypass recreation checks. Bounds across several
sources need not be one simultaneous snapshot; any stronger claim requires a
source-specific contract.

Apache Iggy is one optional broker candidate. Its exact-range reader, decoder and
incarnation checks are useful. The stream prototype still needs topology and
bound-capture qualification, planner integration and dependency admission. Another
source can establish the core protocol without taking on that client first.

## Make checkpoint participation explicit

A checkpoint binds a source boundary, relevant operator state and required output
effects. Initially serialize requests and hold each participating input at its
marker until the others reach the same identifier. This alignment avoids saving
in-flight rows, but can wait for a slow input. Queued or unaligned checkpoints
are alternatives only if their extra state and recovery cost are justified.

Use the job runner when the recovery domain fits one job; distributed execution
delegates through the driver and running tasks. Local execution needs no new
driver. Stable flow identity must survive query attempts and process restarts;
a refresh creates a distinct generation.

An ended input, a closed channel and a completed effect are different facts.
A bounded run permits intermediate checkpoints, then succeeds only after its
final prepared work is durable. A continuous run uses the same protocol without
captured ends. Explicitly reject unsupported trigger, output and retraction
semantics rather than quietly choosing append behavior.

## Prepare output before committing it

Persist the checkpoint’s exact boundaries, normalized configuration, semantic
version, state references and effect identities before table effects. Persist
immutable output chunks when replay cannot guarantee identical rows. Positions
alone do not guarantee source retention, deterministic transformation or stable
output after a restart.

If an effect already committed, its identity must never acquire more rows. For
example, one sink commits rows through position 6 and another fails. Retrying
that identity through position 10 loses the extra rows at the completed sink;
a fresh identity can instead repeat the original rows. Finish the original
pending effects before advancing them.

Delta’s application identifier and transaction version can identify repeated
append writes. They do not supply owner fencing, stable flow identity, refresh
separation or a complete checkpoint protocol. Other targets need equivalent
commit and reconciliation capabilities, not merely metadata carrying a tag.

For one flow with several effects, record each completion separately. Recovery
can finish partial progress without promising atomic visibility across tables.
Retain preparation and state until no pending effect or admitted restart point
can use them. Restore the state named by that recovery point, never simply the
newest snapshot found in storage.

## Enforce ownership and bound resource use

Every durable target needs a commit-time fence: the accepting authority atomically
checks owner epoch, generation, table incarnation, effect identity and content.
A lease or catalog table-version check alone cannot stop a stale writer that
reloads the latest head. Build the missing managed Delta and Iceberg enforcement
paths; do not offer an unfenced durable fallback.

The contract covers creation, enrollment, schema mutation, refresh and worker
commits. A cooperating Sail-only property cannot constrain external engines;
all permitted writers need the enforced protocol. An effect accepted before
takeover may finish publishing its exact content, but an old owner cannot accept
new work. Unknown outcomes require reconciliation under the same effect identity.

Use Sail’s memory pools and temporary-file facilities to budget transport,
preparation and state. The append prototype buffers a whole interval and the
local transport can accumulate unbounded overflow. Replace those assumptions
with byte accounting, chunked artifacts, spill or backpressure. A blocking queue
alone can deadlock a fan-out graph, so qualify aggregate resource bounds and
progress together under slow consumers. Periodic checkpoints are not memory limits.

## Event time and intentional differences from Spark

Sail’s watermark marker promises that older timestamped data will not follow.
A threshold derived from observed timestamps does not establish that promise
when late data may arrive. A future event-time operator must enforce the promise
at its declared plan position, or propose an explicit revised contract.

For multiple inputs, progress must reflect all active participants and survive
recovery with the evidence needed to preserve it. Do not discard per-input progress
or truncate precision solely because Spark does. Keep event-time policies independent
of checkpoint scheduling. Windows and deduplication need their own state and
late-data contracts before admission.

Strict typed configuration applies equally to YAML, JSON and APIs; optional Dhall
is an authoring frontend, not a second runtime. Validate effective options before
dependent planning and bind their semantic identity to prepared work.

## What settles the implementation choices

Choose the first replayable source and the target authority that can enforce
all publication paths. Demonstrate real restarts around preparation, commit and
completion, stale-writer rejection, source recreation, barrier alignment and
bounded resources through actual local and distributed plans.

Existing prototypes cover controlled marker alignment, a simulated file-sink
restart and separate Delta write options. They do not establish durable distributed
coordination, the integrated fenced sink or the production planner path. Those
are required implementation work, with component failures and preserved controls
providing focused starting tests.
