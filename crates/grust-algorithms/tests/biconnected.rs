//! Bridges, articulation points and biconnected components, each against its
//! definition: remove the thing and recount, or enumerate the simple cycles.

use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, Orientation,
    ProjectionEdge, SnapshotIdentity, biconnectivity,
};

fn limits(work_units: usize) -> ExecutionLimits {
    ExecutionLimits {
        memory_bytes: 512 * 1024 * 1024,
        work_units,
        batch_rows: 1024,
        deadline: None,
    }
}

fn context() -> ExecutionContext {
    ExecutionContext::new(limits(500_000_000)).unwrap()
}

fn graph(
    n: usize,
    edges: &[(usize, usize)],
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
                // Not the slot, so a test can tell the two apart.
                ordinal: 100 + ordinal,
                id: None,
            })
            .collect(),
        None,
        orientation,
        context,
    )
    .unwrap()
}

struct Sets(Vec<usize>);
impl Sets {
    fn new(n: usize) -> Self {
        Self((0..n).collect())
    }
    fn find(&mut self, mut x: usize) -> usize {
        while self.0[x] != x {
            self.0[x] = self.0[self.0[x]];
            x = self.0[x];
        }
        x
    }
    fn union(&mut self, a: usize, b: usize) {
        let (a, b) = (self.find(a), self.find(b));
        self.0[a.max(b)] = a.min(b);
    }
}

/// Connected components among the nodes left, using the edges left.
fn pieces(
    n: usize,
    edges: &[(usize, usize)],
    without_edge: Option<usize>,
    without_node: Option<usize>,
) -> usize {
    let mut sets = Sets::new(n);
    for (index, &(a, b)) in edges.iter().enumerate() {
        if Some(index) != without_edge && Some(a) != without_node && Some(b) != without_node {
            sets.union(a, b);
        }
    }
    (0..n)
        .filter(|&v| Some(v) != without_node && sets.find(v) == v)
        .count()
}

/// Two edges share a component exactly when a simple cycle runs through both.
/// Enumerate every simple cycle, parallel pairs included, and merge along each.
fn components_by_cycles(n: usize, edges: &[(usize, usize)]) -> Vec<Option<usize>> {
    let mut sets = Sets::new(edges.len());
    fn extend(
        start: usize,
        at: usize,
        edges: &[(usize, usize)],
        on_path: &mut Vec<bool>,
        used: &mut Vec<usize>,
        sets: &mut Sets,
    ) {
        for (index, &(a, b)) in edges.iter().enumerate() {
            if a == b || used.contains(&index) || (a != at && b != at) {
                continue;
            }
            let next = if a == at { b } else { a };
            if next == start && !used.is_empty() {
                for &other in used.iter() {
                    sets.union(index, other);
                }
            } else if !on_path[next] && next > start {
                on_path[next] = true;
                used.push(index);
                extend(start, next, edges, on_path, used, sets);
                used.pop();
                on_path[next] = false;
            }
        }
    }
    for start in 0..n {
        let mut on_path = vec![false; n];
        on_path[start] = true;
        extend(
            start,
            start,
            edges,
            &mut on_path,
            &mut Vec::new(),
            &mut sets,
        );
    }
    // Name each class by its smallest ordinal, which is 100 + the smallest slot.
    (0..edges.len())
        .map(|slot| (edges[slot].0 != edges[slot].1).then(|| 100 + sets.find(slot)))
        .collect()
}

