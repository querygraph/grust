# Grust Arrow interchange (unreleased)

Enable the facade's `arrow` feature and use `grust::arrow::ArrowGraph`, or depend
on `grust-arrow`. Arrow 59.3 tables are shared by reference; conversion to/from
Grust's row-oriented model materializes values and builds a validation index.
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
