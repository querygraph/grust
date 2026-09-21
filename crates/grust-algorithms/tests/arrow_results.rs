#![cfg(feature = "arrow")]

use arrow_array::{Array, Float64Array, LargeListArray, StringArray, UInt64Array};
use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, Orientation,
    PageRankOptions, ProjectionEdge, SnapshotIdentity, YensOptions, bfs, pagerank, shortest_paths,
    weakly_connected_components, yens,
};

fn graph(context: &ExecutionContext) -> GraphProjection {
    GraphProjection::from_topology(
        SnapshotIdentity::new("g".into(), "r1".into(), "reader".into()).unwrap(),
        vec!["a".into(), "b".into(), "isolate".into()],
        vec![ProjectionEdge {
            source: 0,
            target: 1,
            ordinal: 42,
            id: None,
        }],
        Some(vec![2.5]),
        Orientation::Outgoing,
        context,
    )
    .unwrap()
}

fn context() -> ExecutionContext {
    ExecutionContext::new(ExecutionLimits {
        memory_bytes: 512 * 1024,
        work_units: 1_000_000,
        batch_rows: 2,
        deadline: None,
    })
    .unwrap()
}

#[test]
fn arrow_distances_preserve_nulls_batch_bounds_and_retained_admission() {
    let context = context();
    let graph = graph(&context);
    let mut cursor = bfs(&graph, "a").unwrap().into_arrow_results();
    drop(graph);
    let first = cursor.next_batch().unwrap().unwrap();
    assert_eq!(first.record_batch().num_rows(), 2);
    let values = first
        .record_batch()
        .column_by_name("distance")
        .unwrap()
        .as_any()
        .downcast_ref::<Float64Array>()
        .unwrap();
    assert_eq!(values.values().as_ref(), &[0.0, 1.0]);
    let last = cursor.next_batch().unwrap().unwrap();
    assert_eq!(last.record_batch().num_rows(), 1);
    assert!(
        last.record_batch()
            .column_by_name("distance")
            .unwrap()
            .is_null(0)
    );
    assert!(cursor.next_batch().unwrap().is_none());
    let retained = first.clone();
    drop(cursor);
    drop(first);
    drop(last);
    assert_eq!(
        context.usage().unwrap().live_bytes,
        retained.reserved_bytes()
    );
    let bytes = retained.reserved_bytes();
    let raw = retained.record_batch().clone();
    drop(retained);
    assert_eq!(context.usage().unwrap().live_bytes, bytes);
    let slice = raw.column(0).slice(0, 1);
    drop(raw);
    assert_eq!(context.usage().unwrap().live_bytes, bytes);
    drop(slice);
    assert_eq!(context.usage().unwrap().live_bytes, 0);
}

#[test]
fn arrow_full_paths_are_typed_and_keep_original_edge_ordinals() {
    let context = context();
    let graph = graph(&context);
    let mut cursor = shortest_paths(&graph, "a")
        .unwrap()
        .into_arrow_results()
        .unwrap();
    let source = cursor.next_batch().unwrap().unwrap();
    let source_edges = source
        .record_batch()
        .column_by_name("edgeOrdinals")
        .unwrap()
        .as_any()
        .downcast_ref::<LargeListArray>()
        .unwrap();
    assert_eq!(source_edges.value_length(0), 0);
    let destination = cursor.next_batch().unwrap().unwrap();
    let batch = destination.record_batch();
    let nodes = batch
        .column_by_name("nodeIds")
        .unwrap()
        .as_any()
        .downcast_ref::<LargeListArray>()
        .unwrap()
        .value(0);
    let nodes = nodes.as_any().downcast_ref::<StringArray>().unwrap();
    assert_eq!(nodes.iter().collect::<Vec<_>>(), vec![Some("a"), Some("b")]);
    let costs = batch
        .column_by_name("costs")
        .unwrap()
        .as_any()
        .downcast_ref::<LargeListArray>()
        .unwrap()
        .value(0);
    assert_eq!(
        costs
            .as_any()
            .downcast_ref::<Float64Array>()
            .unwrap()
            .values()
            .as_ref(),
        &[0.0, 2.5]
    );
    let edges = batch
        .column_by_name("edgeOrdinals")
        .unwrap()
        .as_any()
        .downcast_ref::<LargeListArray>()
        .unwrap()
        .value(0);
    assert_eq!(
        edges
            .as_any()
            .downcast_ref::<UInt64Array>()
            .unwrap()
            .values()
            .as_ref(),
        &[42]
    );
    assert!(cursor.next_batch().unwrap().is_none());
}

