//! Yen's k shortest loopless paths against exhaustive enumeration.
//!
//! The oracle here shares nothing with the kernel: it enumerates every simple
//! path by brute force from the edge list the test wrote, ranks them by the
//! documented order, and takes the first k. It does not call `dijkstra`, it
//! does not read the projection, and it does not know what a spur is. That is
//! deliberate — an oracle grown from the kernel has twice in this repository
//! agreed with the kernel's own mistake.

use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, Orientation,
    ProjectionEdge, SnapshotIdentity, YensOptions, yens,
};

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

/// One enumerated path: its node rows and its total cost.
type Found = (Vec<usize>, f64);

/// Every simple path from `source` to `target`, by exhaustive depth-first
/// enumeration over an adjacency matrix of cheapest hop costs, ranked as the
/// kernel documents: total cost first, then the node rows lexicographically.
///
/// A hop's cost is the cheapest edge joining its two nodes, because a path is a
/// node sequence and parallel edges collapse. Costs are summed from the source
/// in path order, as the kernel sums them, so equality is exact.
fn all_simple_paths(
    n: usize,
    edges: &[(usize, usize)],
    weights: &[f64],
    orientation: Orientation,
    source: usize,
    target: usize,
) -> Vec<Found> {
    let mut hop = vec![vec![f64::INFINITY; n]; n];
    for (slot, &(a, b)) in edges.iter().enumerate() {
        let (from, to) = match orientation {
            Orientation::Outgoing | Orientation::Undirected => (a, b),
            Orientation::Incoming => (b, a),
        };
        hop[from][to] = hop[from][to].min(weights[slot]);
        if orientation == Orientation::Undirected {
            hop[to][from] = hop[to][from].min(weights[slot]);
        }
    }
    let mut found = Vec::new();
    let mut path = vec![source];
    let mut used = vec![false; n];
    used[source] = true;
    walk(&hop, &mut path, &mut used, 0.0, target, &mut found);
    // The documented order, applied by the oracle's own comparison.
    found.sort_by(|(left, left_cost), (right, right_cost)| {
        left_cost
            .total_cmp(right_cost)
            .then_with(|| left.cmp(right))
    });
    found
}

