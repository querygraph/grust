//! Eigenvector, Katz and HITS against dense linear algebra done in the test.

use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, IterationOptions,
    KatzOptions, Orientation, ProjectionEdge, SnapshotIdentity, eigenvector, hits, katz,
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

/// `m[v][u]`: total weight of arcs u -> v, so `m x` pulls along arcs.
fn pull_matrix(
    n: usize,
    edges: &[(usize, usize)],
    weights: Option<&[f64]>,
    orientation: Orientation,
) -> Vec<Vec<f64>> {
    let mut m = vec![vec![0.0; n]; n];
    for (index, &(a, b)) in edges.iter().enumerate() {
        let w = weights.map_or(1.0, |w| w[index]);
        match orientation {
            Orientation::Outgoing => m[b][a] += w,
            Orientation::Incoming => m[a][b] += w,
            Orientation::Undirected => {
                m[b][a] += w;
                if a != b {
                    m[a][b] += w;
                }
            }
        }
    }
    m
}

fn times(m: &[Vec<f64>], x: &[f64]) -> Vec<f64> {
    m.iter()
        .map(|row| row.iter().zip(x).map(|(a, b)| a * b).sum())
        .collect()
}

fn transposed(m: &[Vec<f64>]) -> Vec<Vec<f64>> {
    (0..m.len())
        .map(|i| (0..m.len()).map(|j| m[j][i]).collect())
        .collect()
}

fn dot(a: &[f64], b: &[f64]) -> f64 {
    a.iter().zip(b).map(|(x, y)| x * y).sum()
}

/// `m x = λ x` with `λ = x·mx`, for a unit `x`; zero vectors pass trivially.
fn assert_eigenvector(m: &[Vec<f64>], x: &[f64], what: &str) {
    let mx = times(m, x);
    let lambda = dot(x, &mx);
    for (row, (&left, &value)) in mx.iter().zip(x).enumerate() {
        assert!(
            (left - lambda * value).abs() <= 1e-6 * (1.0 + lambda),
            "{what}: row {row}: (Mx) = {left}, λx = {}",
            lambda * value
        );
    }
}

fn assert_unit_nonnegative(x: &[f64], what: &str) {
    assert!(x.iter().all(|&v| v >= 0.0), "{what}: {x:?}");
    assert!((dot(x, x).sqrt() - 1.0).abs() < 1e-12, "{what}: {x:?}");
}

