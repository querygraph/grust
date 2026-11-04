# Streaming tables and change capture: architecture questions

Internal working architecture for the discussion packet. Every component
choice below is proposed. No maintainer answer has been recorded. This document
describes required properties and candidate mechanisms, not an approved
production coordinator or a claim that the prototypes establish recovery.

## Decide the recovery domain first

A checkpoint identifies an input boundary, operator state and output effects.
The recovery domain is the set of effects that must complete together.
The maintainers must choose among these scopes before placement is settled:

| Candidate scope | Required recovery work | Deliberately excluded |
| --- | --- | --- |
| One append flow into one transactional table | Stable identity, positions and state paired with its table commit | Change capture and shared recovery across tables |
| One flow, including change capture | The preceding work plus sealed rows and separate receipts for auxiliary and target writes | Shared recovery across independent flows |
| Several flows or sinks together | A shared prepared boundary and completion accounting for every participating effect | No additional exclusion decided yet |

A single logical change-capture sink still has two physical table effects.
Choosing one flow per domain therefore does not eliminate partial commits.

## Why positions and tags are insufficient

Suppose both tables committed checkpoint 1 at input position 3. Checkpoint 2
records position 6, but only A commits it. Restart from position 3 and reuse
identifier 2 at position 10: A skips rows 6 through 9. Use identifier 3 instead:
A receives rows 3 through 5 twice.

Recording positions before commits prevents an effect from having no recorded
boundary. It does not permit replacing a partially committed boundary. Reading
the least committed identifier is likewise insufficient without preserving the
outstanding prepared work. The [transition model](evidence/redesign-discussion-1/checkpoint_boundary_model.py)
and its [result](evidence/redesign-discussion-1/checkpoint-boundary-model.json)
demonstrate this logical failure; they do not execute the Rust coordinator.

## Components and ownership candidates

| Component | Existing foundation | Proposed responsibility or open choice |
| --- | --- | --- |
| Pipeline layer | Registration, analysis and scheduling | Build admitted flow-event plans; own user-visible run completion |
| Streaming rewriter | Sources and stateless streaming operators | Add only the operators admitted by the chosen scope |
| Job runner and driver | Local execution without a driver; cluster execution with worker scans | Candidate coordinator ownership, conditional on whether the recovery domain fits a job |
| Checkpointable source | Prototype rate and Iggy implementations | Stable identity, exact position semantics, replay capability, bound capture and explicit checkpoint participation |
| State store | Prototype Arrow snapshots and manifests | Immutable prepared snapshots, contract checks and recovery-aware retention |
| Append sink | File sink and separate Delta write-option prototype | Tagged writes under the accepted identity and completion protocol |
| Change-capture sink | Existing bounded runtime's validation, sealing and merge paths | Adapt archive and individual effect receipts to checkpoints; not implemented in the streaming prototypes |

The source interface must not silently treat a non-resumable source as safe.
Repeatable rows are also weaker than repeatable computation: nondeterministic
expressions and watermark interleaving can change output.

## Candidate prepared-checkpoint contract

If the accepted scope includes partial effects, a candidate is a durable
prepared record before the first output commit. It would bind:

- Stable flow identity and refresh generation, distinct from a transient query handle.
- The participating sources, their incarnations and exact input boundaries.
- The operator manifests and the schema and plan contract they describe.
- Sealed output artifacts where re-evaluation is not an accepted recovery mechanism.
- Evidence that every original change row passed the required validation.
- The participating table effects and a separate completion receipt for each.

This is a contract to discuss, not a new control-store implementation request.
Reuse of the current control model should be evaluated before inventing another
log. Storage placement, atomic publication and power-loss guarantees remain open.

A possible execution order is alignment, state and artifact preparation,
durable publication of the prepared record, then individually tagged effects.
Recovery finishes the original prepared effects using their original identity.
It cannot assign newly evaluated rows to a tag that an effect already holds.
Source replay, if used, must reproduce the exact accepted boundary and semantics.
An archive may instead supply already prepared output without re-reading it.

The coordinator may report completion only after every required effect is
confirmed. An output stream ending is not itself that confirmation. Visible
partial table effects can exist before overall completion; this proposal does
not provide atomic visibility across independent tables.

## State retention and source completion

Recovery loads the manifest named by the accepted recovery record, not the
newest manifest. A snapshot referenced by outstanding work remains immutable.
Reclamation must retain everything needed by incomplete effects and the oldest
valid restart point. Merely recording a newer source position cannot authorize
deletion of older state. Schema equality alone is not a complete operator
compatibility check.

A bounded source captures its end in coordination with its reader and checks
incarnation while doing so. Otherwise consumption can pass the captured end,
or a recreated empty partition can appear already finished. End of data means
no further rows, not release from every checkpoint obligation. Independent
source bounds do not imply one atomic pipeline-wide snapshot.

An input that ends and later closes must count once. Ordinary and final
checkpoint requests must not overwrite each other. Serializing requests is a
candidate initial rule; explicit request queues are another. If periodic
checkpoints are admitted for bounded runs, final completion must wait for
outstanding checkpoints and then the globally final checkpoint.

The current append sink holds interval data in memory. A final-only policy
therefore needs an admitted size limit or spill policy. Cadence alone is not
a memory bound: slow commits, open-window cardinality and stalled watermarks
also need resource controls. Full snapshots trade replay distance against
state materialization and write cost. No performance claim is established.