fn walk(
    hop: &[Vec<f64>],
    path: &mut Vec<usize>,
    used: &mut Vec<bool>,
    cost: f64,
    target: usize,
    found: &mut Vec<Found>,
) {
    let node = *path.last().unwrap();
    if node == target {
        found.push((path.clone(), cost));
        // A path ends at the target: continuing would revisit it.
        return;
    }
    for next in 0..used.len() {
        if used[next] || !hop[node][next].is_finite() {
            continue;
        }
        used[next] = true;
        path.push(next);
        walk(hop, path, used, cost + hop[node][next], target, found);
        path.pop();
        used[next] = false;
    }
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

/// The nodes, costs and edges of every path a result holds.
fn rows(paths: &grust_algorithms::KShortestPaths) -> Vec<(Vec<usize>, Vec<f64>, Vec<usize>)> {
    (0..paths.len())
        .map(|index| {
            let path = paths.path(index).unwrap();
            (
                path.nodes.to_vec(),
                path.costs.to_vec(),
                path.edges.to_vec(),
            )
        })
        .collect()
}

#[test]
fn yens_matches_an_independent_oracle() {
    let mut random = Xorshift(0x9E37_79B9_7F4A_7C15);
    let (mut full, mut short, mut none) = (0, 0, 0);
    for _ in 0..600 {
        // n <= 8, as the catalog's Tier B row asks: exhaustive enumeration of
        // simple paths is factorial, and eight is where it stays a test rather
        // than a benchmark.
        let n = 2 + random.below(7);
        let count = random.below(3 * n);
        let edges: Vec<(usize, usize)> = (0..count)
            .map(|_| (random.below(n), random.below(n)))
            .collect();
        // Small integers, so every sum is exact and a tie is a real tie rather
        // than a rounding accident. Zero weights are included on purpose: they
        // are what makes the lexicographic tie-break hard to reach.
        let weights: Vec<f64> = (0..count).map(|_| random.below(4) as f64).collect();
        let source = random.below(n);
        let target = random.below(n);
        for orientation in ORIENTATIONS {
            let what = format!("{orientation:?} {source}->{target} {edges:?} {weights:?}");
            let expected = all_simple_paths(n, &edges, &weights, orientation, source, target);
            for k in [1usize, 2, 3, 8] {
                let context = context();
                let projection = topology(n, &edges, &weights, orientation, &context);
                let found = yens(
                    &projection,
                    &format!("n{source}"),
                    &format!("n{target}"),
                    YensOptions { k },
                )
                .unwrap();
                let wanted = expected.len().min(k);
                assert_eq!(found.len(), wanted, "{what} k={k}");
                if wanted == 0 {
                    none += 1;
                } else if wanted < k {
                    short += 1;
                } else {
                    full += 1;
                }
                for (index, (nodes, costs, hops)) in rows(&found).into_iter().enumerate() {
                    let (ref want_nodes, want_cost) = expected[index];
                    // Identity, not merely cost: the tie-break is a contract.
                    assert_eq!(&nodes, want_nodes, "{what} k={k} rank {index}");
                    assert_eq!(
                        costs.last().copied(),
                        Some(want_cost),
                        "{what} rank {index}"
                    );
                    assert_eq!(costs[0], 0.0, "{what}");
                    assert_eq!(hops.len(), nodes.len() - 1, "{what}");
                    // Every hop is a real edge of the projection, and the
                    // cumulative costs add its weight.
                    for step in 1..nodes.len() {
                        let slot = hops[step - 1];
                        let (a, b) = edges[slot];
                        let forward = (a, b) == (nodes[step - 1], nodes[step]);
                        let backward = (b, a) == (nodes[step - 1], nodes[step]);
                        assert!(
                            match orientation {
                                Orientation::Outgoing => forward,
                                Orientation::Incoming => backward,
                                Orientation::Undirected => forward || backward,
                            },
                            "{what}: hop {step} uses edge {slot}"
                        );
                        assert_eq!(
                            costs[step] - costs[step - 1],
                            weights[slot],
                            "{what}: hop {step} cost"
                        );
                    }
                }
            }
        }
    }
    // The three outcomes the kernel has to get right are all exercised.
    assert!(
        full > 500 && short > 500 && none > 200,
        "{full}/{short}/{none}"
    );
}

#[test]
fn yens_returns_the_classic_hand_computed_example() {
    // Yen's own shape: two ways out of the source, a crossing between them, and
    // a common tail. Nodes 0=C 1=D 2=E 3=F 4=G 5=H, arcs written as
    // C->D 3, C->E 2, D->F 4, E->D 1, E->F 2, D->G 4, F->G 2, G->H 1.
    //
    // Every simple path from C to H, summed by hand:
    //   C E F G H   2+2+2+1 =  7
    //   C D G H     3+4+1   =  8
    //   C E D G H   2+1+4+1 =  8
    //   C D F G H   3+4+2+1 = 10
    //   C E D F G H 2+1+4+2+1 = 10
    // The two pairs tie, and within each pair the node rows decide: D (row 1)
    // before E (row 2).
    let edges = [
        (0, 1),
        (0, 2),
        (1, 3),
        (2, 1),
        (2, 3),
        (1, 4),
        (3, 4),
        (4, 5),
    ];
    let weights = [3.0, 2.0, 4.0, 1.0, 2.0, 4.0, 2.0, 1.0];
    let context = context();
    let projection = topology(6, &edges, &weights, Orientation::Outgoing, &context);
    let found = yens(&projection, "n0", "n5", YensOptions { k: 3 }).unwrap();
    assert_eq!(found.len(), 3);
    assert_eq!(found.path(0).unwrap().nodes, [0, 2, 3, 4, 5]);
    assert_eq!(found.total_cost(0), Some(7.0));
    assert_eq!(found.path(1).unwrap().nodes, [0, 1, 4, 5]);
    assert_eq!(found.total_cost(1), Some(8.0));
    assert_eq!(found.path(2).unwrap().nodes, [0, 2, 1, 4, 5]);
    assert_eq!(found.total_cost(2), Some(8.0));
    // Asking for more than exists returns what exists, in the same order, and
    // the exhaustive enumeration above is the whole answer.
    let every = yens(&projection, "n0", "n5", YensOptions { k: 50 }).unwrap();
    assert_eq!(every.len(), 5);
    assert_eq!(every.path(3).unwrap().nodes, [0, 1, 3, 4, 5]);
    assert_eq!(every.total_cost(3), Some(10.0));
    assert_eq!(every.path(4).unwrap().nodes, [0, 2, 1, 3, 4, 5]);
    assert_eq!(every.total_cost(4), Some(10.0));
    let all = all_simple_paths(6, &edges, &weights, Orientation::Outgoing, 0, 5);
    assert_eq!(all.len(), 5);
    for (index, (nodes, cost)) in all.iter().enumerate() {
        assert_eq!(every.path(index).unwrap().nodes, nodes.as_slice());
        assert_eq!(every.total_cost(index), Some(*cost));
    }
}

#[test]
fn yens_states_its_tie_break_and_holds_to_it() {
    // Four routes of cost 2 from 0 to 3, laid out so that the node sequences
    // order differently from the edge ordinals: the deviation nodes are 2, 1,
    // 4 in edge order, so a kernel that ranked by discovery would differ here.
    let edges = [(0, 2), (2, 3), (0, 1), (1, 3), (0, 4), (4, 3), (0, 3)];
    let weights = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 2.0];
    let context = context();
    let projection = topology(5, &edges, &weights, Orientation::Outgoing, &context);
    let found = yens(&projection, "n0", "n3", YensOptions { k: 4 }).unwrap();
    assert_eq!(found.len(), 4);
    // Every cost is 2, so the ranking is the documented lexicographic one:
    // [0,1,3] < [0,2,3] < [0,3] < [0,4,3]. A shorter path is not preferred:
    // [0,3] sits third because 3 > 2 at the second node.
    let sequences: Vec<Vec<usize>> = rows(&found).into_iter().map(|(n, _, _)| n).collect();
    assert_eq!(
        sequences,
        vec![vec![0, 1, 3], vec![0, 2, 3], vec![0, 3], vec![0, 4, 3]]
    );
    for index in 0..4 {
        assert_eq!(found.total_cost(index), Some(2.0));
    }
    // Repeating the run gives the same answer, byte for byte.
    let again = yens(&projection, "n0", "n3", YensOptions { k: 4 }).unwrap();
    assert_eq!(rows(&found), rows(&again));
}

