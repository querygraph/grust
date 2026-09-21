//! Spanning forests against an exhaustive search over edge subsets.

use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, Orientation,
    ProjectionEdge, SnapshotIdentity, SpanningObjective, SpanningTreeOptions, spanning_tree,
};

fn limits(work_units: usize) -> ExecutionLimits {
    ExecutionLimits {
        memory_bytes: 256 * 1024 * 1024,
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
                // Descending, so "smaller ordinal" is not "earlier slot".
                ordinal: usize::MAX / 2 - ordinal,
                id: None,
            })
            .collect(),
        weights.map(<[f64]>::to_vec),
        orientation,
        context,
    )
    .unwrap()
}

fn find(parent: &mut [usize], mut x: usize) -> usize {
    while parent[x] != x {
        parent[x] = parent[parent[x]];
        x = parent[x];
    }
    x
}

/// Components, or `None` if the chosen edges contain a cycle.
fn forest_components(n: usize, edges: &[(usize, usize)], chosen: &[usize]) -> Option<usize> {
    let mut parent: Vec<usize> = (0..n).collect();
    for &slot in chosen {
        let (a, b) = (
            find(&mut parent, edges[slot].0),
            find(&mut parent, edges[slot].1),
        );
        if a == b {
            return None;
        }
        parent[a] = b;
    }
    Some((0..n).filter(|&v| find(&mut parent, v) == v).count())
}

