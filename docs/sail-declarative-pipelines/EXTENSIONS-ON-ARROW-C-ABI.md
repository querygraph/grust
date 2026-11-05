# Native scalar extensions through Comet’s Arrow C boundary

Sail should load separately packaged native scalar functions while reducing their
coupling to DataFusion releases. Add the Arrow-only scalar calling contract used
by Apache DataFusion Comet beside Sail’s existing `datafusion-ffi` route. Keep
relation integration separate because scalar calls do not define relation planning
or execution.

## Existing foundation and the proposed boundary

The existing pipeline branch discovers Python extension packages, validates their
build identity, binds native functions and relations, and loads matching scalar
implementations on workers. Functions retain package owners. Distributed plans
carry package/configuration identity and function name. Native memory leases
already use C callbacks with host-funded quotas.

That implementation crosses DataFusion objects through `datafusion-ffi` and must
match the host’s DataFusion and Arrow versions. The upstream-based StreamSource
foundation does not yet contain this extension host. Preserve its behavior as
an independently tested integration increment.

Comet’s scalar interface crosses schemas and arrays using the Arrow C Data
Interface, with records of C-callable function pointers. A factory creates a
kernel instance. Initialization determines its return field; execution consumes
argument arrays and returns an array. Version and discovery symbols identify
this interface. The host adapts the imported kernel to its own DataFusion version.

## What compatibility this buys

The Arrow-only route avoids exposing DataFusion’s Rust types. It does not provide
a general stable plugin ABI. Comet explicitly disclaims compatibility across its
releases, including patch releases. Its pinned SDK documentation supports
SDK-built libraries and does not publish a C header as a supported development
surface. Carry a pinned, attributed contract and verify actual independently
built binaries before claiming interoperability.

The implementation reference is Comet commit
`0f7f8e45399847715093b3d3affdfa97614b39dc`:
[scalar layout and ownership](https://github.com/apache/datafusion-comet/blob/0f7f8e45399847715093b3d3affdfa97614b39dc/native/comet-udf-sdk/src/c_abi.rs),
[SDK support boundary](https://github.com/apache/datafusion-comet/blob/0f7f8e45399847715093b3d3affdfa97614b39dc/native/comet-udf-sdk/src/lib.rs).

The supported contract admits pure immutable functions. Initialization’s constant
argument pointer is reserved and must be null. A function needing constant values
to determine its return type needs another supported interface or an explicit
refusal. Do not infer additional capabilities from a similar Sedona structure;
similar layouts can have different discovery and initialization semantics.

## Ownership is part of execution correctness

Argument transfer, output ownership and error-string lifetime follow the pinned
interface. Returned arrays may retain release callbacks into the library after
a function, plan or session has been dropped. Keeping a library handle only inside
the function does not establish their safety.

Use process-retained library code for the first adapter, matching the existing
host policy and Comet’s importer. Keep session state and memory admissions scoped
and releasable. Code retention does not authorize retaining session allocations.
An unloadable design is possible, but every dependent allocation and callback must
retain the library; that broader ownership mechanism needs separate evidence.

## Admission and distributed identity

A package must declare each boundary it exports. Preserve exact host-version
checks for any `datafusion-ffi` channel, including mixed packages. A pure C scalar
channel can have separate admission tied to the pinned interface and verified
version probe. Do not invent an Arrow C interface version field without a defined
negotiation contract.

Carry boundary selection, code digest, normalized configuration and function name
through plan serialization. Workers must resolve the same identity or refuse the
plan. Explicit selection avoids silently switching semantics when both routes
export the same name. Native functions must remain outside marker evaluation:
operators must forward markers and pass only user data to kernels. Projection
and asynchronous expression isolation remain unbuilt on the foundation branch.

## Evidence and implementation increments

The standalone Sail scalar prototype implements Comet-shaped discovery and calls
a handwritten fixture. Its reported tests cover ordinary results, nulls, argument
order and errors. They establish neither SDK-built Comet interoperability nor
package and worker integration. Full argument-field metadata, admission and
returned-array lifetime still need qualification.

The standalone adapter can proceed independently of porting the extension host.
Before package integration, verify result lifetime after dropping function owners,
metadata, empty/sliced/nested arrays, error ownership and refusal of unsupported
functions. Then connect package admission and worker identity through both scalar
routes, preserving existing cancellation, cleanup and quota behavior.

Arrow-only relations require another decision. Sedona’s provider and execution
adapters include planning semantics, expression transport, asynchronous execution
and runtime support. They are not two trivial converters. Inspect the required
operations and dependency closure before choosing attributed Sail-owned adapters
or a dependency. Comet’s scalar ABI alone supplies no relation boundary.

## Decisions before dependent implementation

Use process-retained code for the first scalar adapter? This gives a narrow
lifetime contract whose result callbacks remain valid; unloading adds ownership
work that is not needed for initial package integration.

Which pinned Comet SDK/library pair demonstrates interoperability? Require its
independent binary to pass the same result, error and lifetime checks as the fixture.

Which relation capabilities require a C interface initially? Preserve the existing
relation route while that requirement determines the separate implementation scope.
