# Engineering audit of streaming and change-capture semantics

## Conclusion and evidence boundary

Replace compatibility-driven nondeterminism, action-dependent equality rules,
mandatory two-table storage, and unfenced durable admission. Retain independently
useful properties: stable identity, nonambiguous keys and order, validation of
all original events, anti-resurrection state, immutable prepared work and
explicit completion. Spark is a source of examples and migration behavior,
not the correctness specification for the new engine.

This audit inspected source. It did not execute Spark, Sail, Delta, Iceberg or
broker suites. The accompanying `semantics_model.py` is a small Python algebra
model; its output is in `semantics-model.json`. It checks source-derived rules,
not either engine. Proposed mechanisms below remain unimplemented.

Sources are pinned as follows. Every abbreviated path below expands against
these roots; line numbers refer to these versions, not a future working tree.

| Prefix | Root and reference |
| --- | --- |
| D | `/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines`, document HEAD `f23da50ccdf4ac1258fa1c6803aeb54df042a03e` |
| R | `/Users/alexy/src/sail-pipelines-proposal/crates/sail-spark-connect/src/pipelines`, runtime `99dc47788941daf28eec847527949a4cadafdbd2` |
| S | `/Users/alexy/src/spark-sdp-4.2.1`, Spark `617618396087429b5627a86ce933bb0f5d6645cb`, version 4.2.1 |
| U | Sail Git object `85c6cca01cd521dd778bc200c987a34edf141de1`; inspected through the Sail repository |

The current eight streaming documents were read completely in their preceding
editorial review and their semantic claims were inspected again here. The
older activation, control-store, reuse, runtime-review and configuration
documents were searched for retained compatibility assumptions. They are
lineage evidence, not acceptance of their outdated status statements. This
ledger covers semantic choices in those documents and the inspected execution
paths; it is not a claim to audit every Spark feature or every Sail operator.

## Source anchors

| Anchor | Exact source and observation |
| --- | --- |
| S1 | `S/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/Scd1BatchProcessor.scala:80`: same-key, same-sequence `max_by` winners are expressly undefined; grouping occurs at :104. |
| S2 | Same file :113 and :131: delete condition is evaluated before payload projection; only true means delete, including null in the upsert branch. |
| S3 | Same file :220, :242 and :265: strictly older events are filtered against tombstones; auxiliary delete advances on `>` and upsert clears on `>=`. |
| S4 | Same file :322 and :356: target contains live rows only; upsert uses `>=`, delete `>`; :362 calls upsert priority an arbitrary deliberate choice. |
| S5 | `S/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/Scd1ForeachBatchHandler.scala:39`: validation, lazy reconciliation, auxiliary merge, target merge. :35 claims replay safety through inequalities; these calls do not attach a batch transaction tag or persist reconciled rows. |
| S6 | `S/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/ScdBatchValidator.scala:45`: orderability plus aggregated original-row null counts, sequence error before key errors. `S/sql/api/src/main/scala/org/apache/spark/sql/catalyst/expressions/OrderUtils.scala:26` defines Spark type orderability. |
| S7 | `S/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/graph/FlowExecution.scala:478`: row-level-operation capability refusal; :514 resolver-aware key names/types as a set; :552 tolerates schema nullability and metadata changes. |
| S8 | `S/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/graph/DatasetManager.scala:301`: truncate target, :306 drop auxiliary, :324 merge schema incrementally or use current output schema on refresh. |
| S9 | `S/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/graph/Flow.scala:254`: reserved-prefix check; :258 selected payload must include keys; :272 sequence expression; :285 exposes operational metadata in the output schema; :296 SCD2 refused. |
| S10 | `S/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/ChangeArgs.scala:25`: only unqualified key/selection names; :79 projection keeps source field order; :172 requires nonempty keys. |
| S11 | `S/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/graph/GraphValidations.scala:40`: any CDC destination with multiple flows is refused; :91 separates streaming/batch flow kinds. |
| S12 | `S/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/graph/TriggeredGraphExecution.scala:76`: available-now trigger. `S/sql/catalyst/src/main/java/org/apache/spark/sql/connector/read/streaming/SupportsTriggerAvailableNow.java:23`: multiple batches, captured source end, first-uncommitted-batch exception at :40. |
| S13 | `S/sql/core/src/main/scala/org/apache/spark/sql/execution/streaming/runtime/WatermarkTracker.scala:41`: min default and optional max; :123 observed maximum minus delay; :139 missing progress becomes zero. |
| S14 | `S/sql/core/src/main/scala/org/apache/spark/sql/execution/streaming/operators/stateful/statefulOperators.scala:537`: different prior/current watermark roles; :632 window-end or event-time `<=` predicate. |
| U1 | `U/crates/sail-common-datafusion/src/streaming/event/marker.rs:18`: watermark promises no future older timestamp; :27 checkpoint; :30 end of data still waits for checkpoint. |
| R1 | `R/autocdc/dedup.rs:1` and :76: direct Spark `max_by` semantics, no tie order. `R/autocdc/reconcile.rs:176` reduces, classifies, projects and filters tombstones. |
| R2 | `R/autocdc/merge.rs:91` and :229: exact two-table inequalities copied from Spark. `R/autocdc/reconcile.rs:134` supplies tombstone anti-join. |
| R3 | `R/autocdc/write.rs:385` creates evaluated helper expressions in a lazy plan; :420 validation executes a clone; :441 reconciles; :474 executes and seals only afterward. `R/autocdc/microbatch.rs:80` executes the validator aggregation. |
| R4 | `R/autocdc/microbatch.rs:35` copies orderability restrictions, including Arrow union/run-end-encoded refusal; :55 aggregate counts and error precedence. |
| R5 | `R/autocdc/schema.rs:127` reserved prefix; :142 keys required in selected payload; :167 metadata/schema generation. `R/autocdc/mod.rs:140` definition error order; :222 simple key identifiers; :295 multiple-flow refusal. |
| R6 | `R/autocdc/auxiliary.rs:259` key schema drift; :332 row-level-operation capability check. |
| R7 | `R/autocdc/flow_source.rs:507` per-input watermarks reset on restart; :753 Spark-style batch watermarks; :821 global min; :859 saves query watermark; :1152 state compatibility checks types, not full operator identity. |
| R8 | `R/autocdc/run.rs:1` bounded available-now lineage; :10 explicitly labels its unfenced path test-only; :104 mirrors Spark checkpoint-directory generations. |

