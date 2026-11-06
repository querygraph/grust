# Building recoverable streaming pipelines on Sail

Streaming pipelines should maintain tables continuously and recover without
losing or repeating effects. Change capture adds ordered keyed replacements and
deletions whose final state must not depend on checkpoint size. The implementation
should extend Sail’s flow events, execution ownership and table commits, while
repairing the foundation those guarantees depend on.

Start with one flow, a computation feeding one target. Include append and change
capture, developing the simpler append path first to exercise shared recovery.
Do not make windows, joins, independent multi-flow transactions or a broker-specific
client prerequisites for that path.

## Repair the foundation before promising recovery

Sail already carries data and ordered control markers through streaming plans.
At Sail `b52144955`, the rewrite can evaluate expressions on marker placeholders;
fan-in and shuffle do not establish graph-wide checkpoint alignment. Component
probes also reproduced zero-column decoding, decimal placeholder and schema
metadata defects. A local reference implementation now repairs event fidelity,
isolates filter predicates from markers and propagates terminal query failures.
Its workspace and selected public checks passed. Dense alternating markers expose
a material filtering cost that persists in optimized component diagnostics.
The branch and evidence are described in
[Streaming foundation repairs and remaining decisions](STREAMSOURCE-FOUNDATION-RESULTS.md).

A local projection increment now evaluates synchronous and supported asynchronous
expressions only on ordered data runs, preserves qualified names and metadata,
and reconstructs the node through the worker codec. Its immutable workspace and
selected public checks passed. Standard metrics remain enabled; mixed-marker
fragmentation still has material cost. Logical optimization can erase a streaming
source before detection, so preserve source participation before claiming global
isolation or durable coordination. The
[projection results](STREAMSOURCE-PROJECTION-RESULTS.md) bound the evidence.

A flow-aware transform must evaluate user code only on data and forward markers
without alteration. Use Sail-owned adapters or narrowly attributed
implementations where dependency behavior must change; avoid accumulating expression-specific
workarounds. Preserve existing stateless behavior with controls that fail on
the unmodified path.

Distinguish successful completion, cancellation, input failure and physical stream
closure. A bounded source emits end of data, then participates in the final
checkpoint. A run succeeds only after the required effects complete. Propagate
sink failures and refuse unsupported retractions or execution options instead of
silently ignoring them. Console failures and atomic terminal failure reporting
are implemented locally; final durable completion and cancellation classification
are still separate work.

These repairs precede durable sink claims because losing a marker, hiding an
error or evaluating a marker as data invalidates every recovery protocol above it.

## Establish execution identity and source control

`StreamSource` is a planning descriptor, not a live distributed control handle.
A scan is reconstructed in a running task. Add a capability description and
register runtime control endpoints identified by flow, source, partition and
task attempt. Route checkpoint and bound requests through existing job-runner,
driver and task actors. Reject responses from superseded attempts.

Local execution needs no new driver. A recovery domain inside one job can use
its job runner; distributed execution delegates through its driver. Stable flow
identity survives process restarts, while query attempts and refresh generations
remain distinct. Source positions include incarnation and versioned interpretation.

Serialize checkpoint requests initially. Align the same marker across participating
inputs in the actual transport graph, with explicit end/close accounting. Test
staggered completion, task replacement, overlapping ordinary/final requests and
barriers passing through shuffle. Local merge tests alone are insufficient.

## Build mandatory commit fencing in parallel

A lease cannot stop an old owner that resumes after takeover. Every durable
target must enforce owner epoch, generation, table incarnation and effect identity
at its commit boundary. Ordinary optimistic table-version checks do not establish
that contract.

Extend the existing staged-commit and catalog seams. Build managed Delta and
Iceberg adapters rather than retaining their unfenced execution path. The first
adapter may use a narrower backend, but every admitted target needs the same
acceptance guarantees. Creation, enrollment, schema mutation, refresh and worker
commit routing are part of the adapter, not exceptions.

An accepted effect may finish publishing exact bytes after takeover; an obsolete
owner may not authorize another effect. Persist acceptance and reconcile uncertain
outcomes by identity. Test both sides of takeover and timeouts around acceptance,
including a stale owner that reloads the latest table head. If external engines
can write, the enforcement boundary must constrain them too.

Use an existing catalog if it can enforce the contract. A commit service adds
availability, access-control and operational obligations and is justified only
when it can actually become the authoritative publication boundary.

## Prove one durable append path

Connect a replayable source, aligned checkpoint, durable prepared record and
fenced target writer. Preparation binds exact source boundaries, semantic and
configuration identity, necessary state, immutable output chunks and effect IDs.
A proven identical replay path may replace saved output; offsets alone are not
that proof.

Recover pending original effects before accepting new work under their identifiers.
A target receipt, source progress and coordinator completion are distinct facts.
An unknown outcome must be reconciled without inventing a new write identity.
Retain all artifacts needed by incomplete work and admitted restart points.

