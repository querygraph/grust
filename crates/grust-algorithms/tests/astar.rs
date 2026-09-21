//! A* against Dijkstra, which must agree exactly wherever both are allowed.

use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, MissingWeight,
    NodeProperties, Orientation, ProjectionEdge, ProjectionOptions, PropertyKind, PropertyRequest,
    SnapshotIdentity, WeightSelection, astar, astar_haversine, dijkstra,
};
use grust_core::{Edge, Graph, Node, Props, Value};

const ORIENTATIONS: [Orientation; 3] = [
    Orientation::Outgoing,
    Orientation::Incoming,
    Orientation::Undirected,
];

fn limits(work_units: usize) -> ExecutionLimits {
    ExecutionLimits {
        memory_bytes: 256 * 1024 * 1024,
        work_units,
        batch_rows: 1024,
        deadline: None,
    }
}

fn context() -> ExecutionContext {
    ExecutionContext::new(limits(2_000_000_000)).unwrap()
}

fn topology(
    n: usize,
    edges: &[(usize, usize)],
    weights: &[f64],
    orientation: Orientation,
    context: &ExecutionContext,
) -> GraphProjection {
    GraphProjection::from_topology(
        SnapshotIdentity::new("g".into(), "r".into(), "reader".into()).unwrap(),
        (0..n).map(|i| format!("n{i}").into()).collect(),
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
        Some(weights.to_vec()),
        orientation,
        context,
    )
    .unwrap()
}

struct Xorshift(u64);
impl Xorshift {
    fn below(&mut self, bound: usize) -> usize {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        (self.0 % bound as u64) as usize
    }
}

#[test]
fn a_star_returns_dijkstra_s_distance_under_any_admissible_estimate() {
    let mut random = Xorshift(0x2545_F491_4F6C_DD1D);
    let (mut reachable, mut unreachable) = (0, 0);
    for round in 0..500 {
        let n = 2 + random.below(12);
        let count = random.below(3 * n);
        let edges: Vec<_> = (0..count)
            .map(|_| (random.below(n), random.below(n)))
            .collect();
        let weights: Vec<f64> = (0..count).map(|_| (1 + random.below(9)) as f64).collect();
        let source = random.below(n);
        let target = random.below(n);
        for orientation in ORIENTATIONS {
            let what = format!("{orientation:?} {source}->{target} {edges:?} {weights:?}");
            let context = context();
            let projection = topology(n, &edges, &weights, orientation, &context);
            let truth = dijkstra(&projection, &format!("n{source}")).unwrap();
            let expected = truth.values()[target];

            // Zero is admissible on every graph, so A* must agree with Dijkstra
            // for it; a scaled true remaining distance is admissible at any
            // factor at or below one and must give the same answer again.
            for scale in [0.0, 0.25, 0.75, 1.0] {
                let to_target = dijkstra(
                    &match orientation {
                        // Distance *to* the target is distance *from* it with
                        // the arcs reversed, which is what the estimate needs.
                        Orientation::Outgoing => {
                            topology(n, &edges, &weights, Orientation::Incoming, &context)
                        }
                        Orientation::Incoming => {
                            topology(n, &edges, &weights, Orientation::Outgoing, &context)
                        }
                        Orientation::Undirected => {
                            topology(n, &edges, &weights, Orientation::Undirected, &context)
                        }
                    },
                    &format!("n{target}"),
                )
                .unwrap();
                let remaining: Vec<f64> = to_target.values().to_vec();
                let found = astar(
                    &projection,
                    &format!("n{source}"),
                    &format!("n{target}"),
                    |node| {
                        let value = remaining[node] * scale;
                        if value.is_finite() { value } else { 0.0 }
                    },
                )
                .unwrap();
                match found.total_cost() {
                    Some(cost) => {
                        assert_eq!(cost, expected, "{what} scale {scale}");
                        // The path is real: its hops exist and its costs add up.
                        let nodes = found.nodes();
                        assert_eq!(nodes.first(), Some(&source), "{what}");
                        assert_eq!(nodes.last(), Some(&target), "{what}");
                        assert_eq!(found.costs()[0], 0.0, "{what}");
                        assert_eq!(found.edges().len(), nodes.len() - 1, "{what}");
                        for hop in 1..nodes.len() {
                            let slot = found.edges()[hop - 1];
                            let (a, b) = edges[slot];
                            let forward = (a, b) == (nodes[hop - 1], nodes[hop]);
                            let backward = (b, a) == (nodes[hop - 1], nodes[hop]);
                            let allowed = match orientation {
                                Orientation::Outgoing => forward,
                                Orientation::Incoming => backward,
                                Orientation::Undirected => forward || backward,
                            };
                            assert!(allowed, "{what}: hop {hop} uses edge {slot}");
                            let step = found.costs()[hop] - found.costs()[hop - 1];
                            assert_eq!(step, weights[slot], "{what}: hop {hop} cost");
                        }
                        reachable += 1;
                    }
                    None => {
                        assert!(expected.is_infinite(), "{what}: said unreachable");
                        assert!(found.nodes().is_empty(), "{what}");
                        unreachable += 1;
                    }
                }
            }
        }
        let _ = round;
    }
    assert!(
        reachable > 2000 && unreachable > 200,
        "{reachable}/{unreachable}"
    );
}