## What the counterexamples establish

The model selects the later equal-version row as one permitted Spark `max_by`
outcome. Upsert `A@5` and delete `@5` in one interval can leave the target
absent. The same events in separate intervals leave `A` live because a delete
must be strictly newer. Two different upserts at version 5 choose whichever
arrives in the later interval. Sealing one interval does not remove either
dependence on grouping or arrival order. These are consequences of S1–S5,
not claims that every Spark execution chooses the modeled tie.

A delete at 5 and upsert at 9 also demonstrate a storage distinction. Reduced
together they create no tombstone. Process upsert 9 then delete 5 and a
tombstone 5 exists beside the same live row 9. The auxiliary-table contents
are therefore not themselves the logical current-state contract.

The proposed model uses one complete order, remembers canonical content for
each version, rejects conflicting equal versions, and takes the maximum for
current state. All 12 distinct-order/partition cases of a valid three-event
example agree; all 24 cases of a conflicting example report conflict. This
does **not** prove a finite latest-value store can detect every old conflict:
the model retains every tested version. The storage cost is addressed below.

## Decision ledger

### 1. Undefined equal versions: replace

Current justification: D/CHANGE-CAPTURE-ON-STREAMSOURCE.md:128–151,
D/REDESIGN-REVIEW-PACKET.md:113 and D/DECISION-NOTES-STREAMING.md:300–318
preserve Spark freedom and seal whichever row won. S1 and R1 verify the
behavior. Cost: successful output depends on scheduling, checkpoint size and
rebuild execution. Replace with a declared source/application order per key.
An equal complete order with equal normalized content is a duplicate;
different content is a conflict, never arrival-order last-write-wins.

### 2. Upsert `>=` versus delete `>`: replace as a core rule

