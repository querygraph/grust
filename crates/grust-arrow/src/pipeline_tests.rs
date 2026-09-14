use super::*;
use array::{Int64Array, RecordBatchIterator};
use std::{cell::Cell, io::Cursor, rc::Rc};

fn numbers() -> RecordBatch {
    RecordBatch::try_from_iter([(
        "n",
        Arc::new(Int64Array::from(vec![1, 2, 3, 4, 5])) as ArrayRef,
    )])
    .unwrap()
}
fn reader(batch: RecordBatch) -> impl RecordBatchReader {
    let schema = batch.schema();
    RecordBatchIterator::new(std::iter::once(Ok(batch)), schema)
}

#[test]
fn bounded_slices_retain_buffers_and_order() {
    let input = numbers();
    let array = input
        .column(0)
        .as_any()
        .downcast_ref::<Int64Array>()
        .unwrap();
    let mut batches = BatchReader::new(
        reader(input.clone()),
        NonZeroUsize::new(2).unwrap(),
        NonZeroUsize::new(4096).unwrap(),
    );
    let a = batches.next().unwrap().unwrap();
    assert_eq!(a.num_rows(), 2);
    assert_eq!(
        a.column(0)
            .as_any()
            .downcast_ref::<Int64Array>()
            .unwrap()
            .values()
            .as_ptr(),
        array.values().as_ptr()
    );
    let b = batches.next().unwrap().unwrap();
    assert_eq!(
        b.column(0)
            .as_any()
            .downcast_ref::<Int64Array>()
            .unwrap()
            .values()
            .as_ref(),
        &[3, 4]
    );
    assert_eq!(batches.next().unwrap().unwrap().num_rows(), 1);
    assert!(batches.next().is_none());
    assert!(batches.next().is_none());
}

#[test]
fn limits_fail_once_before_yielding_a_large_batch() {
    let mut batches = BatchReader::new(
        reader(numbers()),
        NonZeroUsize::new(1).unwrap(),
        NonZeroUsize::new(1).unwrap(),
    );
    let ArrowError::ExternalError(error) = batches.next().unwrap().unwrap_err() else {
        panic!("expected resource error")
    };
    assert!(matches!(
        error.downcast_ref::<grust_core::GrustError>(),
        Some(grust_core::GrustError::ResourceLimitExceeded {
            resource: "Arrow input batch bytes",
            limit: 1,
            ..
        })
    ));
    assert!(batches.next().is_none());
}

#[test]
fn pipeline_is_lazy_and_preserves_source_failure() {
    let pulls = Rc::new(Cell::new(0));
    let counter = Rc::clone(&pulls);
    let source = RecordBatchIterator::new(
        std::iter::from_fn(move || {
            counter.set(counter.get() + 1);
            Some(Err(ArrowError::ParseError("broken source".into())))
        }),
        numbers().schema(),
    );
    let mut batches = BatchReader::new(
        source,
        NonZeroUsize::new(2).unwrap(),
        NonZeroUsize::new(4096).unwrap(),
    );
    assert_eq!(pulls.get(), 0);
    assert!(
        matches!(batches.next().unwrap(), Err(ArrowError::ParseError(message)) if message == "broken source")
    );
    assert!(batches.next().is_none());
    assert_eq!(pulls.get(), 1);
}

#[test]
fn ipc_handles_multiple_batches_and_schema_only_streams() {
    let batch = numbers();
    let mut bytes = Vec::new();
    write_ipc_stream(
        &mut bytes,
        RecordBatchIterator::new(vec![Ok(batch.clone()), Ok(batch.clone())], batch.schema()),
    )
    .unwrap();
    let decoded = read_ipc_stream(Cursor::new(bytes))
        .unwrap()
        .collect::<Result<Vec<_>, _>>()
        .unwrap();
    assert_eq!(decoded, [batch.clone(), batch.clone()]);
    let mut bytes = Vec::new();
    write_ipc_stream(
        &mut bytes,
        RecordBatchIterator::new(std::iter::empty(), batch.schema()),
    )
    .unwrap();
    let mut decoded = read_ipc_stream(Cursor::new(bytes)).unwrap();
    assert_eq!(decoded.schema(), batch.schema());
    assert!(decoded.next().is_none());
}

#[test]
fn schema_drift_is_rejected_by_reader_and_writer() {
    let source = || RecordBatchIterator::new(vec![Ok(numbers())], Arc::new(Schema::empty()));
    let mut batches = BatchReader::new(
        source(),
        NonZeroUsize::new(2).unwrap(),
        NonZeroUsize::new(4096).unwrap(),
    );
    assert!(matches!(
        batches.next().unwrap(),
        Err(ArrowError::SchemaError(_))
    ));
    assert!(batches.next().is_none());
    assert!(matches!(
        write_ipc_stream(Vec::new(), source()),
        Err(ArrowError::SchemaError(_))
    ));
}