#[test]
fn arrow_ranked_paths_carry_their_rank_and_keep_a_schema_when_empty() {
    let context = context();
    let graph = graph(&context);
    let mut cursor = yens(&graph, "a", "b", YensOptions { k: 3 })
        .unwrap()
        .into_arrow_results();
    let only = cursor.next_batch().unwrap().unwrap();
    let batch = only.record_batch();
    // The shape `shortestPaths` emits, with the rank appended.
    assert_eq!(
        batch
            .schema()
            .fields()
            .iter()
            .map(|field| field.name().clone())
            .collect::<Vec<_>>(),
        vec![
            "sourceNodeId",
            "targetNodeId",
            "totalCost",
            "nodeIds",
            "costs",
            "edgeOrdinals",
            "index"
        ]
    );
    assert_eq!(batch.num_rows(), 1);
    assert!(only.reserved_bytes() >= batch.get_array_memory_size());
    assert_eq!(
        batch
            .column_by_name("index")
            .unwrap()
            .as_any()
            .downcast_ref::<UInt64Array>()
            .unwrap()
            .values()
            .as_ref(),
        &[0]
    );
    let ordinals = batch
        .column_by_name("edgeOrdinals")
        .unwrap()
        .as_any()
        .downcast_ref::<LargeListArray>()
        .unwrap()
        .value(0);
    assert_eq!(
        ordinals
            .as_any()
            .downcast_ref::<UInt64Array>()
            .unwrap()
            .values()
            .as_ref(),
        &[42]
    );
    // One path exists, so the cursor is done after it.
    assert!(cursor.next_batch().unwrap().is_none());

    // No path at all still says what the columns are, in one empty batch.
    let mut cursor = yens(&graph, "b", "a", YensOptions { k: 3 })
        .unwrap()
        .into_arrow_results();
    let empty = cursor.next_batch().unwrap().unwrap();
    assert_eq!(empty.record_batch().num_rows(), 0);
    assert_eq!(empty.record_batch().num_columns(), 7);
    assert!(cursor.next_batch().unwrap().is_none());
}

#[test]
fn arrow_component_ids_convergence_and_terminal_cancellation() {
    let context = context();
    let graph = graph(&context);
    let mut components = weakly_connected_components(&graph)
        .unwrap()
        .into_arrow_results();
    let batch = components.next_batch().unwrap().unwrap();
    let ids = batch
        .record_batch()
        .column_by_name("componentId")
        .unwrap()
        .as_any()
        .downcast_ref::<StringArray>()
        .unwrap();
    assert_eq!(ids.iter().collect::<Vec<_>>(), vec![Some("a"), Some("a")]);
    let mut rank = pagerank(&graph, PageRankOptions::default())
        .unwrap()
        .into_arrow_results();
    let batch = rank.next_batch().unwrap().unwrap();
    assert!(batch.record_batch().column_by_name("converged").is_some());
    context.cancel().unwrap();
    assert!(matches!(rank.next_batch(), Err(AlgorithmError::Cancelled)));
    assert!(matches!(
        rank.next_batch(),
        Err(AlgorithmError::CursorFailed)
    ));
}

