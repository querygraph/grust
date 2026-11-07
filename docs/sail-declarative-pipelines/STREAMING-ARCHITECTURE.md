# Durable streaming on Sail's existing execution model

Streaming tables append newly available rows without rebuilding their history.
Change capture maintains current records from ordered updates and deletes.
Both need stable results, recoverable writes and rejection of obsolete writers.
A fence enforces that rejection where a durable write is accepted.

Build these capabilities on Sail's continuous flow-event execution. Checkpoints
control recovery and resource use; they must not determine business results.
The initial scope is one independently recoverable flow, a computation feeding
a target. Independent multi-flow coordination and general streaming joins remain
outside that scope.

This optional detailed reference explains the required contracts and alternatives
for source participation, state and durable publication.

## Existing foundation and required work

Sail's `StreamSource` provides a streaming scan. Flow events carry data batches,
per-row retractions and ordered control markers. A retraction cancels a previous
row; it is not a business delete with an ordering value. A checkpoint marker
identifies an ordered boundary. A durable prepared record must bind that boundary
to source positions, state and effects before recovery can depend on it.

| Existing component | Reuse | Required correction or addition |
| --- | --- | --- |
| Source trait and provider bridge | Source resolution and scan planning | Replay capabilities, stable identity and controls for each running partition |
| Streaming rewriter and physical planner | Existing source and stateless plan integration | Data-only expression evaluation, explicit supported operators and safe optimizer transformations |
| Arrow encoding and plan codec | Batch transport and worker reconstruction | Exact row counts, types, metadata and recovery identities |
| Job runners and task actors | Local execution without a driver; cluster execution through driver and workers | Checkpoint control and acknowledgements scoped to task attempts |
| Exchange and stream transport | Per-channel ordering and data movement | Marker-aware routing, aligned fan-in and resource accounting |
| Query lifecycle and table commit paths | Registration, cancellation and publication seams | Truthful completion, durable effect identity and enforced fencing |

The local reference now preserves Arrow fields and zero-column rows, isolates
markers in supported filter and projection paths, and protects streaming sources
before optimizer pruning. It also repairs dependent projection composition and
preserves declared schemas. These qualified paths include supported asynchronous
expressions; they do not establish distributed recovery.

Mixed-marker fragmentation and short-stream compilation costs remain unresolved.
The composition rule's measured deep-wide slowdown is repaired, with a small
shallow-wide residual. Shared-host diagnostics establish no production performance
envelope. [Optional composition evidence](PROJECTION-COMPOSITION-RESULTS.md) records
the exact scope and every measured case.

Align participating channels at every supported exchange; ordinary asynchronous
merging is insufficient. Hash routing must not use fabricated marker payloads.

Collector retractions and final-checkpoint obligations across distributed plans remain
required. Distinguish cancellation, failure, input exhaustion and durable success.
The local append coordinator waits for its final table commit before reporting success;
ordinary query termination alone does not establish that commit.

## Source participation and execution ownership

A source capability must describe source identity, partition incarnation,
position meaning, replay guarantees and bounded-end capture. An incarnation
distinguishes a recreated source whose offsets may restart. Rate and socket
sources exercise execution but do not provide durable replay guarantees.
Bind the broker or storage descriptor and participating partitions to each
prepared interval. New partitions need an explicit discovery and bootstrap
policy; earliest retained data is not automatically a complete history.

Separate the planning descriptor from its live control endpoint. Workers
reconstruct fresh executable plans; an in-process source object held by a
planner cannot control those scans. Register endpoints when tasks start,
route commands through existing execution ownership and reject responses from
replaced attempts. Preserve stable flow and rebuild identities across transient
job identifiers.

Prefer job-runner ownership for a recovery domain contained in one job. The
recovery domain is the set of effects tracked together through restart.
Broader ownership needs justification from an actual multi-job requirement,
not a new service assumed in advance.

A bounded run captures source end positions in coordination with its readers.
Independent bounds do not constitute an atomic cross-source snapshot. Serialize
checkpoint requests initially. End of data and later stream closure count once;
ended inputs retain their assigned acknowledgements. Final success waits for
all required effects, not merely a closed stream.

## Ordered changes, evaluated once

A normalized change contains an entity key, complete per-key order, immutable
event identity, explicit upsert or delete action, payload and semantic version.
An upsert replaces the whole row. The semantic version identifies the key,
comparison, action, schema and normalization rules.
Preserve source provenance outside user projection or require input records
carrying the necessary identity and ordering fields. Stable replacement-event identity can derive from source incarnation,
canonical key and complete order; an independent native identifier is optional.

Require a source or application order that distinguishes different changes to
the same key. A log position plus row ordinal can qualify. Arrival order or
lexical broker partition names do not automatically express business order.
Deterministic fanout needs stable output ordinals; joins and aggregates need
separate identity contracts.

Apply greater orders and ignore smaller ones for both actions. Equal order
with identical canonical action and payload is a duplicate; different content
is a conflict. Canonical equality compares logical values under the declared
schema, not Arrow layout. Keep each key's winning order and deletion state so
an older update cannot resurrect a deleted row.

Evaluate key, order, action and payload once, then validate those exact values
before reduction. Invalid losing events must fail too. Require deterministic
normalization by default. Other computations need a separately logged immutable
normalization step with its own retention and rebuild contract.

Default verification checks every original row, conflicts within the prepared
interval and equality against the current durable version. Repeated identities
must map consistently within that retained scope. A detected conflict prevents
that interval's effects; earlier completed intervals remain committed.
This guarantees stable output for valid inputs, not detection of every invalid
superseded event in history. Exhaustive verification requires a limit on retained
conflict history, a source position proving older events cannot arrive, and a storage budget.

