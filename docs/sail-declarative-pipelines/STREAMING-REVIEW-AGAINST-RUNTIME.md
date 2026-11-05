# What the bounded change-capture runtime contributes to StreamSource

A continuous change-capture pipeline must preserve validated input, recover
partially completed writes and reject obsolete owners. The bounded Sail
implementation contains useful mechanisms for those obligations, but also copies
Spark behavior that should not govern the replacement. Reuse its correctness
boundaries through Sail’s existing execution and commit interfaces, rather than
porting its microbatch loop wholesale.

This review distinguishes source observations from implementation requirements.
The inspected bounded runtime is Sail `99dc47788941daf28eec847527949a4cadafdbd2`;
the continuous foundation is upstream `85c6cca01cd521dd778bc200c987a34edf141de1`.
No integrated StreamSource replacement has been executed.

## Reuse the mechanisms, not the scheduling model

The bounded runtime plans finite source ranges, evaluates a batch, stores selected
rows and applies change-capture effects. `StreamSource` instead describes a
long-lived scan carrying data and ordered control markers. A checkpoint can bind
an interval of that scan to prepared work, but substituting its identifier for
a batch number does not prove equivalent ordering or recovery.

| Existing mechanism | Reuse opportunity | Necessary correction |
| --- | --- | --- |
| Source range and incarnation checks | Stable source identity, exact reads and explicit retention failure | Bind the full descriptor and partition set; provide live task control and a partition-discovery policy |
| Prepared artifacts and validation receipts | Persist exactly what a retry is authorized to write | Normalize once, validate the same values and connect the receipt to the actual streaming writer |
| Per-effect completion and ratification | Recover partial table writes and ambiguous responses | Bind checkpoint semantics and fixed content; retain pending effects across takeover |
| Delta staged bytes and create-only publication | Finish an accepted effect without changing it | Cover creation, managed targets, workers and all mutation entry points |
| Key and schema checks | Prevent incompatible state interpretation | Use explicit semantic versions and migrations instead of copying Spark metadata layout |
| Query binding and lifecycle | Reuse Sail’s planner, job services and cancellation ownership | Run continuous event plans and distinguish cancellation, failure and final durable completion |

A general new control service is not implied by these mechanisms. Reuse existing
job and catalog boundaries first. A separate authority is justified only if the
selected backend cannot enforce the required atomic ownership decision.

## Keep validation but eliminate repeated evaluation

The bounded write path constructs lazy key, sequence and delete expressions,
executes a clone for original-row validation, then separately executes reduction
before sealing the winners. Source inspection identifies a risk: nondeterministic
input or transformation can change between those executions. This has not been
reproduced as an engine failure in this review.

Normalize each original event once and validate those exact values before it can
lose during reduction. Require deterministic normalization by default. A logged
normalization mode can admit nondeterministic work only by making its output
immutable input with explicit retention and rebuild semantics.

Preserve a receipt binding validated input, prepared output, schema and semantic
identity. Check that receipt at the actual write boundary. A standalone receipt
type or a test of a helper does not establish that every merge verifies it.

Whole-memory collection and serialization are not correctness requirements of
sealing. Use immutable chunks, incremental digests and scans with memory and disk
budgets. Retain artifacts while incomplete effects depend on them.

## Replace Spark’s ambiguous event rules

Spark 4.2.1 reduces each microbatch to a winner per key, leaving equal sequences
undefined. Its target merge accepts equal-sequence upserts but requires greater
sequences for deletes. Sealing freezes a selected winner for retry, but cannot
make the first choice independent of batch grouping.

Require complete source/application order per key. Use one comparator for both
actions: apply greater versions, ignore older versions and recognize identical
equal-version events as duplicates. Conflicting equal-version content is an error.
An immutable identity may be native or derived from source incarnation, key and
complete version for replacement events.

Default validation checks original rows, within-interval conflicts and equality
with current durable state. It does not retain an unlimited history to detect
all contradictions at superseded versions. Exhaustive verification is an explicit
option with a source frontier, admissible horizon and retention budget.

