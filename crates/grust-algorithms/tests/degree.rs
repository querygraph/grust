use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, Orientation,
    ProjectionEdge, SnapshotIdentity, degree,
};

fn context() -> ExecutionContext {
    ExecutionContext::new(ExecutionLimits {
        memory_bytes: 1 << 20,
        work_units: usize::MAX,
        batch_rows: 2,
        deadline: None,
    })
    .unwrap()
}

fn graph(
    edges: &[(usize, usize, f64)],
    orientation: Orientation,
    weighted: bool,
    context: &ExecutionContext,
) -> GraphProjection {
    GraphProjection::from_topology(
        SnapshotIdentity::new("g".into(), "r1".into(), "reader".into()).unwrap(),
        vec!["a".into(), "b".into(), "isolate".into()],
        edges
            .iter()
            .enumerate()
            .map(|(ordinal, &(source, target, _))| ProjectionEdge {
                source,
                target,
                ordinal,
                id: Some("repeated-id".into()),
            })
            .collect(),
        weighted.then(|| edges.iter().map(|e| e.2).collect()),
        orientation,
        context,
    )
    .unwrap()
}

#[test]
fn exhaustive_two_node_multigraphs_match_original_edge_oracle() {
    for encoding in 0..81usize {
        let mut remaining = encoding;
        let mut edges = Vec::new();
        for source in 0..2 {
            for target in 0..2 {
                for copy in 0..remaining % 3 {
                    edges.push((source, target, copy as f64));
                }
                remaining /= 3;
            }
        }
        for orientation in [
            Orientation::Outgoing,
            Orientation::Incoming,
            Orientation::Undirected,
        ] {
            let mut counts = [0usize; 3];
            let mut strengths = [0.0; 3];
            // Independent original-edge enumeration, including loops only once.
            for &(source, target, weight) in &edges {
                for node in 0..3 {
                    let incident = match orientation {
                        Orientation::Outgoing => source == node,
                        Orientation::Incoming => target == node,
                        Orientation::Undirected => source == node || target == node,
                    };
                    if incident {
                        counts[node] += 1;
                        strengths[node] += weight;
                    }
                }
            }
            for weighted in [false, true] {
                let context = context();
                let graph = graph(&edges, orientation, weighted, &context);
                let retained = context.usage().unwrap().live_bytes;
                let result = degree(&graph).unwrap();
                assert_eq!(result.counts(), counts);
                assert_eq!(result.strengths(), weighted.then_some(strengths.as_slice()));
                assert_eq!(result.projection().identity(), graph.identity());
                assert!(context.usage().unwrap().live_bytes > retained);
                drop(result);
                assert_eq!(context.usage().unwrap().live_bytes, retained);
            }
        }
    }
}

#[test]
fn strength_overflow_and_cancellation_release_result_admission() {
    let context = context();
    let graph = graph(
        &[(0, 1, f64::MAX), (0, 1, f64::MAX)],
        Orientation::Outgoing,
        true,
        &context,
    );
    let retained = context.usage().unwrap().live_bytes;
    assert!(matches!(degree(&graph), Err(AlgorithmError::Numerical(_))));
    assert_eq!(context.usage().unwrap().live_bytes, retained);
    context.cancel().unwrap();
    assert!(matches!(degree(&graph), Err(AlgorithmError::Cancelled)));
    assert_eq!(context.usage().unwrap().live_bytes, retained);
}

#[test]
fn empty_projection_preserves_weight_presence_without_rows() {
    for weights in [None, Some(Vec::new())] {
        let weighted = weights.is_some();
        let context = context();
        let graph = GraphProjection::from_topology(
            SnapshotIdentity::new("g".into(), "r1".into(), "reader".into()).unwrap(),
            Vec::new(),
            Vec::new(),
            weights,
            Orientation::Outgoing,
            &context,
        )
        .unwrap();
        let result = degree(&graph).unwrap();
        assert!(result.counts().is_empty());
        assert_eq!(result.strengths(), weighted.then_some([].as_slice()));
    }
}

#[test]
fn result_allocation_obeys_the_shared_memory_envelope() {
    let context = context();
    let graph = graph(&[(0, 1, 1.0)], Orientation::Outgoing, false, &context);
    let retained = context.usage().unwrap().live_bytes;
    let held = context
        .reserve(context.limits().memory_bytes - retained)
        .unwrap();
    assert!(matches!(
        degree(&graph),
        Err(AlgorithmError::BudgetExceeded {
            resource: "memory",
            ..
        })
    ));
    assert_eq!(
        context.usage().unwrap().live_bytes,
        context.limits().memory_bytes
    );
    drop(held);
    assert_eq!(context.usage().unwrap().live_bytes, retained);
}

#[test]
fn chunk_boundaries_preserve_arc_counts_and_exact_successful_work_charges() {
    let context = context();
    let edges = (0..2051).map(|i| (i % 2, 1, 1.0)).collect::<Vec<_>>();
    let graph = graph(&edges, Orientation::Outgoing, true, &context);
    let before = context.usage().unwrap();
    let result = degree(&graph).unwrap();
    assert_eq!(result.counts(), &[1026, 1025, 0]);
    assert_eq!(result.strengths(), Some([1026.0, 1025.0, 0.0].as_slice()));
    assert_eq!(
        context.usage().unwrap().counted_work().expect("counted")
            - before.counted_work().expect("counted"),
        2054
    );
    drop(result);
    let used = context.usage().unwrap().counted_work().expect("counted");
    context
        .charge_work(context.limits().work_units - used - 10)
        .unwrap();
    assert!(matches!(
        degree(&graph),
        Err(AlgorithmError::BudgetExceeded {
            resource: "work",
            ..
        })
    ));
    assert_eq!(context.usage().unwrap().live_bytes, before.live_bytes);
}

#[test]
fn node_chunks_preserve_large_isolate_sets() {
    let context = context();
    let graph = GraphProjection::from_topology(
        SnapshotIdentity::new("g".into(), "r1".into(), "reader".into()).unwrap(),
        (0..2049).map(|id| id.to_string().into()).collect(),
        Vec::new(),
        None,
        Orientation::Outgoing,
        &context,
    )
    .unwrap();
    let before = context.usage().unwrap().counted_work().expect("counted");
    let result = degree(&graph).unwrap();
    assert_eq!(result.counts(), vec![0; 2049]);
    assert_eq!(
        context.usage().unwrap().counted_work().expect("counted") - before,
        2049
    );
}
