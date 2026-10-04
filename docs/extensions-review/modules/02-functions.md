# 2. Functions {#module-2}

[Discovery](01-discovery.md) gives Sail a bound package owner. The simplest
use of that owner is a scalar function: the client submits an ordinary named
function call, and Sail resolves it without a custom expression protocol.
Sedona provides the concrete example. Its
[170-line Rust adapter](../code-listings.md#listing-sedona-lib) wraps existing
Apache SedonaDB Rust and GEOS kernels rather than reimplementing spatial
operations in Sail.

The **public behavior** is `scalar_udfs()` returning objects whose
`__datafusion_scalar_udf__()` method exports a `datafusion_scalar_udf` capsule
containing `FFI_ScalarUDF`. Names, aliases, argument and return semantics,
including metadata-bearing fields, must survive planning and worker execution.
The package owner remains live for every exported callback. The current policy
rejects collisions with built-ins or other registrations. Scalar packages use
`placement: "any"`; every executing worker must have the matching installed
package identity. Native function pointers do not travel over the network.

The **implementation** retains Python owners, wraps imported functions and
encodes package identity plus expression fields in Sail's task codec. Those
wrapper types and registry structures can change without becoming an API that
extension authors implement. The semantic requirement is that a geometry's
metadata survives intervening built-ins and a shuffle, and that a worker
rejects an unavailable or different package instead of selecting another
implementation by name.

The Sedona scope is deliberately smaller than a spatial engine. The package
exports 128 native scalar functions, not the entire SedonaDB catalog. It
omits five colliding functions: `st_asbinary`, `st_geomfromwkb`,
`st_geogfromwkb`, `st_setsrid` and `st_srid`. Each binding captures immutable
default options because the FFI configuration path does not preserve Sedona's
typed runtime services; host `SET sedona.*` propagation is absent. Raster,
GeoParquet readers, PROJ services and indexed `SpatialJoinExec` are not supplied.
General Sail joins can use spatial predicates, but this does not demonstrate
an indexed spatial join or its performance.
[Exact package scope](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/examples/extensions/sedona/README.md#L70).

A raw `Expression.extension` would support custom expression syntax but require
another client representation and dispatch contract. A linked built-in would
avoid dynamic loading while coupling domain releases to the host build.
Driver-only functions could serve local use, but would need an explicit
placement restriction in distributed queries. Name resolution is the smallest
current choice for existing DataFusion scalar kernels, not an answer to every
extension shape.

Acceptance should cover nulls, aliases, geometry-field composition, worker
identity mismatch and an actual shuffle; the repository contains corresponding
fixtures, not a fresh execution verdict from this document. Reviewers should
decide the collision and configuration policies explicitly. A function still
returns values within a row: producing a new table requires the
[relation boundary](03-relations.md).
