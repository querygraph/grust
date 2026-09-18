use super::*;
use crate::{DataFusionEngine, ExecutionOptions, SpillPolicy};
use grust_arrow::{ArrowGraph, ArrowGraphTables};
use grust_core::{Edge, Graph, Node, Props};
use grust_cypher::ReadQueryPolicy;
use std::sync::Arc;

const NODES: usize = 20_000;

fn engine(working_memory_bytes: usize) -> DataFusionEngine {
    DataFusionEngine::new(ExecutionOptions {
        working_memory_bytes: working_memory_bytes.try_into().unwrap(),
        target_partitions: 4.try_into().unwrap(),
        batch_rows: 1024.try_into().unwrap(),
        spill: SpillPolicy::Disabled,
    })
    .unwrap()
}

fn graph() -> Arc<Graph> {
    let nodes = (0..NODES)
        .map(|id| {
            let mut props = Props::from([("bucket".into(), Value::Int((id % 16) as i64))]);
            if id % 3 == 0 {
                props.insert("tag".into(), Value::String(format!("t{}", id % 5)));
            }
            Node::new(if id % 2 == 0 { "N" } else { "M" }, id.to_string(), props)
        })
        .collect();
    let edges = (0..100)
        .map(|id| Edge::new("E", id.to_string(), (id + 1).to_string(), Props::new()))
        .collect();
    Arc::new(Graph::new(nodes, edges))
}

fn policy() -> ReadQueryPolicy {
    ReadQueryPolicy {
        max_candidate_work: 10_000_000,
        max_result_rows: 50,
        ..ReadQueryPolicy::default()
    }
}

const SCANS: &[&str] = &[
    "MATCH (n:N) WHERE n.bucket = 3 RETURN count(*) AS count LIMIT 1",
    "MATCH (n) WHERE n.bucket >= 14 RETURN id(n) AS id ORDER BY id LIMIT 7",
    "MATCH (n:M) RETURN n.bucket AS bucket, count(*) AS count ORDER BY bucket LIMIT 20",
    "MATCH (n) WHERE n.tag IS NULL RETURN count(*) AS count LIMIT 1",
    "MATCH (n {tag: 't2'}) RETURN DISTINCT n.bucket AS bucket ORDER BY bucket LIMIT 20",
    "MATCH (n:N) RETURN max(n.bucket) AS high, min(n.tag) AS low LIMIT 1",
];

#[tokio::test]
async fn automatic_scans_match_reference_results() {
    let engine = engine(64 << 20);
    let routed = RoutedGraph::capture(&engine, graph())
        .unwrap()
        .with_min_datafusion_nodes(0);
    let parameters = CypherParameters::new();
    for text in SCANS {
        let expected = grust_cypher::run_bounded_read_query_indexed(
            routed.index(),
            text,
            &parameters,
            &policy(),
        )
        .unwrap();
        let automatic = routed
            .run_bounded_read_query(text, &parameters, &policy(), RouteMode::Automatic)
            .await
            .unwrap();
        assert_eq!(automatic.explain.chosen, ReadRoute::DataFusion, "{text}");
        assert_eq!(automatic.explain.datafusion_declined, None, "{text}");
        assert!(automatic.explain.physical_plan.is_some(), "{text}");
        assert_eq!(automatic.table, expected, "{text}");
        let reference = routed
            .run_bounded_read_query(
                text,
                &parameters,
                &policy(),
                RouteMode::Force(ReadRoute::Reference),
            )
            .await
            .unwrap();
        assert_eq!(reference.explain.chosen, ReadRoute::Reference);
        assert_eq!(
            reference.explain.datafusion_declined,
            Some(RouteDecline::ReferenceForced)
        );
        assert_eq!(reference.table, expected, "{text}");
    }
}

#[tokio::test]
async fn joins_and_unsupported_shapes_stay_on_reference() {
    let engine = engine(64 << 20);
    let routed = RoutedGraph::capture(&engine, graph())
        .unwrap()
        .with_min_datafusion_nodes(0);
    let parameters = CypherParameters::new();
    let join = "MATCH (a)-[:E]->(b) RETURN count(*) AS count LIMIT 1";
    let result = routed
        .run_bounded_read_query(join, &parameters, &policy(), RouteMode::Automatic)
        .await
        .unwrap();
    assert_eq!(result.explain.chosen, ReadRoute::Reference);
    assert_eq!(
        result.explain.datafusion_declined,
        Some(RouteDecline::RelationshipJoin)
    );
    assert_eq!(result.table.rows, vec![vec![Value::Int(100)]]);
    let forced = routed
        .run_bounded_read_query(
            join,
            &parameters,
            &policy(),
            RouteMode::Force(ReadRoute::DataFusion),
        )
        .await
        .unwrap_err();
    assert!(forced.to_string().contains("route unavailable"), "{forced}");
    let optional = routed
        .explain(
            "OPTIONAL MATCH (n:N) RETURN count(*) AS count LIMIT 1",
            &parameters,
            &policy(),
            RouteMode::Automatic,
        )
        .await
        .unwrap();
    assert_eq!(optional.chosen, ReadRoute::Reference);
    assert!(matches!(
        optional.datafusion_declined,
        Some(RouteDecline::Unsupported { .. })
    ));
    // Invalid Cypher is an error, never a route decline.
    assert!(
        routed
            .run_bounded_read_query(
                "MATCH (n) RETURN absent.x AS x LIMIT 1",
                &parameters,
                &policy(),
                RouteMode::Automatic
            )
            .await
            .is_err()
    );
}

