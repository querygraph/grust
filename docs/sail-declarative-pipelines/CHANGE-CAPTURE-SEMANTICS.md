# Change capture with stable event ordering

Change capture maintains a table from keyed updates and deletes, including
changes delivered out of order. Users need retries and different checkpoint
sizes to produce the same current records. This proposal makes that guarantee
depend on explicit event identity and ordering, rather than Spark's batch
boundaries or an arbitrary winner among tied events.

The initial operation is full-row replacement or deletion. Partial field
updates, historical versions and arbitrary stateful transformations need
their own semantics and are outside this first contract.

## Fit with Sail

Sail's `StreamSource` supplies a streaming scan. Flow events carry data batches
and ordered control markers through its execution plans. A checkpoint marker
can identify a boundary at which source progress and operator state are saved.
These are the execution foundations; they do not yet provide the event contract
or durable mutation protocol described here.

Add a normalizer that evaluates and validates change events, a reducer that
selects the greatest event for each key, and a fenced target writer. A fence
rejects writes from an obsolete owner at the authority that publishes commits.
Checkpointing controls durability and resource use. It must not change which
valid event wins.

## Define an event before defining a checkpoint

Each normalized event has the following fields:

| Field | Meaning |
| --- | --- |
| Entity key | Stable identity of the record being changed |
| Complete order | Source or application version that totally orders changes to that key |
| Event identity | Stable native or derived event identity, including source incarnation |
| Action | Explicit upsert or delete; upsert replaces the complete payload |
| Payload | Typed values written by an upsert |
| Semantic version | The key, order, action, schema and normalization rules used to interpret the event |

A database log position plus a transaction row ordinal can provide a complete
order. An event timestamp alone cannot do so when two different changes can
share it. Require a source-owned secondary order in that case. Do not invent
business order by sorting unrelated broker partition names or using arrival
time. A business-configured tie-breaker is acceptable when its meaning is
explicit and stable.

The default requires immutable event identity and complete order per key.
A native event identifier can supply identity. For replacement events, deriving
it from source incarnation, canonical key and complete order is also sufficient
when that combination uniquely names the event. A separate native identifier is
required only for a guarantee that consumes it, such as transport-level duplicate
detection. Preserve necessary provenance through filters and projections;
payload-only source rows do not automatically carry it. A transformation producing several rows needs a stable emission
ordinal. Joins and aggregates need separately defined output identities;
they do not automatically inherit this contract.

Use one canonical equality and comparison rule across normalization, reduction
and storage. Canonical equality compares logical values, not Arrow batch layout
or transport timestamps. Type qualification must define nested nulls, numeric
edge cases, collation and timestamp precision where applicable. Payload type
support follows the admitted target rather than Spark's type list.

## Apply one rule to upserts and deletes

Keep the greatest accepted complete order for each key, with its event identity,
canonical action and payload. Apply a greater event. Ignore a smaller event.
An event
at the same order with identical action and payload is an idempotent duplicate;
a different action or payload is a conflict.

A deletion retains its order even after its payload disappears. Otherwise an
older upsert could recreate the row. Both live rows and deleted keys therefore
need durable version state. Delete state can be reclaimed only after a durable
source contract makes older events inadmissible, not after an arbitrary timeout.

This makes reduction an optimization. For valid, completely ordered replacement
events, selecting the greatest event in each group and then comparing those
winners produces the same result as comparing all events together. Checkpoint
segmentation and delivery order do not change the final current state. This
does not promise identical intermediate visibility while events are arriving.

## Distinguish input correctness from exhaustive conflict detection

The recommended default requires the source's complete-order and immutable-event
contract. Validate every original row, check equal orders within each prepared
interval, and compare original versions with a pinned durable-state snapshot
before reduction discards evidence. If durable version 8 has payload A, input
8:B must conflict even when a later 9:C wins the interval. Bind that snapshot
to the commit precondition; changed state requires safe reconciliation or
revalidation of the same immutable normalized input. Check that repeated identities map to the same key, order, action and payload within that
retained scope. A detected conflict stops the affected flow before that prepared interval is applied;
earlier completed intervals remain committed. Never silently select the last
arrival or retry a conflict as a transient storage error.

This current-version default does not detect every invalid superseded event in
history. After accepting version 9, inconsistent version-8 payloads may be
ignored as stale. A different schedule might expose their conflict earlier.
The guarantee is deterministic output for valid inputs, not schedule-independent
detection of every violation of the source contract.

If exhaustive conflict detection is required, retain fingerprints of all
admitted key/version and event-identity mappings within an explicit horizon.
Refuse input outside that horizon. Retiring fingerprints needs a durable
source frontier and a stated state budget. Without a frontier, exhaustive
history verification requires unbounded retention. That stronger verification
should be an explicit option, not an invisible cost of ordinary change capture.

