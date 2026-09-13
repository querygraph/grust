use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, Orientation,
    ProjectionEdge, SnapshotIdentity, bfs, strongly_connected_components,
    weakly_connected_components,
};
use grust_algorithms::{TopologicalOrder, depth_first, multi_source_bfs, topological_sort};

fn context() -> ExecutionContext {
    ExecutionContext::new(ExecutionLimits {
        memory_bytes: 32 * 1024 * 1024,
        work_units: usize::MAX,
        batch_rows: 128,
        deadline: None,
    })
    .unwrap()
}

fn graph(
    n: usize,
    edges: &[(usize, usize)],
    orientation: Orientation,
    ctx: &ExecutionContext,
) -> GraphProjection {
    GraphProjection::from_topology(
        SnapshotIdentity::new("test".into(), "1".into(), "reader".into()).unwrap(),
        (0..n).map(|i| i.to_string().into()).collect(),
        edges
            .iter()
            .enumerate()
            .map(|(ordinal, &(source, target))| ProjectionEdge {
                source,
                target,
                ordinal,
                id: None,
            })
            .collect(),
        None,
        orientation,
        ctx,
    )
    .unwrap()
}

#[test]
fn directed_bfs_keeps_isolates_and_parallel_edges() {
    let ctx = context();
    let graph = graph(
        6,
        &[(0, 1), (0, 1), (1, 2), (2, 0), (2, 3), (4, 4)],
        Orientation::Outgoing,
        &ctx,
    );
    let distances = bfs(&graph, "0").unwrap();
    assert_eq!(
        distances.values(),
        &[0.0, 1.0, 2.0, 3.0, f64::INFINITY, f64::INFINITY]
    );
    assert!(matches!(
        bfs(&graph, "missing"),
        Err(AlgorithmError::InvalidArguments(_))
    ));
    let retained = ctx.usage().unwrap().live_bytes;
    drop(distances);
    assert!(ctx.usage().unwrap().live_bytes < retained);
    drop(graph);
    assert_eq!(ctx.usage().unwrap().live_bytes, 0);
}

#[test]
fn traversal_orientation_is_explicit() {
    for (orientation, expected) in [
        (
            Orientation::Outgoing,
            vec![f64::INFINITY, f64::INFINITY, 0.0],
        ),
        (Orientation::Incoming, vec![2.0, 1.0, 0.0]),
        (Orientation::Undirected, vec![2.0, 1.0, 0.0]),
    ] {
        let ctx = context();
        let graph = graph(3, &[(0, 1), (1, 2)], orientation, &ctx);
        assert_eq!(bfs(&graph, "2").unwrap().values(), expected);
    }
}

#[test]
fn components_are_canonical_minimum_node_rows() {
    let ctx = context();
    let graph = graph(
        7,
        &[(0, 1), (1, 0), (1, 2), (2, 3), (3, 2), (4, 4), (6, 5)],
        Orientation::Outgoing,
        &ctx,
    );
    assert_eq!(
        weakly_connected_components(&graph).unwrap().values(),
        &[0, 0, 0, 0, 4, 5, 5]
    );
    assert_eq!(
        strongly_connected_components(&graph).unwrap().values(),
        &[0, 0, 2, 2, 4, 5, 6]
    );
}

#[test]
fn empty_components_and_long_iterative_chain() {
    let ctx = context();
    let empty = graph(0, &[], Orientation::Outgoing, &ctx);
    assert!(
        weakly_connected_components(&empty)
            .unwrap()
            .values()
            .is_empty()
    );
    assert!(
        strongly_connected_components(&empty)
            .unwrap()
            .values()
            .is_empty()
    );
    let n = 65_536;
    let edges: Vec<_> = (1..n).map(|i| (i - 1, i)).collect();
    let chain = graph(n, &edges, Orientation::Outgoing, &ctx);
    let components = strongly_connected_components(&chain).unwrap();
    assert!(components.values().iter().copied().eq(0..n));
    assert_eq!(bfs(&chain, "0").unwrap().values()[n - 1], (n - 1) as f64);
}

#[test]
fn cancelled_kernel_releases_scratch() {
    let ctx = context();
    let graph = graph(3, &[(0, 1)], Orientation::Outgoing, &ctx);
    let retained = ctx.usage().unwrap().live_bytes;
    ctx.cancel().unwrap();
    assert!(matches!(bfs(&graph, "0"), Err(AlgorithmError::Cancelled)));
    assert_eq!(ctx.usage().unwrap().live_bytes, retained);
}

#[test]
fn additional_traversals_reuse_projection_and_report_concrete_cycles() {
    let ctx = context();
    let graph = graph(
        6,
        &[(0, 1), (0, 2), (1, 3), (2, 3), (4, 3)],
        Orientation::Outgoing,
        &ctx,
    );
    assert_eq!(depth_first(&graph, "0").unwrap().values(), &[0, 1, 3, 2]);
    assert_eq!(
        multi_source_bfs(&graph, &["0".into(), "4".into(), "0".into()])
            .unwrap()
            .values(),
        &[0.0, 1.0, 1.0, 1.0, 0.0, f64::INFINITY]
    );
    assert!(multi_source_bfs(&graph, &[]).is_err());
    let TopologicalOrder::Acyclic(order) = topological_sort(&graph).unwrap() else {
        panic!("acyclic fixture");
    };
    let mut positions = vec![0; graph.node_count()];
    for (position, &node) in order.values().iter().enumerate() {
        positions[node] = position;
    }
    for edge in graph.edges() {
        assert!(positions[edge.source] < positions[edge.target]);
    }
    let cyclic = self::graph(
        4,
        &[(0, 1), (1, 2), (2, 1), (2, 3)],
        Orientation::Outgoing,
        &ctx,
    );
    let TopologicalOrder::Cycle(cycle) = topological_sort(&cyclic).unwrap() else {
        panic!("cyclic fixture");
    };
    assert_eq!(cycle.values().first(), cycle.values().last());
    for pair in cycle.values().windows(2) {
        assert!(
            cyclic
                .edges()
                .iter()
                .any(|edge| edge.source == pair[0] && edge.target == pair[1])
        );
    }
}
