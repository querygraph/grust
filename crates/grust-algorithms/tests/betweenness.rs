//! Betweenness against an all-pairs definition that counts shortest paths.

use grust_algorithms::{
    AlgorithmError, BetweennessOptions, ExecutionContext, ExecutionLimits, GraphProjection,
    Orientation, ProjectionEdge, SnapshotIdentity, betweenness,
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

/// The definition, with no traversal in it: all-pairs distances by
/// Floyd-Warshall, path counts by summing over last arcs, then the pair sum.
fn by_definition(
    n: usize,
    edges: &[(usize, usize)],
    weights: Option<&[f64]>,
    orientation: Orientation,
) -> Vec<f64> {
    let mut arcs = Vec::new();
    for (index, &(a, b)) in edges.iter().enumerate() {
        let w = weights.map_or(1.0, |w| w[index]);
        if a == b {
            continue;
        }
        match orientation {
            Orientation::Outgoing => arcs.push((a, b, w)),
            Orientation::Incoming => arcs.push((b, a, w)),
            Orientation::Undirected => {
                arcs.push((a, b, w));
                arcs.push((b, a, w));
            }
        }
    }
    let mut dist = vec![vec![f64::INFINITY; n]; n];
    for (v, row) in dist.iter_mut().enumerate() {
        row[v] = 0.0;
    }
    for &(a, b, w) in &arcs {
        dist[a][b] = dist[a][b].min(w);
    }
    for k in 0..n {
        for i in 0..n {
            for j in 0..n {
                let through = dist[i][k] + dist[k][j];
                if through < dist[i][j] {
                    dist[i][j] = through;
                }
            }
        }
    }
    let mut sigma = vec![vec![0.0f64; n]; n];
    for s in 0..n {
        let mut order: Vec<usize> = (0..n).filter(|&t| dist[s][t].is_finite()).collect();
        order.sort_by(|&a, &b| dist[s][a].total_cmp(&dist[s][b]));
        sigma[s][s] = 1.0;
        for &t in &order {
            if t == s {
                continue;
            }
            sigma[s][t] = arcs
                .iter()
                .filter(|&&(u, v, w)| v == t && dist[s][u] + w == dist[s][t])
                .map(|&(u, _, _)| sigma[s][u])
                .sum();
        }
    }
    let mut scores = vec![0.0; n];
    for s in 0..n {
        for t in 0..n {
            if s == t || sigma[s][t] == 0.0 {
                continue;
            }
            for v in 0..n {
                if v != s && v != t && dist[s][v] + dist[v][t] == dist[s][t] {
                    scores[v] += sigma[s][v] * sigma[v][t] / sigma[s][t];
                }
            }
        }
    }
    if orientation == Orientation::Undirected {
        for score in &mut scores {
            *score /= 2.0;
        }
    }
    scores
}

fn assert_close(actual: &[f64], expected: &[f64], what: &str) {
    assert_eq!(actual.len(), expected.len(), "{what}");
    for (row, (a, e)) in actual.iter().zip(expected).enumerate() {
        assert!(
            (a - e).abs() <= 1e-9 * (1.0 + e.abs()),
            "{what}: row {row} is {a}, the definition says {e}"
        );
    }
}

fn check(n: usize, edges: &[(usize, usize)], weights: Option<&[f64]>) {
    for orientation in ORIENTATIONS {
        let context = context();
        let result = betweenness(
            &graph(n, edges, weights, orientation, &context),
            BetweennessOptions::default(),
        )
        .unwrap();
        assert_close(
            result.values(),
            &by_definition(n, edges, weights, orientation),
            &format!("{orientation:?} {edges:?} {weights:?}"),
        );
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

#[test]
fn betweenness_matches_the_definition_on_every_small_graph() {
    let mut checked = 0;
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
            check(n, &edges, None);
            checked += 3;
        }
    }
    assert_eq!(checked, 3 * (1 + 1 + 2 + 8 + 64 + 1024));
}

#[test]
fn betweenness_matches_the_definition_on_random_multigraphs_with_and_without_weights() {
    let mut random = Xorshift(0x2545_F491_4F6C_DD1D);
    for round in 0..1500 {
        let n = 2 + random.below(8);
        let count = random.below(3 * n);
        // Any pair, in either direction, repeated or looping.
        let edges: Vec<_> = (0..count)
            .map(|_| (random.below(n), random.below(n)))
            .collect();
        if round % 2 == 0 {
            check(n, &edges, None);
        } else {
            // Small integers: sums are exact, so ties are real ties.
            let weights: Vec<f64> = (0..count).map(|_| (1 + random.below(3)) as f64).collect();
            check(n, &edges, Some(&weights));
        }
    }
}

#[test]
fn betweenness_states_its_textbook_values() {
    let context = context();
    // A path 0-1-2-3-4: the middle lies between 2*2 pairs, its neighbours 1*3.
    let path = [(0, 1), (1, 2), (2, 3), (3, 4)];
    let undirected = betweenness(
        &graph(5, &path, None, Orientation::Undirected, &context),
        BetweennessOptions::default(),
    )
    .unwrap();
    assert_eq!(undirected.values(), [0.0, 3.0, 4.0, 3.0, 0.0]);
    let directed = betweenness(
        &graph(5, &path, None, Orientation::Outgoing, &context),
        BetweennessOptions::default(),
    )
    .unwrap();
    assert_eq!(directed.values(), [0.0, 3.0, 4.0, 3.0, 0.0]);

    // A star's hub lies between every pair of leaves; normalised, that is 1.
    let star = [(0, 1), (0, 2), (0, 3), (0, 4)];
    let normalized = betweenness(
        &graph(5, &star, None, Orientation::Undirected, &context),
        BetweennessOptions {
            normalized: true,
            ..Default::default()
        },
    )
    .unwrap();
    assert_eq!(normalized.values(), [1.0, 0.0, 0.0, 0.0, 0.0]);

    // Parallel edges are distinct shortest paths: two of the three 0-3 routes
    // pass through 1.
    let doubled = [(0, 1), (0, 1), (0, 2), (1, 3), (2, 3)];
    let result = betweenness(
        &graph(4, &doubled, None, Orientation::Outgoing, &context),
        BetweennessOptions::default(),
    )
    .unwrap();
    assert_close(
        result.values(),
        &[0.0, 2.0 / 3.0, 1.0 / 3.0, 0.0],
        "parallel edges",
    );

    // Fewer than three nodes: nothing is between anything, normalised or not.
    let pair = betweenness(
        &graph(2, &[(0, 1)], None, Orientation::Undirected, &context),
        BetweennessOptions {
            normalized: true,
            ..Default::default()
        },
    )
    .unwrap();
    assert_eq!(pair.values(), [0.0, 0.0]);
}

#[test]
fn betweenness_rejects_zero_weights_and_an_empty_sample() {
    let context = context();
    let projection = graph(
        3,
        &[(0, 1), (1, 2)],
        Some(&[1.0, 0.0]),
        Orientation::Outgoing,
        &context,
    );
    let held = context.usage().unwrap().live_bytes;
    assert!(matches!(
        betweenness(&projection, BetweennessOptions::default()),
        Err(AlgorithmError::InvalidArguments(message)) if message.contains("zero weight")
    ));
    assert!(matches!(
        betweenness(
            &projection,
            BetweennessOptions {
                sampling_size: Some(0),
                ..Default::default()
            }
        ),
        Err(AlgorithmError::InvalidArguments(_))
    ));
    assert_eq!(context.usage().unwrap().live_bytes, held);
}

fn scrambled(n: usize, edges: usize) -> Vec<(usize, usize)> {
    let mut random = Xorshift(0x9E37_79B9_7F4A_7C15);
    (0..edges)
        .map(|_| {
            let a = random.below(n);
            let b = random.below(n).pow(2) / n;
            (a, b)
        })
        .collect()
}

#[test]
fn a_sample_of_every_node_is_the_exact_answer_and_a_smaller_one_is_seeded() {
    let edges = scrambled(300, 1500);
    let context = context();
    let projection = graph(300, &edges, None, Orientation::Outgoing, &context);
    let exact = betweenness(&projection, BetweennessOptions::default()).unwrap();
    for size in [300, 5000] {
        let all = betweenness(
            &projection,
            BetweennessOptions {
                sampling_size: Some(size),
                seed: 7,
                ..Default::default()
            },
        )
        .unwrap();
        assert_eq!(all.values(), exact.values());
    }
    let sample = |seed| {
        betweenness(
            &projection,
            BetweennessOptions {
                sampling_size: Some(60),
                seed,
                ..Default::default()
            },
        )
        .unwrap()
        .values()
        .to_vec()
    };
    assert_eq!(sample(1), sample(1));
    assert_ne!(sample(1), sample(2));
    // The estimate is scaled to the exact total, not a fifth of it.
    let total: f64 = exact.values().iter().sum();
    let estimated: f64 = sample(1).iter().sum();
    assert!(
        (estimated / total - 1.0).abs() < 0.5,
        "{estimated} vs {total}"
    );
}

#[test]
fn betweenness_is_identical_at_any_pool_width_and_charges_the_same_work() {
    let edges = scrambled(500, 3000);
    let weights: Vec<f64> = (0..edges.len()).map(|i| (1 + i % 4) as f64).collect();
    for weighted in [false, true] {
        let run = |threads: usize| {
            let context = context().with_concurrency(threads).unwrap();
            let projection = graph(
                500,
                &edges,
                weighted.then_some(&weights[..]),
                Orientation::Undirected,
                &context,
            );
            let before = context.usage().unwrap().counted_work().expect("counted");
            let result = betweenness(&projection, BetweennessOptions::default()).unwrap();
            let work = context.usage().unwrap().counted_work().expect("counted") - before;
            let bits: Vec<u64> = result.values().iter().map(|v| v.to_bits()).collect();
            (bits, work)
        };
        let (bits, work) = run(1);
        for threads in [2, 3, 8] {
            let (other, other_work) = run(threads);
            assert_eq!(other, bits, "{threads} threads, weighted {weighted}");
            assert_eq!(other_work, work, "{threads} threads charged differently");
        }
    }
}

#[test]
fn betweenness_observes_cancellation_and_budget_and_releases_scratch() {
    let edges = scrambled(300, 3000);
    let context = context();
    let projection = graph(300, &edges, None, Orientation::Undirected, &context);
    let projection_work = context.usage().unwrap().counted_work().expect("counted");
    let held = context.usage().unwrap().live_bytes;
    context.cancel().unwrap();
    assert!(matches!(
        betweenness(&projection, BetweennessOptions::default()),
        Err(AlgorithmError::Cancelled)
    ));
    assert_eq!(context.usage().unwrap().live_bytes, held);

    let tight = ExecutionContext::new(limits(projection_work + 50_000)).unwrap();
    let projection = graph(300, &edges, None, Orientation::Undirected, &tight);
    let held = tight.usage().unwrap().live_bytes;
    assert!(matches!(
        betweenness(&projection, BetweennessOptions::default()),
        Err(AlgorithmError::BudgetExceeded {
            resource: "work",
            ..
        })
    ));
    assert_eq!(tight.usage().unwrap().live_bytes, held);
}
