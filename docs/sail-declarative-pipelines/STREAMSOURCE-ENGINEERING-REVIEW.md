# StreamSource architecture and required engineering changes

Sail can support durable streaming pipelines by extending its existing source,
flow-event and job execution model. This optional diagnostic reviews Sail baseline
`85c6cca01` and the existing pipeline runtime that processes finite input ranges.
Its findings explain constraints on durable execution and the required corrections.

Spark Declarative Pipelines is a useful behavioral reference, not the authority
for Sail's architecture or correctness. Preserve useful client interfaces and
well-defined behavior. Replace nondeterminism, weak ownership and permissive
configuration where they undermine reliable execution.

The local reference has since repaired Arrow fidelity, zero-column rows, supported
filter/projection marker isolation, source preservation before pruning and dependent
projection composition. Supported asynchronous expressions are isolated too. These
repairs have local component and public-query evidence, not distributed recovery
qualification. Mixed-marker fragmentation and short-stream planning cost remain
unresolved; the composition repair retains a small shallow-wide residual and no
production performance claim. [Optional current results](PROJECTION-COMPOSITION-RESULTS.md)
state the qualified scope. The diagnostic findings below describe the named baseline.

## What Sail already provides

The source baseline is Sail `85c6cca01`. `StreamSource` supplies a data schema,
filter capabilities and a scan producing encoded flow events. Each event is
a data batch with retraction flags or a control marker. Retractions cancel
previous rows; they are distinct from business deletes carrying an order.
Markers describe latency, event-time progress, checkpoints and end of data.

| Existing component | Reuse | Required extension or correction |
| --- | --- | --- |
| Source trait and table-provider bridge | Source resolution and the streaming scan boundary | Optional replay capabilities, stable source identity and controls for the actual running partition |
| Logical rewriter and physical planner | Existing source, projection, filter, union and limit planning | Make admitted operators act on data without evaluating expressions on marker placeholders |
| Arrow encoding and plan codec | Event transport and worker plan reconstruction | Preserve exact types, row counts, schema metadata and source identity |
| Job runner, driver and task actors | Local execution without a driver; distributed execution through running tasks | Route checkpoint commands and acknowledgements through task attempts and reject stale responses |
| Stream transport and exchange | Per-channel ordering and existing data movement | Align all participating channels, route markers correctly and account for retained bytes |
| Query lifecycle and sinks | Query registration, cancellation and write integration | Separate input exhaustion, failure, cancellation and durably completed output |
| Catalog and format commit operators | Actual table publication boundaries | Enforced writer fencing and recoverable operation identities for every admitted target |

The only concrete `StreamSource` implementations in this baseline are rate and socket
sources. They do not supply durable replay contracts. A rate row counter does
not reproduce wall-clock timestamps, and a socket stream cannot recover data it
never retained. Neither establishes exactly-once source-to-table execution.

## Correctness gaps that affect the design

**Expressions are not isolated from control events.** Marker batches contain
placeholder payload values. The rewriter uses ordinary projections and a
predicate shaped as `user_predicate OR marker_present`; the user predicate is
evaluated first. A valid data query can therefore fail or invoke a function
on a marker. Use flow-aware transform adapters that evaluate only data and
forward markers unchanged. Rearranging one Boolean expression is not a general
solution for projections and functions.

**The actual execution graph does not align checkpoints.** Stream fan-in
uses ordinary asynchronous merging, and shuffle partitions ordinary batches.
Per-channel ordering does not produce a consistent boundary across channels.
Define alignment, marker propagation and participants at every admitted
exchange boundary, including plans rewritten for cluster execution. Continue
to refuse unsupported shapes until those semantics exist.

**Completion is not durable success.** The collector discards markers and
ignores retractions. The bounded adapter ends without completing a checkpoint,
and the limit operator can terminate before final markers. Console output can
consume errors, and query stopping drops the stream. Durable execution must
fail visibly, preserve pending accepted work and report success only after its
required effects complete. Support retractions correctly or reject them explicitly.

**Encoding needs exact Arrow coverage.** Focused probes using unchanged source
modules and pinned dependencies reproduced failure to decode zero-column events,
including all four marker kinds. Nonnullable decimal marker payloads failed at
nondefault precision and scale for all four decimal widths. The probes also
reproduced strict-cast failure on marker placeholders and schema metadata loss.
These baseline reproductions were component probes. Later local SQL checks do not
retroactively turn them into distributed workload evidence.

**Bounded channels do not imply bounded memory.** Local replica transport has
an unbounded overflow queue. The append prototype holds an entire interval,
window snapshots materialize full state, and archive paths collect complete
outputs. Reuse Sail's memory pools and temporary-file facilities with explicit
reservations, chunked artifacts and backpressure or spill. A naive bounded
queue can reintroduce fan-out deadlock, so test the real graph under slow consumers.

## Replace compatibility-driven semantics

The useful change-capture abstraction is an ordered stream of entity changes,
not a sequence of Spark-shaped batches. For valid inputs, changing partition
scheduling or checkpoint boundaries must not change the final entity state.

