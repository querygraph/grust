# Streaming pipelines and change capture on Sail

The [human review compendium](HUMAN-REVIEW.md) connects these pipeline contracts
with native Extensions, performance work and the current implementation evidence.

Streaming pipelines maintain tables as source data arrives. Change capture
applies keyed replacements and deletions, including changes delivered out of
order. Build both on Sail’s continuous flow-event execution, with explicit
recovery, bounded resource use and enforced writer ownership.

The initial product scope is one flow, a declared computation feeding a target,
with append and change-capture output. Independent multi-flow transactions,
streaming joins and general stateful coverage can follow separately. Spark API
compatibility remains useful, but it must not determine inferior data semantics
or weaken durability.

## What Sail already supplies

A flow event carries a data batch, per-row retraction flags that cancel earlier
rows, or an ordered control marker. Sail has markers for latency, watermarks,
checkpoints and end of data. A checkpoint identifies a recoverable input boundary;
a watermark promises that older timestamped rows will not follow.

| Existing foundation | Required addition or repair | Why it belongs here |
| --- | --- | --- |
| `StreamSource` describes a streaming scan | Recoverable source identity, replay contract and task-scoped control endpoints | A planning object cannot control a scan reconstructed on another worker |
| Streaming rewriter and encoded flow events | Evaluate user expressions on data only; preserve exact Arrow schemas and markers | Marker placeholder rows must never become user input |
| Execution streams and shuffle | Align checkpoint markers across the actual distributed graph and preserve their ordering | A local merge prototype does not establish distributed barriers |
| Job runner, driver and task actors | Coordinate checkpoints within one job and route commands to live task attempts | Reuse execution ownership without adding a driver to local mode |
| Table write and catalog commit paths | Durable preparation, idempotent effects and commit-time fencing | Format transactions alone do not identify the authorized pipeline owner |
| Memory pools and temporary-file facilities | Account for transport, preparation and state buffers; spill or apply backpressure | Bounded channels and periodic checkpoints do not bound total memory |

The foundation fits the intended design, but needs correctness repairs before
its durability can be extended. A local reference branch repairs zero-column
row counts, marker type fidelity, schema metadata, filter isolation and terminal
failure reporting. Workspace and selected public checks passed. Its mixed-batch
filter still has a material dense-marker performance limitation; projection and
asynchronous expressions remain to be isolated. The branch’s
[implementation results](STREAMSOURCE-FOUNDATION-RESULTS.md) state its evidence
and limits.

Source inspection also found unordered fan-in, an unbounded local replica overflow
queue and completion paths that discard control information. The local repairs
do not establish checkpoint alignment, durable completion or integrated recovery.

## Give change events stable meaning

An event has an entity key, a complete order for that key, an immutable source
event identity, an action and a typed payload. An upsert replaces the complete
row; a delete removes the visible row while retaining its version. A database
log position plus transaction row ordinal can provide the order. A timestamp
alone cannot distinguish different changes at the same instant.

Use the same comparator for both actions. Apply greater versions, ignore older
versions and treat identical events at the same complete version as duplicates.
Different content at the same version is a contract violation. Never invent
business order by sorting unrelated broker partitions or selecting the last
arrival.

Normalize and validate each original event once, before reducing an interval to
its greatest event per key. A losing invalid row must still fail validation.
The default detects conflicts within the prepared interval and against current
durable versions. It relies on an immutable source contract; it does not promise
to detect every contradictory superseded event. Exhaustive historical checking
is optional and needs retained fingerprints, an admission horizon and a budget.

These rules make grouping an optimization: valid events produce the same final
state across input schedules and checkpoint sizes. They do not promise identical
intermediate visibility while events are arriving.

## Choose storage by its guarantees

Live and deleted keys need durable ordering state so old events cannot undo newer
ones. That state need not duplicate every target key in an operator, nor require
Spark’s auxiliary table layout.

Prefer an atomic target transaction that publishes user-row changes together
with their version state or a reference to an immutable version index. This
preserves ordinary table reads only if the format and every admitted writer
maintain that reference. The capability remains to be implemented and tested.

A fenced sidecar state table plus the ordinary target is a reasonable fallback.
Its two effects need separate completion records and recovery after either one
commits. A physical state table exposed through a filtered view is another
option, but changes table identity, schema, DDL and external access. It must be
an explicit product choice, not a hidden substitution.

