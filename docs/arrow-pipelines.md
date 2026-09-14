# Arrow pipelines, ADBC and DataFusion

Grust's Arrow boundary uses Apache Arrow record batches, schemas and
`RecordBatchReader`, rather than a parallel reader/driver hierarchy. Arrow-native
adapters depend on `grust-arrow` for shared pipeline operations. The core graph
model and non-Arrow adapters do not acquire Arrow dependencies.

## Compatibility and ownership

| Consumer | Native Arrow | Shared module | Ingestion boundary |
| --- | --- | --- | --- |
| LanceDB | 58 | `grust_arrow::v58` | `load_arrow` consumes node/edge readers and upserts native batches |
| Sail | 58 | `grust_arrow::v58` | `load_arrow` consumes readers; Spark Connect requires IPC for each staged batch |
| Ladybug (private crate) | 55 | `grust_arrow::v55` | Native reader registration; persisted graph bulk loading uses registered Arrow tables and COPY |
| DataFusion foundation | 59 | `grust_arrow::v59` | Native table/provider registration and result streams |
| Graph interchange and ADBC helper | 59 | `grust_arrow::v59`, also root exports | Standard readers, optional ADBC statement binding |

The version modules compile the same graph, table, pipeline and storage source
files against their native dependency versions. Cargo features are additive;
`default-features = false` avoids pulling Arrow 59 into a backend that only
needs 55 or 58. There is no transmute or local-version IPC bridge hidden in a
batch conversion. Rust types from different Arrow majors are not interchangeable.

`ArrowTable` retains arbitrary Arrow types, extension metadata, row order and
batch boundaries, including schema-only empty streams. Construction validates
schema agreement. Cloning shares buffers; `into_reader` transfers ownership into
the standard reader. Neither operation builds Grust nodes or edges.

`BatchReader` pulls only when the consumer asks for another batch. It slices
large batches by rows without copying their buffers and rejects schema drift.
Source errors are returned once, then the reader is exhausted. Dropping it drops
the source and pending batch. There is no worker, prefetch queue or implicit I/O.
A slice can keep its original backing allocation alive. The inclusive input-byte
limit checks Arrow's reported array memory before yielding any part of that
batch; it is neither an RSS cap nor protection against upstream decoder
allocations. Shared allocations may be counted multiple times.

`read_ipc_stream` and `write_ipc_stream` compose with standard readers and sinks,
including multi-batch streams. IPC encoding is a real copy/serialization boundary.
`collect_batches` and `ArrowTable::read` are explicit bounded collection operations
for consumers such as Ladybug registration that require every batch simultaneously.
Their admission sums reported array memory plus a header per retained batch,
including empty batches. It does not account for every allocator or schema cost.
`ByteLimitWriter` bounds encoded output bytes before they enter a sink; failures
leave any previously written prefix intact.

## ADBC

The optional `adbc` feature adds `grust_arrow::adbc::ingest`. It configures a
caller-owned statement with ADBC's target-table and ingestion-mode options,
binds the Arrow 59 reader through `Statement::bind_stream`, and calls
`execute_update`. Driver status/details and an unknown affected-row count are
preserved. Driver handles, transactions, cancellation, schema/catalog selection,
and capability discovery remain with ADBC. Grust does not invent a second driver
manager, and ADBC append is not interpreted as graph upsert.

The facade exposes this through its `adbc` feature. The current helper is checked
against `adbc_core` 0.24, with Arrow 59 selected in the release lockfile. ADBC's Rust
reader must resolve to the same Arrow major as its producer. The native modules
also compose directly with ADBC versions using Arrow 55 or 58 at the standard
reader boundary; the optional helper itself is Arrow 59.

The optional `ffi` feature exports standard C streams through upstream Arrow's
`FFI_ArrowArrayStream::new`. The exported object owns its reader and release
callback. Foreign consumers must follow the Arrow C Stream ownership rules.
Grust adds no unsafe code. IPC remains the explicit serialized interoperability
option when native types or language boundaries cannot share a reader.

