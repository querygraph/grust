# Change capture on Sail’s streaming foundation

Change capture maintains current records from keyed replacements and deletions.
Users need late arrivals, retries and different checkpoint sizes to produce the
same final records. Build it on Sail’s `StreamSource` and flow events with a
stable event contract, validated preparation and fenced table publication.

The initial operation replaces complete rows or deletes them. Historical-version
queries, partial field patches and arbitrary streaming joins are separate features.
Spark-compatible APIs may describe the flow, but undefined Spark behavior must
not become its correctness contract.

## Fit with Sail

Sail already describes streaming scans and transports data with ordered control
markers. A checkpoint marker supplies a boundary for source progress and state;
end of data marks a bounded source’s end. Neither marker by itself proves that
output is durable.

Add three components to this model: a normalizer that evaluates and validates
change events, an interval reducer, and a fenced target writer. The reducer
selects the greatest event per key between checkpoints. Cross-interval ordering
lives in durable target-associated state rather than a duplicate in-memory copy
of every key ever observed.

Existing marker encoding and expression handling need repair, and the actual
execution transport needs aligned barriers. Local reduction and merge prototypes
are evidence about individual mechanisms, not an integrated change-capture path.
Source controls must address running task attempts through Sail’s existing job
and driver ownership, not a source object left in the planner.

## Make ordering a source contract

Each normalized event has a key, a complete order for that key, an immutable
identity, an explicit action and a typed payload. A log position plus a stable
transaction row ordinal can order changes. A timestamp alone is insufficient
when distinct changes share it. A declared business tie-breaker is acceptable;
arrival order and arbitrary sorting of unrelated partitions are not.

An identity may be native to the source or derived from its incarnation, canonical
key and complete order when that combination uniquely names the replacement event.
A source incarnation distinguishes recreation from continuation. Preserve necessary
provenance through projection, or require an admitted input envelope. A payload-only
scan does not automatically supply this identity.

Use one comparison for upserts and deletes. Apply a greater version and ignore
a smaller one. Equal complete versions with identical canonical action and payload
are duplicates; different content is a conflict. A deletion retains its version
after its visible row disappears, preventing an older upsert from resurrecting it.
Canonical equality compares typed logical values, not Arrow buffer layout.

For valid ordered inputs, selecting maxima in intervals gives the same final
state as selecting the maximum across all events. Checkpoints therefore control
recovery and resource use without changing business results. Intermediate table
visibility can still differ while input is arriving.

## Validate the exact values that can be written

Normalize each original event once. Validate its key, order, action and schema
before reduction can discard it. A losing invalid row must fail the interval.
Use explicit non-null order and action rules, with defined equality for supported
key types; a null delete expression must not silently become an upsert.

Default admission requires deterministic normalization and immutable source events.
A nondeterministic computation needs a separately logged normalization step whose
output becomes immutable input, with explicit retention and rebuild semantics.
Evaluating a lazy plan for validation and evaluating it again for reduction does
not prove that the written rows were validated.

Default conflict checks cover each prepared interval and original versions matching
a pinned durable-state snapshot. Check before reduction discards evidence: durable
8:A conflicts with incoming 8:B even if 9:C wins. Bind the snapshot to the commit
precondition. These checks do not detect every contradictory superseded event in history.
If exhaustive verification is required, retain version and identity fingerprints
under an explicit admissible horizon and state budget. A durable source frontier
can justify reclamation; an arbitrary timeout cannot.

A validation receipt binds the checked normalized input, semantic version and
prepared output. The writer verifies it before publication. Preserve complete
validation without adding a second execution of the source plan.

## Choose storage by atomicity and table behavior

Durable state must remember the greatest version of both live and deleted keys.
Spark’s separate tombstone table is one layout, not a semantic requirement.

Prefer a target capability that atomically publishes row mutations with version
state or a reference to an immutable key-state index. It must preserve the ordinary
user table’s schema, reads and operations. Delta and Iceberg adapters need to prove
metadata preservation and enforcement for every admitted writer before claiming
that capability.

A fenced sidecar table plus the ordinary target is a valid alternative when
one transaction cannot cover both. Persist immutable prepared rows and record
each effect separately. A crash between effects must complete the original work.
Cross-table atomic visibility is not promised.

A physical state table exposed through a filtered view can combine live and deleted
state, but changes the public table contract. External reads, table identity,
schema and DDL all need explicit product acceptance. A hidden table-to-view
substitution is not an implementation shortcut.

## Make every effect recoverable and fenced

A prepared checkpoint binds source identity and boundaries, configuration and
semantic version, validation evidence, immutable output and required effect IDs.
Retries use that same work. Source replay may replace saved output only with a
proof that the same input and normalization remain available until completion.
Chunk artifacts and budget memory, disk and retention rather than collecting a
whole interval or archive in memory.

Every admitted durable target must reject obsolete owners at commit acceptance.
Atomically check epoch, refresh generation, table incarnation, effect identity
and content. A lease or serialized catalog commit is insufficient: an old owner
can reload the latest head. Build missing managed Delta and Iceberg adapters;
remove the unfenced fallback. Source and target admission report a missing capability
until its enforcement exists.

Cover creation, enrollment, schema changes, maintenance, refresh and worker commits.
External writers must obey the same authority or mandatory protocol. Reconcile
unknown commit outcomes by the original identity. An effect accepted before
ownership changed may finish publishing exact bytes; the replaced owner may not
authorize new effects.

## Refresh and migration

Keep correct key resolution and schema checks, including harmless key declaration
reordering. Changes to key meaning, ordering, normalization or storage need a
versioned migration. Resolve pending work under its recorded contract, fence old
writers and inspect retained versions and deletion state before switching.

A rebuild needs authoritative source data. That may be a consistent snapshot
plus a continuation frontier, rather than physical offset zero. Verify completeness
before destructive effects. Prefer building and publishing a new fenced generation
when supported; otherwise define the visibility and recovery of an in-place reset.

Existing data may have lost tied-event order or deletion history. Such state
cannot be repaired by changing a comparator alone. Require reconstruction or an
explicitly accepted baseline with a new source admission frontier.

## Deliberate differences from Spark

Spark 4.2.1 leaves equal-sequence winners within a batch undefined and gives equal
upserts different treatment from equal deletes in target merges. Those rules can
change the outcome when the same events cross a batch boundary. Replace them
with complete per-key order and one action-independent comparison. Sealing an
arbitrary winner would fix retries but leave the initial ambiguity.

Retain original-row validation, anti-resurrection state, schema checks and immutable
prepared work because they protect correctness. Do not preserve an auxiliary-table
name, error ordering, batch-lag watermark rule or permissive configuration fallback
merely for parity. Public metadata changes still require an explicit migration.

## Decisions and evidence

Choose the first source’s complete-order contract and the target’s atomic-state
capability. If atomic publication cannot preserve the ordinary table interface,
use fenced sidecar recovery rather than quietly changing that interface. Decide
whether the default validation scope is sufficient for the application or whether
historical conflict verification is worth its retention cost.

Pinned Spark and Sail source inspection and a small logic model support the
ordering counterexamples. They do not demonstrate a replacement engine. Acceptance
requires actual source-to-table permutations, checkpoint regrouping, invalid losing
rows, partial effects, stale writers, refresh recovery and external-reader checks.
The streaming normalizer, reducer, durable checkpoint integration and merge sink
remain to be built.
