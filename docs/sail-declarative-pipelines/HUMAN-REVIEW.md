# Human review: declarative pipelines, Extensions and performance on Sail

Build Sail Declarative Pipelines to maintain tables continuously from declared
computations, including ordered change capture and recovery after failure. Preserve
separately packaged native Extensions and add Apache DataFusion Comet’s Arrow-only
C scalar interface. Incorporate measured performance advances within Sail’s
existing execution architecture, with small changes that people can understand,
verify and maintain.

The desired result is one coherent Sail capability. Pipeline declarations describe
what to compute; Sail plans and executes it; Extensions supply additional functions
or relations; recoverable publication makes the resulting table effects durable.
This work does not require streaming joins, arbitrary stateful operators or
transactions spanning independent pipelines in its first usable delivery.

## Start from the guarantees people need

A table-maintenance system must give each input change a stable meaning. Retrying
work after a crash must neither lose nor duplicate its effects. A successor must
reject writes from an obsolete owner. User expressions must see actual data,
rather than internal control records. Native code must preserve schemas and keep
its callbacks valid until their final use. These requirements determine the design;
matching a Spark API does not justify weakening them.

For example, suppose a checkpoint writes one table and crashes before recording
completion. Retrying under a new write identity can duplicate rows. Reusing the
identity with different content can silently lose rows. Persist a prepared record
that binds the original input boundary, computation and effect identities before
publication. Include immutable saved output or a proven identical replay path.
Recover those exact effects, reconciling uncertain outcomes before
advancing progress.

A lease alone cannot enforce that rule. An old process may resume after its lease
expires and reload the latest table head. Every admitted durable target therefore
needs ownership checks at commit acceptance. Successful cancellation, stream closure
and durable completion are different events and must remain distinguishable.

## Fit the work to Sail’s foundations

Sail already represents streaming computation as continuous flow events. An event
contains data with per-row retraction flags that cancel earlier rows, or an ordered
marker for latency, watermark, checkpoint or end of data. `StreamSource` describes
a streaming scan; the executing task owns the live scan. Use this foundation
instead of replacing it with repeated bounded batch jobs.

| Existing Sail component | Responsibility of the redesign |
| --- | --- |
| StreamSource, flow events and streaming rewriter | Preserve data types, isolate expressions from markers, expose replay and task-attempt source controls |
| Local job runner, distributed driver and task actors | Coordinate checkpoints through existing execution ownership; keep local mode independent of a new driver |
| Plan resolver and physical-plan codec | Preserve scoped names, source identity and complete expression fields across worker reconstruction |
| Catalog and staged table commits | Prepare original effects, enforce writer fencing and reconcile target receipts |
| Memory pools, task resources and temporary storage | Fund queues, native allocations, prepared output and state; bound retention and provide spill where required |
| Extension discovery, registration and worker loading in the existing integration branch | Port package identity, placement, cleanup and native function/relation behavior to the foundation while adding another scalar boundary |

Follow Sail’s Rust, Arrow and DataFusion patterns. Prefer focused operators and
existing ownership seams over parallel frameworks. New physical nodes and expressions
need codec support whenever execution can reach workers. Keep optional connector
dependencies behind the established feature pattern. If dependency behavior must
change, assess a narrowly attributed Sail-owned implementation against an upstream
change; avoid layers of compensating special cases.

## Give change capture deterministic meaning

Each change carries an entity key, a complete order for that key, an immutable
event identity, an action and a typed payload. Apply greater versions, ignore older
versions and treat conflicting content at the same complete version as an error.
Use the same rule for upserts and deletes. Retain deletion versions so an old
upsert cannot resurrect a deleted row.

Normalize and validate original events before reducing them. Otherwise a later
valid winner can hide an invalid row or a conflict against durable state. A timestamp
alone is insufficient when distinct changes can share it. Neither arrival order
nor arbitrary ordering of broker partitions supplies business meaning.