References: [ADBC Rust statement interface](https://github.com/apache/arrow-adbc/blob/apache-arrow-adbc-24/rust/core/src/sync.rs),
[ADBC standard](https://arrow.apache.org/adbc/current/format/specification.html),
[Arrow C Stream interface](https://arrow.apache.org/docs/format/CStreamInterface.html).

## Graph layouts and validation

There are deliberately distinct representations:

* `ArrowGraph` is the existing scalar-property interchange contract:
  `node_id,label` and `source,target,label,edge_id`, with native `property.*`
  columns and `present.*` markers. It preserves absent versus explicit null.
  Its original two-file API still accepts one batch per file. `into_tables`
  exposes standard readers without converting properties or identities.
* Universal storage batches use `id,label,props` and
  `key,id,from_id,to_id,label,props`. `props` preserves the existing tagged Grust
  property serialization, including complex values. Shared encoders and decoders
  maintain that contract; edge decoding rejects keys that disagree with identity.
* Sail's existing SQL tables use plain JSON properties so SQL JSON expressions
  can operate on them. Its reader API accepts its documented column names and
  normalizes legacy property values. Identity buffers are reused; properties
  requiring normalization and generated edge metadata require allocations.
* Arbitrary Arrow tables passed to ADBC or native registration are not restricted
  to the scalar `ArrowGraph` model. Driver-supported nested, dictionary, temporal
  and extension columns remain Arrow columns, with no hidden JSON coercion.

`project_batch` explicitly maps source names to a destination schema, sharing
arrays and checking types and actual required-column nulls. It never casts or
silently converts unsupported types. Projection deliberately omits unselected
columns. Backend-specific column names, graph constraints, upsert semantics and
SQL belong to adapters; buffer slicing, IPC, native projection and shared storage
serialization belong to `grust-arrow`.

Native graph loads validate one bounded batch before writing it. Some validation
and typed mirrors require batch-local Grust values, but there is no whole-stream
`Graph` materialization. Nodes precede edges; each backend write retains its own
commit boundary. Failure or cancellation may leave earlier batches committed.
Sail's graph IPC convenience loader now uses this streaming contract, including
partial progress on a later invalid batch. Use an appropriate caller-managed
transaction/staging strategy when an application needs atomic whole-import
replacement. No rollback or atomicity is implied by the word “bulk”.

## DataFusion 55 foundation

The optional facade `datafusion` feature exposes `grust-datafusion`. Its
`DataFusionEngine` consumes native Arrow 59 `ArrowTable` values or validated
`ArrowGraphTables`, sharing payload buffers with upstream memory tables. Graphs
register as `<catalog>.graph.nodes` and `.edges`; this changes a session catalog,
not persistent backend data. Both providers are prepared before replacing the
catalog, preserving graph registration as one operation.

Custom DataFusion 55 providers retain their native scan and pushdown interfaces.
The engine exposes upstream DataFrames and read-only SQL result streams, with
no implicit result collection. Callers explicitly choose working-memory,
parallelism, batch rows and disabled or bounded-directory spill. Upstream memory
accounting is not a process RSS cap; inputs, retained results and untracked
allocations need separate admission. Context extensions remain trusted code.

`BlockingReader` adapts results to standard synchronous Arrow readers, including
ADBC ingestion. Consume it on an ordinary thread or `spawn_blocking` while its
caller-owned Tokio runtime remains alive. It introduces no prefetch queue,
hidden thread or serialization. Pulling it on an async runtime worker follows
Tokio's documented panic contract.

This foundation accepts SQL explicitly. It does not implicitly lower Cypher,
replace graph kernels or upgrade older DataFusion engines embedded in database
SDKs. Each such integration needs semantic conformance and end-to-end evidence.

## Extending and measuring

A new Arrow backend should consume its SDK's `RecordBatchReader` or native stream,
select the matching shared version module, and add only its schema/protocol and
mutation semantics. A new Arrow major needs a small version module and dependency
feature, not a fork of the pipeline implementation. Do not add a row conversion
or IPC round trip just to satisfy an internal trait boundary.

Tests exercise all three versions from the same test sources: batch limits,
source errors, laziness, schema drift, multi-batch IPC, projection and buffer
identity, C Stream round trips, and property/edge identity. ADBC binding tests use
the actual upstream statement trait. Adapter tests verify graph outcomes and
invalid-input behavior. Native database availability remains separate from pure
pipeline tests.

`cargo bench -p grust-arrow --bench pipelines` measures native slicing versus an
explicit IPC encode/decode boundary with the same 65,536-row data and 4,096-row
outputs. It measures transport/conversion overhead, not database throughput or
an end-to-end backend comparison. Retain the environment and Criterion output
when reporting a result.
