# Grust Arrow interchange

Enable the facade's `arrow` feature and use `grust::arrow::ArrowGraph`, or depend
on `grust-arrow`. Arrow 59.3 tables are shared by reference. Native construction validates columns
without building property rows or adjacency; `to_graph` explicitly materializes
Grust values.
No database service, JSON payload, or text edge-list conversion is required.

```rust,no_run
use grust::arrow::ArrowGraph;
use std::fs::File;
# fn main() -> Result<(), Box<dyn std::error::Error>> {
let graph = grust::Graph::default();
let tables = ArrowGraph::from_graph(&graph)?;
tables.write_ipc(File::create("nodes.arrow")?, File::create("edges.arrow")?)?;
let restored = ArrowGraph::read_ipc(
    File::open("nodes.arrow")?, File::open("edges.arrow")?,
)?.to_graph()?;
assert_eq!(graph, restored);
# Ok(()) }
```

## Table contract

The node table has non-null UTF-8 `node_id` and `label`. The edge table has
non-null UTF-8 `source`, `target`, `label`, and nullable UTF-8 `edge_id`.
Endpoint IDs must exist; node IDs must be unique. Row order, isolates, loops,
parallel edges and explicit edge IDs survive round trips. Direction is encoded
by source/target; this format does not encode an undirected-graph flag.

Each property uses a nullable `property.<key>` column plus a non-null Boolean
`present.<key>` column. A false marker with a null value means absent; true with
null means explicit `Value::Null`. Keys can contain dots or reserved base names
because all property names are prefixed. Properties are native Arrow Null,
Boolean, Int64, Float64 or Utf8. Integer precision and floating-point values are
not routed through JSON. Mixed non-null types within a property and complex
Grust values (lists, JSON, temporal, decimal, path, graph) currently return errors;
they are never silently converted to strings or discarded.

IPC uses one record batch in each of two Arrow **file-format** streams. The
caller owns sinks and file lifecycle. A failure writing the second sink does
not undo the first. Reading multiple batches or IPC streaming-format files is
not supported yet. Reads materialize the batch; there is no mmap, spill, byte
budget or protection against arbitrarily large untrusted IPC allocations.

The tables can be consumed as RecordBatches in Arrow/DataFusion. Icecat's local
`grustcat` adapter feeds them directly to Icecat's Arrow table builder and
exports them again with properties intact. Select `property.weight` as the
Icecat weight column. Icecat's simple graph semantics reject parallel edges;
Grust's model preserves them. See Icecat for the algorithms and benchmark runner.


## Native pipelines and ADBC

The default `arrow-59` feature exports `ArrowGraph`, `ArrowGraphTables`,
`ArrowTable`, `BatchReader`, IPC readers/writers and storage batch encoders.
Optional `arrow-55` and `arrow-58` expose the same implementation through `v55`
and `v58`; `v59` is also available explicitly. Disable default features when
only an older SDK version is required.

`ArrowTable` preserves arbitrary Arrow types, schema metadata and batch
boundaries. `ArrowGraphTables` validates the scalar graph contract across
multiple batches. Standard `RecordBatchReader` inputs and outputs compose with
ADBC and other Arrow applications. `BatchReader` lazily slices rows without
copying buffers and checks decoded input-batch memory; `ByteLimitWriter` bounds
encoded output. These are explicit accounting limits, not process-RSS caps.

The `adbc` feature supplies `adbc::ingest` for a caller-owned ADBC 0.24 statement
and native Arrow 59 reader. Driver errors, unknown counts and ownership remain
with ADBC. The optional `ffi` feature exports standard C streams through
upstream Arrow. Grust does not add unsafe code or an alternative driver manager.

LanceDB, Sail, Ladybug and the optional QueryGraph Memory Sail adapter use these
shared pipeline operations. Graph storage layouts and mutation boundaries are
documented in [Arrow pipelines](../../docs/arrow-pipelines.md). Sail's SQL property
normalization is distinct from the universal tagged Grust property format.

### Borrowed graph serialization (Ostracod 0.18.0)

`ArrowGraphTables::as_serializable_graph()` presents the ordinary Grust graph
serde contract directly over native Arrow 55/58/59 columns. It preserves row and
batch order, identity, sorted property keys, scalar tags, and missing versus null
properties. It builds only per-batch column descriptors, without row graphs,
property maps or string-value copies. The caller selects the serializer and sink;
a bounded writer over `std::io::sink()` can count exact JSON bytes without keeping
the encoded output. Writer errors propagate and may leave a prefix in a real sink.
This enables native input-size admission; automatic routing and full query
resource-policy integration remain separate work.