D/CHANGE-CAPTURE-ON-STREAMSOURCE.md:40 and D/REDESIGN-PLAN.md:92 directly
adopt S4/R2. The rule can independently express a business preference for
upserts, but mixing it with an undefined reducer is incoherent. Use the same
complete-order comparison for both actions. If a product needs operation
priority, declare it as part of the order and use it everywhere. Do not choose
delete priority merely to differ from Spark; it is also a business policy.

### 3. Checkpoint boundaries determine logical winners: replace

S1/R1 group events by microbatch; the proposal groups by checkpoint. Keep
reduction as a resource optimization only after normalization and validation.
For conflict-free, totally ordered replace-row events, `max(max(A),max(B))`
equals `max(A union B)`. The winner must be independent of segmentation.
This claim does not cover patch updates, noncommutative transformations,
floating-point aggregation or arbitrary joins. Those need separate contracts.

### 4. Tombstones and maximum-version memory: retain the invariant

S3/R2 prevent an old update from restoring a deleted key. That protection is
independently necessary under out-of-order delivery. Keep the greatest accepted
order and canonical winner for live keys and deletions. A deleted key's payload
may be removed; its order cannot expire on an arbitrary wall-clock timeout.
Reclaim it only after a durable source/admission frontier makes older events
inadmissible. Otherwise tombstone state can grow and requires a budget.

### 5. A mandatory auxiliary table: replace with a storage capability choice

D/STREAMING-ARCHITECTURE.md:28 and D/CHANGE-CAPTURE-ON-STREAMSOURCE.md:75
assume S3–S5's physical layout. The invariant needs durable version/deletion
state, not two SQL tables. Prefer an admitted target transaction that atomically
publishes changed user rows and a versioned reference to an immutable key-state
index, including delete versions. This keeps the ordinary table schema/read
path if the format and commit authority actually support it. It is a proposed
capability, not established Delta/Iceberg behavior. External writers, log
checkpointing, snapshot retention and metadata preservation must qualify it.

If unavailable, a fenced sidecar plus target is a legitimate two-effect
implementation with immutable preparation and receipts. A unified physical
state table containing deleted rows plus a filtered view/provider removes the
second effect, but changes the public table, DDL, write and external-engine
contract. Do not silently substitute a view. A separate key/value state store
plus user table still has two durability domains unless their publication is
atomic; it does not remove recovery by changing the storage technology.

### 6. Auxiliary-first merge ordering: conditional, not universal

S5 and R/autocdc/write.rs:517 establish the existing protocol. Preserve that order only
for the existing layout and prepared-output recovery proof. A unified atomic
transaction has no intermediate merge order. A sidecar design must name the
authoritative version state and prevent interleaving until all effects finish.
Never allow target metadata and sidecar state to become independent authorities.

### 7. Losing deletes must have specific auxiliary effects: replace

D/CHANGE-CAPTURE-ON-STREAMSOURCE.md:43 inherits S1/S3's no-tombstone result
for a losing delete. A highest-order register may discard every losing action
after validating it. Internal tombstone rows need not reproduce Spark's
batch-dependent contents. Keep logical anti-resurrection and public data
behavior; classify inspection of old internal metadata as a migration change.

### 8. Delete classification and payload projection: retain and strengthen

S2 and R/autocdc/reconcile.rs:47 justify classifying actions before dropping their
input columns. Keep this dependency. Replace nullable predicates silently
becoming upserts with an explicit non-null action enum in the normalized event.
A compatibility input adapter may map `true` to delete and false/null to upsert
only when that mapping is explicitly selected. Default unknown/null action
fails before mutation; absence of a delete rule can explicitly mean all upserts.

### 9. Validate every original event: retain; evaluate once

S6 and R3 validate before reduction, independently preventing invalid losing
events from disappearing. Keep key/order/action/schema validation on every
original event. But R3 executes a lazy input once for validation and again for
reconciliation. Neither sealing winners afterward nor naming a receipt proves
those evaluations saw identical values. S5 has the same separation. This is a
source-path risk, not a runtime reproduction. Normalize once into immutable
accepted events; validate and reduce that exact evaluation. Deterministic
transforms may use a proved replay path; nondeterministic transforms require
persisted normalized events before acceptance, with explicit retention.

### 10. Full scans for Spark error counts and precedence: replace

