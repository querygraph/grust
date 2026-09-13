//! Exhaustive small directed graphs compared with a matrix closure, independent
//! of adjacency traversal, union-find and the SCC implementation.
use grust_algorithms::*;

#[test]
fn all_three_vertex_topologies_match_matrix_oracles() {
    const N: usize = 3;
    for bits in 0u16..(1 << (N * N)) {
        for orientation in [
            Orientation::Outgoing,
            Orientation::Incoming,
            Orientation::Undirected,
        ] {
            let context = ExecutionContext::new(ExecutionLimits {
                memory_bytes: 64 * 1024,
                work_units: usize::MAX,
                batch_rows: 1,
                deadline: None,
            })
            .unwrap();
            let edges: Vec<_> = (0..N * N)
                .filter(|bit| bits & (1 << bit) != 0)
                .map(|bit| ProjectionEdge {
                    source: bit / N,
                    target: bit % N,
                    ordinal: bit,
                    id: None,
                })
                .collect();
            let mut distance = [[f64::INFINITY; N]; N];
            let mut weak = [[false; N]; N];
            for i in 0..N {
                distance[i][i] = 0.0;
                weak[i][i] = true;
            }
            for edge in &edges {
                let (a, b) = match orientation {
                    Orientation::Incoming => (edge.target, edge.source),
                    _ => (edge.source, edge.target),
                };
                distance[a][b] = distance[a][b].min(1.0);
                if orientation == Orientation::Undirected {
                    distance[b][a] = distance[b][a].min(1.0);
                }
                weak[a][b] = true;
                weak[b][a] = true;
            }
            for k in 0..N {
                for i in 0..N {
                    for j in 0..N {
                        distance[i][j] = distance[i][j].min(distance[i][k] + distance[k][j]);
                        weak[i][j] |= weak[i][k] && weak[k][j];
                    }
                }
            }
            let graph = GraphProjection::from_topology(
                SnapshotIdentity::new("oracle".into(), bits.to_string(), "test".into()).unwrap(),
                (0..N).map(|n| n.to_string().into()).collect(),
                edges,
                None,
                orientation,
                &context,
            )
            .unwrap();
            for (source, expected) in distance.iter().enumerate() {
                assert_eq!(bfs(&graph, &source.to_string()).unwrap().values(), expected);
            }
            let expected_scc: Vec<_> = (0..N)
                .map(|i| {
                    (0..N)
                        .find(|&j| distance[i][j].is_finite() && distance[j][i].is_finite())
                        .unwrap()
                })
                .collect();
            let expected_wcc: Vec<_> = (0..N)
                .map(|i| (0..N).find(|&j| weak[i][j]).unwrap())
                .collect();
            assert_eq!(
                strongly_connected_components(&graph).unwrap().values(),
                expected_scc
            );
            assert_eq!(
                weakly_connected_components(&graph).unwrap().values(),
                expected_wcc
            );
            drop(graph);
            assert_eq!(context.usage().unwrap().live_bytes, 0);
        }
    }
}
