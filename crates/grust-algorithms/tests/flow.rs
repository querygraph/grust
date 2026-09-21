//! Max flow against brute-force minimum cuts and the flow's own constraints.

use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, Orientation,
    ProjectionEdge, SnapshotIdentity, max_flow,
};

const ORIENTATIONS: [Orientation; 3] = [
    Orientation::Outgoing,
    Orientation::Incoming,
    Orientation::Undirected,
];

fn limits(work_units: usize) -> ExecutionLimits {
    ExecutionLimits {
        memory_bytes: 512 * 1024 * 1024,
        work_units,
        batch_rows: 1024,
        deadline: None,
    }
}

fn context() -> ExecutionContext {
    ExecutionContext::new(limits(2_000_000_000)).unwrap()
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
        weights.map(<[f64]>::to_vec),
        orientation,
        context,
    )
    .unwrap()
}

/// Capacity from a to b, summed over parallel edges, as the orientation reads them.
fn capacities(
    n: usize,
    edges: &[(usize, usize)],
    weights: Option<&[f64]>,
    orientation: Orientation,
) -> Vec<Vec<f64>> {
    let mut c = vec![vec![0.0; n]; n];
    for (index, &(a, b)) in edges.iter().enumerate() {
        let w = weights.map_or(1.0, |w| w[index]);
        if a == b {
            continue;
        }
        if orientation != Orientation::Incoming {
            c[a][b] += w;
        }
        if orientation != Orientation::Outgoing {
            c[b][a] += w;
        }
    }
    c
}

/// Capacity leaving the set `inside` describes.
fn leaving(c: &[Vec<f64>], inside: impl Fn(usize) -> bool) -> f64 {
    c.iter()
        .enumerate()
        .filter(|&(a, _)| inside(a))
        .flat_map(|(_, row)| row.iter().enumerate())
        .filter(|&(b, _)| !inside(b))
        .map(|(_, capacity)| capacity)
        .sum()
}