## Evaluate once, validate before reducing

Evaluate each event's key, complete order, action and payload once. Validate
that normalized event before allowing reduction to discard it. A losing row
with an invalid key or order must not disappear unnoticed.

Require non-null keys, complete orders and actions by default. An unknown or
null action fails; a configured absence of a delete rule may explicitly mean
all upserts. Nullable key members require a defined canonical equality rule.
Keep action and order separate from payload selection, so dropping an input
column cannot erase deletion or ordering information.

The default requires deterministic normalization. A nondeterministic
computation can be admitted only as a separately logged normalization step:
its output becomes immutable input before acceptance, with its own retention
and rebuild contract. Running a lazy plan once for validation and again for
reduction does not establish that the written rows were the validated rows.

Before output effects begin, persist the prepared boundary, its validated
output and its semantic identity. A proved equivalent replay mechanism may
replace saved output. Retries must use the original prepared work, even after
new source events arrive. Resource limits, backpressure or spill must bound
preparation; a checkpoint period alone cannot do that.

## Choose storage without changing the public table accidentally

The invariant is durable key/version/deletion state coupled to the user-visible
mutation. It does not require Spark's separate auxiliary table.

Prefer a target capability that atomically commits the user-row changes and
a versioned reference to an immutable key-state index. This can preserve an
ordinary table's schema and external read path while keeping deleted-key
versions outside live rows. It is a proposed capability: Delta and Iceberg
adapters must demonstrate metadata preservation, snapshot recovery, concurrent
commit behavior and enforcement for every admitted writer.

| Alternative | Benefit | Cost and contract |
| --- | --- | --- |
| Target transaction includes key-state publication | One atomic durability boundary; ordinary table reads can remain intact | Requires format and commit-authority support; external writers must preserve the index and fence |
| Fenced sidecar state plus ordinary target | Reuses two-effect recovery where one transaction cannot cover both | Requires immutable prepared work, separate completion records and recovery between effects |
| Physical state table plus filtered view or provider | Live and deleted state can share one table transaction | Changes table identity, DDL, external reads and write APIs; requires explicit product acceptance |

A key/value store beside a target still creates two durability domains unless
their publication is atomic. Whichever layout is chosen, define one authority
for version state and protect every mutation, including schema changes,
maintenance and reset. An unfenced catalog is work to complete, not a supported
durable fallback. Cross-table atomic visibility is not implied by the sidecar
alternative.

## Refresh and migration

Changing key meaning, order comparison or normalization semantics requires a
new semantic identity and an explicit migration. A harmless key declaration
reordering need not rebuild data. A rename or type conversion needs proof that
identity and order are preserved; other changes may require rebuilding.

A complete rebuild needs authoritative source information, which may be a
snapshot plus a change-log frontier rather than physical offset zero. Verify
that information before destructive effects. Prefer constructing a new fenced
generation and publishing it atomically where the target supports that contract.
An in-place reset needs explicit visibility and crash-recovery behavior.

Do not silently upgrade existing targets. Resolve their pending work, fence
old writers and inspect retained row versions and tombstones. Old state cannot
reconstruct discarded ties, missing secondary order or lost deletion history.
Those cases need a complete rebuild or an explicitly accepted baseline with
a new source admission frontier. Visible metadata or table-to-view changes
are product migrations, not transparent internal refactors.

## Differences from Spark and the decision

Spark 4.2.1 leaves same-key, same-sequence winners within a batch undefined.
Its target merge gives equal-sequence upserts priority over deletes. Consequently,
an upsert and delete at the same sequence can produce different outcomes when
grouped together or separately. The pinned
[processor](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/Scd1BatchProcessor.scala#L80)
defines those rules. Sealing a chosen winner fixes retries of that preparation,
but does not fix the initial dependence on grouping.

Replace those rules with the complete-order contract above. Retain validation,
anti-resurrection state and recoverable publication because they serve
correctness independently. Spark protocol translation can remain at the API
boundary; it must not silently select legacy semantics for new durable writes.

Source inspection and a small logic model support the counterexamples. They
do not demonstrate an implemented replacement. Acceptance needs permutations,
checkpoint regrouping, duplicates, conflict cases, crash recovery, stale-writer
rejection and external-reader checks against the actual source and target.

Three decisions make the first implementation concrete:

1. Which source supplies the complete per-key order and immutable event identity?
2. Is the default validation scope sufficient, or is retained historical conflict verification required?
3. Can the first target commit user data and key state atomically while preserving its public table contract, or does it need the fenced sidecar protocol?
