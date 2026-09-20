//! Bellman-Ford against exhaustive enumeration of simple paths and cycles.

use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, Orientation,
    ProjectionEdge, SnapshotIdentity, bellman_ford, dijkstra,
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

fn edges_of(edges: &[(usize, usize)]) -> Vec<ProjectionEdge> {
    edges
        .iter()
        .enumerate()
        .map(|(ordinal, &(source, target))| ProjectionEdge {
            source,
            target,
            ordinal,
            id: None,
        })
        .collect()
}

fn signed(
    n: usize,
    edges: &[(usize, usize)],
    weights: &[f64],
    orientation: Orientation,
    context: &ExecutionContext,
) -> GraphProjection {
    GraphProjection::from_signed_topology(
        SnapshotIdentity::new("g".into(), "r".into(), "reader".into()).unwrap(),
        (0..n).map(|i| format!("n{i}").into()).collect(),
        edges_of(edges),
        weights.to_vec(),
        orientation,
        context,
    )
    .unwrap()
}

/// Arcs as the orientation reads them: (from, to, weight).
fn arcs(
    edges: &[(usize, usize)],
    weights: &[f64],
    orientation: Orientation,
) -> Vec<(usize, usize, f64)> {
    let mut arcs = Vec::new();
    for (&(a, b), &w) in edges.iter().zip(weights) {
        match orientation {
            Orientation::Outgoing => arcs.push((a, b, w)),
            Orientation::Incoming => arcs.push((b, a, w)),
            Orientation::Undirected => {
                arcs.push((a, b, w));
                if a != b {
                    arcs.push((b, a, w));
                }
            }
        }
    }
    arcs
}

/// By enumeration, with no relaxation in it: is a negative simple cycle
/// reachable from the source, and otherwise the cheapest simple path to each
/// node. Without a negative cycle a shortest walk is a simple path.
fn by_enumeration(n: usize, arcs: &[(usize, usize, f64)], source: usize) -> Option<Vec<f64>> {
    struct Search<'a> {
        arcs: &'a [(usize, usize, f64)],
        on_path: Vec<bool>,
        position: Vec<f64>,
        best: Vec<f64>,
        negative: bool,
    }
    impl Search<'_> {
        fn visit(&mut self, node: usize, cost: f64) {
            self.best[node] = self.best[node].min(cost);
            self.on_path[node] = true;
            self.position[node] = cost;
            for &(from, to, weight) in self.arcs {
                if from != node {
                    continue;
                }
                if self.on_path[to] {
                    // Closing a cycle: its weight is what was added since `to`.
                    if cost + weight - self.position[to] < 0.0 {
                        self.negative = true;
                    }
                } else {
                    self.visit(to, cost + weight);
                }
            }
            self.on_path[node] = false;
        }
    }
    let mut search = Search {
        arcs,
        on_path: vec![false; n],
        position: vec![0.0; n],
        best: vec![f64::INFINITY; n],
        negative: false,
    };
    search.visit(source, 0.0);
    (!search.negative).then_some(search.best)
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
fn distances_or_a_checkable_negative_cycle_on_every_small_signed_graph() {
    let mut random = Xorshift(0x2545_F491_4F6C_DD1D);
    let (mut with_cycle, mut without) = (0, 0);
    for _ in 0..4000 {
        let n = 1 + random.below(7);
        let count = random.below(2 * n + 1);
        let edges: Vec<_> = (0..count)
            .map(|_| (random.below(n), random.below(n)))
            .collect();
        // Integers from -3 to 6: every sum is exact, and negatives are common
        // enough to make cycles without making every graph one.
        let weights: Vec<f64> = (0..count).map(|_| random.below(10) as f64 - 3.0).collect();
        let source = random.below(n);
        for orientation in ORIENTATIONS {
            let what = format!("{orientation:?} from {source}: {edges:?} {weights:?}");
            let context = context();
            let projection = signed(n, &edges, &weights, orientation, &context);
            let result = bellman_ford(&projection, &format!("n{source}")).unwrap();
            let arcs = arcs(&edges, &weights, orientation);
            match by_enumeration(n, &arcs, source) {
                Some(expected) => {
                    without += 1;
                    assert!(result.negative_cycle().is_none(), "{what}");
                    assert_eq!(result.distances().unwrap(), expected, "{what}");
                }
                None => {
                    with_cycle += 1;
                    assert!(result.distances().is_none(), "{what}");
                    let cycle = result.negative_cycle().expect(&what);
                    // The witness is checkable without trusting the kernel: its
                    // arcs exist, they sum below zero, and the source reaches it.
                    let mut total = 0.0;
                    for (index, &from) in cycle.iter().enumerate() {
                        let to = cycle[(index + 1) % cycle.len()];
                        let cheapest = arcs
                            .iter()
                            .filter(|arc| arc.0 == from && arc.1 == to)
                            .map(|arc| arc.2)
                            .fold(f64::INFINITY, f64::min);
                        assert!(
                            cheapest.is_finite(),
                            "{what}: no arc {from}->{to} in {cycle:?}"
                        );
                        total += cheapest;
                    }
                    assert!(total < 0.0, "{what}: witness {cycle:?} weighs {total}");
                    let mut distinct = cycle.to_vec();
                    distinct.sort_unstable();
                    distinct.dedup();
                    assert_eq!(
                        distinct.len(),
                        cycle.len(),
                        "{what}: {cycle:?} repeats a node"
                    );
                    let mut reached = vec![false; n];
                    let mut stack = vec![source];
                    while let Some(node) = stack.pop() {
                        if !std::mem::replace(&mut reached[node], true) {
                            stack.extend(arcs.iter().filter(|arc| arc.0 == node).map(|arc| arc.1));
                        }
                    }
                    assert!(reached[cycle[0]], "{what}: {cycle:?} is not reachable");
                }
            }
        }
    }
    assert!(
        with_cycle > 1000 && without > 1000,
        "{with_cycle} with, {without} without"
    );
}