#[test]
fn yens_handles_a_single_edge_the_same_node_twice_and_no_path_at_all() {
    let context = context();
    let single = topology(2, &[(0, 1)], &[2.5], Orientation::Outgoing, &context);
    let found = yens(&single, "n0", "n1", YensOptions { k: 5 }).unwrap();
    assert_eq!(found.len(), 1);
    assert_eq!(found.path(0).unwrap().nodes, [0, 1]);
    assert_eq!(found.path(0).unwrap().costs, [0.0, 2.5]);
    assert_eq!(found.path(0).unwrap().edges, [0]);
    assert_eq!(found.endpoints(), (0, 1));

    // Source and target the same: the zero-hop path, once, whatever k says.
    // There is no second loopless path from a node to itself.
    let same = yens(&single, "n0", "n0", YensOptions { k: 5 }).unwrap();
    assert_eq!(same.len(), 1);
    assert_eq!(same.path(0).unwrap().nodes, [0]);
    assert_eq!(same.path(0).unwrap().costs, [0.0]);
    assert!(same.path(0).unwrap().edges.is_empty());
    assert_eq!(same.total_cost(0), Some(0.0));

    // The wrong way down a directed edge is no path, which is a result.
    let nothing = yens(&single, "n1", "n0", YensOptions { k: 5 }).unwrap();
    assert!(nothing.is_empty() && nothing.path(0).is_none());

    // An isolate reaches nothing, in either direction.
    let with_isolate = topology(3, &[(0, 1)], &[1.0], Orientation::Undirected, &context);
    assert!(
        yens(&with_isolate, "n0", "n2", YensOptions { k: 3 })
            .unwrap()
            .is_empty()
    );
    assert!(
        yens(&with_isolate, "n2", "n0", YensOptions { k: 3 })
            .unwrap()
            .is_empty()
    );
}

#[test]
fn yens_states_multigraph_and_self_loop_semantics() {
    // Two parallel edges 0->1 of cost 5 and 1, a self-loop on 1, and one hop on
    // to 2. A path is a node sequence: [0,1,2] is one path, reported with the
    // cheaper of the parallel edges, and the self-loop cannot appear in it.
    let edges = [(0, 1), (0, 1), (1, 1), (1, 2)];
    let weights = [5.0, 1.0, 0.0, 1.0];
    let context = context();
    let projection = topology(3, &edges, &weights, Orientation::Outgoing, &context);
    let found = yens(&projection, "n0", "n2", YensOptions { k: 5 }).unwrap();
    assert_eq!(found.len(), 1);
    assert_eq!(found.path(0).unwrap().nodes, [0, 1, 2]);
    // Edge slot 1, the cheap parallel edge, not slot 0.
    assert_eq!(found.path(0).unwrap().edges, [1, 3]);
    assert_eq!(found.total_cost(0), Some(2.0));

    // Undirected projections walk each edge either way; the answer is the same
    // path here, and the oracle agrees for both orientations.
    for orientation in [Orientation::Outgoing, Orientation::Undirected] {
        let projection = topology(3, &edges, &weights, orientation, &context);
        let found = yens(&projection, "n0", "n2", YensOptions { k: 5 }).unwrap();
        let expected = all_simple_paths(3, &edges, &weights, orientation, 0, 2);
        assert_eq!(found.len(), expected.len(), "{orientation:?}");
        for (index, (nodes, cost)) in expected.iter().enumerate() {
            assert_eq!(found.path(index).unwrap().nodes, nodes.as_slice());
            assert_eq!(found.total_cost(index), Some(*cost));
        }
    }
}

