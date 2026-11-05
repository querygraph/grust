# Native extensions in recoverable streaming pipelines

Pipelines should use separately packaged native functions and relations without
making those packages dependencies of Sail. Preserve Sail’s existing extension
loading and execution contracts while adding the Arrow-only scalar boundary used
by Apache DataFusion Comet. Streaming recovery requires additional contracts beyond
loading and calling a native library.

## Existing implementation and proposed additions

The existing extension implementation discovers Python packages, validates their
manifests and binds their native functions and relations. Its `datafusion-ffi`
boundary carries DataFusion types, so it checks the host’s DataFusion and Arrow
versions. Scalars retain their package owner. Distributed plans identify them by
package/configuration identity and function name; workers resolve the matching
loaded implementation. Native memory leases use C callbacks and host-funded quotas.

This implementation lives on the pipeline integration branch. It is reference
code to preserve and adapt, rather than functionality already present in the
new upstream-based StreamSource foundation branch.

| Capability | Existing implementation | Required integration |
| --- | --- | --- |
| Package admission and identity | Version checks, package ownership and worker-side scalar lookup | Include the selected boundary and actual code/configuration identity in planning and recovery |
| Native scalar calls | DataFusion foreign-function interface | Add Comet’s Arrow-only C scalar interface while retaining the existing route |
| Native relations | Bound relation dispatch and driver placement support | Preserve resolver scope, cancellation, cleanup and placement in the new execution path |
| Native memory | Host-funded memory lease with retain/release callbacks | Keep admission alive until every dependent native allocation and task effect settles |
| Streaming expressions | Ordered data and control markers in Arrow batches | Evaluate native functions on data only, preserving retractions and markers in Sail |

The C ABI is the binary calling contract between independently compiled libraries.
Comet’s scalar boundary passes Arrow schemas and arrays through C records and
callbacks, rather than exporting DataFusion’s Rust types. This reduces coupling
to DataFusion releases. Comet explicitly does not promise ABI compatibility across
its own releases, including patch releases. Pin and verify the actual boundary;
an Arrow-only layout does not make every kernel or future header compatible.

## Why two routes remain necessary

Replacing every existing native package immediately would combine loader,
execution and compatibility changes in one migration. Keeping only the existing
route would retain its DataFusion-version coupling. Add an explicit boundary
choice per exported function, with deterministic name resolution and identity.
Do not silently select another implementation when the requested one is unavailable.
Any later default preference needs demonstrated equivalence for affected packages.

The standalone scalar prototype implements Comet-shaped discovery, a version probe
and calls through a Sail-owned fixture. It is useful implementation material.
It does not yet establish package loading, distributed execution or loading
Comet-built binaries. The prototype also needs complete argument-field metadata
and explicit admission of pure immutable kernels, as Comet’s interface requires.
The existing package loader does not enforce that purity requirement.
The pinned Comet ABI v1 reserves the constant-argument pointer and requires it
to be null. Functions needing those values for type resolution must be refused
unless a separately versioned interface supplies them. Declaring a stateful
function immutable would permit unsafe constant folding.

Returned arrays may invoke library-owned release callbacks long after evaluation.
Keeping the library alive only while its function exists is insufficient unless
the returned arrays independently retain it. Choose process-retained code, as in
the existing extension model, or ownership that follows every exported allocation.
Use process-retained code initially because it matches the existing host policy
and Comet’s importer. The existing scalar registry retains the full package owner;
the port must separate code retention from session state rather than assume
that state is already released correctly. Keep session allocations separately scoped. Either choice
must be tested after dropping plans, functions and sessions while
retaining results. A successful scalar result alone does not prove this lifetime.

## Streaming and replay boundaries

Sail owns flow events: data with per-row retraction flags, or ordered markers
for latency, watermarks, checkpoints and end of data. These control columns must
remain outside native user-function arguments. Marker-safe filtering is implemented
on the foundation branch; projection and asynchronous expressions still need the
same isolation. This is a prerequisite for native functions in those positions.

An ordinary finite relation can participate as finite input where the execution
graph defines its completion. It does not become a replayable stream source merely
because it returns Arrow batches. A live extension source needs explicit source
identity, replay positions, retention and task-attempt checkpoint controls through
`StreamSource`. A finite source used in recovery also needs reproducible snapshot
identity or saved prepared output. Extending a scalar C interface does not supply
either source contract.

Recovery must retain the original function identity and normalized configuration.
Pure deterministic computation may support identical replay when all inputs and
dependencies are fixed. For nondeterministic computation, persist validated output
before committing effects. Native functions that perform external mutations require
an explicit effect protocol; do not admit them as replay-safe merely because their
manifest says immutable. Target commits still require enforced ownership fencing.

## Human-reviewable implementation boundaries

Preserve package identity, owner lifetime, worker lookup, memory admission
and cleanup as independently verifiable host contracts on the new foundation.
Exercise the existing DataFusion route before replacing any boundary. This provides
a control for failures introduced by the C adapter.

The standalone Comet scalar adapter can proceed independently of that host port,
using a pinned layout and attribution.
Before connecting it to packages, verify metadata, nulls, literal inputs expanded
as arrays, refusal of unsupported initialization requirements, sliced and
nested arrays, declared volatility, error ownership and result lifetime. Then test
package admission, duplicate names, worker identity mismatch, cancellation and
session cleanup through both routes. Verify independently compiled Comet-compatible
binaries; a handwritten fixture remains a narrower check.

Treat Arrow-only relations as a separate design. Comet’s scalar interface alone
does not define relation planning, properties, asynchronous execution or task
placement. A relation boundary needs its own pinned provider contract and evidence.
Neither an entire Comet dependency nor an entire Sedona dependency is required
merely to adopt a small attributed C layout.

Should code remain loaded for the process lifetime, or must every result carry
library ownership? Settle this before the production scalar adapter.

Which native functions are eligible for replay, and which require persisted output
or effect handling? Settle this before integrating them into durable preparation.

Which relation capabilities need a C boundary initially? Keep the existing route
available while actual required operations determine that interface.
