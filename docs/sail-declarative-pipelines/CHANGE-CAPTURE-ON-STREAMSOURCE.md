# Maintaining current records from a stream of changes

Change data capture, or CDC, maintains a table from record replacements and deletions.
An account update may arrive late, arrive twice, or arrive after a deletion. Those
conditions should not change the final table when the source supplies an unambiguous
order for that account's changes.

The first operation replaces a complete row or deletes it. Partial field updates and
queries over historical versions need separate semantics.

## Add record ordering to recoverable writes

The streaming design saves fixed work before writing it, retries the same writes after
failure, and makes the destination reject replaced workers. Change capture adds three
steps: turn each source event into a well-defined change, select the newest change for
each key, and merge those changes with the destination's stored versions.

A key identifies the record being changed, such as an account number. The system
must retain each record's latest version even after deletion. The proposed layout keeps
this information beside the table instead of in the executing operator's state.
Sail's `StreamSource` and ordered control messages provide the execution foundation;
these change operators and their recovery integration remain unbuilt.

## Make “newest” independent of arrival order

Suppose account A is deleted at version 12. A late update at version 11 must not restore
it, while an update at version 13 may do so. The version remembered for the deletion
provides that protection. Restarting, changing checkpoint frequency or regrouping the
same valid events should leave the same final record. Intermediate visibility may differ
while events arrive.

Each change therefore needs a key, a complete order for that key, an immutable event
identity, an explicit action and a typed payload. A complete order distinguishes different
changes to the same record; it need not order unrelated records.

A database log position plus the row's position within its transaction can supply this
order. A broker offset also works if broker append order defines the intended record
order and all changes to a key remain in the same partition. Stable application versions
or business tie-breakers are alternatives. Timestamps alone are insufficient when two
changes share a timestamp. Partition replacement or migration needs an explicit rule;
sorting offsets from unrelated partitions invents an order.

If a source cannot supply this information, it can still feed an append-only pipeline.
It cannot support deterministic replacement of current records under this contract.

An event's identity distinguishes a retry from a new event. It can come from the source
or be derived from the source's unique creation identity, key and complete order when
those uniquely name an event. Preserve that information through projections, or require
an input record that carries it. Ordinary payload columns do not automatically provide it.

Use one comparison for both updates and deletes. Apply greater versions and ignore older
ones. Equal versions with equal actions and payloads are duplicates; different content
is a conflict. Compare typed logical values, not the arrangement of Arrow memory buffers.

## Check every change before discarding older ones

Selecting only the newest row too early hides invalid or contradictory input. If the
table stores version 8 with value A, an incoming version 8 with value B is a conflict
even when version 9 with value C appears in the same checkpoint and would win.

Evaluate each original event once. Check its key, order, action and schema before
reducing the set to one winner per key. Invalid losing rows must fail the interval too.
Require non-null orders and actions, define equality for supported key types, and reject
an ambiguous null delete condition. Do not run one lazy computation to validate rows
and another to write them: they need not produce the same values.

By default, source events must be immutable and their conversion into changes must be
deterministic. Nondeterministic conversion needs a separate saved result with explicit
retention and rebuild rules.

Compare conflicts within the input and against the matching versions in a fixed snapshot
of the stored state. The commit must check that it still applies to that snapshot.
Persist evidence identifying the checked input, comparison rules and intended output.
This validation receipt lets the writer verify that it publishes the work that passed
validation. It does not replace the checks themselves.

Within the input and retained verification state, reusing an event identity with a
different key, version, action or payload is also a conflict.

There is a deliberate limit to historical conflict detection. The default checks the
current interval and the retained state. Detecting every contradictory old event requires
keeping fingerprints of older versions and identities, including identities reused for
different keys. That stronger mode costs storage and needs a defined verification range.
Discard records only when a durable source position or another explicit guarantee rules
out relevant older events; an arbitrary timeout does not establish that safety.

## Store versions without changing the public table unexpectedly

Flink commonly keeps per-key state in the running job and checkpoints it, with disk-backed
storage available. That is a reasonable alternative to target-associated versions. It
requires coordinating state restoration with table publication and defining how other
permitted writers affect that state. The proposed target-associated layout keeps ordering
history with the table, but adds lookup and indexing work to its adapter. Compare these
costs before choosing a layout; neither approach removes the need for durable state.

Readers should continue to access an ordinary table. Live and deleted keys both need
version state, but that does not require Spark's particular auxiliary-table layout.

| Choice | Benefit | Cost or limitation |
| --- | --- | --- |
| Commit row changes and version state together | Readers and recovery observe one consistent change | The target must preserve the state or an immutable reference to it; all permitted writers must maintain it |
| Keep version state in a separate protected store | Works when one transaction cannot cover both | Recovery must finish partly completed writes; readers cannot assume atomic visibility across the two stores |
| Store all state in a table and expose live rows through a view | Live and deleted state can share a transaction | Changes table identity, schema, operations and external access |

Prefer a single transaction when the target can demonstrate it while preserving ordinary
table behavior. Otherwise evaluate a separate store with the same retry and ownership
protections as the visible table. A silent table-to-view substitution is not an equivalent
implementation. Delta and Iceberg each need their own capability and interoperability checks.

## Rebuild without forgetting deletions

Changing key meaning, ordering, conversion rules or storage requires a versioned
migration. Harmless reordering of key declarations need not rebuild data. Finish pending
work under its recorded rules, prevent old workers from starting new writes, and inspect
retained versions before switching.

A rebuild needs complete authoritative input, such as a consistent snapshot followed
by its change log. Verify that completeness before destructive work. Prefer a separately
identified replacement generation when the target supports it; an in-place reset needs
explicit visibility and failure behavior. A new comparator cannot recover missing event
order or deletion history. Reconstruct that history or explicitly start from a new baseline
with a defined earliest accepted source position.

## Deliberate differences from Spark

Spark 4.2.1 leaves equal-sequence winners within a batch undefined and treats equal
updates differently from equal deletes during merges. The same events can therefore
produce different results across batch boundaries. Complete per-key order and the same
comparison for both actions remove that ambiguity.

Preserve useful schema checks, validation of original rows and protection against old
updates restoring deleted records. Auxiliary-table names, error ordering, batch-lag
watermark behavior and permissive configuration do not justify weaker guarantees.
Public metadata changes still require migration.

## Decisions and evidence

Which source supplies the required record order and event identity? Can the first target
commit rows and versions together while preserving ordinary table access? Does the
application need conflict verification beyond the default retained scope?

Source inspection and a small logic model support the ordering counterexamples. Acceptance
still needs real source-to-table tests with reordered input, changed checkpoint groupings,
invalid losing rows, partial writes, replaced workers and interrupted rebuilds. The
[Flink comparison](FLINK-COMPARISON.md) explains why checkpoint recovery and a stream of
updates do not, by themselves, supply this record-version policy.
