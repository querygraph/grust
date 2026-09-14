use super::{EDGE_ORDINAL, GraphSnapshot};
use crate::{DataFusionEngine, ExecutionOptions, SpillPolicy};
use datafusion::arrow::array::{Array, StringArray, UInt64Array};
use grust_arrow::{ArrowGraph, ArrowGraphTables, ArrowTable};
use grust_core::{Edge, Graph, Node, Props};

#[tokio::test]
async fn physical_edge_identity_survives_batches_partitions_and_catalog_replacement() {
    let engine = DataFusionEngine::new(ExecutionOptions {
        working_memory_bytes: (16 * 1024 * 1024).try_into().unwrap(),
        target_partitions: 4.try_into().unwrap(),
        batch_rows: 1024.try_into().unwrap(),
        spill: SpillPolicy::Disabled,
    })
    .unwrap();
    let mut duplicate = Edge::new("E", "a", "a", Props::new());
    duplicate.id = Some("duplicate".into());
    let graph = Graph::new(
        vec![
            Node::new("N", "a", Props::new()),
            Node::new("N", "isolate", Props::new()),
        ],
        vec![
            duplicate.clone(),
            duplicate,
            Edge::new("E", "a", "a", Props::new()),
        ],
    );
    let arrow = ArrowGraph::from_graph(&graph).unwrap();
    let original = arrow.edges().column(0).clone();
    let edges = ArrowTable::try_new(
        arrow.edges().schema(),
        vec![arrow.edges().slice(0, 1), arrow.edges().slice(1, 2)],
    )
    .unwrap();
    assert_eq!(
        edges.batches()[0].column(0).to_data().buffers()[1].as_ptr(),
        original.to_data().buffers()[1].as_ptr()
    );
    let tables = ArrowGraphTables::try_new(ArrowTable::from(arrow.nodes().clone()), edges).unwrap();
    engine
        .register_graph("replacement", tables.clone())
        .unwrap();
    let snapshot = GraphSnapshot::try_new(&engine, tables).unwrap();
    let captured = snapshot.edges(engine.context()).unwrap();
    let (nodes, edges) = ArrowGraph::from_graph(&Graph::new(vec![], vec![]))
        .unwrap()
        .into_tables();
    engine
        .register_graph(
            "replacement",
            ArrowGraphTables::try_new(nodes, edges).unwrap(),
        )
        .unwrap();
    let batches = captured.collect().await.unwrap();
    let mut identities = Vec::new();
    let mut external = Vec::new();
    for batch in batches {
        assert_eq!(
            batch.column_by_name("source").unwrap().to_data().buffers()[1].as_ptr(),
            original.to_data().buffers()[1].as_ptr()
        );
        let ordinals = batch
            .column_by_name(EDGE_ORDINAL)
            .unwrap()
            .as_any()
            .downcast_ref::<UInt64Array>()
            .unwrap();
        let ids = batch
            .column_by_name("edge_id")
            .unwrap()
            .as_any()
            .downcast_ref::<StringArray>()
            .unwrap();
        for row in 0..batch.num_rows() {
            identities.push(ordinals.value(row));
            external.push((!ids.is_null(row)).then(|| ids.value(row).to_owned()));
        }
    }
    identities.sort_unstable();
    assert_eq!(identities, [0, 1, 2]);
    assert_eq!(
        external
            .iter()
            .filter(|id| id.as_deref() == Some("duplicate"))
            .count(),
        2
    );
    assert_eq!(external.iter().filter(|id| id.is_none()).count(), 1);
    let nodes = snapshot
        .clone()
        .nodes(engine.context())
        .unwrap()
        .collect()
        .await
        .unwrap();
    assert_eq!(nodes.iter().map(|batch| batch.num_rows()).sum::<usize>(), 2);
}
