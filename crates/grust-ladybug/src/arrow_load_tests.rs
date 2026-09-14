use super::*;
use arrow::array::{ArrayRef, Int64Array, RecordBatch};
use grust_arrow::v55::ArrowTable;
use std::{num::NonZeroUsize, sync::Arc};

#[test]
fn native_readers_register_multiple_batches_and_stream_relationships() -> Result<()> {
    let store = LadybugGraphStore::in_memory()?;
    let nodes =
        RecordBatch::try_from_iter([("id", Arc::new(Int64Array::from(vec![0, 1])) as ArrayRef)])
            .unwrap();
    let table = ArrowTable::try_new(nodes.schema(), vec![nodes.slice(0, 1), nodes.slice(1, 1)])?;
    store.register_arrow_node_reader("Person", table.into_reader(), NonZeroUsize::MAX)?;
    let edges = RecordBatch::try_from_iter([
        ("from", Arc::new(Int64Array::from(vec![0, 1])) as ArrayRef),
        ("to", Arc::new(Int64Array::from(vec![1, 0])) as ArrayRef),
        ("weight", Arc::new(Int64Array::from(vec![7, 9])) as ArrayRef),
    ])
    .unwrap();
    store.register_arrow_rel_reader(
        "Knows",
        ArrowTable::from(edges).into_reader(),
        "Person",
        "Person",
        NonZeroUsize::MAX,
    )?;
    let mut weights = Vec::new();
    store.visit_arrow_batches(
        "MATCH (a:Person)-[r:Knows]->(b:Person) RETURN r.weight ORDER BY a.id;",
        NonZeroUsize::new(1).unwrap(),
        |batch| {
            let column = batch
                .column(0)
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap();
            weights.extend(column.values().iter().copied());
            Ok(())
        },
    )?;
    assert_eq!(weights, [7, 9]);
    Ok(())
}

#[test]
fn reader_limit_fails_before_registering_and_callback_error_is_preserved() -> Result<()> {
    let store = LadybugGraphStore::in_memory()?;
    let batch =
        RecordBatch::try_from_iter([("id", Arc::new(Int64Array::from(vec![1, 2])) as ArrayRef)])
            .unwrap();
    assert!(matches!(
        store.register_arrow_node_reader(
            "Person",
            ArrowTable::from(batch.clone()).into_reader(),
            NonZeroUsize::new(1).unwrap(),
        ),
        Err(GrustError::ResourceLimitExceeded { .. })
    ));
    // The same table name can be registered after the rejected input.
    store.register_arrow_node_reader(
        "Person",
        ArrowTable::from(batch).into_reader(),
        NonZeroUsize::MAX,
    )?;
    let mut calls = 0;
    let error = store.visit_arrow_batches(
        "MATCH (p:Person) RETURN p.id;",
        NonZeroUsize::new(1).unwrap(),
        |_| {
            calls += 1;
            Err(GrustError::Backend("consumer stopped".into()))
        },
    );
    assert_eq!(calls, 1);
    assert!(matches!(error, Err(GrustError::Backend(message)) if message == "consumer stopped"));
    Ok(())
}