Use real process restart tests around preparation, acceptance, publication and
completion recording. The existing file-sink harness retains positions in memory;
separate Delta transaction-option tests do not qualify the integrated path.
Exercise source retention loss and recreation, authority failure and corrupt or
missing artifacts as explicit failures, never skipped progress.

## Add deterministic change capture

Require a complete source/application order per entity key and immutable event
identity. Normalize key, order, action and payload once; validate those values
before reduction. Apply greater versions, ignore older versions and detect
conflicting equal versions. Use the same rule for upserts and deletes. Retain
the latest version after deletion so an older upsert cannot resurrect the row.

Default conflict checks cover the prepared interval and current durable version.
They rely on the source contract and do not verify every superseded event in
history. Offer exhaustive fingerprint retention only with an explicit admission
horizon and state budget.

Choose storage by atomic publication and the ordinary table interface. Prefer
one transaction publishing user-row changes and version state where supported.
Otherwise use a fenced sidecar with separate effect completion and recovery between
commits. A state table exposed through a view requires explicit product acceptance;
it must not silently replace a table.

Test permutations and checkpoint regrouping of valid events, duplicate deliveries,
conflicts, invalid losing rows, null actions and interrupted publication. Include
durable 8:A against incoming 8:B followed by 9:C: reduction must not hide the
conflict with the pinned validation snapshot. Bind that snapshot to the commit
precondition and budget original-version checking without reevaluating input. Check
ordinary external reads and table operations. A streaming reducer and merge sink
remain implementation work; whole-batch prototype reduction is not that path.

## Bound resources and validate configuration throughout

Reserve memory for transport queues, interval reduction, output preparation and
operator state using Sail’s existing memory pools. Reuse temporary-file facilities
for spill, with disk and retained-artifact limits. Avoid whole-output archives
and synchronous full-state rewrites as an assumed scalable default.

An unbounded replica overflow queue protects fan-out liveness today. Replacing
it with a blocking queue can deadlock a forked graph. Prove graph-wide progress
under slow consumers using bounded credits or spill, and measure aggregate bytes,
not merely batch counts. Checkpoint frequency does not provide this bound.

Use one typed, versioned configuration model before dependent planning. Strict
YAML, JSON and API inputs share schemas, defaults, alias rules and connector
validation. Optional Dhall compiles against the expected type to ordinary JSON.
A shared acceptance corpus must catch duplicate keys, coercions, unknown options,
conflicting scopes and frontend/schema drift.

Configuration work and foundation repairs can proceed independently. Stable
semantic identity is needed before durable preparation, so effective normalized
configuration and schema versions must be defined before that integration lands.

## Preserve native Extensions and add the Comet scalar boundary

Port the existing native extension host as independently verifiable contracts:
package identity, relation dispatch, scalar worker lookup, placement, memory
admission and lifecycle cleanup. This preserves separately packaged functions and
relations in the StreamSource redesign rather than rebuilding only pipeline SQL.

The standalone Arrow-only scalar adapter can develop independently using Comet’s
pinned C interface. Its package integration depends on the host port and verified
result lifetime, metadata and immutable-function admission. Keep the existing
DataFusion-FFI route for current packages; select each boundary explicitly and
retain its identity through planning and recovery. Comet does not promise ABI
stability across releases.

Native functions need data-only projection and asynchronous expression evaluation
before those operators may call them safely. Live extension sources need the same
checkpoint/replay contracts as other StreamSources. Durable computation must bind
code/configuration identity and either reproduce identical results or persist
prepared output. Define C relation capabilities separately from scalar calls.
The standalone [extension integration design](EXTENSIONS-STREAMSOURCE-INTEGRATION.md)
explains alternatives, existing code and the decisions preceding dependent code.

## Migrate only after the replacement proves its contract

Spark 4.2.1 source remains evidence for retained behaviors, not an obligation to
keep undefined ties, asymmetric action comparisons, permissive option fallbacks
or batch-dependent event-time decisions. Tests should state intentional differences
and compare independently specified results. Preserve correct name resolution,
original-row validation, replay receipts and schema checks.

Existing pending effects must finish under their recorded semantics before a
new generation takes ownership. Inspect retained key versions and deletion state;
missing historical information may require a rebuild. A consistent snapshot plus
continuation frontier can be a valid bootstrap, so do not require physical origin
where the source supplies a stronger usable contract.

Windows and deduplication follow only when their state, watermark and reclamation
contracts are defined. Preserve Sail’s promise that a watermark excludes later
older timestamps, or explicitly change that contract before relying on it.

Replacement requires integrated recovery, fencing, resource and interoperability
evidence at the actual source/target boundary. Component probes identify defects;
prototype reports demonstrate limited mechanisms. Neither is a production gate
for the unbuilt distributed checkpoint and change-capture integration.
