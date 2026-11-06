# Change capture on Sail’s streaming foundation

Change capture maintains current records from keyed replacements and deletions.
Late arrivals, retries and different checkpoint sizes must produce the same final
records for valid input. Add a stable event contract and durable per-key versions
to Sail’s continuous streaming execution.

The initial operation replaces complete rows or deletes them. Partial field
patches and historical-version queries require separate semantics.

## Add ordering to recoverable publication

The [streaming proposal](STREAMING-ON-STREAMSOURCE.md) supplies the shared recovery
protocol: prepare fixed work before publication, recover its original effects and
reject obsolete writers at commit acceptance. Change capture adds a normalizer
that evaluates and validates events, a reducer that selects the greatest event
per key between checkpoints, and a target merge that preserves versions across
checkpoints. Durable target-associated state avoids keeping every historical key
in the executing operator’s memory.

Sail’s `StreamSource` and flow events provide the scan and ordered control markers.
Local repairs now isolate supported filter and projection expressions from markers
and preserve declared schemas. Distributed checkpoint alignment, durable preparation
and the change-capture operators remain unbuilt. The
[foundation results](PROJECTION-COMPOSITION-RESULTS.md) describe the qualified scope;
individual reduction and merge prototypes do not demonstrate integrated recovery.

## Require an order for each key

Each normalized event has an entity key, a complete order for that key, an immutable
identity, an explicit action and a typed payload. A complete order distinguishes
different replacements of the same record. It need not order unrelated records.

A database log position plus a transaction row ordinal can provide that order.
A broker need not supply a transaction ordinal if it provides another stable
per-key order. Offsets suffice when broker append order is the declared record
order and every change to a key stays in the same partition without recreation.
A stable application version or declared business tie-breaker can also suffice.
Partition migration needs an explicit ordering contract. Sorting unrelated
partitions or using arrival order invents meaning;
timestamps alone fail when distinct changes share them. Refuse change-capture
admission when the source cannot supply the required order. It can still feed
append-only pipelines; ingestion alone does not establish replacement order.

Identity may be native or derived from source incarnation, canonical key and complete
order when that combination uniquely names the event. An incarnation distinguishes
recreation from continuation. Preserve this provenance through projection, or require
an input envelope that carries it. Payload-only rows do not automatically supply it.

Use one comparison for upserts and deletes. Apply greater versions and ignore older
ones. Equal versions with identical canonical action and payload are duplicates;
different content is a conflict. Canonical equality compares typed logical values,
not Arrow buffer layouts. Retain a deletion’s version after removing its visible row.

For example, deleting account A at version 12 must prevent a late version-11 upsert
from recreating it. A version-13 upsert may recreate it. Grouping these valid events
into different checkpoints leaves the same final record, although intermediate
visibility can differ while events arrive.

## Validate before reduction loses evidence

Evaluate each original event once. Validate its key, order, action and schema before
reduction discards it. A losing invalid row fails the interval. Require non-null
orders and actions, define equality for admitted key types, and never interpret a
null delete expression silently as an upsert.

Default admission requires deterministic normalization and immutable source events.
Nondeterministic normalization needs a separately logged step whose immutable output
has explicit retention and rebuild semantics. Running a lazy plan once for validation
and again for reduction cannot prove that the written rows were validated.

Check conflicts within each prepared interval and against matching original versions
in a pinned durable-state snapshot. If durable version 8 contains A, incoming 8:B
must conflict even when 9:C wins the interval. Bind that snapshot to the commit
precondition. A validation receipt identifies the checked normalized input, semantic
version and prepared output; the writer verifies it before publication.

Within the retained verification scope, reusing an event identity with a different
canonical key, order, action or payload is also a conflict. Equal-version checks
alone would miss an identity reused across different keys.

These checks do not detect every contradictory superseded event in history. Exhaustive
verification requires retained version and identity fingerprints, a defined admission
horizon and a state budget. A durable source frontier can justify reclamation;
an arbitrary timeout cannot. This stronger mode is a selectable retention cost,
not an implicit promise of the default.

## Choose how versions accompany the public table

Both live and deleted keys need durable versions. Spark’s auxiliary-table layout
is one possible implementation, not a correctness requirement.

| Layout | Benefit | Required capability or cost |
| --- | --- | --- |
| Publish row changes and version state in one target transaction | Atomic visibility while preserving ordinary table access | The target preserves the state or an immutable index reference; every admitted writer maintains it |
| Fenced sidecar state plus ordinary target | Works when one transaction cannot cover both | Separate effect receipts and recovery between commits; no cross-table atomic visibility |
| Physical state table exposed through a filtered view | Live and deleted state share a transaction | Changes table identity, schema, table operations and external access; requires explicit product acceptance |

Prefer the first layout when the adapter proves its capabilities. Delta and Iceberg
support must demonstrate metadata preservation and enforcement for every admitted
writer. Otherwise evaluate fenced sidecar recovery. A hidden table-to-view substitution
does not preserve the public table contract.

All layouts inherit mandatory fencing, immutable preparation and bounded artifact
retention from the streaming protocol. The first delivery may admit one enforced
target; it cannot admit another through an unfenced fallback.

## Refresh without losing ordering history

Changes to key meaning, ordering, normalization or storage need a versioned migration.
Harmless key declaration reordering need not rebuild data. Resolve pending work under
its recorded contract, fence old writers and inspect retained versions before switching.

A rebuild needs authoritative data, possibly a consistent snapshot plus a continuation
frontier. Verify completeness before destructive effects. Prefer publishing a new
fenced generation when supported; an in-place reset needs explicit visibility and
recovery behavior. Missing tied-event order or deletion history cannot be recovered
by changing a comparator. Reconstruct it or explicitly accept a new baseline and
source admission frontier.

## Deliberate differences from Spark

Spark 4.2.1 leaves equal-sequence winners within a batch undefined and treats equal
upserts differently from equal deletes during merges. The same events can therefore
produce different outcomes across batch boundaries. Complete per-key order and one
action-independent comparison remove that ambiguity. Preserve useful schema checks,
original-row validation and anti-resurrection state. Do not preserve auxiliary-table
names, error ordering, batch-lag watermark rules or permissive configuration merely
for parity. Public metadata changes still require migration.

## Decisions and verification

Which source supplies the required per-key order and immutable identity? Can the
first target publish rows and versions atomically while preserving its public table
contract, or does it need sidecar recovery? Does the application need historical
conflict verification beyond the default scope?

Pinned source inspection and a small logic model support the ordering counterexamples.
Acceptance still requires actual source-to-table permutations, checkpoint regrouping,
invalid losing rows, partial effects, stale writers, refresh recovery and external-reader
checks. The implementation must demonstrate these guarantees together.
