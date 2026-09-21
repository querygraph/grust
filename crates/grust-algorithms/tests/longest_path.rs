//! Longest paths in a DAG against two oracles that share nothing with the
//! kernel: exhaustive enumeration of every path, and a dynamic program over a
//! topological order produced by Kahn's algorithm rather than by the kernel's
//! depth-first colouring. Both are written here, in full, because an oracle that
//! calls the subject twice agrees with its bugs.

use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, Orientation,
    ProjectionEdge, SnapshotIdentity, TableValue, longest_path,
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

fn graph(
    n: usize,
    edges: &[(usize, usize)],
    weights: Option<&[f64]>,
    orientation: Orientation,
    context: &ExecutionContext,
) -> GraphProjection {
    GraphProjection::from_topology(
        SnapshotIdentity::new("g".into(), "r".into(), "reader".into()).unwrap(),
        (0..n).map(|i| format!("n{i}").into()).collect(),
        edges_of(edges),
        weights.map(<[f64]>::to_vec),
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

/// Kahn's algorithm: peel nodes of in-degree zero. Its order, or `None` if the
/// arcs hold a cycle. Nothing here is the kernel's depth-first colouring.
fn kahn_order(n: usize, arcs: &[(usize, usize, f64)]) -> Option<Vec<usize>> {
    let mut indegree = vec![0usize; n];
    for &(_, to, _) in arcs {
        indegree[to] += 1;
    }
    let mut ready: Vec<usize> = (0..n).filter(|&node| indegree[node] == 0).collect();
    let mut order = Vec::new();
    while let Some(node) = ready.pop() {
        order.push(node);
        for &(from, to, _) in arcs {
            if from == node {
                indegree[to] -= 1;
                if indegree[to] == 0 {
                    ready.push(to);
                }
            }
        }
    }
    (order.len() == n).then_some(order)
}

/// Every (weight, hops) pair of every directed path ending at each node, the
/// empty path included. Exponential, and exact; only small graphs go through it.
fn every_path(n: usize, arcs: &[(usize, usize, f64)]) -> Vec<Vec<(f64, i64)>> {
    fn walk(
        node: usize,
        weight: f64,
        hops: i64,
        arcs: &[(usize, usize, f64)],
        reaching: &mut [Vec<(f64, i64)>],
    ) {
        reaching[node].push((weight, hops));
        for &(from, to, w) in arcs {
            if from == node {
                walk(to, weight + w, hops + 1, arcs, reaching);
            }
        }
    }
    let mut reaching = vec![Vec::new(); n];
    for start in 0..n {
        walk(start, 0.0, 0, arcs, &mut reaching);
    }
    reaching
}

/// The dynamic program, written out over Kahn's order: a node's value is final
/// when it is visited, so one pass over its out-arcs settles its successors.
fn dp_over(order: &[usize], n: usize, arcs: &[(usize, usize, f64)]) -> Vec<f64> {
    let mut best = vec![0.0f64; n];
    for &node in order {
        for &(from, to, weight) in arcs {
            if from == node && best[node] + weight > best[to] {
                best[to] = best[node] + weight;
            }
        }
    }
    best
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
fn longest_path_matches_an_independent_oracle() {
    let mut random = Xorshift(0x1234_5678_9ABC_DEF1);
    let (mut cyclic, mut acyclic) = (0, 0);
    for _ in 0..3000 {
        let n = 1 + random.below(6);
        let count = random.below(n + 3);
        let edges: Vec<_> = (0..count)
            .map(|_| (random.below(n), random.below(n)))
            .collect();
        // Small integers: every sum is exact, so equality is the right assertion.
        let weights: Vec<f64> = (0..count).map(|_| random.below(7) as f64).collect();
        for orientation in ORIENTATIONS {
            let what = format!("{orientation:?}: {edges:?} {weights:?}");
            let context = context();
            let projection = graph(n, &edges, Some(&weights), orientation, &context);
            let result = longest_path(&projection).unwrap();
            let arcs = arcs(&edges, &weights, orientation);
            match kahn_order(n, &arcs) {
                Some(order) => {
                    acyclic += 1;
                    assert!(result.cycle().is_none(), "{what}");
                    let reaching = every_path(n, &arcs);
                    let distances = result.distances().expect(&what);
                    let hops = result.hops().expect(&what);
                    for node in 0..n {
                        let best = reaching[node]
                            .iter()
                            .map(|&(weight, _)| weight)
                            .fold(f64::NEG_INFINITY, f64::max);
                        assert_eq!(distances[node], best, "{what}: node {node}");
                        // The reported hop count must belong to a path that
                        // actually weighs what was reported.
                        assert!(
                            reaching[node].contains(&(distances[node], hops[node])),
                            "{what}: node {node} reports {} in {} hops, which is no path",
                            distances[node],
                            hops[node]
                        );
                    }
                    // The same answer from the same recurrence over a different
                    // topological order: the result cannot depend on which order.
                    assert_eq!(distances, dp_over(&order, n, &arcs), "{what}");
                }
                None => {
                    cyclic += 1;
                    assert!(result.distances().is_none(), "{what}");
                    assert!(result.hops().is_none(), "{what}");
                    let cycle = result.cycle().expect(&what);
                    assert!(!cycle.is_empty(), "{what}: empty witness");
                    // Checkable without trusting the kernel: every arc of the
                    // witness exists, and it visits no node twice.
                    for (index, &from) in cycle.iter().enumerate() {
                        let to = cycle[(index + 1) % cycle.len()];
                        assert!(
                            arcs.iter().any(|&(a, b, _)| a == from && b == to),
                            "{what}: no arc {from}->{to} in {cycle:?}"
                        );
                    }
                    let mut distinct = cycle.to_vec();
                    distinct.sort_unstable();
                    distinct.dedup();
                    assert_eq!(distinct.len(), cycle.len(), "{what}: {cycle:?} repeats");
                }
            }
        }
    }
    // Both answers are shapes of this kernel's result, and both must be reached
    // often: a fixture set that never cycles would test half the kernel.
    assert!(
        cyclic > 500 && acyclic > 500,
        "{cyclic} cyclic, {acyclic} not"
    );
}

#[test]
fn longest_path_recomputes_the_dp_over_a_larger_layered_dag() {
    // Forward arcs only, so it is a DAG by construction and large enough that
    // exhaustive enumeration is out of reach but the recurrence is not.
    let mut random = Xorshift(0xDEAD_BEEF_0BAD_F00D);
    for _ in 0..40 {
        let n = 40 + random.below(60);
        let count = 4 * n;
        let edges: Vec<_> = (0..count)
            .map(|_| {
                let a = random.below(n - 1);
                (a, a + 1 + random.below(n - a - 1))
            })
            .collect();
        let weights: Vec<f64> = (0..count).map(|_| random.below(9) as f64).collect();
        let context = context();
        let projection = graph(n, &edges, Some(&weights), Orientation::Outgoing, &context);
        let result = longest_path(&projection).unwrap();
        let arcs = arcs(&edges, &weights, Orientation::Outgoing);
        let order = kahn_order(n, &arcs).expect("forward arcs cannot cycle");
        assert_eq!(result.distances().unwrap(), dp_over(&order, n, &arcs));
        // The fixture reaches what it claims to: a long path, not a one-arc one.
        assert!(result.hops().unwrap().iter().any(|&hops| hops > 3));
    }
}

#[test]
fn the_documented_cases() {
    let context = context();

    // Hand-computed. 0->1 is the heavier first arc, but the heaviest path to 3
    // goes through the lighter one: a kernel that extended the best node so far
    // would answer 5 at node 3 and 7 at node 4.
    //          0 -3-> 1 -1-> 3 -2-> 4
    //          0 -1-> 2 -5-> 3
    let edges = [(0, 1), (0, 2), (1, 3), (2, 3), (3, 4)];
    let weights = [3.0, 1.0, 1.0, 5.0, 2.0];
    let result = longest_path(&graph(
        5,
        &edges,
        Some(&weights),
        Orientation::Outgoing,
        &context,
    ))
    .unwrap();
    assert_eq!(result.distances().unwrap(), [0.0, 3.0, 1.0, 6.0, 8.0]);
    // Two arcs to node 3, three to node 4: the heavier route, not the longer.
    assert_eq!(result.hops().unwrap(), [0, 1, 1, 2, 3]);

    // Unweighted: every arc weighs one, so the distance is the hop count.
    let result = longest_path(&graph(
        4,
        &[(0, 1), (1, 2), (2, 3)],
        None,
        Orientation::Outgoing,
        &context,
    ))
    .unwrap();
    assert_eq!(result.distances().unwrap(), [0.0, 1.0, 2.0, 3.0]);
    assert_eq!(result.hops().unwrap(), [0, 1, 2, 3]);

    // A single node, with no arcs at all: the empty path, and no cycle.
    let result = longest_path(&graph(1, &[], None, Orientation::Outgoing, &context)).unwrap();
    assert_eq!(result.distances().unwrap(), [0.0]);
    assert_eq!(result.hops().unwrap(), [0]);
    assert!(result.cycle().is_none());
    // A single node with a self-loop is a cycle of one.
    let result = longest_path(&graph(1, &[(0, 0)], None, Orientation::Outgoing, &context)).unwrap();
    assert_eq!(result.cycle().unwrap(), [0]);
    assert!(result.distances().is_none());

    // Disconnected: two chains and an isolate, each component answered on its
    // own. The isolate is a node of the graph, and its answer is zero, not null.
    let result = longest_path(&graph(
        5,
        &[(0, 1), (2, 3)],
        Some(&[4.0, 7.0]),
        Orientation::Outgoing,
        &context,
    ))
    .unwrap();
    assert_eq!(result.distances().unwrap(), [0.0, 4.0, 0.0, 7.0, 0.0]);

    // Parallel arcs are arcs like any other: the heaviest of them wins.
    let result = longest_path(&graph(
        2,
        &[(0, 1), (0, 1)],
        Some(&[2.0, 5.0]),
        Orientation::Outgoing,
        &context,
    ))
    .unwrap();
    assert_eq!(result.distances().unwrap(), [0.0, 5.0]);

    // Incoming reverses the arcs, and the answer with them.
    let result = longest_path(&graph(
        3,
        &[(0, 1), (1, 2)],
        Some(&[1.0, 2.0]),
        Orientation::Incoming,
        &context,
    ))
    .unwrap();
    assert_eq!(result.distances().unwrap(), [3.0, 2.0, 0.0]);

    // Undirected: one edge is two arcs, there and back, which is a cycle.
    let result = longest_path(&graph(
        2,
        &[(0, 1)],
        Some(&[1.0]),
        Orientation::Undirected,
        &context,
    ))
    .unwrap();
    let cycle = result.cycle().unwrap();
    assert_eq!(cycle.len(), 2);

    // The table says the same thing: distances and hops null under a cycle,
    // the witness readable as the rows with a nonnegative cycleIndex.
    let table = longest_path(&graph(
        3,
        &[(0, 1), (1, 2), (2, 1)],
        None,
        Orientation::Outgoing,
        &context,
    ))
    .unwrap()
    .into_table()
    .unwrap();
    assert_eq!(table.rows(), 3);
    assert_eq!(
        (0..3)
            .map(|row| table.value(0, row))
            .collect::<Vec<TableValue<'_>>>(),
        vec![TableValue::Null; 3]
    );
    let indices: Vec<i64> = table.integers("cycleIndex").unwrap().to_vec();
    let mut witness: Vec<usize> = (0..3).filter(|&row| indices[row] >= 0).collect();
    witness.sort_by_key(|&row| indices[row]);
    assert_eq!(witness, [1, 2]);
    assert_eq!(
        table.scalar_value("cyclic"),
        Some(grust_algorithms::TableScalar::Boolean(true))
    );
    // And on an acyclic graph nothing is on a cycle.
    let table = longest_path(&graph(
        2,
        &[(0, 1)],
        Some(&[2.5]),
        Orientation::Outgoing,
        &context,
    ))
    .unwrap()
    .into_table()
    .unwrap();
    assert_eq!(table.numbers("distance").unwrap(), [0.0, 2.5]);
    assert_eq!(table.integers("cycleIndex").unwrap(), [-1, -1]);
    assert_eq!(
        table.scalar_value("cyclic"),
        Some(grust_algorithms::TableScalar::Boolean(false))
    );
}

#[test]
fn longest_path_refuses_a_signed_projection() {
    let context = context();
    let projection = GraphProjection::from_signed_topology(
        SnapshotIdentity::new("g".into(), "r".into(), "reader".into()).unwrap(),
        vec!["n0".into(), "n1".into()],
        edges_of(&[(0, 1)]),
        vec![-1.0],
        Orientation::Outgoing,
        &context,
    )
    .unwrap();
    // The recurrence would survive a negative weight; the catalog rule is that
    // a projection admitting them is bellmanFord's alone, and the refusal says so.
    match longest_path(&projection) {
        Err(AlgorithmError::InvalidArguments(message)) => {
            assert!(message.contains("signed projection"), "{message}");
            assert!(message.contains("longestPath"), "{message}");
        }
        other => panic!("{:?}", other.map(|_| ())),
    }
}

#[test]
fn longest_path_observes_cancellation_and_budget_and_releases_scratch() {
    let n = 50_000;
    let edges: Vec<_> = (1..n).map(|node| (node - 1, node)).collect();
    let weights = vec![1.5; n - 1];

    let context = context();
    let projection = graph(n, &edges, Some(&weights), Orientation::Outgoing, &context);
    let held = context.usage().unwrap().live_bytes;
    let result = longest_path(&projection).unwrap();
    assert_eq!(result.distances().unwrap()[n - 1], 1.5 * (n - 1) as f64);
    assert_eq!(result.hops().unwrap()[n - 1], (n - 1) as i64);
    drop(result);
    assert_eq!(context.usage().unwrap().live_bytes, held);

    context.cancel().unwrap();
    assert!(matches!(
        longest_path(&projection),
        Err(AlgorithmError::Cancelled)
    ));

    let build = ExecutionContext::new(limits(usize::MAX)).unwrap();
    let cost = {
        let _ = graph(n, &edges, Some(&weights), Orientation::Outgoing, &build);
        build.usage().unwrap().work_units
    };
    let tight = ExecutionContext::new(limits(cost + 1000)).unwrap();
    let projection = graph(n, &edges, Some(&weights), Orientation::Outgoing, &tight);
    let held = tight.usage().unwrap().live_bytes;
    assert!(matches!(
        longest_path(&projection),
        Err(AlgorithmError::BudgetExceeded {
            resource: "work",
            ..
        })
    ));
    assert_eq!(tight.usage().unwrap().live_bytes, held);
}