Default conflict checks cover the prepared interval and current durable versions.
They rely on the immutable source contract; exhaustive historical checking needs
separate fingerprint retention, an admission horizon and a state budget.

Prefer an atomic publication of user rows and version state while preserving an
ordinary table interface. A fenced sidecar is a possible fallback, but its separate
effects need explicit recovery and do not provide atomic visibility across tables.
A state table hidden behind a view changes table behavior and requires a separate
product decision.

## Preserve Extensions while adding the Comet route

The existing extension implementation uses Python package discovery, build checks,
DataFusion foreign-function interfaces, worker identity lookup and host-funded
native memory leases. Preserve those capabilities through integration with the
new runtime. This host is reference code on the existing integration branch,
not yet part of the upstream-based foundation. Keeping its behavior as a control
makes boundary changes reviewable.

Comet’s scalar interface passes Arrow schemas and arrays through C callbacks instead
of exposing DataFusion’s Rust types. It reduces dependency coupling, but its pinned
binary calling contract, or ABI, is specific to a Comet release. It admits trusted
pure immutable functions; a numeric version probe cannot establish pointer safety
or truthful purity.

Add explicit per-export boundary selection. Keep DataFusion/Arrow build checks for
every existing DataFusion-FFI channel, including mixed packages. Bind code,
configuration and function identity into worker resolution and durable preparation.
Missing implementations must produce named refusals rather than silent substitution.

Retain callback code for as long as returned arrays can use it. Initially keep
library code loaded for the process lifetime, while releasing session state and
memory separately. An unloadable design would need ownership following every
dependent allocation. Separating code from session state is required integration
work: the existing process-wide scalar registry retains the full package owner.
Preserve complete Arrow fields during planning and execution.
Comet’s scalar interface does not define a C relation protocol; choose required
relation capabilities and dependencies independently while retaining existing relations.

A nonnullable scalar declaration concerns evaluated values, including encoded
nulls. Check selected dictionary keys, actual union IDs and active physical runs
recursively rather than expanding compressed data into a null bitmap. Admission
must still bound selected-value traversal and nesting; compressed output is not free.

## Treat performance as an engineering requirement

Correct results and bounded resources come first; a working implementation with
a material regression remains unfinished. Evaluate performance changes on the
actual current code and resolved dependencies. Earlier optimization branches are
sources of hypotheses, not patches or speedups to assume still apply.

Compare identical semantics and inputs. Retain every measured cell, including
slowdowns, exact-output checks, profiles and host limitations. Shared-host ratios
are diagnostic; production throughput and memory claims need appropriate conditions.
Do not optimize away marker ordering, failure propagation or fencing to improve
a number.

The repaired filter illustrates this discipline. Data-only costs stayed near its
predecessor in component probes, but mixed data/marker batches fragmented into more
outputs. Optimized sparse/grouped fixtures also showed overhead. A bounded batching
prototype is justified, provided a preceding marker is emitted before evaluating
later data that may fail. Its copies, retained bytes, latency and cooperative
polling need measurement before selecting a policy.

## Current implementation and evidence boundaries

| Area | Current demonstrated state | Work still required |
| --- | --- | --- |
| Flow-event foundation | Local repairs preserve Arrow fidelity and zero-column rows, isolate filter and supported projection expressions, preserve worker reconstruction and report terminal failures; workspace and selected public checks passed | Source identity across optimization, mixed-marker performance, collector retractions and complete termination semantics |
| Source and checkpoint protocol | Existing planning/actor seams inspected; limited source and merge prototypes exist | Live attempt-scoped controls, transport alignment, durable preparation and process-restart recovery |
| Durable targets and change capture | Existing bounded-runtime behavior and transaction mechanisms inspected | Enforced adapters for every admitted target, deterministic streaming reducer/merge and migration |
| Extensions | Existing host inspected; standalone adapter source reviews, immutable workspace checks and pinned Comet SDK probes passed locally | Package/worker integration, resource admission and C relations remain separate increments |
| Configuration | Strict typed YAML/JSON/API and optional Dhall typed authoring frontend specified | Shared normalized model, frontend validation corpus and integration before durable semantic identity |