#[test]
fn yens_walks_zero_weight_ties_without_leaving_the_shortest_paths() {
    // Zero-weight arcs make the set of minimum-cost paths a graph with cycles
    // in it, which is exactly where a greedy lexicographic walk can wander into
    // a dead end. 0->1 and 1->0 cost nothing, both reach 2 at cost 5, and the
    // lexicographically smallest minimum-cost path from 0 is [0,1,2] only if
    // 1 can still finish; the kernel checks that rather than assuming it.
    let edges = [(0, 1), (1, 0), (0, 2), (1, 2)];
    let weights = [0.0, 0.0, 5.0, 5.0];
    let context = context();
    let projection = topology(3, &edges, &weights, Orientation::Outgoing, &context);
    let found = yens(&projection, "n0", "n2", YensOptions { k: 4 }).unwrap();
    let expected = all_simple_paths(3, &edges, &weights, Orientation::Outgoing, 0, 2);
    assert_eq!(found.len(), expected.len());
    for (index, (nodes, cost)) in expected.iter().enumerate() {
        assert_eq!(found.path(index).unwrap().nodes, nodes.as_slice());
        assert_eq!(found.total_cost(index), Some(*cost));
    }

    // And the case where the smaller row is a genuine dead end: 1 has no way to
    // 2 of its own, so the minimum-cost path from 0 is [0,2] even though 1 is
    // reachable for nothing and sorts first.
    let edges = [(0, 1), (1, 0), (0, 2)];
    let weights = [0.0, 0.0, 5.0];
    let projection = topology(3, &edges, &weights, Orientation::Outgoing, &context);
    let found = yens(&projection, "n0", "n2", YensOptions { k: 4 }).unwrap();
    assert_eq!(found.len(), 1);
    assert_eq!(found.path(0).unwrap().nodes, [0, 2]);
}

#[test]
fn yens_rejects_invalid_options_and_a_signed_projection() {
    let context = context();
    let projection = topology(2, &[(0, 1)], &[1.0], Orientation::Outgoing, &context);
    assert!(matches!(
        yens(&projection, "n0", "n1", YensOptions { k: 0 }),
        Err(AlgorithmError::InvalidArguments(message)) if message.contains("k must be at least 1")
    ));
    assert!(yens(&projection, "n0", "nowhere", YensOptions { k: 1 }).is_err());
    assert!(yens(&projection, "nowhere", "n1", YensOptions { k: 1 }).is_err());

    // Dijkstra underneath means nonnegative weights, and the guard is the same
    // one every other kernel built on it uses.
    let signed = GraphProjection::from_signed_topology(
        SnapshotIdentity::new("g".into(), "r".into(), "reader".into()).unwrap(),
        vec!["n0".into(), "n1".into()],
        vec![ProjectionEdge {
            source: 0,
            target: 1,
            ordinal: 0,
            id: None,
        }],
        vec![-1.0],
        Orientation::Outgoing,
        &context,
    )
    .unwrap();
    assert!(matches!(
        yens(&signed, "n0", "n1", YensOptions { k: 1 }),
        Err(AlgorithmError::InvalidArguments(message)) if message.contains("signed projection")
    ));
}

#[test]
fn yens_observes_cancellation_and_budget_and_releases_scratch() {
    // A budget too small to finish is refused rather than answered partially.
    let tight = ExecutionContext::new(limits(3_000)).unwrap();
    let side = 6usize;
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
    let projection = topology(side * side, &edges, &weights, Orientation::Outgoing, &tight);
    assert!(matches!(
        yens(
            &projection,
            "n0",
            &format!("n{}", side * side - 1),
            YensOptions { k: 20 }
        ),
        Err(AlgorithmError::BudgetExceeded { .. })
    ));

    // Cancellation is observed, and every buffer the kernel took is released.
    let context = context();
    let projection = topology(
        side * side,
        &edges,
        &weights,
        Orientation::Outgoing,
        &context,
    );
    let retained = context.usage().unwrap().live_bytes;
    context.cancel().unwrap();
    assert!(matches!(
        yens(
            &projection,
            "n0",
            &format!("n{}", side * side - 1),
            YensOptions { k: 20 }
        ),
        Err(AlgorithmError::Cancelled)
    ));
    assert_eq!(context.usage().unwrap().live_bytes, retained);
}
