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
    let statistics = snapshot.statistics();
    assert_eq!(statistics.node_rows, 2);
    assert_eq!(statistics.edge_rows, 3);
    assert_eq!(statistics.node_batches, 1);
    assert_eq!(statistics.edge_batches, 2);
    assert_eq!(statistics.edge_ordinal_bytes, 24);
    assert_eq!(statistics.serialized_graph_bytes, None);
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
    assert_eq!(snapshot.clone().statistics(), statistics);
}

#[test]
fn empty_snapshot_statistics_are_exact_without_executing_a_plan() {
    let engine = DataFusionEngine::new(ExecutionOptions {
        working_memory_bytes: (1 << 20).try_into().unwrap(),
        target_partitions: 4.try_into().unwrap(),
        batch_rows: 1024.try_into().unwrap(),
        spill: SpillPolicy::Disabled,
    })
    .unwrap();
    let arrow = ArrowGraph::from_graph(&Graph::new(vec![], vec![])).unwrap();
    let nodes = ArrowTable::try_new(arrow.nodes().schema(), vec![]).unwrap();
    let edges = ArrowTable::try_new(arrow.edges().schema(), vec![]).unwrap();
    let snapshot =
        GraphSnapshot::try_new(&engine, ArrowGraphTables::try_new(nodes, edges).unwrap()).unwrap();
    assert_eq!(
        snapshot.statistics(),
        super::SnapshotStatistics {
            node_rows: 0,
            edge_rows: 0,
            node_batches: 0,
            edge_batches: 0,
            edge_ordinal_bytes: 0,
            serialized_graph_bytes: None,
        }
    );
}

#[test]
fn native_input_admission_matches_exact_graph_bytes_and_retains_measurement() {
    let engine = DataFusionEngine::new(ExecutionOptions {
        working_memory_bytes: (1 << 20).try_into().unwrap(),
        target_partitions: 4.try_into().unwrap(),
        batch_rows: 1024.try_into().unwrap(),
        spill: SpillPolicy::Disabled,
    })
    .unwrap();
    let parameters = grust_cypher::CypherParameters::new();
    for graph in [
        Graph::new(vec![], vec![]),
        Graph::new(
            vec![
                Node::new("N", "a\"", Props::new()),
                Node::new("N", "b", Props::new()),
            ],
            vec![Edge::new("E", "a\"", "b", Props::new())],
        ),
    ] {
        let bytes = serde_json::to_vec(&graph).unwrap().len();
        let (nodes, edges) = ArrowGraph::from_graph(&graph).unwrap().into_tables();
        let tables = ArrowGraphTables::try_new(nodes, edges).unwrap();
        let policy = grust_cypher::ReadQueryPolicy {
            max_graph_bytes: bytes,
            ..grust_cypher::ReadQueryPolicy::default()
        };
        let request = grust_cypher::PreparedReadRequest::new(
            "MATCH (n) RETURN count(*) LIMIT 1",
            &parameters,
            &policy,
        )
        .unwrap();
        let snapshot =
            GraphSnapshot::try_new_with_input_policy(&engine, tables.clone(), &request).unwrap();
        assert_eq!(snapshot.statistics().serialized_graph_bytes, Some(bytes));
        assert_eq!(snapshot.clone().statistics(), snapshot.statistics());
        let too_small = grust_cypher::PreparedReadRequest::new(
            "MATCH (n) RETURN count(*) LIMIT 1",
            &parameters,
            &grust_cypher::ReadQueryPolicy {
                max_graph_bytes: bytes - 1,
                ..policy
            },
        )
        .unwrap();
        assert!(GraphSnapshot::try_new_with_input_policy(&engine, tables, &too_small).is_err());
    }
}