#[test]
fn projection_preserves_arrays_and_checks_required_nulls() {
    let batch = numbers();
    let schema = Arc::new(Schema::new(vec![Field::new(
        "renamed",
        DataType::Int64,
        false,
    )]));
    let mapped = project_batch(&batch, schema.clone(), &["n"]).unwrap();
    assert!(Arc::ptr_eq(mapped.column(0), batch.column(0)));
    let nullable = RecordBatch::try_from_iter([(
        "n",
        Arc::new(Int64Array::from(vec![Some(1), None])) as ArrayRef,
    )])
    .unwrap();
    assert!(matches!(
        project_batch(&nullable, schema, &["n"]),
        Err(ArrowError::SchemaError(_))
    ));
}

#[cfg(feature = "ffi")]
#[test]
fn c_stream_export_import_retains_native_values() {
    let batch = numbers();
    let exported = export_c_stream(Box::new(reader(batch.clone())));
    let mut imported = array::ffi_stream::ArrowArrayStreamReader::try_new(exported).unwrap();
    assert_eq!(imported.schema(), batch.schema());
    let result = imported.next().unwrap().unwrap();
    assert_eq!(result, batch);
    let original = batch
        .column(0)
        .as_any()
        .downcast_ref::<Int64Array>()
        .unwrap();
    let received = result
        .column(0)
        .as_any()
        .downcast_ref::<Int64Array>()
        .unwrap();
    assert_eq!(original.values().as_ptr(), received.values().as_ptr());
    assert!(imported.next().is_none());
}

#[test]
fn collection_limits_sum_across_batches() {
    let batch = numbers();
    let source =
        RecordBatchIterator::new(vec![Ok(batch.clone()), Ok(batch.clone())], batch.schema());
    let limit =
        NonZeroUsize::new(batch.get_array_memory_size() + std::mem::size_of::<RecordBatch>())
            .unwrap();
    let error = collect_batches(source, limit).unwrap_err();
    assert!(matches!(
        into_grust_error(error),
        grust_core::GrustError::ResourceLimitExceeded {
            resource: "Arrow retained batch bytes",
            ..
        }
    ));
}

#[test]
fn table_preserves_metadata_batches_and_zero_column_row_counts() {
    let schema = Arc::new(
        Schema::empty().with_metadata(std::collections::HashMap::from([(
            "source".into(),
            "adbc".into(),
        )])),
    );
    let options = array::RecordBatchOptions::new().with_row_count(Some(3));
    let batch = RecordBatch::try_new_with_options(schema.clone(), vec![], &options).unwrap();
    let table =
        super::super::ArrowTable::try_new(schema.clone(), vec![batch.clone(), batch.clone()])
            .unwrap();
    assert_eq!(table.num_rows(), 6);
    assert_eq!(table.schema(), schema);
    let reader = table.into_reader();
    assert_eq!(reader.schema().metadata().get("source").unwrap(), "adbc");
    assert_eq!(
        reader.collect::<Result<Vec<_>, _>>().unwrap(),
        [batch.clone(), batch.clone()]
    );
    let projected = project_batch(&batch, schema, &[]).unwrap();
    assert_eq!(projected.num_rows(), 3);
}

#[test]
fn native_graph_tables_validate_across_batch_boundaries() {
    use super::super::{ArrowGraph, ArrowGraphTables, ArrowTable};
    use grust_core::{Edge, Graph, Node, Props};
    let graph = Graph::new(
        vec![
            Node::new("N", "a", Props::new()),
            Node::new("N", "b", Props::new()),
        ],
        vec![Edge::new("E", "a", "b", Props::new())],
    );
    let encoded = ArrowGraph::from_graph(&graph).unwrap();
    let nodes = ArrowTable::try_new(
        encoded.nodes().schema(),
        vec![encoded.nodes().slice(0, 1), encoded.nodes().slice(1, 1)],
    )
    .unwrap();
    let edges = ArrowTable::from(encoded.edges().clone());
    let valid = ArrowGraphTables::try_new(nodes.clone(), edges.clone()).unwrap();
    assert_eq!(valid.nodes().num_rows(), 2);
    assert!(Arc::ptr_eq(
        valid.edges().batches()[0].column(0),
        encoded.edges().column(0)
    ));
    let duplicate = ArrowTable::try_new(
        encoded.nodes().schema(),
        vec![encoded.nodes().clone(), encoded.nodes().slice(0, 1)],
    )
    .unwrap();
    assert!(matches!(
        ArrowGraphTables::try_new(duplicate, edges.clone()),
        Err(grust_core::GrustError::Schema(_))
    ));
    let missing = ArrowTable::from(encoded.nodes().slice(0, 1));
    assert!(matches!(
        ArrowGraphTables::try_new(missing, edges),
        Err(grust_core::GrustError::Schema(_))
    ));
}
