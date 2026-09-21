//! FastRP against the same computation done densely, in double precision.

use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, FastRpOptions, GraphProjection, Orientation,
    ProjectionEdge, SnapshotIdentity, fast_rp,
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
    ExecutionContext::new(limits(4_000_000_000)).unwrap()
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

/// `w[v][u]`: weight of arcs v -> u as the orientation reads them; an
/// undirected loop is one arc.
fn arcs(
    n: usize,
    edges: &[(usize, usize)],
    weights: Option<&[f64]>,
    orientation: Orientation,
) -> Vec<Vec<f64>> {
    let mut w = vec![vec![0.0; n]; n];
    for (index, &(a, b)) in edges.iter().enumerate() {
        let weight = weights.map_or(1.0, |w| w[index]);
        match orientation {
            Orientation::Outgoing => w[a][b] += weight,
            Orientation::Incoming => w[b][a] += weight,
            Orientation::Undirected => {
                w[a][b] += weight;
                if a != b {
                    w[b][a] += weight;
                }
            }
        }
    }
    w
}

fn unit(row: &[f64]) -> Vec<f64> {
    let norm = row.iter().map(|v| v * v).sum::<f64>().sqrt();
    row.iter()
        .map(|v| if norm > 0.0 { v / norm } else { 0.0 })
        .collect()
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
fn fast_rp_matches_a_dense_recomputation_from_its_own_random_vectors() {
    let mut random = Xorshift(0x2545_F491_4F6C_DD1D);
    for round in 0..300 {
        let n = 1 + random.below(12);
        let count = random.below(3 * n);
        let edges: Vec<_> = (0..count)
            .map(|_| (random.below(n), random.below(n)))
            .collect();
        let weights: Vec<f64> = (0..count).map(|_| (1 + random.below(4)) as f64).collect();
        let weights = (round % 2 == 1).then_some(&weights[..]);
        let d = 8 + random.below(24);
        let strength = [0.0, -0.5, 0.5][round % 3];
        let iteration_weights = [0.5, 1.0, -0.25, 2.0];
        let iteration_weights = &iteration_weights[..random.below(5)];
        let self_influence = [0.0, 1.0, 0.3][random.below(3)];
        for orientation in ORIENTATIONS {
            let what = format!("{orientation:?} d={d} β={strength} {edges:?} {weights:?}");
            let context = context();
            let projection = graph(n, &edges, weights, orientation, &context);
            let options = |iteration_weights, self_influence| FastRpOptions {
                dimension: d,
                iteration_weights,
                self_influence,
                normalization_strength: strength,
                seed: round as u64,
            };

            // Round zero alone returns each random vector at unit length. Its
            // entries are 0 or ±√3·scale, so the count of nonzeros gives the
            // length back, and the degree gives the scale.
            let zero = fast_rp(&projection, options(&[], 1.0)).unwrap();
            let w = arcs(n, &edges, weights, orientation);
            let mut current: Vec<Vec<f64>> = (0..n)
                .map(|v| {
                    let row = zero.embedding(v);
                    let nonzero = row.iter().filter(|&&x| x != 0.0).count() as f64;
                    let degree: f64 = w[v].iter().sum();
                    // A node of degree zero scales by zero unless the strength is zero.
                    let scale = if strength == 0.0 {
                        1.0
                    } else if degree == 0.0 {
                        0.0
                    } else {
                        degree.powf(strength)
                    };
                    row.iter()
                        .map(|&x| f64::from(x) * (3.0 * nonzero).sqrt() * scale)
                        .collect()
                })
                .collect();
            let mut expected: Vec<Vec<f64>> = current
                .iter()
                .map(|row| unit(row).iter().map(|v| v * self_influence).collect())
                .collect();
            for &weight in iteration_weights {
                current = (0..n)
                    .map(|v| {
                        let total: f64 = w[v].iter().sum();
                        (0..d)
                            .map(|j| {
                                if total > 0.0 {
                                    (0..n).map(|u| w[v][u] * current[u][j]).sum::<f64>() / total
                                } else {
                                    0.0
                                }
                            })
                            .collect()
                    })
                    .collect();
                for (into, row) in expected.iter_mut().zip(&current) {
                    for (value, add) in into.iter_mut().zip(unit(row)) {
                        *value += weight * add;
                    }
                }
            }

            let result = fast_rp(&projection, options(iteration_weights, self_influence)).unwrap();
            assert_eq!(result.dimension(), d);
            for (v, wanted_row) in expected.iter().enumerate() {
                for (j, (&actual, &wanted)) in
                    result.embedding(v).iter().zip(wanted_row).enumerate()
                {
                    assert!(
                        (f64::from(actual) - wanted).abs() < 1e-4,
                        "{what}: node {v} entry {j}: {actual} vs {wanted}"
                    );
                }
            }
        }
    }
}

#[test]
fn the_random_vectors_are_sparse_seeded_and_independent_of_the_graph() {
    let context = context();
    let n = 2000;
    let edges: Vec<_> = (1..n).map(|node| (node - 1, node)).collect();
    let run = |seed, edges: &[(usize, usize)]| {
        fast_rp(
            &graph(n, edges, None, Orientation::Outgoing, &context),
            FastRpOptions {
                dimension: 64,
                iteration_weights: &[],
                self_influence: 1.0,
                seed,
                ..Default::default()
            },
        )
        .unwrap()
        .values()
        .to_vec()
    };
    let first = run(1, &edges);
    assert_eq!(first, run(1, &edges));
    assert_eq!(first, run(1, &[]), "round zero does not look at arcs");
    assert_ne!(first, run(2, &edges));
    // A third of the entries are nonzero, half of those positive.
    let nonzero = first.iter().filter(|&&v| v != 0.0).count() as f64;
    let positive = first.iter().filter(|&&v| v > 0.0).count() as f64;
    let total = first.len() as f64;
    assert!(
        (nonzero / total - 1.0 / 3.0).abs() < 0.01,
        "{}",
        nonzero / total
    );
    assert!(
        (positive / nonzero - 0.5).abs() < 0.01,
        "{}",
        positive / nonzero
    );
}

#[test]
fn neighbours_in_a_clique_embed_closer_than_strangers() {
    // Not a claim about quality: only that averaging pulls a clique together.
    let mut edges = Vec::new();
    for base in [0, 10] {
        for a in base..base + 10 {
            for b in a + 1..base + 10 {
                edges.push((a, b));
            }
        }
    }
    let context = context();
    let result = fast_rp(
        &graph(20, &edges, None, Orientation::Undirected, &context),
        FastRpOptions {
            seed: 9,
            ..Default::default()
        },
    )
    .unwrap();
    let cosine = |a: usize, b: usize| {
        let (x, y) = (result.embedding(a), result.embedding(b));
        let dot: f32 = x.iter().zip(y).map(|(p, q)| p * q).sum();
        let norm = |v: &[f32]| v.iter().map(|p| p * p).sum::<f32>().sqrt();
        dot / (norm(x) * norm(y))
    };
    assert!(cosine(0, 5) > 0.9, "{}", cosine(0, 5));
    assert!(cosine(0, 15).abs() < 0.5, "{}", cosine(0, 15));
}

#[test]
fn fast_rp_rejects_bad_options_and_handles_the_empty_graph() {
    let context = context();
    let projection = graph(3, &[(0, 1)], None, Orientation::Outgoing, &context);
    let held = context.usage().unwrap().live_bytes;
    for options in [
        FastRpOptions {
            dimension: 0,
            ..Default::default()
        },
        FastRpOptions {
            iteration_weights: &[f64::NAN],
            ..Default::default()
        },
        FastRpOptions {
            self_influence: f64::INFINITY,
            ..Default::default()
        },
    ] {
        assert!(matches!(
            fast_rp(&projection, options),
            Err(AlgorithmError::InvalidArguments(_))
        ));
    }
    assert_eq!(context.usage().unwrap().live_bytes, held);
    let empty = fast_rp(
        &graph(0, &[], None, Orientation::Outgoing, &context),
        FastRpOptions::default(),
    )
    .unwrap();
    assert!(empty.values().is_empty());
}

#[test]
fn fast_rp_is_identical_at_any_pool_width_and_charges_the_same_work() {
    let mut random = Xorshift(0x9E37_79B9_7F4A_7C15);
    let n = 5000;
    let edges: Vec<_> = (0..30_000)
        .map(|_| (random.below(n), random.below(n)))
        .collect();
    let run = |threads: usize| {
        let context = context().with_concurrency(threads).unwrap();
        let projection = graph(n, &edges, None, Orientation::Undirected, &context);
        let before = context.usage().unwrap().counted_work().expect("counted");
        let result = fast_rp(
            &projection,
            FastRpOptions {
                dimension: 32,
                normalization_strength: -0.5,
                self_influence: 0.2,
                ..Default::default()
            },
        )
        .unwrap();
        let bits: Vec<u32> = result.values().iter().map(|v| v.to_bits()).collect();
        (
            bits,
            context.usage().unwrap().counted_work().expect("counted") - before,
        )
    };
    let first = run(1);
    for threads in [2, 3, 8] {
        assert_eq!(run(threads), first, "{threads} threads");
    }
}

#[test]
fn fast_rp_observes_cancellation_and_budget_and_releases_scratch() {
    let edges: Vec<_> = (1..4000).map(|node| (node / 2, node)).collect();
    let context = context();
    let projection = graph(4000, &edges, None, Orientation::Undirected, &context);
    let projection_work = context.usage().unwrap().counted_work().expect("counted");
    let held = context.usage().unwrap().live_bytes;
    context.cancel().unwrap();
    assert!(matches!(
        fast_rp(&projection, FastRpOptions::default()),
        Err(AlgorithmError::Cancelled)
    ));
    assert_eq!(context.usage().unwrap().live_bytes, held);

    let tight = ExecutionContext::new(limits(projection_work + 100_000)).unwrap();
    let projection = graph(4000, &edges, None, Orientation::Undirected, &tight);
    let held = tight.usage().unwrap().live_bytes;
    assert!(matches!(
        fast_rp(&projection, FastRpOptions::default()),
        Err(AlgorithmError::BudgetExceeded {
            resource: "work",
            ..
        })
    ));
    assert_eq!(tight.usage().unwrap().live_bytes, held);
}

#[cfg(feature = "arrow")]
#[test]
fn fast_rp_arrow_batches_are_fixed_size_lists_of_float32() {
    use arrow_array::{Array, FixedSizeListArray, Float32Array};
    let context = context();
    let projection = graph(
        5,
        &[(0, 1), (1, 2)],
        None,
        Orientation::Undirected,
        &context,
    );
    let result = fast_rp(
        &projection,
        FastRpOptions {
            dimension: 6,
            ..Default::default()
        },
    )
    .unwrap();
    let expected = result.values().to_vec();
    let mut cursor = result.into_table().unwrap().into_arrow_results();
    let batch = cursor.next_batch().unwrap().unwrap();
    let batch = batch.record_batch();
    assert_eq!(batch.schema().field(1).name(), "embedding");
    let lists = batch
        .column(1)
        .as_any()
        .downcast_ref::<FixedSizeListArray>()
        .unwrap();
    assert_eq!(
        (lists.len(), lists.value_length(), lists.null_count()),
        (5, 6, 0)
    );
    let values = lists.values();
    let values = values.as_any().downcast_ref::<Float32Array>().unwrap();
    assert_eq!(values.values().to_vec(), expected);
}
