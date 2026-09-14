use super::*;
use crate::{DataFusionEngine, ExecutionOptions, SpillPolicy};
use datafusion::arrow::array::Int64Array;
use grust_arrow::{ArrowGraph, ArrowGraphTables};
use grust_core::{Edge, Graph, Node, Props};

#[tokio::test]
async fn common_planner_selects_shapes_without_hiding_errors() {
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
    let parameters = CypherParameters::new();
    for (text, expected_kind, expected_count) in [
        ("MATCH () RETURN count(*) AS count", PlanKind::NodeScan, 2),
        (
            "MATCH ()-->() RETURN count(*) AS count",
            PlanKind::RelationshipScan,
            1,
        ),
    ] {
        let query = grust_cypher::parser::parse_query(text).unwrap();
        let QueryPlan::Supported { kind, frame } = snapshot
            .plan(&query, engine.context(), &parameters)
            .unwrap()
        else {
            panic!("{text}");
        };
        assert_eq!(kind, expected_kind);
        let batches = frame.collect().await.unwrap();
        assert_eq!(
            batches[0]
                .column(0)
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap()
                .value(0),
            expected_count
        );
    }
    let query =
        grust_cypher::parser::parse_query("MATCH ()-->()-->() RETURN count(*) AS count").unwrap();
    assert!(matches!(
        snapshot
            .plan(&query, engine.context(), &parameters)
            .unwrap(),
        QueryPlan::Unsupported {
            kind: PlanKind::RelationshipScan,
            reason: UnsupportedScan::QueryShape
        }
    ));
    let query = grust_cypher::parser::parse_query("MATCH () RETURN absent.x AS x").unwrap();
    assert!(
        snapshot
            .plan(&query, engine.context(), &parameters)
            .is_err()
    );
}