/// Solve `(I - alpha m) x = beta` by Gaussian elimination with pivoting.
fn katz_by_elimination(m: &[Vec<f64>], alpha: f64, beta: f64) -> Vec<f64> {
    let n = m.len();
    let mut a: Vec<Vec<f64>> = (0..n)
        .map(|i| {
            let mut row: Vec<f64> = (0..n)
                .map(|j| f64::from(u8::from(i == j)) - alpha * m[i][j])
                .collect();
            row.push(beta);
            row
        })
        .collect();
    for column in 0..n {
        let pivot = (column..n)
            .max_by(|&i, &j| a[i][column].abs().total_cmp(&a[j][column].abs()))
            .unwrap();
        a.swap(column, pivot);
        for row in 0..n {
            if row != column {
                let factor = a[row][column] / a[column][column];
                let pivot_row = a[column].clone();
                for (value, pivot) in a[row].iter_mut().zip(&pivot_row).skip(column) {
                    *value -= factor * pivot;
                }
            }
        }
    }
    (0..n).map(|i| a[i][n] / a[i][i]).collect()
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
fn converged_runs_satisfy_their_defining_equations() {
    let mut random = Xorshift(0x2545_F491_4F6C_DD1D);
    let (mut eigen, mut hubs) = (0, 0);
    for round in 0..600 {
        let n = 1 + random.below(10);
        let count = random.below(4 * n);
        let edges: Vec<_> = (0..count)
            .map(|_| (random.below(n), random.below(n)))
            .collect();
        let weights: Vec<f64> = (0..count).map(|_| (1 + random.below(4)) as f64).collect();
        let weights = (round % 2 == 1).then_some(&weights[..]);
        for orientation in ORIENTATIONS {
            let what = format!("{orientation:?} {edges:?} {weights:?}");
            let context = context();
            let projection = graph(n, &edges, weights, orientation, &context);
            let m = pull_matrix(n, &edges, weights, orientation);

            let result = eigenvector(&projection, IterationOptions::default()).unwrap();
            let x = result.values("score").unwrap();
            assert_unit_nonnegative(x, &what);
            if result.converged() {
                assert_eigenvector(&m, x, &what);
                eigen += 1;
            } else {
                assert_eq!(result.iterations(), 1000, "{what}");
            }

            let result = hits(&projection, IterationOptions::default()).unwrap();
            let (hub, authority) = (
                result.values("hub").unwrap(),
                result.values("authority").unwrap(),
            );
            if count > 0 && m.iter().flatten().any(|&w| w > 0.0) {
                assert_unit_nonnegative(hub, &what);
                assert_unit_nonnegative(authority, &what);
            }
            if result.converged() {
                // Authorities are an eigenvector of M Mᵀ, hubs of Mᵀ M.
                let mt = transposed(&m);
                // Column i of M Mᵀ is M times row i of M; both products are symmetric.
                let mmt: Vec<Vec<f64>> = (0..n).map(|i| times(&m, &m[i])).collect();
                let mtm: Vec<Vec<f64>> = (0..n).map(|i| times(&mt, &mt[i])).collect();
                assert_eigenvector(&mmt, authority, &what);
                assert_eigenvector(&mtm, hub, &what);
                hubs += 1;
            }

            // An alpha under the sufficient bound always converges to the solve.
            let strongest = m
                .iter()
                .map(|row| row.iter().sum::<f64>())
                .fold(0.0, f64::max);
            let alpha = 0.5 / strongest.max(1.0);
            let options = KatzOptions {
                alpha,
                beta: 1.5,
                ..Default::default()
            };
            let result = katz(&projection, options).unwrap();
            assert!(result.converged(), "{what}");
            let expected = katz_by_elimination(&m, alpha, 1.5);
            for (row, (a, e)) in result
                .values("score")
                .unwrap()
                .iter()
                .zip(&expected)
                .enumerate()
            {
                assert!(
                    (a - e).abs() <= 1e-6 * (1.0 + e.abs()),
                    "{what}: row {row}: {a} vs {e}"
                );
            }
        }
    }
    assert!(
        eigen > 800 && hubs > 1500,
        "{eigen} eigenvector and {hubs} HITS runs converged"
    );
}

#[test]
fn the_textbook_cases_are_as_documented() {
    let context = context();
    // A star is bipartite: plain power iteration oscillates, the shifted one
    // converges. Hub to leaf is sqrt(leaves) to one.
    let star = [(0, 1), (0, 2), (0, 3), (0, 4)];
    let result = eigenvector(
        &graph(5, &star, None, Orientation::Undirected, &context),
        IterationOptions::default(),
    )
    .unwrap();
    assert!(result.converged());
    let x = result.values("score").unwrap();
    assert!((x[0] / x[1] - 2.0).abs() < 1e-6, "{x:?}");
    assert!((x[1] - x[4]).abs() < 1e-12);

    // Directed: influence flows along arcs, so the pointed-at node gains.
    let result = katz(
        &graph(3, &[(0, 2), (1, 2)], None, Orientation::Outgoing, &context),
        KatzOptions::default(),
    )
    .unwrap();
    assert_eq!(result.values("score").unwrap(), [1.0, 1.0, 1.2]);
    let normalized = katz(
        &graph(3, &[(0, 2), (1, 2)], None, Orientation::Outgoing, &context),
        KatzOptions {
            normalized: true,
            ..Default::default()
        },
    )
    .unwrap();
    let x = normalized.values("score").unwrap();
    assert!((dot(x, x) - 1.0).abs() < 1e-12);

    // HITS: 0 and 1 point at 2. They are the hubs, 2 the authority.
    let result = hits(
        &graph(3, &[(0, 2), (1, 2)], None, Orientation::Outgoing, &context),
        IterationOptions::default(),
    )
    .unwrap();
    assert!(result.converged());
    let half = 0.5f64.sqrt();
    let close = |a: &[f64], e: [f64; 3]| a.iter().zip(e).all(|(a, e)| (a - e).abs() < 1e-9);
    assert!(close(result.values("hub").unwrap(), [half, half, 0.0]));
    assert!(close(result.values("authority").unwrap(), [0.0, 0.0, 1.0]));

    // No arcs: HITS is zero everywhere, eigenvector stays uniform, both settle.
    let empty = graph(4, &[], None, Orientation::Outgoing, &context);
    let result = hits(&empty, IterationOptions::default()).unwrap();
    assert!(result.converged());
    assert_eq!(result.values("authority").unwrap(), [0.0; 4]);
    let result = eigenvector(&empty, IterationOptions::default()).unwrap();
    assert!(result.converged());
    assert_eq!(result.values("score").unwrap(), [0.5; 4]);
}

#[test]
fn a_katz_alpha_that_is_too_large_is_reported_not_hidden() {
    let context = context();
    // A triangle has λmax = 2, so alpha must be below 0.5.
    let triangle = graph(
        3,
        &[(0, 1), (1, 2), (2, 0)],
        None,
        Orientation::Undirected,
        &context,
    );
    let with = |alpha, max_iterations| {
        katz(
            &triangle,
            KatzOptions {
                alpha,
                iteration: IterationOptions {
                    max_iterations,
                    ..Default::default()
                },
                ..Default::default()
            },
        )
    };
    assert!(with(0.45, 1000).unwrap().converged());
    let stalled = with(0.5, 50).unwrap();
    assert!(!stalled.converged() && stalled.iterations() == 50);
    assert!(matches!(
        with(3.0, 5000),
        Err(AlgorithmError::Numerical(message)) if message.contains("alpha")
    ));
    for options in [
        KatzOptions {
            alpha: 0.0,
            ..Default::default()
        },
        KatzOptions {
            beta: f64::NAN,
            ..Default::default()
        },
    ] {
        assert!(matches!(
            katz(&triangle, options),
            Err(AlgorithmError::InvalidArguments(_))
        ));
    }
    assert!(matches!(
        eigenvector(
            &triangle,
            IterationOptions {
                max_iterations: 0,
                ..Default::default()
            }
        ),
        Err(AlgorithmError::InvalidArguments(_))
    ));
}

fn scrambled(n: usize, edges: usize) -> Vec<(usize, usize)> {
    let mut random = Xorshift(0x9E37_79B9_7F4A_7C15);
    (0..edges)
        .map(|_| (random.below(n), random.below(n).pow(2) / n))
        .collect()
}

#[test]
fn the_iterations_are_identical_at_any_pool_width_and_charge_the_same_work() {
    // More than one chunk of 4096, so the chunked sums are exercised.
    let n = 10_000;
    let edges = scrambled(n, 60_000);
    let weights: Vec<f64> = (0..edges.len()).map(|i| (1 + i % 7) as f64 / 3.0).collect();
    let run = |threads: usize| {
        let context = context().with_concurrency(threads).unwrap();
        let projection = graph(n, &edges, Some(&weights), Orientation::Outgoing, &context);
        let before = context.usage().unwrap().work_units;
        let options = IterationOptions {
            max_iterations: 30,
            ..Default::default()
        };
        let results = [
            eigenvector(&projection, options).unwrap(),
            hits(&projection, options).unwrap(),
            katz(
                &projection,
                KatzOptions {
                    alpha: 0.001,
                    iteration: options,
                    ..Default::default()
                },
            )
            .unwrap(),
        ];
        let bits: Vec<u64> = results
            .iter()
            .flat_map(|result| {
                ["score", "hub", "authority"]
                    .into_iter()
                    .filter_map(|name| result.values(name))
                    .flatten()
                    .map(|v| v.to_bits())
                    .chain([result.residual().to_bits(), result.iterations() as u64])
                    .collect::<Vec<_>>()
            })
            .collect();
        (bits, context.usage().unwrap().work_units - before)
    };
    let first = run(1);
    for threads in [2, 3, 8] {
        assert_eq!(run(threads), first, "{threads} threads");
    }
}

#[test]
fn the_iterations_observe_cancellation_and_budget_and_release_scratch() {
    let edges = scrambled(5000, 40_000);
    let context = context();
    let projection = graph(5000, &edges, None, Orientation::Undirected, &context);
    let projection_work = context.usage().unwrap().work_units;
    let held = context.usage().unwrap().live_bytes;
    context.cancel().unwrap();
    assert!(matches!(
        eigenvector(&projection, IterationOptions::default()),
        Err(AlgorithmError::Cancelled)
    ));
    assert_eq!(context.usage().unwrap().live_bytes, held);

    let tight = ExecutionContext::new(limits(projection_work + 200_000)).unwrap();
    let projection = graph(5000, &edges, None, Orientation::Undirected, &tight);
    let held = tight.usage().unwrap().live_bytes;
    for outcome in [
        eigenvector(&projection, IterationOptions::default()).map(drop),
        hits(&projection, IterationOptions::default()).map(drop),
    ] {
        assert!(matches!(
            outcome,
            Err(AlgorithmError::BudgetExceeded {
                resource: "work",
                ..
            })
        ));
    }
    assert_eq!(tight.usage().unwrap().live_bytes, held);
}