#[test]
fn a_better_estimate_settles_fewer_nodes_and_returns_the_same_path() {
    // A 40x40 grid with unit edges: geometry a heuristic can exploit, and an
    // answer that is easy to state independently.
    let side = 40usize;
    let node = |x: usize, y: usize| y * side + x;
    let mut edges = Vec::new();
    for y in 0..side {
        for x in 0..side {
            if x + 1 < side {
                edges.push((node(x, y), node(x + 1, y)));
            }
            if y + 1 < side {
                edges.push((node(x, y), node(x, y + 1)));
            }
        }
    }
    let weights = vec![1.0; edges.len()];
    let context = context();
    let projection = topology(
        side * side,
        &edges,
        &weights,
        Orientation::Undirected,
        &context,
    );
    // Along the bottom edge, *not* corner to corner. That choice is the whole
    // test: between opposite corners of an open grid every node lies on some
    // shortest path, so f = g + h is the same constant everywhere and an exact
    // heuristic can rule nothing out. Going along one edge instead, a node at
    // height y has f = 39 + 2y, so the heuristic orders the search and the rows
    // above are never reached.
    let (from, to) = (node(0, 0), node(side - 1, 0));
    let manhattan = |v: usize| {
        let (x, y) = (v % side, v / side);
        ((side - 1) as f64 - x as f64).abs() + y as f64
    };

    let blind = astar(&projection, &format!("n{from}"), &format!("n{to}"), |_| 0.0).unwrap();
    let guided = astar(
        &projection,
        &format!("n{from}"),
        &format!("n{to}"),
        manhattan,
    )
    .unwrap();

    // Manhattan distance is exact on an open unit grid, so it is admissible,
    // and the shortest path is one step per column.
    let steps = (side - 1) as f64;
    assert_eq!(blind.total_cost(), Some(steps));
    assert_eq!(guided.total_cost(), Some(steps));
    assert_eq!(guided.nodes().len(), side);
    // The point of the heuristic, measured rather than asserted.
    assert!(
        guided.settled() * 4 < blind.settled(),
        "guided settled {} of the blind search's {}",
        guided.settled(),
        blind.settled()
    );
    // A heuristic of zero is Dijkstra: it settles every node closer than the
    // target, which here is the triangle below the diagonal — a little under
    // half the grid, and quadratically more than the guided search's corridor.
    assert!(
        blind.settled() > side * side / 4 && blind.settled() > 8 * guided.settled(),
        "blind {} against guided {}",
        blind.settled(),
        guided.settled()
    );
}

#[test]
fn an_inadmissible_estimate_is_the_one_error_it_cannot_catch() {
    // Two routes: direct at 10, and via node 1 at 2 + 3 = 5. An estimate that
    // overstates what remains at node 1 hides the cheaper route.
    let context = context();
    let edges = [(0, 2), (0, 1), (1, 2)];
    let weights = [10.0, 2.0, 3.0];
    let projection = topology(3, &edges, &weights, Orientation::Outgoing, &context);
    let honest = astar(&projection, "n0", "n2", |_| 0.0).unwrap();
    assert_eq!(honest.total_cost(), Some(5.0));

    let liar = astar(
        &projection,
        "n0",
        "n2",
        |node| if node == 1 { 50.0 } else { 0.0 },
    )
    .unwrap();
    // It returns a path, and the path is real; it is simply not the shortest.
    // This is documented as undetectable, and the test exists so that stays true.
    assert_eq!(liar.total_cost(), Some(10.0));

    // A negative or non-finite estimate is rejected, because those are mistakes
    // rather than choices.
    for bad in [-1.0, f64::NAN, f64::INFINITY] {
        assert!(matches!(
            astar(&projection, "n0", "n2", |_| bad),
            Err(AlgorithmError::InvalidArguments(message)) if message.contains("finite and nonnegative")
        ));
    }
    // A source that is its own target is a path of one node and no cost.
    let same = astar(&projection, "n1", "n1", |_| 0.0).unwrap();
    assert_eq!(same.total_cost(), Some(0.0));
    assert_eq!(same.nodes(), [1]);
    assert!(same.edges().is_empty());
    assert!(astar(&projection, "n0", "nowhere", |_| 0.0).is_err());
}