The foundation qualification does not establish integrated recovery. Standalone
fixture success does not establish SDK interoperability. Standalone SDK probes
do not establish package or worker integration. These boundaries remain explicit
until evidence at the corresponding interface proves otherwise.

## Plans precede dependent implementation

Each increment starts with a self-contained technical plan: user problem, required
guarantees, relevant Sail behavior, reasonable alternatives, recommendation, costs,
unresolved decisions and a discriminating verification method. Explain why a choice
is needed and what it constrains. Links provide optional detail; the argument must
work without them. Keep design documents below two thousand words and short
decision notes below three hundred.

Keep code changes focused enough to explain line by line. Preserve controls that
reproduce the original defect and test observable behavior. Qualify the cumulative
tree on an immutable revision with an independent build directory. Review correctness,
performance, regression risk, scope, test quality, research and design independently.
Resolve introduced defects before offering a change as ready. Small local reference
increments do not imply approval for upstream publication.

Dependencies govern implementation order. Expression isolation enables arbitrary
native expressions. Stable source, computation and configuration identity enables
durable preparation. Fencing and preparation enable recoverable append; change capture
adds ordering and version-state publication. Typed configuration and standalone
scalar work can proceed independently of distributed checkpoint integration.

Configuration must have one meaning across authoring formats and execution attempts.
Reject duplicate or unknown keys, accidental scalar coercions and conflicting options
before planning. Normalize YAML, JSON and API input into one versioned typed model.
Dhall can optionally check authoring types and render the same validated input;
server validation remains authoritative. This prevents parser quirks from becoming
different computations under the same recovery identity.

## Review compendium and immediate decisions

The flow-event and filtering repairs are detailed in
[foundation results](STREAMSOURCE-FOUNDATION-RESULTS.md). The
[pipeline plan](REDESIGN-PLAN.md),
[streaming architecture](STREAMING-ARCHITECTURE.md) and
[change-capture proposal](CHANGE-CAPTURE-ON-STREAMSOURCE.md) expand the contracts above.
The [extension integration plan](EXTENSIONS-STREAMSOURCE-INTEGRATION.md) preserves
both native routes. The [standalone scalar results](COMET-SCALAR-RESULTS.md) qualify
the component evidence. The [standalone scalar plan](COMET-SCALAR-ADAPTER.md) and
[filter batching note](STREAMSOURCE-FILTER-BATCHING.md) bound the immediate work.
The [projection plan](STREAMSOURCE-PROJECTION.md) and
[projection results](STREAMSOURCE-PROJECTION-RESULTS.md) establish ordered data-only
synchronous and supported asynchronous evaluation, nullable marker construction,
qualified names, metadata and worker reconstruction in the local reference.
Workspace and selected public checks passed. Standard metrics remain enabled;
data-only component costs are close to ordinary projection, while mixed-marker
fragmentation remains material. Logical optimization can erase a streaming source
before detection, so preserving source participation remains a correctness obligation
before any global expression-isolation or recovery claim.

Which source-preservation boundary prevents optimization from erasing checkpoint
participants? Settle it with constant-false and zero-output flows. Which bounded
batching policy preserves marker-before-error ordering under measured memory
and latency limits?

Which replayable source and fenced target will qualify the first durable append
path? Decide using actual replay, publication and external-writer constraints.
Can that target publish rows and version state atomically without changing its table
interface? If it cannot, assess explicit two-effect recovery. Which native packages
and pinned Comet SDK producer establish the first integration acceptance cases?
Their required operations should determine the adapter scope.

Maintain this compendium as contracts and evidence change. Keep detailed failure
logs and implementation receipts available for inspection, while keeping authoring
history out of the technical argument. The standard is a system whose guarantees,
implementation and limitations remain understandable to its maintainers.