R4 and S6 compute aggregate null counts and prioritize sequence errors. The
correctness property is rejection before relevant output commits, not exact
counts, error text or evaluation order. Validate incrementally in the streaming
normalizer, retaining bounded diagnostic samples and durable rejection status.
Default failure stops progress before the invalid event's accepted effect;
earlier completed checkpoints remain committed. A quarantine path is an explicit
output/progress contract, never silently counted as successfully applied data.
Exact Spark error formatting may remain at a client adapter when cheap.

### 11. Null key/order and Arrow type restrictions: separate correctness from parity

Default non-null keys and a non-null complete order are independently useful:
they prevent missing identity and ambiguous comparison. Spark checks top-level
declared columns, not all nested values; S6/R4 do not justify copying this
accident as the new type contract. Define canonical key equality and order for
each admitted type, including struct members, NaN, signed zero, collation and
timestamp units. Nullable key members require explicit equality semantics.
Do not reject Arrow dictionary/run-end representations merely because Spark
lacks them; normalize representation and qualify the comparator. Unordered
maps need an explicit canonical key/order projection, not an invented natural
ordering. Payload types need only the admitted target's storage support.

### 12. Simple-column-only keys and payload-selected keys: relax at the boundary

S9/S10 and R5 require simple identifiers and visible selected keys. The core
needs stable canonical key values, not Spark's syntactic restriction. Permit
deterministic projections that materialize named key/order fields before CDC.
Avoid arbitrary expression reevaluation inside the merge. Hiding keys from a
physical user table is allowed only if the selected storage/index can address
rows unambiguously; otherwise retain visible keys as an implementation
capability requirement. This is not an automatic permission to remove keys.

### 13. Reserved Spark metadata names and visible metadata: replace internally

S9 and R/autocdc/schema.rs:21–28, :127 reserve `__spark_autocdc_` and expose metadata.
Collision avoidance remains necessary. Spark's name, schema and order need not
be the native API. Prefer an explicit internal metadata namespace/index whose
representation is versioned and distinct from user fields. Preserve existing
visible columns for existing tables until explicit migration; arbitrary
external readers may already depend on them. Do not hide a format change.

### 14. Key drift requires full refresh: retain refusal, add explicit migration

S7/R6 correctly prevent silently reinterpreting persisted entity identity.
Key reordering and equivalent canonical mappings should not force a rebuild.
A rename or lossless mapping may use a verified migration with uniqueness and
collision checks; a new identity definition may require a complete rebuild.
Pin resolved field identities, comparator and normalization versions rather
than relying on a mutable session resolver. No automatic in-place key change.

### 15. Destructive truncate/drop refresh: replace as the preferred rebuild

S8 and D/CHANGE-CAPTURE-ON-STREAMSOURCE.md:104 use destructive reset. A new
generation is independently necessary, but truncate-before-rebuild exposes an
empty/partial target and complicates failure. Prefer build a new protected
generation, validate it, then atomically publish the target binding where the
catalog/format supports that contract. Preserve the prior readable generation
until switch completion. If direct path readers require the same physical
table identity, a shadow swap changes their contract; a fenced in-place reset
with declared visibility and resumable effects remains an explicit alternative.

### 16. Absolute source origin required for every refresh: replace with completeness

S8 proves no universal connector-origin policy. A full rebuild needs sufficient
authoritative information, which may be a consistent source snapshot plus a
change-log frontier, retained complete events, or a certified export. Physical
offset zero is not the invariant. Preflight that information and its identities
before destructive work. A live-row-only target snapshot cannot recover lost
delete versions for subsequent old events without a new admissible frontier.

### 17. Schema equality and schema evolution: strengthen contract identity

R7 only checks types when restoring state; D/STREAMING-ARCHITECTURE.md:118
already recognizes the insufficiency. Persist normalized plan, key/order/action
semantics, field identities, encoding and version information. Permit additive
payload evolution with an explicit missing-field/default policy; narrowing,
key/order changes and comparator changes need migration. Spark's automatic
schema union at S8 is neither universally safe nor a reason to freeze every
payload schema. Invalid state must fail rather than be reinterpreted.

### 18. SCD1 full-row replacement versus patch updates/history: retain declared scope