#[test]
fn it_agrees_with_dijkstra_wherever_dijkstra_is_allowed() {
    let mut random = Xorshift(0x9E37_79B9_7F4A_7C15);
    for _ in 0..300 {
        let n = 2 + random.below(60);
        let count = random.below(4 * n);
        let edges: Vec<_> = (0..count)
            .map(|_| (random.below(n), random.below(n)))
            .collect();
        let weights: Vec<f64> = (0..count).map(|_| random.below(9) as f64).collect();
        for orientation in ORIENTATIONS {
            let context = context();
            let projection = GraphProjection::from_topology(
                SnapshotIdentity::new("g".into(), "r".into(), "reader".into()).unwrap(),
                (0..n).map(|i| format!("n{i}").into()).collect(),
                edges_of(&edges),
                Some(weights.clone()),
                orientation,
                &context,
            )
            .unwrap();
            let expected = dijkstra(&projection, "n0").unwrap();
            let result = bellman_ford(&projection, "n0").unwrap();
            assert_eq!(result.distances().unwrap(), expected.values());
        }
    }
}

#[test]
fn the_documented_cases() {
    let context = context();
    // Cheaper the long way round, through a negative arc Dijkstra would miss.
    let edges = [(0, 1), (0, 2), (2, 1), (1, 3)];
    let weights = [4.0, 5.0, -3.0, 1.0];
    let result = bellman_ford(
        &signed(5, &edges, &weights, Orientation::Outgoing, &context),
        "n0",
    )
    .unwrap();
    assert_eq!(
        result.distances().unwrap(),
        [0.0, 2.0, 5.0, 3.0, f64::INFINITY]
    );

    // A negative cycle the source cannot reach is not its problem.
    let edges = [(0, 1), (2, 3), (3, 2)];
    let weights = [1.0, -5.0, 1.0];
    let result = bellman_ford(
        &signed(4, &edges, &weights, Orientation::Outgoing, &context),
        "n0",
    )
    .unwrap();
    assert_eq!(result.distances().unwrap()[1], 1.0);
    // From inside it, it is the whole answer, in the order its arcs run.
    let result = bellman_ford(
        &signed(4, &edges, &weights, Orientation::Outgoing, &context),
        "n2",
    )
    .unwrap();
    let mut cycle = result.negative_cycle().unwrap().to_vec();
    cycle.sort_unstable();
    assert_eq!(cycle, [2, 3]);

    // An undirected negative edge is a negative cycle, there and back.
    let result = bellman_ford(
        &signed(2, &[(0, 1)], &[-1.0], Orientation::Undirected, &context),
        "n0",
    )
    .unwrap();
    assert_eq!(result.negative_cycle().unwrap().len(), 2);
    // A negative self-loop is a cycle of one.
    let result = bellman_ford(
        &signed(1, &[(0, 0)], &[-2.0], Orientation::Outgoing, &context),
        "n0",
    )
    .unwrap();
    assert_eq!(result.negative_cycle().unwrap(), [0]);

    assert!(matches!(
        bellman_ford(
            &signed(1, &[], &[], Orientation::Outgoing, &context),
            "missing"
        ),
        Err(AlgorithmError::InvalidArguments(_))
    ));
    // Infinite and NaN weights are refused even when negatives are not.
    assert!(
        GraphProjection::from_signed_topology(
            SnapshotIdentity::new("g".into(), "r".into(), "reader".into()).unwrap(),
            vec!["a".into(), "b".into()],
            edges_of(&[(0, 1)]),
            vec![f64::NEG_INFINITY],
            Orientation::Outgoing,
            &context,
        )
        .is_err()
    );
}

