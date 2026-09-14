#![cfg(all(feature = "cypher", feature = "datafusion"))]
use grust::arrow::{ArrowGraph, ArrowGraphTables};
use grust::datafusion::cypher::{CypherExecution, GraphSnapshot, OutputLimits};
use grust::datafusion::{DataFusionEngine, ExecutionOptions, SpillPolicy};
use grust::{Graph, Node, Props, Value};

#[tokio::test]
async fn combined_facade_features_execute_cypher_without_direct_adapter_dependencies() {
    let graph = Graph::new(vec![Node::new("N", "a", Props::new())], vec![]);
    let (nodes, edges) = ArrowGraph::from_graph(&graph).unwrap().into_tables();
    let engine = DataFusionEngine::new(ExecutionOptions {
        working_memory_bytes: (16 * 1024 * 1024).try_into().unwrap(),
        target_partitions: 1.try_into().unwrap(),
        batch_rows: 1024.try_into().unwrap(),
        spill: SpillPolicy::Disabled,
    })
    .unwrap();
    let snapshot =
        GraphSnapshot::try_new(&engine, ArrowGraphTables::try_new(nodes, edges).unwrap()).unwrap();
    let CypherExecution::Completed { table, .. } = snapshot
        .execute(
            "MATCH (n:N) RETURN id(n) AS id",
            engine.context(),
            &grust::CypherParameters::new(),
            OutputLimits {
                max_rows: 1,
                max_serialized_bytes: 1024,
            },
        )
        .await
        .unwrap()
    else {
        panic!("facade query unsupported");
    };
    assert_eq!(table.columns, ["id"]);
    assert_eq!(table.rows, vec![vec![Value::String("a".into())]]);
}