S1/S4 implements current-state full-row upserts; the model's `max` law relies on
that operation. A sparse patch or event delta is not interchangeable: reduction
to one event can lose earlier field updates. Keep a named replace-row contract.
Patch CDC and SCD2 history require separate composition/history semantics and
storage budgets. S9's SCD2 refusal is not a reason to implement history now,
nor a permanent limitation imposed by Spark.

### 19. Require a MERGE interface for every target: replace with capabilities

S7/R6 admits a particular connector API. Require atomic or recoverable row
mutation, key-version state, idempotent identity and enforced writer fencing.
A target providing atomic partition replacement or a native keyed transaction
could meet those properties without Spark's interface. A plain file sink with
no atomic publication cannot. Admit proven capabilities, not format names.

### 20. One CDC flow per target and one recovery domain: retain the safe default

S11/R5 reject multiple flows by syntax. One mutation owner per physical target
is an independent safety property until ordering, fencing and shared commit
state are established. Multiple source streams can feed one explicitly ordered
flow. Later independent flows need disjoint keys or a shared order/ownership
contract. Do not introduce their coordination just to avoid Spark's refusal.

### 21. Catalog-managed writers may run unfenced: replace

D/DECISION-NOTES-STREAMING.md:365–378 and D/STREAMING-ARCHITECTURE.md:184
leave external single-writer discipline as an option. The latest requirement
removes that fallback for admitted durable mutation. Build a fence checked
atomically at the publication authority for every mutation, including schema,
maintenance, reset and no-op effects. Epoch, target incarnation and generation
are distinct identities. Ordinary commits being serializable does not prevent
a stale owner from submitting a later serializable write. The lead's fencing
audit owns detailed provider coverage; S5 contains no equivalent fence.

### 22. Available-now only and one final checkpoint: do not retain as constraints

S12/R8 explain the old bounded loop. Bounded drain-to-frontier is independently
useful; so is continuous service. Keep both on one execution protocol. A source
bound is per source, not a global snapshot. Permit intermediate checkpoints
for either mode, with a final completed checkpoint for a bounded run. This
direction already exists in D/STREAMING-ON-STREAMSOURCE.md:81. Do not regress
to the old only-available-now or single-final-checkpoint interpretation.

### 23. Spark batch watermark lag and rounding: replace with stream contracts

S13/S14 and R7 make decisions depend on batch boundaries, separate lagged
filter/eviction values, and millisecond conversion. Do not recreate that lag
or precision loss in a continuous stream. U1 is a strong no-older-event
promise. Keep it unless intentionally introducing a distinct threshold marker.
A progress-estimation policy must enforce its late-event treatment before
emitting that strong promise. Checkpoint boundaries must not define lateness.

### 24. Watermark composition, idleness and restart: define explicitly

The conservative minimum has an independent justification: every participating
input must pass a completeness frontier. Missing progress should be unknown,
not universally timestamp zero. An idle timeout is not proof no older data can
return. Use replayable per-input frontier/idle/end transitions, restore every
required tracker, and define reactivation. R7's reset of local trackers while
retaining a combined value is not sufficient evidence of equivalence. Use the
event-time precision supported by the declared operator, with explicit rounding
only where necessary. Without a source lateness bound or an explicit rejection
policy, finite state and exact results for arbitrarily late input cannot all
be promised. Windows may remain excluded until this contract is implemented.

### 25. Window acceptance versus the strong marker: choose one coherent contract

D/DECISION-NOTES-STREAMING.md:225 accepts a row into any still-open window even
when its timestamp precedes a threshold, reflecting S14. That rule cannot
implicitly coexist with U1's no-older-row promise. A safe starting option uses
deterministic per-input progress and late-event handling before the strict
frontier, then closes windows whose end is at/before it. A separate threshold
contract can retain open-window acceptance but must specify downstream state,
chained aggregates and replay. Preserve neither behavior just for Spark parity.

### 26. Spark directory names, error labels and resolver accidents: isolate

R8's checkpoint directory layout is not an identity protocol. Use opaque
stable IDs and escaped presentation paths, preserving old path discovery only
through migration. R5's exact parser/error precedence and Java name-comparison
behavior may be useful at the Spark client boundary, but must not infect
durable canonical identity. Reject ambiguous field resolutions, including
duplicate/case-colliding names. A typed definition must serialize the resolved
mapping and semantic version. Exact error-string parity is not a correctness
gate for the new contract.

