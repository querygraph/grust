# Native extensions for Sail over Arrow-only C boundaries

A proposal for Sail's maintainers, extending the contract posted in
[discussion #2001](https://github.com/lakehq/sail/discussions/2001). Status:
draft for discussion, 2026-11-04.

## What this is

A **native extension** is a library, compiled separately from Sail and
installed as a Python package, that adds functions or relations to Sail
without becoming a Sail dependency. The contract already proposed lets the
host (Sail) discover such packages through Python entry points, refuse one
whose declared versions do not match the host's, dispatch a Spark Connect
relation to it, keep its stateful work on the driver, and fund its memory
through a small C lease. That contract crosses relations through
`datafusion-ffi`, the FFI that DataFusion ships for its own types.

This document changes one thing: the boundary that functions and relations
cross. It proposes Arrow-only C definitions, the ones Apache Sedona and
Apache DataFusion Comet already use, in place of `datafusion-ffi`, so that an
extension depends on Arrow's C Data Interface and nothing else. Everything
else in the contract stays.

## Why Arrow-only

`datafusion-ffi` carries DataFusion's own types across the boundary, so a
library built against it is bound to one DataFusion major version. When Sail
upgrades DataFusion, every extension must be rebuilt, and authors do not
backport. Comet measured this directly: a DataFusion upgrade removed one trait
method and would have forced a source edit and a rebuild of every library on
the `datafusion-ffi` flavor, while the Arrow-only flavor needed no change. An
extension that crosses only Arrow arrays, schemas and streams is bound to
Arrow's C interface, which is stable, and to a small versioned header, which
changes rarely and is probed at load.

## The boundaries

Three C surfaces, each a struct of function pointers with a private data
pointer and a release function, so ownership never crosses.

**Scalar functions** use the scalar kernel of Sedona's header, which Comet
adopted unchanged: a kernel factory that names the function and creates an
instance; an instance that, given the argument types and any constant
arguments, reports the return type, and then, given argument arrays and a row
count, returns a result array. Errors come back as a code plus a last-error
string. The library exports a discovery symbol that lists its kernels and a
version probe that returns the header version. Sail resolves a function by
name from the list, checks the probe against the version it was built for,
and refuses a mismatch before calling anything.

**Relations** use Sedona's table provider and execution plan structs. A table
provider reports a schema and produces an execution plan for a scan given
encoded arguments; an execution plan reports its schema, exposes named
properties as Arrow arrays, can be re-created with a property changed, and
executes into an Arrow array stream, with an asynchronous variant for
engines that need it. Sail's existing bounded-relation dispatch keeps its
shape: the host resolves the relation's children to plans, exports them across
the boundary as C execution plans, asks the extension for its plan, and imports
that plan as a DataFusion execution plan. The import and export adapters exist
in Sedona's Rust crate for that header; Sail would depend on that crate or
carry the two adapters, which are small.

**Memory** keeps the lease already proposed, a C record with a version, a
size, a byte quota, an owner pointer and retain and release callbacks. It has
no Arrow or DataFusion type in it and is unchanged.

## What is declared and what is refused

A package's manifest declares three things: the header version of each C
surface it uses, the Arrow C interface it was built against, and the Sail
extension API version. The host compares all three with its own at discovery
and refuses a mismatch with the declaration quoted. No DataFusion version
appears in the manifest any more, because no DataFusion type crosses. A
package may additionally ship the `datafusion-ffi` flavor of a function; the
host prefers the Arrow-only flavor when both are present and will drop the
other once no shipped extension needs it.

## What stays outside

The host still does not accept optimizer rules, physical planner extensions
or command plugins from a package; those need DataFusion types by nature and
are the subject of a separate discussion. Catalog providers, which Sedona's
header also defines, are left out of the first version because Sail's catalog
layer has its own contract that a C surface would have to match.

## Keeping this independent of the streaming work

The streaming proposal in the companion document and this one meet at one
point only, and deliberately so. An extension's execution plan is a batch
plan: it has no notion of flow events, markers or retractions. When a
pipeline's streaming plan reads an extension relation, the rewriter adapts
the extension's plan as it adapts any batch input, by emitting its rows and
then the end-of-data marker. The two columns that carry markers never cross
the C boundary. So the extension contract can change without touching
streaming, the streaming model can change without touching extensions, and
each can be reviewed, merged or rejected alone. A streaming table over an
extension relation is admitted as a batch source in a bounded run and refused
in a continuous run, with the reason named.

## Questions for the maintainers

1. If the scalar header moves from Comet to DataFusion or Arrow, Sail follows
   it. Until then, is implementing against Comet's copy, with its version
   probe, acceptable, or would you rather wait for the shared home?
2. For relations, is depending on Sedona's extension crate for the import and
   export adapters acceptable, or should Sail carry the adapters?
3. The lease record is Sail's own C definition. Should it be offered to the
   same shared home as the scalar header, so that an extension author has
   one place to look?

## How it would be built

The scalar channel first, since Sedona's functions import through it with no
change and the matrix of tests exists; then the relation boundary, replacing
the `datafusion-ffi` dispatch and re-running the same relation tests; then the
manifest change. Each step keeps the previous flavor until its tests pass on
the new one.