/// Of all spanning forests, the one whose edges, ranked by (weight, ordinal) and
/// sorted, come first: the greedy basis, found without being greedy.
fn by_search(
    n: usize,
    edges: &[(usize, usize)],
    weights: Option<&[f64]>,
    maximum: bool,
) -> Vec<usize> {
    let mut ranked: Vec<usize> = (0..edges.len()).collect();
    ranked.sort_by(|&a, &b| {
        let (wa, wb) = (weights.map_or(1.0, |w| w[a]), weights.map_or(1.0, |w| w[b]));
        let by_weight = if maximum {
            wb.total_cmp(&wa)
        } else {
            wa.total_cmp(&wb)
        };
        // Ordinals descend with the slot.
        by_weight.then(b.cmp(&a))
    });
    let mut rank = vec![0; edges.len()];
    for (position, &slot) in ranked.iter().enumerate() {
        rank[slot] = position;
    }
    let all: Vec<usize> = (0..edges.len()).collect();
    let pieces = {
        let mut parent: Vec<usize> = (0..n).collect();
        for &(a, b) in edges {
            let (a, b) = (find(&mut parent, a), find(&mut parent, b));
            parent[a] = b;
        }
        (0..n).filter(|&v| find(&mut parent, v) == v).count()
    };
    let mut best: Option<(Vec<usize>, Vec<usize>)> = None;
    for mask in 0u32..1 << edges.len() {
        let chosen: Vec<usize> = all.iter().copied().filter(|s| mask >> s & 1 == 1).collect();
        if forest_components(n, edges, &chosen) != Some(pieces) {
            continue;
        }
        let mut key: Vec<usize> = chosen.iter().map(|&slot| rank[slot]).collect();
        key.sort_unstable();
        if best.as_ref().is_none_or(|(least, _)| key < *least) {
            best = Some((key, chosen));
        }
    }
    best.unwrap().1
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
fn the_forest_is_the_one_an_exhaustive_search_finds() {
    let mut random = Xorshift(0x2545_F491_4F6C_DD1D);
    for round in 0..1500 {
        let n = 1 + random.below(7);
        let count = random.below(11);
        let edges: Vec<_> = (0..count)
            .map(|_| (random.below(n), random.below(n)))
            .collect();
        // Few distinct weights, so ties are the rule.
        let weights: Vec<f64> = (0..count).map(|_| random.below(3) as f64).collect();
        let weights = (round % 3 != 0).then_some(&weights[..]);
        for objective in [SpanningObjective::Minimum, SpanningObjective::Maximum] {
            let context = context();
            let result = spanning_tree(
                &graph(n, &edges, weights, Orientation::Undirected, &context),
                SpanningTreeOptions {
                    objective,
                    source: None,
                },
            )
            .unwrap();
            let expected = by_search(n, &edges, weights, objective == SpanningObjective::Maximum);
            assert_eq!(
                result.edges(),
                expected,
                "{objective:?} {edges:?} {weights:?}"
            );
            let total: f64 = expected
                .iter()
                .map(|&s| weights.map_or(1.0, |w| w[s]))
                .sum();
            assert_eq!(result.total_weight(), total);
            assert_eq!(result.weights().len(), expected.len());
        }
    }
}

#[test]
fn a_source_keeps_the_tree_of_its_own_component() {
    let context = context();
    // Two components: a weighted triangle 0-1-2 and an edge 3-4; 5 is alone.
    let edges = [(0, 1), (1, 2), (2, 0), (3, 4)];
    let weights = [5.0, 1.0, 2.0, 7.0];
    let projection = graph(6, &edges, Some(&weights), Orientation::Undirected, &context);
    let with = |objective, source| {
        let result = spanning_tree(&projection, SpanningTreeOptions { objective, source }).unwrap();
        (result.edges().to_vec(), result.total_weight())
    };
    assert_eq!(
        with(SpanningObjective::Minimum, None),
        (vec![1, 2, 3], 10.0)
    );
    assert_eq!(
        with(SpanningObjective::Maximum, None),
        (vec![0, 2, 3], 14.0)
    );
    assert_eq!(
        with(SpanningObjective::Minimum, Some("n2")),
        (vec![1, 2], 3.0)
    );
    assert_eq!(with(SpanningObjective::Minimum, Some("n4")), (vec![3], 7.0));
    assert_eq!(with(SpanningObjective::Minimum, Some("n5")), (vec![], 0.0));
    assert!(matches!(
        spanning_tree(
            &projection,
            SpanningTreeOptions {
                source: Some("nowhere"),
                ..Default::default()
            }
        ),
        Err(AlgorithmError::InvalidArguments(_))
    ));
    assert!(matches!(
        spanning_tree(
            &graph(2, &[(0, 1)], None, Orientation::Outgoing, &context),
            SpanningTreeOptions::default()
        ),
        Err(AlgorithmError::InvalidArguments(message)) if message.contains("undirected")
    ));
}

#[test]
fn the_forest_is_identical_at_any_pool_width_and_charges_the_same_work() {
    let mut random = Xorshift(0x9E37_79B9_7F4A_7C15);
    let n = 20_000;
    let edges: Vec<_> = (0..120_000)
        .map(|_| (random.below(n), random.below(n)))
        .collect();
    let weights: Vec<f64> = (0..edges.len()).map(|_| random.below(50) as f64).collect();
    let run = |threads: usize| {
        let context = context().with_concurrency(threads).unwrap();
        let projection = graph(n, &edges, Some(&weights), Orientation::Undirected, &context);
        let before = context.usage().unwrap().counted_work().expect("counted");
        let result = spanning_tree(&projection, SpanningTreeOptions::default()).unwrap();
        (
            result.edges().to_vec(),
            result.total_weight().to_bits(),
            context.usage().unwrap().counted_work().expect("counted") - before,
        )
    };
    let first = run(1);
    assert!(first.0.len() > 19_000);
    for threads in [2, 8] {
        assert_eq!(run(threads), first, "{threads} threads");
    }
}

#[test]
fn spanning_tree_observes_cancellation_and_budget_and_releases_scratch() {
    let edges: Vec<_> = (1..5000).map(|node| (node / 2, node)).collect();
    let context = context();
    let projection = graph(5000, &edges, None, Orientation::Undirected, &context);
    let projection_work = context.usage().unwrap().counted_work().expect("counted");
    let held = context.usage().unwrap().live_bytes;
    context.cancel().unwrap();
    assert!(matches!(
        spanning_tree(&projection, SpanningTreeOptions::default()),
        Err(AlgorithmError::Cancelled)
    ));
    assert_eq!(context.usage().unwrap().live_bytes, held);

    let tight = ExecutionContext::new(limits(projection_work + 3000)).unwrap();
    let projection = graph(5000, &edges, None, Orientation::Undirected, &tight);
    let held = tight.usage().unwrap().live_bytes;
    assert!(matches!(
        spanning_tree(&projection, SpanningTreeOptions::default()),
        Err(AlgorithmError::BudgetExceeded {
            resource: "work",
            ..
        })
    ));
    assert_eq!(tight.usage().unwrap().live_bytes, held);
}