### 27. Reinvoking flow functions to propagate configuration: investigate separately

D/FLOW-CONFIGURATION-DESIGN.md:43–60 prescribes Spark's staged reevaluation.
The semantic requirement is one reproducible effective definition with conflict
detection, not repeated evaluation of arbitrary effectful user code. Prefer a
typed normalized plan/configuration and explicit dependency merge. The assigned
configuration audit owns code verification and Dhall alternatives. This is a
flagged design dependency, not a finding that the implementation misbehaves.

## Recommended event contract and conflict-detection cost

The simplest default accepts replace-row events with a source/application-owned
total order **per entity key**, immutable source event identity, deterministic
normalization and explicit schema/semantic versions. The order may be a database
log position plus transaction row ordinal. A business timestamp alone is not
enough if ties carry different changes. Require a declared secondary order or
reject that source contract. Do not invent a global lexical order from unrelated
broker partitions. A business-configured tie-breaker is valid if deterministic,
stable and applied identically during reduction and storage.

For equal complete order, identical canonical action and payload mean duplicate;
different values mean a contract violation. The default validates local rows,
equal versions present in a prepared interval and equality against the current
durable version. It preserves each live/deleted key's maximum order and winning
event identity. Check repeated identities within the retained scope against
their key, order, action and payload mapping. This does
not promise detection of every invalid superseded event throughout all history.
For example, after version 9, two inconsistent version-8 payloads can be stale
and ignored. Another delivery schedule might expose their conflict earlier.
That is a distinction between deterministic output for valid inputs and
exhaustive detection of all invalid inputs, not permission for ambiguous valid
winners. Document the default's validation scope plainly.

Exhaustive conflict detection requires a retained mapping from key/order and
event identity to canonical content, including superseded versions. Offer it
only with an explicit horizon and state budget. A verified source frontier may
retire fingerprints; events older than the admitted horizon must be refused
instead of treated as newly validated. Without such a frontier, exhaustive
history verification is unbounded. An arbitrary time-to-live silently weakens
the promise. Do not make that unbounded index the default merely to reject
every historical inconsistency.

Canonical equality covers key, complete order, action, payload and their
semantic schema, not transport timestamps or physical Arrow batch layout.
Stable source identity includes incarnation; deterministic fanout needs a
stable emission ordinal. Arbitrary joins/aggregations cannot inherit source
event IDs without defining their own output identity. Nondeterministic key,
order or action expressions are refused by the default contract. Persisted
normalization can admit other computations as an explicitly logged input
stream, with its own retention and rebuild semantics.

## Migration and acceptance

Name the new semantic version and record it in definitions, prepared work and
table identity. Do not silently apply it to existing Spark-shaped targets.
Drain or resolve pending effects under the old contract, fence old writers,
capture source/target incarnations and audit the old state. Live row versions
plus tombstones can seed a new maximum-version register, but cannot reconstruct
discarded equal-version conflicts, a missing secondary order or lost deletion
history. Require a complete authoritative rebuild or an explicit new baseline
and source admission frontier in those cases. Retaining old outcome history
does not make it a proof of the new contract.

Keep Spark protocol translation separate from native semantics. Existing tables
may remain readable; new writes require the new explicit contract. A legacy
execution mode, if retained, must be named, bounded and fenced rather than an
automatic fallback. Changes to visible metadata, table versus view, direct-path
reads, DDL and external writes are product migrations, not regression-free
internal refactors. Spark comparisons should document matches and intentional
differences; the new algebra and failure tests become the correctness oracle.

Required evidence: permute valid ordered events and checkpoint partitions;
duplicate after deletion and after a newer version; exercise equal-order
conflicts and disclose detection limits; validate and commit the same normalized
events; crash around atomic publication or each sidecar effect; replay after
source removal; fence stale writers and resets; restore changed operator/config
versions; test Arrow canonical equality/ordering; qualify external readers and
all admitted writers. None of those storage/integration checks is established
by the small model or by the earlier component pass counts.
