//! Closeness and harmonic centrality against Floyd-Warshall distances.

use grust_algorithms::{
    AlgorithmError, ClosenessOptions, ExecutionContext, ExecutionLimits, GraphProjection,
    HarmonicOptions, Orientation, ProjectionEdge, SnapshotIdentity, closeness, harmonic,
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

fn distances(
    n: usize,
    edges: &[(usize, usize)],
    weights: Option<&[f64]>,
    orientation: Orientation,
) -> Vec<Vec<f64>> {
    let mut dist = vec![vec![f64::INFINITY; n]; n];
    for (v, row) in dist.iter_mut().enumerate() {
        row[v] = 0.0;
    }
    for (index, &(a, b)) in edges.iter().enumerate() {
        let w = weights.map_or(1.0, |w| w[index]);
        if orientation != Orientation::Incoming {
            dist[a][b] = dist[a][b].min(w);
        }
        if orientation != Orientation::Outgoing {
            dist[b][a] = dist[b][a].min(w);
        }
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
    dist
}

/// (closeness, Wasserman-Faust closeness, harmonic, normalised harmonic).
fn by_definition(dist: &[Vec<f64>]) -> [Vec<f64>; 4] {
    let n = dist.len();
    let mut out = [vec![], vec![], vec![], vec![]];
    for (v, row) in dist.iter().enumerate() {
        let reachable: Vec<f64> = row
            .iter()
            .enumerate()
            .filter(|&(u, d)| u != v && d.is_finite())
            .map(|(_, &d)| d)
            .collect();
        let r = reachable.len() as f64;
        let sum: f64 = reachable.iter().sum();
        let plain = if reachable.is_empty() { 0.0 } else { r / sum };
        let reciprocal: f64 = reachable.iter().map(|d| 1.0 / d).sum();
        out[0].push(plain);
        out[1].push(if reachable.is_empty() {
            0.0
        } else {
            plain * r / (n as f64 - 1.0)
        });
        out[2].push(reciprocal);
        out[3].push(if n > 1 {
            reciprocal / (n as f64 - 1.0)
        } else {
            reciprocal
        });
    }
    out
}

fn assert_close(actual: &[f64], expected: &[f64], what: &str) {
    assert_eq!(actual.len(), expected.len(), "{what}");
    for (row, (a, e)) in actual.iter().zip(expected).enumerate() {
        assert!(
            (a - e).abs() <= 1e-12 * (1.0 + e.abs()),
            "{what}: row {row} is {a}, the definition says {e}"
        );
    }
}

fn check(n: usize, edges: &[(usize, usize)], weights: Option<&[f64]>) {
    for orientation in ORIENTATIONS {
        let context = context();
        let projection = graph(n, edges, weights, orientation, &context);
        let expected = by_definition(&distances(n, edges, weights, orientation));
        let what = format!("{orientation:?} {edges:?} {weights:?}");
        for (index, wasserman_faust) in [false, true].into_iter().enumerate() {
            let result = closeness(&projection, ClosenessOptions { wasserman_faust }).unwrap();
            assert_close(result.values(), &expected[index], &what);
        }
        for (index, normalized) in [false, true].into_iter().enumerate() {
            let result = harmonic(&projection, HarmonicOptions { normalized }).unwrap();
            assert_close(result.values(), &expected[2 + index], &what);
        }
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
fn distance_centralities_match_the_definition_on_every_small_graph() {
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
        }
    }
}

#[test]
fn distance_centralities_match_on_random_multigraphs_up_to_forty_nodes() {
    let mut random = Xorshift(0x2545_F491_4F6C_DD1D);
    for round in 0..600 {
        let n = 2 + random.below(39);
        let count = random.below(3 * n);
        let edges: Vec<_> = (0..count)
            .map(|_| (random.below(n), random.below(n)))
            .collect();
        if round % 2 == 0 {
            check(n, &edges, None);
        } else {
            let weights: Vec<f64> = (0..count)
                .map(|_| (1 + random.below(8)) as f64 / 4.0)
                .collect();
            check(n, &edges, Some(&weights));
        }
    }
}

#[test]
fn distance_centralities_state_their_textbook_values() {
    let context = context();
    // A path 0-1-2 and a separate pair 3-4.
    let edges = [(0, 1), (1, 2), (3, 4)];
    let projection = graph(6, &edges, None, Orientation::Undirected, &context);
    let plain = closeness(&projection, ClosenessOptions::default()).unwrap();
    // Per component: the pair scores 1, as high as the path's centre.
    assert_eq!(plain.values(), [2.0 / 3.0, 1.0, 2.0 / 3.0, 1.0, 1.0, 0.0]);
    let corrected = closeness(
        &projection,
        ClosenessOptions {
            wasserman_faust: true,
        },
    )
    .unwrap();
    // Wasserman-Faust: scaled by reached / (n-1), so the pair drops below it.
    assert_eq!(
        corrected.values(),
        [4.0 / 15.0, 2.0 / 5.0, 4.0 / 15.0, 1.0 / 5.0, 1.0 / 5.0, 0.0]
    );
    let raw = harmonic(&projection, HarmonicOptions { normalized: false }).unwrap();
    assert_eq!(raw.values(), [1.5, 2.0, 1.5, 1.0, 1.0, 0.0]);
    let normalized = harmonic(&projection, HarmonicOptions::default()).unwrap();
    assert_eq!(normalized.values()[1], 2.0 / 5.0);

    // Distances run from the node: a chain's head reaches everything, its tail nothing.
    let chain = graph(3, &[(0, 1), (1, 2)], None, Orientation::Outgoing, &context);
    assert_eq!(
        closeness(&chain, ClosenessOptions::default())
            .unwrap()
            .values(),
        [2.0 / 3.0, 1.0, 0.0]
    );
    let reversed = graph(3, &[(0, 1), (1, 2)], None, Orientation::Incoming, &context);
    assert_eq!(
        closeness(&reversed, ClosenessOptions::default())
            .unwrap()
            .values(),
        [0.0, 1.0, 2.0 / 3.0]
    );

    // One node: nothing to be close to, and no division by n-1 = 0.
    let single = graph(1, &[], None, Orientation::Undirected, &context);
    assert_eq!(
        harmonic(&single, HarmonicOptions::default())
            .unwrap()
            .values(),
        [0.0]
    );
    assert_eq!(
        closeness(
            &single,
            ClosenessOptions {
                wasserman_faust: true
            }
        )
        .unwrap()
        .values(),
        [0.0]
    );
}

#[test]
fn distance_centralities_reject_zero_weights() {
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
        closeness(&projection, ClosenessOptions::default()),
        Err(AlgorithmError::InvalidArguments(message)) if message.contains("zero distance")
    ));
    assert!(matches!(
        harmonic(&projection, HarmonicOptions::default()),
        Err(AlgorithmError::InvalidArguments(_))
    ));
    assert_eq!(context.usage().unwrap().live_bytes, held);
}

