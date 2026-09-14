use arrow_array::{ArrayRef, Int64Array, RecordBatch, RecordBatchIterator, StringArray};
use criterion::{Criterion, black_box, criterion_group, criterion_main};
use grust_arrow::{BatchReader, read_ipc_stream, write_ipc_stream};
use std::{num::NonZeroUsize, sync::Arc};

fn pipelines(c: &mut Criterion) {
    let batch = RecordBatch::try_from_iter([
        (
            "id",
            Arc::new(StringArray::from_iter_values(
                (0..65_536).map(|i| format!("node-{i}")),
            )) as ArrayRef,
        ),
        (
            "weight",
            Arc::new(Int64Array::from_iter_values(0..65_536)) as ArrayRef,
        ),
    ])
    .unwrap();
    let mut group = c.benchmark_group("65536_rows_to_4096_row_batches");
    group.sample_size(20);
    group.bench_function("native_reader", |b| {
        b.iter(|| {
            let reader =
                RecordBatchIterator::new(std::iter::once(Ok(batch.clone())), batch.schema());
            let output = BatchReader::new(
                reader,
                NonZeroUsize::new(4096).unwrap(),
                NonZeroUsize::new(16 << 20).unwrap(),
            );
            for batch in output {
                black_box(batch.unwrap());
            }
        })
    });
    // A semantically equivalent cross-version/wire boundary, not a database load.
    // Includes encoding and decoding; the native path has no transport requirement.
    group.bench_function("ipc_boundary", |b| {
        b.iter(|| {
            let reader =
                RecordBatchIterator::new(std::iter::once(Ok(batch.clone())), batch.schema());
            let mut bytes = Vec::new();
            write_ipc_stream(&mut bytes, reader).unwrap();
            let reader = read_ipc_stream(bytes.as_slice()).unwrap();
            let output = BatchReader::new(
                reader,
                NonZeroUsize::new(4096).unwrap(),
                NonZeroUsize::new(16 << 20).unwrap(),
            );
            for batch in output {
                black_box(batch.unwrap());
            }
        })
    });
    group.finish();
}
fn graph_validation(c: &mut Criterion) {
    use grust_arrow::ArrowGraph;
    use grust_core::{Edge, Graph, GraphIndex, Node, Props};
    let nodes = (0..32_768)
        .map(|i| Node::new("N", i.to_string(), Props::new()))
        .collect();
    let edges = (0..131_072)
        .map(|i| {
            Edge::new(
                "E",
                (i % 32_768).to_string(),
                ((i + 1) % 32_768).to_string(),
                Props::new(),
            )
        })
        .collect();
    let graph = ArrowGraph::from_graph(&Graph::new(nodes, edges)).unwrap();
    let mut group = c.benchmark_group("validate_32768_nodes_131072_edges");
    group.sample_size(20);
    group.bench_function("native_columns", |b| {
        b.iter(|| {
            black_box(ArrowGraph::try_new(graph.nodes().clone(), graph.edges().clone()).unwrap());
        })
    });
    // Reproduces the former constructor's row conversion plus full GraphIndex.
    // Setup encodes the same graph once, outside either measurement.
    group.bench_function("former_row_index_validation", |b| {
        b.iter(|| {
            let rows = graph.to_graph().unwrap();
            black_box(GraphIndex::new(&rows).unwrap());
        })
    });
    group.finish();
}
criterion_group!(benches, pipelines, graph_validation);
criterion_main!(benches);