/// The cheapest cut, over every set holding the source and not the target.
fn min_cut(c: &[Vec<f64>], source: usize, target: usize) -> f64 {
    (0u32..1 << c.len())
        .filter(|set| set >> source & 1 == 1 && set >> target & 1 == 0)
        .map(|set| leaving(c, |node| set >> node & 1 == 1))
        .fold(f64::INFINITY, f64::min)
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

fn check(
    n: usize,
    edges: &[(usize, usize)],
    weights: Option<&[f64]>,
    orientation: Orientation,
    source: usize,
    target: usize,
) {
    let what = format!("{orientation:?} {source}->{target} {edges:?} {weights:?}");
    let context = context();
    let projection = graph(n, edges, weights, orientation, &context);
    let result = max_flow(&projection, &format!("n{source}"), &format!("n{target}")).unwrap();
    let c = capacities(n, edges, weights, orientation);
    assert_eq!(result.value(), min_cut(&c, source, target), "{what}");

    // The reported cut separates the two and has the flow's value.
    let side = result.source_side();
    assert!(side[source] && !side[target], "{what}");
    let cut = leaving(&c, |node| side[node]);
    assert_eq!(cut, result.value(), "{what}");

    // Every edge carries at most its capacity, along a direction it allows;
    // what enters a node leaves it, except at the two ends.
    let mut balance = vec![0.0; n];
    let mut previous = None;
    for (from, to, slot, flow) in result.flows() {
        assert!(previous < Some(slot), "{what}: rows out of edge order");
        previous = Some(slot);
        let (a, b) = edges[slot];
        let allowed = match orientation {
            Orientation::Outgoing => (from, to) == (a, b),
            Orientation::Incoming => (from, to) == (b, a),
            Orientation::Undirected => (from, to) == (a, b) || (from, to) == (b, a),
        };
        assert!(allowed, "{what}: edge {slot} carries {from}->{to}");
        assert!(
            flow > 0.0 && flow <= weights.map_or(1.0, |w| w[slot]),
            "{what}"
        );
        balance[from] -= flow;
        balance[to] += flow;
    }
    for (node, &net) in balance.iter().enumerate() {
        let expected = if node == source {
            -result.value()
        } else if node == target {
            result.value()
        } else {
            0.0
        };
        assert_eq!(net, expected, "{what}: node {node}");
    }
}

#[test]
fn max_flow_equals_the_brute_force_minimum_cut_and_is_a_flow() {
    let mut random = Xorshift(0x2545_F491_4F6C_DD1D);
    for round in 0..2500 {
        let n = 2 + random.below(8);
        let count = random.below(4 * n);
        let edges: Vec<_> = (0..count)
            .map(|_| (random.below(n), random.below(n)))
            .collect();
        // Integers, zero included: every sum is exact, so equality is exact.
        let weights: Vec<f64> = (0..count).map(|_| random.below(6) as f64).collect();
        let weights = (round % 3 != 0).then_some(&weights[..]);
        let source = random.below(n);
        let target = (source + 1 + random.below(n - 1)) % n;
        for orientation in ORIENTATIONS {
            check(n, &edges, weights, orientation, source, target);
        }
    }
}

#[test]
fn the_textbook_network_and_the_refusals_are_as_documented() {
    // CLRS figure 26.1: maximum flow 23.
    let edges = [
        (0, 1),
        (0, 2),
        (1, 3),
        (2, 1),
        (2, 4),
        (3, 2),
        (3, 5),
        (4, 3),
        (4, 5),
    ];
    let weights = [16.0, 13.0, 12.0, 4.0, 14.0, 9.0, 20.0, 7.0, 4.0];
    let context = context();
    let projection = graph(6, &edges, Some(&weights), Orientation::Outgoing, &context);
    let result = max_flow(&projection, "n0", "n5").unwrap();
    assert_eq!(result.value(), 23.0);
    assert_eq!(result.source_side(), [true, true, true, false, true, false]);
    // Nothing flows backwards along a directed network.
    assert_eq!(max_flow(&projection, "n5", "n0").unwrap().value(), 0.0);

    let held = context.usage().unwrap().live_bytes;
    assert!(matches!(
        max_flow(&projection, "n0", "n0"),
        Err(AlgorithmError::InvalidArguments(message)) if message.contains("target")
    ));
    assert!(matches!(
        max_flow(&projection, "n0", "nowhere"),
        Err(AlgorithmError::InvalidArguments(_))
    ));
    assert_eq!(context.usage().unwrap().live_bytes, held);
}

#[test]
fn a_long_path_and_a_wide_network_finish_without_recursion() {
    let n = 300_000;
    let edges: Vec<_> = (1..n).map(|node| (node - 1, node)).collect();
    let context = context();
    let projection = graph(n, &edges, None, Orientation::Outgoing, &context);
    let result = max_flow(&projection, "n0", &format!("n{}", n - 1)).unwrap();
    assert_eq!(result.value(), 1.0);
    assert_eq!(result.flows().count(), n - 1);

    // A thousand disjoint two-hop routes: a thousand units.
    let mut edges = Vec::new();
    for middle in 2..1002 {
        edges.push((0, middle));
        edges.push((middle, 1));
    }
    let context = self::context();
    let projection = graph(1002, &edges, None, Orientation::Outgoing, &context);
    assert_eq!(max_flow(&projection, "n0", "n1").unwrap().value(), 1000.0);
}

#[test]
fn max_flow_observes_cancellation_and_budget_and_releases_scratch() {
    let mut random = Xorshift(0x9E37_79B9_7F4A_7C15);
    let edges: Vec<_> = (0..40_000)
        .map(|_| (random.below(3000), random.below(3000)))
        .collect();
    let context = context();
    let projection = graph(3000, &edges, None, Orientation::Outgoing, &context);
    let projection_work = context.usage().unwrap().counted_work().expect("counted");
    let held = context.usage().unwrap().live_bytes;
    context.cancel().unwrap();
    assert!(matches!(
        max_flow(&projection, "n0", "n1"),
        Err(AlgorithmError::Cancelled)
    ));
    assert_eq!(context.usage().unwrap().live_bytes, held);

    let tight = ExecutionContext::new(limits(projection_work + 60_000)).unwrap();
    let projection = graph(3000, &edges, None, Orientation::Outgoing, &tight);
    let held = tight.usage().unwrap().live_bytes;
    assert!(matches!(
        max_flow(&projection, "n0", "n1"),
        Err(AlgorithmError::BudgetExceeded {
            resource: "work",
            ..
        })
    ));
    assert_eq!(tight.usage().unwrap().live_bytes, held);
}