#[tokio::test]
async fn ordinal_admission_follows_emitted_arrays_after_snapshot_drop() {
    use grust_procedures::{ExecutionContext, ExecutionLimits};
    let engine = DataFusionEngine::new(ExecutionOptions {
        working_memory_bytes: (16 * 1024 * 1024).try_into().unwrap(),
        target_partitions: 1.try_into().unwrap(),
        batch_rows: 1024.try_into().unwrap(),
        spill: SpillPolicy::Disabled,
    })
    .unwrap();
    let graph = Graph::new(
        vec![Node::new("N", "a", Props::new())],
        vec![Edge::new("E", "a", "a", Props::new())],
    );
    let tables = || {
        let (nodes, edges) = ArrowGraph::from_graph(&graph).unwrap().into_tables();
        ArrowGraphTables::try_new(nodes, edges).unwrap()
    };
    let context = |memory_bytes| {
        ExecutionContext::new(ExecutionLimits {
            memory_bytes,
            work_units: 1,
            batch_rows: 1024,
            deadline: None,
        })
        .unwrap()
    };
    assert!(GraphSnapshot::try_new_with_context(&engine, tables(), &context(7)).is_err());
    let execution = context(8);
    let snapshot = GraphSnapshot::try_new_with_context(&engine, tables(), &execution).unwrap();
    let batches = snapshot
        .edges(engine.context())
        .unwrap()
        .collect()
        .await
        .unwrap();
    drop(snapshot);
    assert_eq!(execution.usage().unwrap().live_bytes, 8);
    let ordinal = batches[0].column_by_name(EDGE_ORDINAL).unwrap().slice(0, 1);
    drop(batches);
    assert_eq!(execution.usage().unwrap().live_bytes, 8);
    assert_eq!(
        ordinal
            .as_any()
            .downcast_ref::<UInt64Array>()
            .unwrap()
            .value(0),
        0
    );
    drop(ordinal);
    assert_eq!(execution.usage().unwrap().live_bytes, 0);
    assert_eq!(execution.usage().unwrap().work_units, 1);

    let cancelled = context(8);
    cancelled.cancel().unwrap();
    assert!(GraphSnapshot::try_new_with_context(&engine, tables(), &cancelled).is_err());
    assert_eq!(cancelled.usage().unwrap().live_bytes, 0);

    let (nodes, edges) = tables().into_tables();
    let edges = ArrowTable::try_new(
        edges.schema(),
        vec![edges.batches()[0].clone(), edges.batches()[0].clone()],
    )
    .unwrap();
    let partial = context(8);
    assert!(
        GraphSnapshot::try_new_with_context(
            &engine,
            ArrowGraphTables::try_new(nodes, edges).unwrap(),
            &partial
        )
        .is_err()
    );
    assert_eq!(partial.usage().unwrap().live_bytes, 0);
    assert_eq!(partial.usage().unwrap().peak_bytes, 8);
    assert_eq!(partial.usage().unwrap().work_units, 1);

    let no_work = ExecutionContext::new(ExecutionLimits {
        work_units: 0,
        ..execution.limits()
    })
    .unwrap();
    assert!(GraphSnapshot::try_new_with_context(&engine, tables(), &no_work).is_err());
    assert_eq!(no_work.usage().unwrap().live_bytes, 0);
}

#[test]
fn combined_capture_preserves_input_limit_and_original_deadline() {
    use grust_procedures::{ExecutionContext, ExecutionLimits};
    let engine = DataFusionEngine::new(ExecutionOptions {
        working_memory_bytes: (16 * 1024 * 1024).try_into().unwrap(),
        target_partitions: 1.try_into().unwrap(),
        batch_rows: 1024.try_into().unwrap(),
        spill: SpillPolicy::Disabled,
    })
    .unwrap();
    let graph = Graph::new(
        vec![Node::new("N", "a", Props::new())],
        vec![Edge::new("E", "a", "a", Props::new())],
    );
    let (nodes, edges) = ArrowGraph::from_graph(&graph).unwrap().into_tables();
    let tables = ArrowGraphTables::try_new(nodes, edges).unwrap();
    let parameters = grust_cypher::CypherParameters::new();
    let policy = grust_cypher::ReadQueryPolicy::default();
    let request = grust_cypher::PreparedReadRequest::new(
        "MATCH (n) RETURN count(*) LIMIT 1",
        &parameters,
        &policy,
    )
    .unwrap();
    let context = |deadline| {
        ExecutionContext::new(ExecutionLimits {
            memory_bytes: 8,
            work_units: 1,
            batch_rows: 1024,
            deadline,
        })
        .unwrap()
    };
    assert!(
        GraphSnapshot::try_new_with_input_policy_and_context(
            &engine,
            tables.clone(),
            &request,
            &context(None)
        )
        .is_err()
    );
    let execution = context(Some(request.deadline()));
    let snapshot = GraphSnapshot::try_new_with_input_policy_and_context(
        &engine,
        tables.clone(),
        &request,
        &execution,
    )
    .unwrap();
    assert_eq!(
        snapshot.statistics().serialized_graph_bytes,
        Some(serde_json::to_vec(&graph).unwrap().len())
    );
    drop(snapshot);
    assert_eq!(execution.usage().unwrap().live_bytes, 0);
    let small = grust_cypher::PreparedReadRequest::new(
        "MATCH (n) RETURN count(*) LIMIT 1",
        &parameters,
        &grust_cypher::ReadQueryPolicy {
            max_graph_bytes: 1,
            ..policy
        },
    )
    .unwrap();
    let execution = context(Some(small.deadline()));
    assert!(
        GraphSnapshot::try_new_with_input_policy_and_context(&engine, tables, &small, &execution)
            .is_err()
    );
    assert_eq!(execution.usage().unwrap().peak_bytes, 0);
}