## Watermark contract remains open

Upstream's marker promises that a source emits no later row with an older
timestamp. An observed-event-time threshold does not itself establish that
promise. S7 asks whether to enforce the existing guarantee before emitting a
marker or explicitly change the marker's meaning and downstream obligations.
The proposed acceptance of an older row into a still-open window must fit that
answer. It cannot be called an unchanged contract without resolving this.

Combining inputs, excluding ended inputs and restoring watermark progress are
separate decisions. The recorded-event prototype does not establish recovery
under different input schedules. Preserving only a combined watermark while
resetting input trackers is not assumed sufficient here.

## Change-capture obligations to preserve

Validate original rows before reducing them. A losing row with a null sequence
must not disappear before validation. Reduce within the checkpoint interval,
retain deletes and their sequences, and seal the winners once before effects.
Ordering across intervals remains a responsibility of the target and auxiliary
tables in the existing runtime, not an unbounded map of every key in the reducer.

There are two distinct tie guarantees. Sealing makes retries use the same
chosen winner. A deterministic winner across independently scheduled sources
also needs an explicit total provenance order. The prototype uses row index
in an already ordered batch and establishes only that narrower case.

Retain auxiliary-table and target-table outcomes separately. Do not discard
sealed rows or their validation evidence because one table committed. A
source retention gap may prevent future reading without invalidating an
already sealed effect that recovery can finish from its archive.

Preserve stored-key checks, name resolution, schema selection and target
capability refusals. Full refresh must check source history before destructive
reset under the proposed Sail retained-origin policy, and define what happens
to interrupted effects and old identities. Preserve enrollment, fencing,
target-recreation checks and reset contracts where the existing runtime
enforces them. Catalog commit ordering is not evidence of an equivalent
stale-writer fence.

## Evidence and its limits

The reviewed prototype heads are P4 `4fad33ca5`, covering P1 and P2 against
upstream `62251e0a2`, and P3 `ef5f848a7` on the integration branch. The current
runtime was inspected at `99dc47788`. The review did not rerun Rust, Spark or
broker suites. Historical prototype results remain distinct from new source
inspection and the transition-model counterexample.

| Inspected evidence | What it establishes or leaves open |
| --- | --- |
| `sail-physical-plan/src/streaming/merge.rs:135` in P4 | Ended and closed counts can count one input twice; controlled reproduction remains open |
| `sail-common-datafusion/src/streaming/checkpoint.rs:98` and `sail-data-source/src/formats/rate/checkpoint.rs:116` in P4 | Requests are not serialized and use a latest-value channel; overlap needs a controlled test |
| `sail-physical-plan/src/streaming/state_store.rs:132` in P4 | Retention API allows removal after recording; no active call site was found |
| `sail-physical-plan/src/streaming/changes.rs:20` in P4 | Tie rule uses supplied row order, not source provenance |
| `sail-iggy-bounded/src/stream.rs:198,459` in P3 | Bound capture lacks an incarnation check before early completion |
| `sail-delta-lake/src/physical_plan/planner/op_write.rs:51` and `sail-delta-lake/src/transaction/mod.rs:1390` in P4 | Concurrent table creation may bypass transaction revalidation; an unexecuted source-path inference |
| Runtime `autocdc/write.rs:420,441,474` | Original-row validation precedes reduction; winners are sealed once |
| Runtime `autocdc/durable.rs:672,711,737,774` | Archive restoration, preparation before effects, separate effect checks and completion after effects |
| Runtime `autocdc/prepared.rs:11` | Stronger identity-bound validation receipt is modeled and tested separately, with production wiring still pending |

Prototype paths are relative to each named checkout's `crates` directory;
runtime paths begin at `crates/sail-spark-connect/src/pipelines`.
Primary Spark-source evidence is recorded in
[evidence/redesign-discussion-1/SPARK-SEMANTICS.md](evidence/redesign-discussion-1/SPARK-SEMANTICS.md).
This architecture does not derive Spark parity from prototype tests.

## Reuse assessment

| Preserve or adapt | Boundary of the claim |
| --- | --- |
| Flow binding, admission and name resolution | Recheck admitted shapes when planning changes; not a wholesale unchanged-code claim |
| Validation before reduction and sealing once | Keep the behavior even if interval construction changes |
| Archive identity and replay, individual effect receipts | Checkpoint identifiers replace sequencing units, not these obligations |
| Merge semantics and target capability checks | Adapt under verified source semantics and the selected target scope |
| Lease, fencing, enrollment and refresh rules | Preserve actual target coverage; no claim all catalogs are fenced |
| Window and deduplication rules and tests | Adapt event scheduling and recovery; do not label changed outcomes as parity |
| Existing Spark suites | Preserve as evidence and regression coverage; rerun applicable suites after implementation |

Replace bounded scan scheduling and per-batch execution loops only after the
accepted streaming plan preserves their required behavior. Do not classify
intent identity, archives or validation receipts as obsolete plumbing.
Joins and unsupported table formats do not become supported through reuse.

## Next decision and allowed work

Present S6 first, then source participation and coordinator ownership. The
decision register records the options, evidence, maintainer answer and the
scope that answer permits. No answer has yet authorized production work.
Any local experiment should test one disputed property and retain its limits.
The next deliverable is the concrete discussion packet for owner review,
not an automatically expanded coordinator prototype.