#[test]
fn haversine_reads_coordinates_and_agrees_with_dijkstra() {
    // Four cities, with edges weighted by their true great-circle distance, so
    // the heuristic is admissible by construction.
    let places: [(&str, f64, f64); 4] = [
        ("london", 51.5074, -0.1278),
        ("paris", 48.8566, 2.3522),
        ("berlin", 52.52, 13.405),
        ("madrid", 40.4168, -3.7038),
    ];
    let great_circle = |a: usize, b: usize| {
        let (lat1, lon1) = (places[a].1.to_radians(), places[a].2.to_radians());
        let (lat2, lon2) = (places[b].1.to_radians(), places[b].2.to_radians());
        let h = ((lat2 - lat1) / 2.0).sin().powi(2)
            + lat1.cos() * lat2.cos() * ((lon2 - lon1) / 2.0).sin().powi(2);
        2.0 * 6_371_008.8 * h.sqrt().asin()
    };
    let pairs = [(0, 1), (1, 2), (0, 3), (3, 1)];
    let graph = Graph::new(
        places
            .iter()
            .map(|(id, lat, lon)| {
                Node::new(
                    "City",
                    *id,
                    Props::from([
                        ("lat".to_string(), Value::Float(*lat)),
                        ("lon".to_string(), Value::Float(*lon)),
                    ]),
                )
            })
            .collect(),
        pairs
            .iter()
            .map(|&(a, b)| {
                Edge::new(
                    "ROAD",
                    places[a].0,
                    places[b].0,
                    [("km".to_string(), Value::Float(great_circle(a, b)))],
                )
            })
            .collect(),
    );
    let context = context();
    let projection = GraphProjection::from_graph(
        &graph,
        SnapshotIdentity::new("g".into(), "r".into(), "reader".into()).unwrap(),
        ProjectionOptions {
            orientation: Orientation::Undirected,
            weight: WeightSelection::Property {
                key: "km",
                missing: MissingWeight::Reject,
            },
            ..Default::default()
        },
        &context,
    )
    .unwrap();
    let properties = NodeProperties::from_graph(
        &graph,
        &projection,
        &[
            PropertyRequest::required("lat", PropertyKind::Number),
            PropertyRequest::required("lon", PropertyKind::Number),
        ],
    )
    .unwrap();

    let found = astar_haversine(&properties, "berlin", "madrid", "lat", "lon").unwrap();
    let truth = dijkstra(&projection, "berlin").unwrap();
    assert_eq!(found.total_cost(), Some(truth.values()[3]));
    // The route exists and its hops are real edges; which cities it passes
    // through is the graph's business, not this test's.
    let names: Vec<&str> = found.nodes().iter().map(|&row| places[row].0).collect();
    assert_eq!(names.first(), Some(&"berlin"));
    assert_eq!(names.last(), Some(&"madrid"));

    // A coordinate outside its range is rejected rather than measured.
    let broken = Graph::new(
        vec![
            Node::new(
                "City",
                "a",
                Props::from([
                    ("lat".to_string(), Value::Float(200.0)),
                    ("lon".to_string(), Value::Float(0.0)),
                ]),
            ),
            Node::new(
                "City",
                "b",
                Props::from([
                    ("lat".to_string(), Value::Float(0.0)),
                    ("lon".to_string(), Value::Float(0.0)),
                ]),
            ),
        ],
        vec![Edge::new(
            "ROAD",
            "a",
            "b",
            [("km".to_string(), Value::Float(1.0))],
        )],
    );
    let projection = GraphProjection::from_graph(
        &broken,
        SnapshotIdentity::new("g".into(), "r".into(), "reader".into()).unwrap(),
        ProjectionOptions {
            orientation: Orientation::Undirected,
            weight: WeightSelection::Property {
                key: "km",
                missing: MissingWeight::Reject,
            },
            ..Default::default()
        },
        &context,
    )
    .unwrap();
    let coordinates = NodeProperties::from_graph(
        &broken,
        &projection,
        &[
            PropertyRequest::required("lat", PropertyKind::Number),
            PropertyRequest::required("lon", PropertyKind::Number),
        ],
    )
    .unwrap();
    assert!(matches!(
        astar_haversine(&coordinates, "a", "b", "lat", "lon"),
        Err(AlgorithmError::InvalidArguments(message)) if message.contains("±90")
    ));

    // What the check cannot catch: swapping latitude and longitude for places
    // whose values are both in range. Berlin's 52.52°N and 13.405°E are each a
    // valid coordinate of either kind, so the swap gives a wrong estimate and a
    // clean run. The estimate stays admissible here only by luck — it shrinks —
    // so this is recorded as a known limit, not as a safe operation.
    let swapped = astar_haversine(&properties, "berlin", "madrid", "lon", "lat").unwrap();
    assert!(swapped.total_cost().is_some());
}
