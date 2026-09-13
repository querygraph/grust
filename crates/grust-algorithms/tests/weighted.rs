use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, Orientation,
    ProjectionEdge, SnapshotIdentity, dijkstra, shortest_paths,
};
use grust_algorithms::{PageRankOptions, pagerank};
use std::ops::ControlFlow;

fn graph(n: usize, edges: &[(usize, usize, f64)]) -> GraphProjection {
    let context = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 1 << 20,
        work_units: usize::MAX,
        batch_rows: 128,
        deadline: None,
    })
    .unwrap();
    GraphProjection::from_topology(
        SnapshotIdentity::new("g".into(), "v1".into(), "reader".into()).unwrap(),
        (0..n).map(|i| i.to_string().into()).collect(),
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
        Some(edges.iter().map(|edge| edge.2).collect()),
        Orientation::Outgoing,
        &context,
    )
    .unwrap()
}

#[test]
fn weighted_paths_preserve_parallel_edge_identity_and_zero_cycles() {
    let graph = graph(
        6,
        &[
            (0, 1, 10.0),
            (0, 1, 2.0),
            (1, 2, 0.0),
            (2, 1, 0.0),
            (0, 3, 1.0),
            (3, 2, 3.0),
            (2, 4, 0.5),
        ],
    );
    assert_eq!(
        dijkstra(&graph, "0").unwrap().values(),
        &[0.0, 2.0, 2.0, 1.0, 2.5, f64::INFINITY]
    );
    let paths = shortest_paths(&graph, "0").unwrap();
    let mut visited = Vec::new();
    let outcome: ControlFlow<()> = paths
        .visit_paths(|path| {
            visited.push(path.target);
            if path.target == 0 {
                assert_eq!(path.nodes, &[0]);
                assert!(path.edges.is_empty());
            }
            if path.target == 4 {
                assert_eq!(path.nodes, &[0, 1, 2, 4]);
                assert_eq!(path.costs, &[0.0, 2.0, 2.0, 2.5]);
                assert_eq!(path.edges, &[1, 2, 6]);
            }
            Ok(ControlFlow::Continue(()))
        })
        .unwrap();
    assert_eq!(outcome, ControlFlow::Continue(()));
    assert_eq!(visited, vec![0, 1, 2, 3, 4]);
    let before = graph.execution().usage().unwrap().live_bytes;
    assert_eq!(
        paths.visit_paths(|_| Ok(ControlFlow::Break(42))).unwrap(),
        ControlFlow::Break(42)
    );
    assert_eq!(graph.execution().usage().unwrap().live_bytes, before);
}

#[test]
fn overflow_is_not_reported_as_unreachable() {
    let graph = graph(3, &[(0, 1, f64::MAX), (1, 2, f64::MAX)]);
    assert!(matches!(
        dijkstra(&graph, "0"),
        Err(AlgorithmError::Numerical(_))
    ));
}

#[test]
fn pull_paths_pin_projection_and_release_storage_on_completion_or_failure() {
    let graph = graph(3, &[(0, 1, 1.0), (1, 2, 2.0)]);
    let execution = graph.execution().clone();
    let mut cursor = shortest_paths(&graph, "0").unwrap().into_cursor().unwrap();
    drop(graph);
    assert_eq!(cursor.next_path().unwrap().unwrap().nodes, &[0]);
    assert_eq!(cursor.next_path().unwrap().unwrap().costs, &[0.0, 1.0]);
    assert_eq!(cursor.next_path().unwrap().unwrap().edges, &[0, 1]);
    assert!(cursor.next_path().unwrap().is_none());
    assert_eq!(execution.usage().unwrap().live_bytes, 0);
    let graph = self::graph(2, &[(0, 1, 1.0)]);
    let execution = graph.execution().clone();
    let mut cursor = shortest_paths(&graph, "0").unwrap().into_cursor().unwrap();
    drop(graph);
    execution.cancel().unwrap();
    assert!(matches!(cursor.next_path(), Err(AlgorithmError::Cancelled)));
    assert_eq!(execution.usage().unwrap().live_bytes, 0);
    assert!(matches!(
        cursor.next_path(),
        Err(AlgorithmError::CursorFailed)
    ));
}

#[test]
fn many_decreases_match_independent_bellman_ford() {
    let n = 37;
    let mut seed = 19u64;
    let mut edges = Vec::new();
    for source in 0..n {
        for target in 0..n {
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
            if seed % 7 < 2 {
                edges.push((source, target, ((seed >> 32) % 100) as f64 / 4.0));
            }
        }
    }
    let graph = graph(n, &edges);
    for source in 0..n {
        let mut expected = vec![f64::INFINITY; n];
        expected[source] = 0.0;
        for _ in 1..n {
            let mut changed = false;
            for &(from, to, weight) in &edges {
                let candidate = expected[from] + weight;
                if candidate < expected[to] {
                    expected[to] = candidate;
                    changed = true;
                }
            }
            if !changed {
                break;
            }
        }
        assert_eq!(
            dijkstra(&graph, &source.to_string()).unwrap().values(),
            expected
        );
    }
}

#[test]
fn pagerank_handles_dangling_personalization_and_large_weights() {
    let graph = graph(3, &[(0, 1, f64::MAX), (0, 1, f64::MAX), (1, 0, 0.0)]);
    let rank = pagerank(&graph, PageRankOptions::default()).unwrap();
    assert!(rank.converged());
    assert!((rank.values().iter().sum::<f64>() - 1.0).abs() < 1e-12);
    assert!((rank.values()[0] - rank.values()[2]).abs() < 1e-12);
    assert!((rank.values()[1] - 1.85 / 3.85).abs() < 1e-8);
    let rank = pagerank(
        &graph,
        PageRankOptions {
            damping: 0.0,
            personalization: Some(&[f64::MAX, 0.0, f64::MAX]),
            ..Default::default()
        },
    )
    .unwrap();
    assert_eq!(rank.values(), &[0.5, 0.0, 0.5]);
    let rank = pagerank(
        &graph,
        PageRankOptions {
            max_iterations: 1,
            tolerance: 0.0,
            ..Default::default()
        },
    )
    .unwrap();
    assert!(!rank.converged());
    assert_eq!(rank.iterations(), 1);
}

#[test]
fn pagerank_rejects_invalid_configuration_and_accepts_empty_graph() {
    let graph = graph(0, &[]);
    let rank = pagerank(&graph, PageRankOptions::default()).unwrap();
    assert!(rank.values().is_empty());
    assert!(rank.converged());
    for damping in [f64::NAN, f64::INFINITY, -0.1, 1.0] {
        assert!(matches!(
            pagerank(
                &graph,
                PageRankOptions {
                    damping,
                    ..Default::default()
                }
            ),
            Err(AlgorithmError::InvalidArguments(_))
        ));
    }
}
