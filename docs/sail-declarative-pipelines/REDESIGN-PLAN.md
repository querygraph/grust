# Implementation plan for streaming pipelines and change capture

Streaming pipelines append new data and apply keyed changes without rebuilding
the target on every run. They need a restart protocol that preserves source
progress, intermediate state and committed table writes together. This plan
builds that protocol on Sail's existing streaming sources and ordered flow
events, then adds only the operators needed by the selected use case.

The proposed first scope is one flow, a computation feeding a target, with
change capture included if its two-table recovery contract is accepted.
Append-only output is a smaller alternative. Coordinated recovery across
independent flows, streaming joins and general stateful coverage are deferred.

## Establish the recovery boundary

A checkpoint names an input boundary, associated operator state and required
output writes. Its recovery domain is the set of writes whose completion is
tracked together. One append target may fit one transaction. Change capture
also writes an auxiliary table of deletion sequences, so one flow can have
two separately committed effects.

The first decision is whether both effects belong in the initial scope.
If one commits before a crash, recovery must finish the other with the same
intended rows. Reusing a committed checkpoint identifier for a wider input
range can lose rows; assigning a fresh identifier to already committed append
rows can duplicate them. The input boundary and the identity of its output
must remain stable while any effect depends on them.

A candidate protocol persists a prepared record before output commits. It
binds source positions, state, saved output where needed, and each effect's
completion record. An alternative can rely on source replay only if it proves
identical input and computation remain available. Reuse existing durable
publication and effect-tracking mechanisms before introducing another store.

This decision precedes component placement because a domain inside one job
can use its job runner, while a domain spanning jobs might require different
ownership. It also determines how much state and output must survive partial
completion. Correct recovery does not imply atomic visibility across tables.

## Agree the contracts needed by the selected path

| Contract | Proposed starting point | What would justify another choice |
| --- | --- | --- |
| Coordination ownership | Job runner when the domain fits one job; driver and running tasks in cluster mode | Recovery participants spanning several jobs |
| Source capability | Optional interface defining identity, position meaning, replay and bounded-end capture | A simpler existing interface that expresses the same guarantees |
| Checkpoint boundary | Align each input at the same marker and serialize requests | Measured alignment cost that justifies saving in-flight rows or queuing requests |
| Bounded completion | All source bounds reached, then required final checkpoint effects completed | A separately specified user-visible stopping contract |
| Checkpoint scheduling | Intermediate checkpoints plus a final bounded checkpoint, with resource limits | Volume triggers or spill better matching the workload |
| Retry output | Persist selected output when replay cannot guarantee the same result | Proven repeatable source input and transformations |
| Stateful operators | Add only those required by the use case, with explicit state recovery | A use case needing windows, duplicate removal or broader operators |
| Source and target admission | One pair with demonstrated replay, commit and ownership behavior | Additional pairs carrying equivalent evidence |

These are interacting contracts. Scheduling must respect the completion
protocol; state size can change scheduling choices; a source may constrain
replay and refresh. Resolve those interactions before implementing the
dependent path. A stateless append path does not need a window state store,
and an optional broker client need not block another suitable source.

## Prove one complete source-to-table path

Implement the selected path through a source, checkpoint, durable target
commit and restart. Begin with planning-time refusals for unsupported sources,
operators and targets so the supported guarantee is explicit.

The path needs the following checks:

- Interrupt before and after each output commit. Recovery must preserve the
  original boundary and produce the required result without lost or repeated effects.
- Interrupt after preparation but before completion is recorded. Confirm
  that the target's actual outcome can be reconciled safely.
- Delay one input, end another, and request an ordinary and final checkpoint
  close together. No input may skip a checkpoint or count as completed twice.
- Change source identity or remove unread retained data. Fail explicitly
  rather than advance progress past missing input.
- Replace a writer and resume the previous writer. Verify the target rejects
  stale ownership wherever that guarantee is promised.

A file-sink test that retains positions in memory does not establish process
restart durability. Separate Delta transaction-option tests do not establish
an integrated streaming sink. The complete path must exercise the actual
source, recovery record and admitted target together.

## Include change capture without weakening its semantics

A change row carries a key, sequence value and action. An upsert inserts or
updates that key; a delete removes it.
Validate every original row before choosing one winner per key for a
checkpoint interval. Invalid rows must fail even if reduction would discard
them. Seal the winners by saving them unchanged before either table write,
then track the auxiliary-table and target-table effects separately.

The sequence comparisons follow Spark 4.2.1: target upserts accept equal or
greater sequences; target deletes require a greater sequence. The auxiliary
table retains deletion sequences to reject older events. Ordering across
intervals belongs in the tables, without retaining every target key forever
in an operator. Spark leaves equal-sequence selection within a batch undefined;
retrying a sealed interval must nevertheless preserve its chosen winners.

Before this path is durable, define how validation evidence identifies its
input and schema, how full refresh creates a new recovery identity, and how
writer ownership is enforced. A refresh rebuilds the target and needs an
explicit policy for available source history before destructive effects.
A writer fence rejects writes from an older ownership number. Commit ordering
alone does not establish that fence.

Exercise failure between the two table writes and during refresh. Compare
source-to-table behavior with Spark 4.2.1 for the selected cases; document
intentional differences separately. Preserve existing supported validation,
merge, archive and ownership guarantees until the replacement passes those
checks. Verify that the actual write path checks validation evidence before
either table effect begins.

## Add stateful operators only with their missing contracts

Windows and duplicate removal need saved state tied to the checkpoint that
produced it. Immutable Arrow snapshots and manifests naming their files are
one starting point. Choose them only if full-snapshot cost is practical for
the intended state size. Keep every snapshot needed by incomplete writes and
valid restart points; a newer recorded position is not permission to delete it.

Sail's watermark marker promises that older timestamped rows will not follow.
A threshold derived from observed timestamps does not ensure that promise.
Either enforce the contract before rows enter the downstream stream,
including arrivals after a watermark, or explicitly change what downstream
operators may assume. Only then implement window
closure, late-row handling and recovery of watermark progress.

Test independently scheduled inputs, growing key counts, slow commits and
stalled watermarks. Periodic checkpoints do not bound memory. Establish byte
limits, backpressure or spill and measure snapshot and recovery cost. Recorded
event replay alone cannot establish correctness under different interleavings.

## Replacement and expansion criteria

Replace an existing path only when the selected implementation demonstrates
its declared recovery and compatibility contract. Broader sources, targets
and operators require their own capability checks and failure cases.

The current mechanism evidence covers marker transport and alignment, a
simulated single-file-sink restart, separate Delta write options, broker
resume checks and state restored from recorded events. Durable coordination,
streaming change-capture merges and the integrated end-to-end replacement
remain unbuilt. Those gaps define the next technical work; the existence of
component tests does not establish the complete protocol.
