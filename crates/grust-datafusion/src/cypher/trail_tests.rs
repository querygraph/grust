use super::*;
use crate::{DataFusionEngine, ExecutionOptions, SpillPolicy};
use datafusion::arrow::array::UInt64Array;
use grust_arrow::{ArrowGraph, ArrowGraphTables};
use grust_core::{Edge, Graph, Node, Props};

#[tokio::test]
async fn trail_joins_preserve_parallel_edges_and_exclude_physical_reuse() {
    let engine = DataFusionEngine::new(ExecutionOptions {
        working_memory_bytes: (16 * 1024 * 1024).try_into().unwrap(),
        target_partitions: 4.try_into().unwrap(),
        batch_rows: 1024.try_into().unwrap(),
        spill: SpillPolicy::Disabled,
    })
    .unwrap();
    let graph = Graph::new(
        vec![
            Node::new("N", "a", Props::new()),
            Node::new("N", "b", Props::new()),
        ],
        vec![
            Edge::new("E", "a", "b", Props::new()),
            Edge::new("E", "a", "b", Props::new()),
            Edge::new("E", "b", "a", Props::new()),
            Edge::new("E", "b", "b", Props::new()),
        ],
    );
    let (nodes, edges) = ArrowGraph::from_graph(&graph).unwrap().into_tables();
    let tables = ArrowGraphTables::try_new(nodes, edges).unwrap();
    let snapshot = GraphSnapshot::try_new(&engine, tables.clone()).unwrap();
    let other_snapshot = GraphSnapshot::try_new(&engine, tables).unwrap();
    let make = |snapshot: &GraphSnapshot, a, r, b| {
        snapshot
            .directed_relationships(engine.context(), a, r, b)
            .unwrap()
    };
    assert!(
        make(&snapshot, "a", "r", "b")
            .join_trail(make(&other_snapshot, "b", "s", "c"))
            .is_err()
    );
    let plan = make(&snapshot, "a", "r", "b")
        .join_trail(make(&snapshot.clone(), "b", "s", "c"))
        .unwrap();
    let projection = vec![
        plan.bindings()
            .relationship_ordinal("r")
            .unwrap()
            .alias("r"),
        plan.bindings()
            .relationship_ordinal("s")
            .unwrap()
            .alias("s"),
    ];
    let (frame, _) = plan.into_parts();
    let mut actual = Vec::new();
    for batch in frame.select(projection).unwrap().collect().await.unwrap() {
        let left = batch
            .column(0)
            .as_any()
            .downcast_ref::<UInt64Array>()
            .unwrap();
        let right = batch
            .column(1)
            .as_any()
            .downcast_ref::<UInt64Array>()
            .unwrap();
        for row in 0..batch.num_rows() {
            actual.push((left.value(row), right.value(row)));
        }
    }
    let mut expected = Vec::new();
    for (i, left) in graph.edges.iter().enumerate() {
        for (j, right) in graph.edges.iter().enumerate() {
            if i != j && left.to == right.from {
                expected.push((i as u64, j as u64));
            }
        }
    }
    actual.sort_unstable();
    assert_eq!(actual, expected);
    let plan = make(&snapshot, "a", "r", "b")
        .join_trail(make(&snapshot, "b", "s", "c"))
        .unwrap()
        .join_trail(make(&snapshot, "c", "t", "d"))
        .unwrap();
    let projection = ["r", "s", "t"]
        .into_iter()
        .map(|name| {
            plan.bindings()
                .relationship_ordinal(name)
                .unwrap()
                .alias(name)
        })
        .collect::<Vec<_>>();
    let (frame, _) = plan.into_parts();
    let mut actual = Vec::new();
    for batch in frame.select(projection).unwrap().collect().await.unwrap() {
        let columns = batch
            .columns()
            .iter()
            .map(|column| column.as_any().downcast_ref::<UInt64Array>().unwrap())
            .collect::<Vec<_>>();
        for row in 0..batch.num_rows() {
            actual.push((
                columns[0].value(row),
                columns[1].value(row),
                columns[2].value(row),
            ));
        }
    }
    let mut expected = Vec::new();
    for (i, first) in graph.edges.iter().enumerate() {
        for (j, second) in graph.edges.iter().enumerate() {
            for (k, third) in graph.edges.iter().enumerate() {
                if i != j && i != k && j != k && first.to == second.from && second.to == third.from
                {
                    expected.push((i as u64, j as u64, k as u64));
                }
            }
        }
    }
    actual.sort_unstable();
    assert_eq!(actual, expected);
}
