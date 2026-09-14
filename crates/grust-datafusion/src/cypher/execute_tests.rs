use super::*;
use crate::{DataFusionEngine, ExecutionOptions, SpillPolicy};
use grust_arrow::{ArrowGraph, ArrowGraphTables};
use grust_core::{Edge, Graph, Node, Props};

#[tokio::test]
async fn text_execution_preserves_results_and_error_boundaries() {
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
        vec![Edge::new("E", "a", "b", Props::new())],
    );
    let (nodes, edges) = ArrowGraph::from_graph(&graph).unwrap().into_tables();
    let snapshot =
        GraphSnapshot::try_new(&engine, ArrowGraphTables::try_new(nodes, edges).unwrap()).unwrap();
    let parameters = CypherParameters::from([("id".into(), Value::String("b".into()))]);
    let output = OutputLimits {
        max_rows: 10,
        max_serialized_bytes: 1024,
    };
    for text in [
        "MATCH (n) WHERE id(n) = $id RETURN id(n) AS id",
        "MATCH ()-->() RETURN count(*) AS count",
        "MATCH ()--() RETURN count(*) AS count",
    ] {
        let query = grust_cypher::parser::parse_query(text).unwrap();
        let expected = grust_cypher::read::execute_read_query(&graph, &query, &parameters).unwrap();
        let CypherExecution::Completed { table, .. } = snapshot
            .execute(text, engine.context(), &parameters, output)
            .await
            .unwrap()
        else {
            panic!("{text}");
        };
        assert_eq!(table, expected);
    }
    assert!(matches!(
        snapshot
            .execute(
                "MATCH ()-->()-->() RETURN count(*) AS count",
                engine.context(),
                &parameters,
                output
            )
            .await
            .unwrap(),
        CypherExecution::Unsupported { .. }
    ));
    for text in ["MATCH (", "MATCH (n) RETURN absent.x AS x"] {
        assert!(
            snapshot
                .execute(text, engine.context(), &parameters, output)
                .await
                .is_err()
        );
    }
    assert!(
        snapshot
            .execute(
                "MATCH () RETURN count(*) AS count",
                engine.context(),
                &parameters,
                OutputLimits {
                    max_rows: 0,
                    ..output
                }
            )
            .await
            .is_err()
    );
    assert!(
        snapshot
            .execute(
                "MATCH () RETURN count(*) AS count",
                engine.context(),
                &parameters,
                OutputLimits {
                    max_serialized_bytes: 0,
                    ..output
                }
            )
            .await
            .is_err()
    );
}
