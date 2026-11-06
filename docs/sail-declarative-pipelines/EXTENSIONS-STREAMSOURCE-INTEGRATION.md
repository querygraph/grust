# Native extensions in recoverable streaming pipelines

Pipelines should use separately packaged native functions and relations without
making those packages dependencies of Sail. Preserve the existing extension host
and add the Arrow-only scalar interface used by Apache DataFusion Comet. Native
calls must preserve Sail’s execution, memory and recovery guarantees.

## Carry the existing host into the streaming foundation

The existing host discovers Python packages, validates manifests and binds native
functions and relations. Its DataFusion foreign-function interface, or FFI, carries
DataFusion types and therefore checks host DataFusion and Arrow versions. Distributed
plans identify scalar functions by package, configuration and function name; workers
resolve the matching implementation. Native memory leases use C callbacks and
host-funded quotas.

This host exists on the pipeline integration branch. Porting it to the upstream-based
streaming foundation must preserve its behavior; that integration is not yet demonstrated.

| Existing responsibility | Required integration |
| --- | --- |
| Package admission and scalar lookup | Include selected boundary and actual code/configuration identity in plans and recovery |
| Native relations and placement | Preserve resolver scope, driver placement, cancellation and cleanup |
| Native memory leases | Retain admission until dependent allocations and task effects settle |
| Package ownership | Separate loaded code lifetime from session state and kernel instances |

The [streaming proposal](STREAMING-ON-STREAMSOURCE.md) supplies fixed prepared work
and fenced publication. Extensions add the requirement that replay use the same
native implementation and that returned memory remain valid after its callers end.

## Keep two explicit scalar boundaries

A binary interface defines the calling contract between compiled libraries.
Comet’s scalar interface passes Arrow schemas and arrays through C records and callbacks,
reducing coupling to DataFusion’s Rust types. Comet does not promise this interface
is stable across its releases, including patch releases. Pin the actual layout and
verify compatible producers; an Arrow-only layout or numeric version probe cannot
establish arbitrary library compatibility.

Replacing all existing packages at once would combine loader and execution changes
with a package migration. Retaining only DataFusion FFI would preserve its version
coupling. Add an explicit boundary choice per export, deterministic name resolution
and a named refusal when the requested implementation is unavailable. A mixed package
still needs DataFusion and Arrow build checks for every DataFusion-FFI channel.
Changing a default requires demonstrated equivalence for affected packages.

The Comet route admits trusted, pure immutable functions. An immutable declaration
does not prove purity, pointer safety or non-unwinding behavior. A stateful function
misdeclared immutable could be folded incorrectly during planning. Package admission
must enforce the supported contract rather than trusting a version number alone.

The pinned interface reserves its constant-argument pointer and requires null.
Functions requiring literal values during type resolution need a separately versioned
interface or a named refusal. Literal values passed during execution can be expanded
into arrays. Preserve complete argument and result fields, including nested metadata;
the native boundary must not reduce them to data types alone.

## Keep callback code alive after evaluation

An Arrow result can retain a library-owned release callback. For example, a client
may hold a sliced result after its query, native function and session are dropped.
Unloading the library then makes eventual result cleanup unsafe.

The initial adapter retains loaded code for the process lifetime. The alternative
is explicit library ownership following every exported allocation, with a larger
ownership and unload protocol. Process retention matches the existing host policy
and Comet importer; session allocations and kernel instances still need independent
cleanup. The existing scalar registry retains the entire package owner, so its port
must separate those lifetimes rather than assuming cleanup already works.

Retained code consumes resources even when discovery later rejects the library.
Bound package admission and identify actual code content to control repeated loading.
Memory leases must remain valid for outstanding results while releasing unrelated
session resources. Test result reading, slicing and destruction after dropping every
query and session owner.

## Admit native work to streaming and recovery

Flow events contain data with retraction flags or ordered control markers. Native
functions must receive data values only; Sail retains marker ordering and retractions.
Local foundation checks now cover filter isolation and supported synchronous and
asynchronous projections, with schema-preserving projection composition. Mixed-marker
batch fragmentation and short streaming startup costs remain performance limits.
The [composition results](PROJECTION-COMPOSITION-RESULTS.md) define that evidence scope.

A finite native relation can participate where the graph defines its completion.
Returning Arrow batches does not make it replayable. A live extension source needs
source identity, replay positions, retention and task-attempt controls through
`StreamSource`. A finite recovery input needs a reproducible snapshot or saved prepared
output. The scalar interface supplies neither source contract.

Bind function identity and normalized configuration into durable preparation.
Deterministic replay needs fixed inputs, code and dependencies. Nondeterministic
computation needs persisted validated output. Native functions performing external
mutations need an explicit effect protocol; a manifest cannot make such mutations
replay-safe. These are additional admission requirements within the shared recovery
protocol, not a second checkpoint system.

## What is established and what remains to decide

The [standalone adapter results](COMET-SCALAR-RESULTS.md) establish complete argument-field
handling, immutable-only admission and process-retained callback code in component
checks. An independently compiled producer using the pinned Comet development kit passed two
interoperability probes. This is stronger than a handwritten fixture, but does not
qualify arbitrary Comet versions, package registration, Spark SQL calls or worker loading.

Before integrating packages, preserve the existing DataFusion route as a control.
Verify both routes through package admission, duplicate-name resolution, worker identity
mismatch, cancellation, memory admission and session cleanup. Extend component coverage
for metadata, literal expansion, sliced and nested arrays, nullability, error ownership
and lifetime through those real interfaces. Nullability checks must respect encoded
dictionary, union and run-end values without unbounded expansion or traversal.

Which packages and pinned producer define the first end-to-end acceptance cases?
Do their operations fit process-retained immutable scalars, or require a separately
designed lifetime or effect contract? Settle these choices before admitting them
to durable execution.

Which relation capabilities require a C boundary? Comet’s scalar interface does not
define relation planning, properties, asynchronous execution or placement. Preserve
existing relations while required operations determine any new provider contract.
A small attributed C layout does not require adopting the whole Comet or Sedona
dependency graph.