## Storage and recoverable publication

The storage invariant is durable key/version/deletion state coupled to the
user-visible mutation. It does not require two SQL tables. A sidecar stores
that state separately from the user-visible rows.

| Candidate | Benefit | Obligation |
| --- | --- | --- |
| Target transaction publishes rows and a reference to an immutable key-state index | One atomic publication; ordinary table reads can remain intact | Prove format metadata, snapshot recovery and all-writer enforcement |
| Fenced sidecar state plus ordinary target | Reuses separate state and data storage | Recover every partially completed effect from identical prepared work |
| Physical state table with filtered view or provider | Live and deleted state share a transaction | Explicitly changes public table identity, reads and write interfaces |

Prefer atomic publication when the target can preserve the ordinary table
contract. Build the required Delta and Iceberg capabilities; do not assume
they already exist. A separate key-value store does not remove the second
durability domain. Never silently substitute a view for a table.

A prepared record binds exact source boundaries, semantic/configuration identity,
state snapshots, validated output and required effect identities before writes.
Sealing saves output unchanged for retries. Equivalent replay is acceptable
only if input and transformed output remain identical and available until
completion. Validation evidence must refer to that exact normalized evaluation.

Suppose two append tables skip already committed transaction identifiers.
One commits an interval before a crash; the other does not. Reusing the
identifier for that interval plus new arrivals loses new rows in the completed
table. Giving the entire replay a new identifier duplicates its original rows.
Preserve each identifier's meaning and each effect outcome until recovery finishes.

Reconcile pending effects before advancing conflicting state. An archive can
finish prepared work after source loss, but cannot replace unread future input.
Keep accepted, rejected and unknown outcomes distinct. A timeout requires lookup
by the same identity, not a newly identified write. Separate effects may be
partly visible; recovery alone does not promise cross-table atomic visibility.

## Enforced ownership at commit acceptance

A lease permits takeover. A fence rejects obsolete ownership where an effect
is accepted. Checking a lease before submitting an ordinary table-version
comparison is insufficient: a paused owner can reload the latest head.

Every durable target must atomically check owner number, authority and table
identity, rebuild generation, expected state, effect identity and content.
An identical accepted request returns its recorded outcome; changed content
under that identifier fails. Exact bytes accepted before takeover may finish
publication, but the obsolete owner cannot authorize new effects.

Extend existing catalog and format commit interfaces. Implement filesystem Delta,
managed Delta and Iceberg adapters, including creation, reset, maintenance and
schema mutations. Worker execution needs authenticated access to the authority,
not merely a serialized token. Missing adapters are required build work; targets
remain unsupported until enforcement is established.

Every permitted writer must use the authority or an enforced protocol. A Sail-only
table property does not fence another engine with direct publication credentials.
Use an existing catalog authority where possible; a new commit service is justified
only if it can control publication and its deployment costs are acceptable.

## State, progress and resource limits

A manifest names snapshot files. Recovery loads the snapshot for its recorded
boundary and checks operator configuration as well as schema. Retain every
artifact required by incomplete effects and valid restart points. A newer
recorded source position does not authorize cleanup. Temporary spill and durable
recovery storage have different lifetimes.

Reuse Sail's memory pools, temporary-file facilities and object-store access.
Account for retained transport buffers, prepared output, state, snapshot workspace
and metadata across tasks. Existing replica transport has unbounded overflow;
replacing it with blocking queues without examining fan-out can deadlock.
Use byte budgets, backpressure or bounded spill while preserving ordered control
progress. Periodic checkpoints alone do not bound memory.

Full snapshots suit only a tested maximum state size. Larger state may need
partitioned or incremental snapshots. Delete markers require durable proof that older input cannot arrive before they can
be discarded; arbitrary expiry is unsafe.

For windows, retain Sail's [watermark promise](https://github.com/lakehq/sail/blob/85c6cca01cd521dd778bc200c987a34edf141de1/crates/sail-common-datafusion/src/streaming/event/marker.rs#L18):
no later row has an older event timestamp. Enforce late-row handling before
rows enter the downstream stream, including after emission. A distinct threshold
marker is an alternative only with explicit downstream semantics. Restore
per-input progress and terminal transitions; idleness alone proves no completeness.
Checkpoint boundaries must not determine lateness.

## Configuration, migration and acceptance

One strict, versioned configuration model should accept YAML, JSON and API
settings. Reject duplicate/unknown keys, wrong types and alias conflicts; resolve
scope before dependent planning. Optional Dhall compilation should produce the
same validated model outside the runtime. Bind effective configuration to prepared
work; type checking does not establish source replay or target fencing.

Changing identity or ordering requires migration. A complete rebuild may use an
authoritative snapshot and its matching log position.
Prefer a new computation generation that prevents the old one from writing, with atomic
publication where supported. Preserve
pending accepted effects and define visibility for any in-place reset.

## Intentional differences from Spark

Spark 4.2.1 permits undefined equal-sequence winners and different equality rules
for upserts and deletes in its [change processor](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/Scd1BatchProcessor.scala#L80).
Replace those rules with the complete-order contract. Sealing alone cannot fix
initial schedule dependence. Preserve validation and recovery because they protect
correctness; isolate protocol translation from native execution semantics.

Acceptance requires real local and cluster marker tests, permutations and checkpoint
regrouping of valid changes, slow-consumer resource tests, partial-commit recovery,
unknown-outcome reconciliation and stale-writer rejection. The first local Delta append
path is implemented; [HUMAN-REVIEW.md](HUMAN-REVIEW.md) records qualification and limits.
Distributed recovery, change capture and other target adapters remain required.
The public change-state representation and each adapter's commit authority need their
own implementation decisions.
