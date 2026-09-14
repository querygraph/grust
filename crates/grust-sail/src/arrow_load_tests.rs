use super::*;
#[test]
fn native_node_stage_retains_identity_and_normalized_property_buffers() {
    let nodes = vec![Node::new(
        "N",
        "a",
        Props::from([("n".into(), Value::Int(42))]),
    )];
    let input = super::super::nodes_record_batch(&nodes).unwrap();
    let decoded = nodes_from_batch(&input).unwrap();
    let staged = node_stage_batch(&input, &decoded).unwrap();
    assert_eq!(decoded, nodes);
    for name in ["id", "label", "props"] {
        assert!(Arc::ptr_eq(
            input.column_by_name(name).unwrap(),
            staged.column_by_name(name).unwrap()
        ));
    }
}
#[test]
fn malformed_node_identity_is_rejected() {
    let input = RecordBatch::try_from_iter([
        (
            "id",
            Arc::new(StringArray::from(vec![None::<&str>])) as ArrayRef,
        ),
        ("label", Arc::new(StringArray::from(vec!["N"])) as ArrayRef),
        ("props", Arc::new(StringArray::from(vec!["{}"])) as ArrayRef),
    ])
    .unwrap();
    assert!(matches!(
        nodes_from_batch(&input),
        Err(GrustError::Serialization(_))
    ));
}
#[test]
fn explicit_empty_edge_id_survives_native_ingestion() {
    let edges = vec![Edge::new("E", "a", "b", Props::new()).with_id("")];
    let input = super::super::edges_record_batch(&edges, &BTreeMap::new()).unwrap();
    let decoded = edges_from_batch(&input).unwrap();
    assert_eq!(decoded, edges);
    let staged = edge_stage_batch(&input, &decoded, &BTreeMap::new()).unwrap();
    for name in ["src_id", "dst_id", "edge_type", "id", "props"] {
        assert!(Arc::ptr_eq(
            input.column_by_name(name).unwrap(),
            staged.column_by_name(name).unwrap()
        ));
    }
}

#[tokio::test]
#[ignore = "requires a live Sail server on 127.0.0.1:50051"]
async fn native_readers_load_multiple_batches_and_keep_typed_tables() {
    use super::super::{SailConfig, SailWarehouse};
    use arrow::array::RecordBatchIterator;
    let store = SailGraphStore::connect(SailConfig {
        warehouse: SailWarehouse::LocalSessionScoped,
        batch_size: 1,
        ..Default::default()
    })
    .await
    .unwrap();
    let schema = GraphSchema::builder()
        .node(
            "N",
            vec![grust_core::Field::required("token", FieldType::String)],
        )
        .edge("E", vec!["N".into()], vec!["N".into()], vec![])
        .unique_node_property("N", "token")
        .build();
    store.apply_schema(&schema).await.unwrap();
    let nodes = vec![
        Node::new(
            "N",
            "a",
            Props::from([("token".into(), Value::String("a".into()))]),
        ),
        Node::new(
            "N",
            "b",
            Props::from([("token".into(), Value::String("b".into()))]),
        ),
    ];
    let edges = vec![
        Edge::new("E", "a", "b", Props::new()).with_id("explicit"),
        Edge::new("E", "a", "a", Props::new()).with_id("loop"),
    ];
    let node_batch = super::super::nodes_record_batch(&nodes).unwrap();
    let edge_batch = super::super::edges_record_batch(&edges, &BTreeMap::new()).unwrap();
    let node_reader = RecordBatchIterator::new(vec![Ok(node_batch.clone())], node_batch.schema());
    let edge_reader = RecordBatchIterator::new(vec![Ok(edge_batch.clone())], edge_batch.schema());
    let report = store
        .load_arrow(
            node_reader,
            edge_reader,
            NonZeroUsize::new(1 << 20).unwrap(),
        )
        .await
        .unwrap();
    assert_eq!((report.nodes, report.edges), (2, 2));
    assert_eq!(
        store.get_node(&nodes[0].id).await.unwrap(),
        Some(nodes[0].clone())
    );
    let persisted = store.get_edges(EdgeQuery::default()).await.unwrap();
    assert_eq!(persisted.len(), edges.len());
    for edge in &edges {
        assert!(persisted.contains(edge));
    }
    let mut count = 0;
    store
        .visit_arrow_batches("SELECT id FROM grust_node_n", |batch| {
            count += batch.num_rows();
            Ok(())
        })
        .await
        .unwrap();
    assert_eq!(count, 2);
    store.clear().await.unwrap();
}

#[tokio::test]
#[ignore = "requires a live Sail server on 127.0.0.1:50051"]
async fn native_reader_load_initializes_tables_without_an_applied_schema() {
    use super::super::{SailConfig, SailWarehouse};
    use grust_arrow::v58::ArrowTable;
    let store = SailGraphStore::connect(SailConfig {
        warehouse: SailWarehouse::LocalSessionScoped,
        ..Default::default()
    })
    .await
    .unwrap();
    let node = Node::new("N", "first", Props::new());
    let nodes = super::super::nodes_record_batch(std::slice::from_ref(&node)).unwrap();
    let edges = super::super::edges_record_batch(&[], &BTreeMap::new()).unwrap();
    let report = store
        .load_arrow(
            ArrowTable::from(nodes).into_reader(),
            ArrowTable::from(edges).into_reader(),
            NonZeroUsize::new(1 << 20).unwrap(),
        )
        .await
        .unwrap();
    assert_eq!((report.nodes, report.edges), (1, 0));
    assert_eq!(store.get_node(&node.id).await.unwrap(), Some(node));
    store.clear().await.unwrap();
}