fn scrambled(n: usize, edges: usize) -> Vec<(usize, usize)> {
    let mut random = Xorshift(0x9E37_79B9_7F4A_7C15);
    (0..edges)
        .map(|_| (random.below(n), random.below(n).pow(2) / n))
        .collect()
}

#[test]
fn distance_centralities_are_identical_at_any_pool_width_and_charge_the_same_work() {
    let edges = scrambled(500, 3000);
    let weights: Vec<f64> = (0..edges.len()).map(|i| (1 + i % 7) as f64 / 3.0).collect();
    for weighted in [false, true] {
        let run = |threads: usize| {
            let pool = rayon::ThreadPoolBuilder::new()
                .num_threads(threads)
                .build()
                .unwrap();
            pool.install(|| {
                let context = context();
                let projection = graph(
                    500,
                    &edges,
                    weighted.then_some(&weights[..]),
                    Orientation::Outgoing,
                    &context,
                );
                let before = context.usage().unwrap().work_units;
                let close = closeness(&projection, ClosenessOptions::default()).unwrap();
                let harm = harmonic(&projection, HarmonicOptions::default()).unwrap();
                let work = context.usage().unwrap().work_units - before;
                let bits: Vec<u64> = close
                    .values()
                    .iter()
                    .chain(harm.values())
                    .map(|v| v.to_bits())
                    .collect();
                (bits, work)
            })
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
fn distance_centralities_observe_cancellation_and_budget_and_release_scratch() {
    let edges = scrambled(300, 3000);
    let context = context();
    let projection = graph(300, &edges, None, Orientation::Undirected, &context);
    let projection_work = context.usage().unwrap().work_units;
    let held = context.usage().unwrap().live_bytes;
    context.cancel().unwrap();
    assert!(matches!(
        closeness(&projection, ClosenessOptions::default()),
        Err(AlgorithmError::Cancelled)
    ));
    assert_eq!(context.usage().unwrap().live_bytes, held);

    let tight = ExecutionContext::new(limits(projection_work + 50_000)).unwrap();
    let projection = graph(300, &edges, None, Orientation::Undirected, &tight);
    let held = tight.usage().unwrap().live_bytes;
    assert!(matches!(
        harmonic(&projection, HarmonicOptions::default()),
        Err(AlgorithmError::BudgetExceeded {
            resource: "work",
            ..
        })
    ));
    assert_eq!(tight.usage().unwrap().live_bytes, held);
}