#[test]
fn a_long_negative_chain_and_a_far_cycle_finish_within_budget_or_say_so() {
    // A path of negative arcs: many relaxations, no cycle.
    let n = 20_000;
    let edges: Vec<_> = (1..n).map(|node| (node - 1, node)).collect();
    let weights = vec![-1.0; n - 1];
    let context = context();
    let projection = signed(n, &edges, &weights, Orientation::Outgoing, &context);
    let result = bellman_ford(&projection, "n0").unwrap();
    assert_eq!(result.distances().unwrap()[n - 1], -((n - 1) as f64));

    // The same path closed into one huge negative cycle.
    let mut edges = edges;
    edges.push((n - 1, 0));
    let mut weights = weights;
    weights.push(-1.0);
    let context = self::context();
    let projection = signed(n, &edges, &weights, Orientation::Outgoing, &context);
    let held = context.usage().unwrap().live_bytes;
    let result = bellman_ford(&projection, "n0").unwrap();
    assert_eq!(result.negative_cycle().unwrap().len(), n);
    drop(result);
    assert_eq!(context.usage().unwrap().live_bytes, held);

    // Cancellation and the work budget stop it, and scratch comes back.
    context.cancel().unwrap();
    assert!(matches!(
        bellman_ford(&projection, "n0"),
        Err(AlgorithmError::Cancelled)
    ));
    let build = ExecutionContext::new(limits(usize::MAX)).unwrap();
    let cost = {
        let _ = signed(n, &edges, &weights, Orientation::Outgoing, &build);
        build.usage().unwrap().work_units
    };
    let tight = ExecutionContext::new(limits(cost + 1000)).unwrap();
    let projection = signed(n, &edges, &weights, Orientation::Outgoing, &tight);
    let held = tight.usage().unwrap().live_bytes;
    assert!(matches!(
        bellman_ford(&projection, "n0"),
        Err(AlgorithmError::BudgetExceeded {
            resource: "work",
            ..
        })
    ));
    assert_eq!(tight.usage().unwrap().live_bytes, held);
}