fn check(n: usize, edges: &[(usize, usize)]) {
    let context = context();
    let result = biconnectivity(&graph(n, edges, Orientation::Undirected, &context)).unwrap();
    let whole = pieces(n, edges, None, None);
    let bridges: Vec<usize> = (0..edges.len())
        .filter(|&edge| pieces(n, edges, Some(edge), None) > whole)
        .collect();
    assert_eq!(result.bridges(), bridges, "bridges of {edges:?}");
    let points: Vec<usize> = (0..n)
        .filter(|&node| {
            // Removing a node also removes it from the count; an isolate's
            // removal lowers the count by one and splits nothing.
            let isolated = !edges
                .iter()
                .any(|&(a, b)| a != b && (a == node || b == node));
            pieces(n, edges, None, Some(node)) > whole - usize::from(isolated)
        })
        .collect();
    assert_eq!(
        result.articulation_points(),
        points,
        "articulation points of {edges:?}"
    );
    assert_eq!(
        result.components(),
        components_by_cycles(n, edges),
        "components of {edges:?}"
    );
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
fn every_simple_graph_of_up_to_five_nodes_matches_the_definitions() {
    for n in 0..=5usize {
        let pairs: Vec<(usize, usize)> = (0..n)
            .flat_map(|a| (a + 1..n).map(move |b| (a, b)))
            .collect();
        for mask in 0u32..1 << pairs.len() {
            let edges: Vec<_> = pairs
                .iter()
                .enumerate()
                .filter(|(bit, _)| mask >> bit & 1 == 1)
                .map(|(_, &pair)| pair)
                .collect();
            check(n, &edges);
        }
    }
}

#[test]
fn random_multigraphs_with_loops_match_the_definitions() {
    let mut random = Xorshift(0x2545_F491_4F6C_DD1D);
    for _ in 0..4000 {
        let n = 1 + random.below(8);
        let count = random.below(n + 4);
        let edges: Vec<_> = (0..count)
            .map(|_| (random.below(n), random.below(n)))
            .collect();
        check(n, &edges);
    }
}

#[test]
fn the_multigraph_cases_are_as_documented() {
    let context = context();
    // 0-1 doubled, 1-2 single, a loop on 2, and 3 alone.
    let edges = [(0, 1), (1, 0), (1, 2), (2, 2)];
    let result = biconnectivity(&graph(4, &edges, Orientation::Undirected, &context)).unwrap();
    // The doubled pair is a cycle of two: no bridge there, one component.
    assert_eq!(result.bridges(), [2]);
    assert_eq!(result.articulation_points(), [1]);
    assert_eq!(result.components(), [Some(100), Some(100), Some(102), None]);

    // Two triangles sharing node 2: one articulation point, no bridge.
    let bowtie = [(0, 1), (1, 2), (2, 0), (2, 3), (3, 4), (4, 2)];
    let result = biconnectivity(&graph(5, &bowtie, Orientation::Undirected, &context)).unwrap();
    assert!(result.bridges().is_empty());
    assert_eq!(result.articulation_points(), [2]);
    assert_eq!(
        result.components(),
        [100, 100, 100, 103, 103, 103].map(Some)
    );

    assert!(matches!(
        biconnectivity(&graph(2, &[(0, 1)], Orientation::Outgoing, &context)),
        Err(AlgorithmError::InvalidArguments(message)) if message.contains("undirected")
    ));
}

#[test]
fn a_million_node_path_does_not_overflow_the_stack() {
    let n = 1_000_000;
    let edges: Vec<_> = (1..n).map(|node| (node - 1, node)).collect();
    let context = context();
    let result = biconnectivity(&graph(n, &edges, Orientation::Undirected, &context)).unwrap();
    assert_eq!(result.bridges().len(), n - 1);
    assert_eq!(result.articulation_points().len(), n - 2);
    // A long cycle is one component, found only when the pass unwinds fully.
    let mut cycle = edges;
    cycle.push((n - 1, 0));
    let context = self::context();
    let result = biconnectivity(&graph(n, &cycle, Orientation::Undirected, &context)).unwrap();
    assert!(result.bridges().is_empty() && result.articulation_points().is_empty());
    assert!(result.components().iter().all(|&c| c == Some(100)));
}

#[test]
fn biconnectivity_observes_cancellation_and_budget_and_releases_scratch() {
    let edges: Vec<_> = (1..5000).map(|node| (node / 2, node)).collect();
    let context = context();
    let projection = graph(5000, &edges, Orientation::Undirected, &context);
    let projection_work = context.usage().unwrap().counted_work().expect("counted");
    let held = context.usage().unwrap().live_bytes;
    context.cancel().unwrap();
    assert!(matches!(
        biconnectivity(&projection),
        Err(AlgorithmError::Cancelled)
    ));
    assert_eq!(context.usage().unwrap().live_bytes, held);

    let tight = ExecutionContext::new(limits(projection_work + 3000)).unwrap();
    let projection = graph(5000, &edges, Orientation::Undirected, &tight);
    let held = tight.usage().unwrap().live_bytes;
    assert!(matches!(
        biconnectivity(&projection),
        Err(AlgorithmError::BudgetExceeded {
            resource: "work",
            ..
        })
    ));
    assert_eq!(tight.usage().unwrap().live_bytes, held);
}