## Prepare once and recover the original effects

Persist a prepared checkpoint before output commits. Bind its source boundaries,
semantic version, normalized configuration, relevant operator state, validated
output and effect identities. Store output as immutable chunks when replay
cannot prove identical rows. Each effect identity must retain the same content
through retries and ownership changes.

If one table commits and another does not, finish the pending original work.
Reusing the identifier for additional rows loses those rows at a sink that
already committed; assigning a new identifier can duplicate the original append.
An unknown commit outcome must be reconciled by its original identity.

Recovery across separate effects does not promise atomic visibility across
tables. Keep state and artifacts while any pending effect or admitted restart
point depends on them. Chunked preparation and explicit memory and disk budgets
are required; reducing the checkpoint period is insufficient.

## Fence every durable mutation

A fence rejects an obsolete owner at commit acceptance. A lease merely permits
a successor to take over. A stale owner can reload the latest table version and
pass an ordinary compare-and-swap, so catalog serialization is insufficient.

The accepting authority must atomically check the owner epoch, refresh generation,
table incarnation, effect identity and intended content. Existing bounded Delta
reference code stages and ratifies exact commit bytes, but managed Delta and
Iceberg use an unfenced path. Build enforced adapters for those targets and
remove that fallback. Reuse catalog commit mechanisms where they can enforce
ownership; an authoritative commit service is justified only where those
mechanisms cannot and the service controls every publication path.

Cover creation, enrollment, schema changes, refresh, ordinary writes and cleanup,
including worker commits. A custom property honored only by Sail cannot fence
another engine. Permitted external writers must use the same authority or a
mandatory protocol that enforces the contract. A target becomes admitted when
its adapter proves this behavior; an external single-writer convention is not
a substitute.

## Make configuration precise

Use one versioned typed model for YAML, JSON and APIs. Reject duplicate or unknown
keys, conflicting aliases, incorrect scalar types and invalid enum values before
dependent planning. Connector options need validation too. Resolve overrides
in a deterministic scope model rather than letting the first analyzed flow
establish another flow’s environment.

Offer Dhall as an optional frontend that checks against the expected Sail type
and compiles to ordinary normalized JSON. The server performs the same validation
for every frontend. A pinned external compiler avoids embedding another runtime
in the execution engine. Deployments may accept only rendered artifacts; imports,
compiler resources and secrets references need explicit policy.

## Deliberate differences from Spark

Spark 4.2.1 leaves tied winners undefined and uses different equal-sequence
comparisons for upserts and deletes. Those choices can make outcomes depend on
batch grouping. Replace them with the complete-order contract. Preserve useful
key/schema validation and replay protection for their engineering value.

Bounded and continuous runs use the same checkpoint protocol. A bounded source
captures an end; success follows the final durable checkpoint, not stream closure.
Do not inherit batch-dependent late-data acceptance or millisecond truncation.
Any future event-time operator must enforce Sail’s watermark promise, or propose
an explicit revised marker contract before downstream operators rely on it.

Refresh requires authoritative reconstruction data, which can be a consistent
snapshot plus a change-log frontier. Physical offset zero is only one bootstrap
option. Changed order or storage semantics require a versioned migration:
resolve old pending work, fence old owners, then migrate or rebuild state.

## Decisions that make implementation concrete

The correctness requirements above are mandatory. The remaining choices are
mechanisms and delivery order:

1. Which replayable source supplies stable per-key order and event identity?
2. Can the first target atomically publish row and version state while preserving
   its ordinary table interface, or should it use fenced two-effect recovery?
3. Which existing catalog or authority can enforce every commit, including those
   from workers and permitted external writers?

Complete control-event handling and truthful completion because every sink
relies on them. Source control, fencing and typed configuration can develop in
parallel around stable identities. Prove one complete append path, then the selected
change-capture storage protocol; neither requires windows or a general state store.

Acceptance needs real process and task restarts, partial effects, unknown outcomes,
stale-owner attempts, source recreation, resource exhaustion and table interoperability.
Component prototypes and source inspection do not establish that protocol. The
streaming merge sink, durable checkpoint integration and end-to-end replacement
remain to be built.