| Previous constraint | Engineering replacement | Consequence |
| --- | --- | --- |
| Undefined equal-sequence winners, stabilized only after sealing | A declared source/application order per key, with immutable event identity and defined duplicate/conflict handling | No arbitrary winner based on arrival order; ambiguous order needs an explicit contract |
| Different equal-version rules for upserts and deletes | Apply the same complete ordering relation to both actions and retain the latest version even after deletion | A delete cannot disappear merely because the same events were grouped into another interval |
| Validate a lazy input, then evaluate it again for reduction | Normalize each accepted event once and validate those exact values before reduction | Nondeterministic re-evaluation cannot invalidate the validation evidence |
| Copy the auxiliary-table layout as part of the semantics | Choose storage by atomicity, ordinary table behavior and interoperability | Prefer one atomic row/version/delete-metadata transaction when supported; otherwise require an explicit recoverable multi-effect protocol |
| Catalog serialization or external single-writer convention substitutes for fencing | Enforce owner generation at commit acceptance for every durable target | Build managed Delta and Iceberg adapters; remove the unfenced durable fallback |
| Execution modes and late-data rules inherit batch-engine accidents | Define bounded and continuous execution on the same event protocol and preserve a coherent watermark promise | Spark scheduling does not determine data correctness |
| YAML coercions, ignored options and order-dependent settings preserve compatibility | Strict versioned configuration and connector admission before dependent planning | Invalid input fails with a useful field-level explanation |

An upsert inserts or replaces a key; a delete removes its visible row but keeps
enough ordering metadata to prevent resurrection by an older event. A complete
order can include a source transaction position and row ordinal. A timestamp
alone is insufficient when distinct changes can share it. Do not invent business
order by sorting unrelated broker partitions. Event identity may be native or
derived from source incarnation, canonical key and complete order for replacement
events. Preserve that provenance through decoding and projection. Bind source
descriptors and checkpoint participants explicitly; newly discovered partitions
need a defined bootstrap policy rather than silent retained-only history.

Identical canonical events at the same complete version are duplicates;
different content is a contract violation. The default checks original rows,
within-interval conflicts and equality against current durable state. It does
not promise exhaustive detection of invalid superseded history. That stronger
check requires retained fingerprints, a justified replay horizon and a budget.
An unbounded conflict index must not become the default merely to make every
invalid history fail at the same point.

Keep original-row validation, stable prepared effects and explicit schema checks
because they protect correctness, not because Spark happens to use them. Likewise,
key changes and schema changes need deliberate migration; relaxing them without
a state migration would be an engineering regression.

## Build fencing at the publication boundary

A lease permits a successor to take over. It cannot prevent the old owner from
resuming. A table-version compare-and-swap can also accept an obsolete writer
that reloads the latest version. The accepting authority must atomically verify
owner generation, target identity, effect identity and content before reserving
or committing the effect.

The bounded Delta reference path already stages and ratifies exact bytes, but
managed Delta and Iceberg take a plain path. New-table creation and worker access
to the authority also need coverage. Generalize existing catalog/commit seams;
use an enforced commit service only where the backend cannot express ownership
and that service can control all publication paths.

A table property respected only by Sail cannot fence another engine. Every
permitted writer must use the enforcement boundary or a mandatory protocol it
honors. Retrying an effect accepted before takeover may finish publishing its
exact bytes; an old owner must never authorize new effects. Unknown commit
outcomes require reconciliation by identity, not a fresh write.

## Make configuration typed without forcing a new language

Use one versioned typed model for YAML, JSON and API-supplied settings. Reject
duplicate and unknown keys, invalid scalar types, conflicting aliases and
unknown enum values. Resolve scope and overrides before dependent planning.
Connector options need schemas too; a map of strings is not semantic validation.

Direct execution of the existing project parser accepted duplicate names,
wrong scalar types and unknown nested library fields. Source inspection also
found an unknown parse-mode value falling back to permissive behavior to match
Spark. These are concrete reasons to replace the behavior.

Offer Dhall as an optional authoring frontend: check against the expected Sail
type, compile to normalized JSON, then run the same admission checks. Prefer a
pinned external compiler over embedding the unmaintained Rust implementation.
Control imports and compiler resources; deployments may accept only rendered
artifacts. Type checking cannot prove that a source retains data or that a
target enforces fencing, so those remain runtime capability checks.

## Implementation order and acceptance

Durable execution requires event-safe operators, exact encoding, truthful completion,
source controls and stable recovery identity. Prove alignment and bounded resources
through actual local and cluster plans. These contracts can develop together;
none requires waiting for an unrelated operator. Qualify one fenced source-to-target
path and its crash tests before admitting further durable targets.

A checkpoint remains a recovery boundary. It must not become a boundary that
changes business results. State, source positions, normalized configuration and
prepared effects share an explicit semantic version. Existing pending work must
be resolved under its recorded contract; changed ordering or storage semantics
require a controlled migration or rebuild from an admitted consistent snapshot.
A complete source origin is one bootstrap option, not the only valid one.

Tests must cover marker/data mixtures, exact Arrow types, task replacement,
slow replicas, overlapping checkpoints, partial writes, writer takeover and
unknown commit outcomes. Compare semantics across checkpoint segmentations and
input schedules. Test YAML, JSON and Dhall for equivalent accepted configuration.
Spark comparisons remain useful where behavior is deliberately retained; exact
parity is not a correctness gate for documented improvements.

The required invariants are settled: safe control events, deterministic valid
change streams, enforced fencing, bounded resources and strict configuration.
The remaining architectural choices are the first source/target pair, the
backend that can enforce commits, and the interoperable storage representation
for retained ordering and deletion metadata. Select those mechanisms by their
actual contracts and costs.