A delete is an ordered business fact, not a retraction cancelling a previously
emitted row. Keep its greatest version after removing the visible payload. That
anti-resurrection requirement survives the redesign; Spark’s asymmetric comparisons
do not.

## Treat the two-table layout as a choice

The bounded implementation updates a tombstone sidecar and a visible target
separately. Its prepared rows and effect receipts matter because a crash can
leave only one write completed. Preserve that protocol if the replacement uses
two effects, including stable no-op outcomes and reconciliation after a lost response.

Prefer a target capability that atomically publishes user rows with durable
version state or an immutable index reference when it preserves ordinary table
behavior. This is proposed adapter work, not an existing universal Delta or
Iceberg capability. A filtered view over a state table changes external reads,
DDL and table identity and needs explicit product acceptance.

Spark’s auxiliary name, metadata schema and directory layout are interoperability
surfaces of existing data, not mandatory internal architecture for new flows.
Changing them requires migration. Source facts about the old layout remain useful;
they do not require the new writer to reproduce that layout forever.

## Generalize real fencing and remove the plain fallback

The bounded runtime fences filesystem-managed Delta but routes managed Delta and
Iceberg to a plain writer. Serialized table commits were treated as sufficient.
They are not: an obsolete owner can reload the newest table head and pass a
version check after a successor takes over.

The Delta reference path stages exact bytes, ratifies an effect through a guarded
authority transaction and publishes with create-only semantics. Its fenced commit
operator refuses new and catalog-managed tables. The worker session construction
also lacks the authority route needed if a fenced commit executes there. These
are source observations, not executed cluster or backend failure tests.

Build adapters that atomically check owner epoch, generation, table incarnation,
effect identity and content at acceptance. Cover creation, enrollment, schema
changes, refresh, cleanup and workers. Accepted exact bytes may finish publication
after takeover; an obsolete owner cannot authorize new effects. Unknown outcomes
must retain their original identity until reconciled.

A cooperating Sail property cannot fence another engine with direct publication
access. All permitted writers must use the same accepting authority or a mandatory
protocol. A process-local authority database needs explicit durability and shared
ownership qualification before claiming multi-host failover. Remove unfenced durable
admission rather than documenting a permanent single-writer workaround.

## Preserve source and state identity through recovery

The Iggy prototype reuses exact-range reading, decoder errors and partition
incarnations. Those checks must apply throughout polling and bound capture,
including an empty recreated partition. Its saved partition positions alone do
not identify the entire source, and its scan can discover new partitions at their
earliest retained offset. Bind the descriptor and participants to each preparation
and define how new partitions bootstrap without silently omitting history.

Raw or JSON payloads also do not automatically provide per-event provenance.
Carry required source identity through transformations or admit an explicit event
envelope. Do not promise complete event identity from checkpoint offsets alone.

Restore operator state by the exact prepared recovery point, not the newest file.
Retain all snapshots still referenced by pending effects or valid restart points.
Renaming a file does not itself qualify power-loss durability. Spark’s practice of
retaining only combined watermark progress is not a reason to discard per-input
state needed to preserve Sail’s event-time contract.

## Migrate behavior deliberately

Resolve old pending effects under their recorded semantics, fence old owners and
establish a new semantic generation before changing ordering or storage. Missing
tie-break information or deletion history may require a rebuild. A consistent
snapshot plus continuation frontier can supply complete reconstruction without
requiring the source’s physical origin.

Preserve meaningful key resolution and schema checks. Do not require traversal-order
configuration, repeated effectful definitions, Spark error-row ordering or silent
unknown-option fallback. Resolve a strict typed configuration before dependent
planning, and bind its effective meaning to recovery.

The replacement must demonstrate real restarts between effects, stale-owner
rejection, equivalent results across valid input permutations and checkpoint
sizes, source recreation and external-table access. Prototype reports and the
focused marker reproductions identify useful tests and defects. They do not
qualify this unbuilt integration.
