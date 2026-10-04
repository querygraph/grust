# 1. Discovery and binding {#module-1}

The first boundary is installation: how does an independently built package
become available to a Sail session? The prototype uses Python packaging for
discovery and DataFusion FFI for native objects. Those are complementary
choices. A wheel supplies a familiar distribution mechanism; it does not, by
itself, establish binary compatibility or define query semantics.

The **public behavior** is a discoverable `pysail.extensions` entry point,
a readable manifest, and a fresh bound owner for each session incarnation.
The manifest names the package, version, API and engine versions, placement,
and supported relation types. Binding returns the object that supplies scalar
functions or relation handlers. Declared mismatches and duplicate registrations
must fail before those registrations become visible. Packages requesting a
native quota additionally implement `bind_with_resources`; ordinary scalar
packages can use `bind`. The owner must remain alive while its callbacks or
exported objects can still be used.

At the pinned Sail commit, the **implementation** checks API version 1,
DataFusion 55.1.0 and Arrow 59.3.0 before importing native capsules. Discovery
is enabled by `SAIL_EXPERIMENTAL_EXTENSIONS=1`. The session loader assigns an
incarnation, hashes installed package files and manifest options, and retains
loaded code for the process lifetime. These checks identify known mismatches;
the loader still trusts the package's declared capsule layout and native
callbacks. They are not a sandbox or proof of arbitrary binary safety.
[Manifest validation and binding](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-session/src/extensions/mod.rs#L158).

Sedona has no Sail host-crate dependency and implements no Sail Rust trait.
The [Sedona listing](../code-listings.md#listing-sedona-lib) nevertheless needs
its own [Python manifest](../code-listings.md#listing-sedona-bootstrap),
[entry point](../code-listings.md#listing-sedona-pyproject),
[Cargo dependencies](../code-listings.md#listing-sedona-cargo) and
[build preparation](../code-listings.md#listing-sedona-prepare). Nutmeg makes a different, explicit choice: its optional memory
contract depends on the small [resource ABI](../code-listings.md#listing-resource-abi)
crate, `sail-native-resource-ffi`. “No host
trait dependency” describes both paths more accurately than “no Sail dependency.”

A statically linked Rust trait can suit an application built as one unit; it
is not the selected boundary for separately compiled wheels. A C loader could
also retain Python packaging or use another discovery mechanism. Python UDFs
remain useful for expression workloads, including wrappers around native code,
but do not alone supply this table-provider contract. None of these alternatives
is intrinsically disqualified by its language.

The acceptance questions are concrete: does an incompatible manifest fail,
does a duplicate name leave no partially registered catalog, and can one
session's owner outlive another without sharing mutable session state? The
source provides validation tests; a platform verdict still needs the matching
artifact receipts. The decision here is whether trusted wheel discovery and
session ownership are the minimum supported surface. With that established,
[functions](02-functions.md) are the smallest useful native export.