#[test]
fn arrow_order_and_cycle_contracts_keep_external_ids() {
    let context = context();
    let graph = graph(&context);
    let mut discovery = grust_algorithms::depth_first(&graph, "a")
        .unwrap()
        .into_arrow_results();
    let batch = discovery.next_batch().unwrap().unwrap();
    let ids = batch
        .record_batch()
        .column_by_name("nodeId")
        .unwrap()
        .as_any()
        .downcast_ref::<StringArray>()
        .unwrap();
    assert_eq!(ids.iter().collect::<Vec<_>>(), vec![Some("a"), Some("b")]);
    let visits = batch
        .record_batch()
        .column_by_name("visitIndex")
        .unwrap()
        .as_any()
        .downcast_ref::<UInt64Array>()
        .unwrap();
    assert_eq!(visits.values().as_ref(), &[0, 1]);
    assert!(discovery.next_batch().unwrap().is_none());
    let mut topology = grust_algorithms::topological_sort(&graph)
        .unwrap()
        .into_arrow_results();
    let batch = topology.next_batch().unwrap().unwrap();
    let status = batch
        .record_batch()
        .column_by_name("acyclic")
        .unwrap()
        .as_any()
        .downcast_ref::<arrow_array::BooleanArray>()
        .unwrap();
    assert!(status.value(0));
    let nodes = batch
        .record_batch()
        .column_by_name("nodeIds")
        .unwrap()
        .as_any()
        .downcast_ref::<LargeListArray>()
        .unwrap()
        .value(0);
    let nodes = nodes.as_any().downcast_ref::<StringArray>().unwrap();
    let nodes: Vec<_> = nodes.iter().map(Option::unwrap).collect();
    assert_eq!(nodes.len(), 3);
    assert!(nodes.iter().position(|&id| id == "a") < nodes.iter().position(|&id| id == "b"));
    let cycle = batch
        .record_batch()
        .column_by_name("cycleNodeIds")
        .unwrap()
        .as_any()
        .downcast_ref::<LargeListArray>()
        .unwrap();
    assert_eq!(cycle.value_length(0), 0);
    assert!(topology.next_batch().unwrap().is_none());
}

#[test]
fn degree_arrow_batches_keep_exact_counts_and_weighted_strengths() {
    let context = context();
    let graph = graph(&context);
    let mut cursor = grust_algorithms::degree(&graph)
        .unwrap()
        .into_arrow_results();
    let mut counts = Vec::new();
    let mut strengths = Vec::new();
    while let Some(batch) = cursor.next_batch().unwrap() {
        assert!(batch.record_batch().num_rows() <= 2);
        let c = batch
            .record_batch()
            .column(1)
            .as_any()
            .downcast_ref::<UInt64Array>()
            .unwrap();
        let w = batch
            .record_batch()
            .column(2)
            .as_any()
            .downcast_ref::<Float64Array>()
            .unwrap();
        counts.extend(c.values().iter().copied());
        strengths.extend(w.values().iter().copied());
    }
    assert_eq!(counts, vec![1, 0, 0]);
    assert_eq!(strengths, vec![2.5, 0.0, 0.0]);
}

#[test]
fn unweighted_degree_arrow_nulls_and_retained_batches_keep_admission() {
    let context = context();
    let graph = GraphProjection::from_topology(
        SnapshotIdentity::new("g".into(), "r1".into(), "reader".into()).unwrap(),
        vec!["a".into(), "isolate".into()],
        vec![ProjectionEdge {
            source: 0,
            target: 0,
            ordinal: 1,
            id: None,
        }],
        None,
        Orientation::Undirected,
        &context,
    )
    .unwrap();
    let retained = context.usage().unwrap().live_bytes;
    let mut cursor = grust_algorithms::degree(&graph)
        .unwrap()
        .into_arrow_results();
    let batch = cursor.next_batch().unwrap().unwrap();
    let counts = batch
        .record_batch()
        .column(1)
        .as_any()
        .downcast_ref::<UInt64Array>()
        .unwrap();
    assert_eq!(counts.values().as_ref(), &[1, 0]);
    assert_eq!(batch.record_batch().column(2).null_count(), 2);
    drop(cursor);
    assert!(context.usage().unwrap().live_bytes > retained);
    drop(batch);
    assert_eq!(context.usage().unwrap().live_bytes, retained);
}
