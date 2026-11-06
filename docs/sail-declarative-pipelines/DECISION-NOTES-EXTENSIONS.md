# Decisions for native extension integration

Native extensions are separately packaged libraries that add functions or relations
to Sail. These optional notes compare mechanisms. Correct fields, callable release
callbacks, explicit code identity and bounded resources are requirements throughout.

## E1. Add Comet’s scalar boundary beside the existing route

Sail’s existing native scalar route uses `datafusion-ffi`, which exposes DataFusion
types and requires matching host build versions. Comet’s scalar C interface passes
Arrow schemas and arrays through C callbacks instead. This reduces DataFusion coupling,
but Comet explicitly disclaims binary-interface stability across releases.

Add a pinned, attributed Comet scalar adapter while retaining the existing route.
Replacing every package at once would combine host migration and boundary changes.
Keeping only DataFusion FFI would retain its version coupling. Select the boundary
explicitly for each function and include it in serialized identity; do not switch
implementations silently.

Comet’s pinned interface admits pure immutable functions. Its constant-argument
initialization pointer is reserved and must be null. Refuse functions requiring
unsupported capabilities rather than extending the interface implicitly.

The standalone adapter passes metadata, null, slice and lifetime controls, plus
two probes from an independently compiled pinned Comet SDK producer. This qualifies
that component, not package admission, worker execution or cross-version compatibility.
Similar Sedona layouts do not establish interchangeable binaries.

Which package exports should use this boundary first? Verify package admission
and worker identity through both routes. [Optional component evidence](COMET-SCALAR-RESULTS.md)
retains the controls; no production performance envelope is established.

## E2. Specify relation capabilities separately

Sail’s existing extension host binds native relations through DataFusion FFI and
supports placement and child-plan dispatch. Comet’s Arrow-only scalar interface
does not define relation planning, properties or asynchronous execution.

Retain the existing relation route while defining the required C relation contract.
Sedona has provider and execution interfaces, but its adapters also carry expression
transport, runtime support and dependencies. Adopting them is a semantic and
maintenance decision, not merely copying two small converters.

Compare a scoped Sail-owned attributed adapter with a pinned dependency after
identifying the operations required by real packages. Neither option creates a
replayable StreamSource automatically. A live source still needs stable identity,
positions, retention and checkpoint control.

Which relation operations need to cross the C boundary initially? Inventory those
operations and compare their dependency closure, placement, schema, cancellation
and ownership behavior before implementation. Scalar adapter work can proceed
independently; relation support remains part of the intended end state.

## E3. Admit each exported boundary explicitly

The existing host checks package API, DataFusion and Arrow versions before binding
DataFusion-FFI objects. Removing those checks from a mixed package would expose
incompatible layouts even if one function uses Arrow-only C.

Keep exact host checks for every DataFusion-FFI channel. Admit a pure C scalar
channel separately against its pinned contract and verified version/discovery
symbols. A successful numeric probe alone does not prove behavior across Comet
releases. Do not invent an Arrow C interface version without defined negotiation.

Record boundary selection, code digest, normalized configuration and exported name.
Workers resolve that exact identity or reject execution. Duplicate names need an
explicit selection or a planning error; a missing C library must not silently
choose another implementation.

Should manifests use explicit per-export boundary declarations? Prefer them over
a package-wide replacement flag because mixed packages can migrate incrementally.
Settle the concrete schema and test mismatch, duplicate-name and worker-resolution
cases before changing package admission.

## E4. Keep code alive independently of session memory

A native result array can retain a release callback into its library after the
function, plan and session have gone. Holding a library only in the function does
not prove that callback remains callable. The standalone adapter now retains code
and passes retained-result lifetime controls.

Retain library code for the process lifetime initially, matching the existing
extension policy and Comet’s importer. Keep session allocations, state and host-funded
memory leases scoped and releasable. The existing scalar registry retains the full
package owner; separating code from session state remains porting work. The standalone
registry retains code without kernel instances or session state. Each opening retains
resources, so package admission still needs a bound and content identity.

An unloadable design could attach library ownership to every dependent allocation
and callback. That enables unloading but adds a broader ownership mechanism.
It is unnecessary for initial scalar integration.

Retain process-lifetime code for integrated packages, or require unloadable ownership?
Test retained results after dropping functions, plans and sessions, including errors
and sliced arrays. Check release callbacks and quota settlement independently before
integrating the loader.

## E5. Keep streaming control and durable effects in Sail

Sail encodes user data, retractions and ordered markers in Arrow batches. Native
scalar kernels must see only user arguments. Supported local filter and projection
paths now isolate markers, including supported asynchronous expression execution.
This does not qualify native package or worker integration.

Keep markers and retractions under Sail operator control. Native scalar arrays
remain ordinary arrays; do not pass private control columns through Comet’s C interface.
This preserves the existing scalar interface without inventing a streaming interface.
Mixed-marker execution fragmentation and short-stream compilation costs remain
unresolved. The separate projection-composition repair resolves its measured deep
identity regression, with a small shallow-wide residual. These are shared-host
diagnostics, not production throughput claims.

A finite relation needs a defined completion boundary. Durable replay additionally
needs reproducible input identity or saved prepared output. A live extension source
needs StreamSource checkpoint participation. Scalar purity alone supplies neither.
External mutations require an explicit effect protocol and fenced publication.

Which extension computations may replay identically, and which require persisted
output or effect handling? Define admission before durable preparation depends on
those computations. Test markers before failing native expressions, worker identity
mismatch and recovery with changed packages. General optimizer, command and catalog
plugins remain separate contracts; they do not substitute for these requirements.