#[tokio::test]
async fn threshold_and_candidate_work_decline_before_execution() {
    let engine = engine(64 << 20);
    const { assert!(DEFAULT_MIN_DATAFUSION_NODES < NODES) };
    let routed = RoutedGraph::capture(&engine, graph())
        .unwrap()
        .with_min_datafusion_nodes(NODES + 1);
    let parameters = CypherParameters::new();
    let text = SCANS[0];
    let explain = routed
        .explain(text, &parameters, &policy(), RouteMode::Automatic)
        .await
        .unwrap();
    assert_eq!(explain.chosen, ReadRoute::Reference);
    assert_eq!(
        explain.datafusion_declined,
        Some(RouteDecline::BelowThreshold {
            node_rows: NODES,
            threshold: NODES + 1
        })
    );
    assert_eq!(explain.capture.unwrap().node_rows, NODES);
    let routed = routed.with_min_datafusion_nodes(0);
    let tight = ReadQueryPolicy {
        max_candidate_work: NODES - 1,
        ..policy()
    };
    let explain = routed
        .explain(text, &parameters, &tight, RouteMode::Automatic)
        .await
        .unwrap();
    assert_eq!(
        explain.datafusion_declined,
        Some(RouteDecline::CandidateWork {
            required: NODES,
            limit: NODES - 1
        })
    );
    let exact = ReadQueryPolicy {
        max_candidate_work: NODES,
        ..policy()
    };
    let result = routed
        .run_bounded_read_query(text, &parameters, &exact, RouteMode::Automatic)
        .await
        .unwrap();
    assert_eq!(result.explain.chosen, ReadRoute::DataFusion);
}

#[tokio::test]
async fn intermediate_bytes_are_enforced_across_partitions() {
    let engine = engine(64 << 20);
    let routed = RoutedGraph::capture(&engine, graph())
        .unwrap()
        .with_min_datafusion_nodes(0);
    let parameters = CypherParameters::new();
    // Filtering keeps half the nodes, so operators emit far more than 4 KiB
    // before the final LIMIT, even though the result is seven rows.
    let small = ReadQueryPolicy {
        max_intermediate_bytes: 4096,
        ..policy()
    };
    let error = routed
        .run_bounded_read_query(
            "MATCH (n:N) RETURN id(n) AS id ORDER BY id LIMIT 7",
            &parameters,
            &small,
            RouteMode::Force(ReadRoute::DataFusion),
        )
        .await
        .unwrap_err();
    assert!(
        error.to_string().contains("cumulative intermediate bytes"),
        "{error}"
    );
}

#[tokio::test]
async fn capture_failure_keeps_the_reference_route() {
    let engine = engine(64 << 20);
    let nodes = (0..3)
        .map(|id| {
            Node::new(
                "N",
                id.to_string(),
                // Mixed property types have no single native Arrow column.
                Props::from([(
                    "mixed".into(),
                    if id == 0 {
                        Value::String("zero".into())
                    } else {
                        Value::Int(id)
                    },
                )]),
            )
        })
        .collect();
    let routed = RoutedGraph::capture(&engine, Arc::new(Graph::new(nodes, vec![])))
        .unwrap()
        .with_min_datafusion_nodes(0);
    let result = routed
        .run_bounded_read_query(
            "MATCH (n:N) RETURN count(*) AS count LIMIT 1",
            &CypherParameters::new(),
            &policy(),
            RouteMode::Automatic,
        )
        .await
        .unwrap();
    assert_eq!(result.explain.chosen, ReadRoute::Reference);
    assert!(matches!(
        result.explain.datafusion_declined,
        Some(RouteDecline::CaptureUnavailable(_))
    ));
    assert_eq!(result.table.rows, vec![vec![Value::Int(3)]]);
}

#[tokio::test]
async fn single_large_batches_are_split_without_round_robin() {
    let rows = 4 * 8192 * 3;
    let nodes = (0..rows)
        .map(|id| {
            Node::new(
                "N",
                id.to_string(),
                Props::from([("bucket".into(), Value::Int((id % 16) as i64))]),
            )
        })
        .collect();
    // A pool smaller than four copies of the whole batch: the former
    // round-robin plan charged every queued slice the full parent buffers.
    let graph = Arc::new(Graph::new(nodes, vec![]));
    let (nodes, edges) = ArrowGraph::from_graph(&graph).unwrap().into_tables();
    let whole = nodes.batches()[0].get_array_memory_size();
    let engine = engine(whole * 3);
    let snapshot =
        GraphSnapshot::try_new(&engine, ArrowGraphTables::try_new(nodes, edges).unwrap()).unwrap();
    let query = grust_cypher::parser::parse_query(
        "MATCH (n:N) WHERE n.bucket = 3 RETURN count(*) AS count",
    )
    .unwrap();
    let frame = || match snapshot
        .plan(&query, engine.context(), &CypherParameters::new())
        .unwrap()
    {
        QueryPlan::Supported { frame, .. } => frame,
        QueryPlan::Unsupported { .. } => panic!("scan must be supported"),
    };
    let plan = frame().create_physical_plan().await.unwrap();
    let text = datafusion::physical_plan::displayable(plan.as_ref())
        .indent(true)
        .to_string();
    assert!(!text.contains("RoundRobinBatch"), "{text}");
    // Repeat enough times that the former scheduling-dependent failure would
    // have been likely to appear at least once.
    for _ in 0..20 {
        let table = collect_result(frame(), 1, 1024).await.unwrap();
        assert_eq!(table.rows, vec![vec![Value::Int((rows / 16) as i64)]]);
    }
}
