//! Node similarity against an O(n^2) recomputation from the edge list.

use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, NodeSimilarityOptions,
    Orientation, ProjectionEdge, SimilarityMetric, SnapshotIdentity, node_similarity,
};
use std::collections::BTreeMap;

const ORIENTATIONS: [Orientation; 3] = [
    Orientation::Outgoing,
    Orientation::Incoming,
    Orientation::Undirected,
];
const METRICS: [SimilarityMetric; 3] = [
    SimilarityMetric::Jaccard,
    SimilarityMetric::Overlap,
    SimilarityMetric::Cosine,
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

type Rows = Vec<(usize, usize, f64)>;

/// Every ordered pair, from neighbour maps built straight off the edge list.
/// Weights in these tests are small integers, so every sum is exact and the
/// kernel must agree to the bit, order included.
fn by_definition(
    n: usize,
    edges: &[(usize, usize)],
    weights: Option<&[f64]>,
    orientation: Orientation,
    options: NodeSimilarityOptions,
) -> Rows {
    let mut sets = vec![BTreeMap::<usize, f64>::new(); n];
    for (index, &(a, b)) in edges.iter().enumerate() {
        let w = weights.map_or(1.0, |w| w[index]);
        if a == b {
            continue;
        }
        // Without weights a neighbour is in the set or not; with them, parallel
        // edges add up.
        let mut add = |from: usize, to: usize| {
            let entry = sets[from].entry(to).or_insert(0.0);
            *entry = if weights.is_some() { *entry + w } else { 1.0 };
        };
        if orientation != Orientation::Incoming {
            add(a, b);
        }
        if orientation != Orientation::Outgoing {
            add(b, a);
        }
    }
    let admitted = |v: usize| {
        sets[v].len() >= options.degree_cutoff
            && options
                .upper_degree_cutoff
                .is_none_or(|upper| sets[v].len() <= upper)
    };
    let mut rows = Rows::new();
    for a in (0..n).filter(|&a| admitted(a)) {
        let mut mine = Rows::new();
        for b in (0..n).filter(|&b| b != a && admitted(b)) {
            let (mut low, mut dot, mut any) = (0.0, 0.0, false);
            for (key, &x) in &sets[a] {
                if let Some(&y) = sets[b].get(key) {
                    any = true;
                    low += x.min(y);
                    dot += x * y;
                }
            }
            if !any {
                continue;
            }
            let total = |v: usize| sets[v].values().sum::<f64>();
            let norm = |v: usize| sets[v].values().map(|w| w * w).sum::<f64>().sqrt();
            let union = total(a) + total(b) - low;
            let similarity = match options.metric {
                SimilarityMetric::Jaccard => low / union,
                SimilarityMetric::Overlap => low / total(a).min(total(b)),
                SimilarityMetric::Cosine => dot / (norm(a) * norm(b)),
            };
            if similarity > 0.0 && similarity.is_finite() && similarity >= options.similarity_cutoff
            {
                mine.push((a, b, similarity));
            }
        }
        mine.sort_by(|x, y| y.2.total_cmp(&x.2).then(x.1.cmp(&y.1)));
        mine.truncate(options.top_k);
        rows.extend(mine);
    }
    if options.top_n > 0 {
        rows.sort_by(|x, y| y.2.total_cmp(&x.2).then(x.0.cmp(&y.0)).then(x.1.cmp(&y.1)));
        rows.truncate(options.top_n);
    }
    rows
}

fn run(projection: &GraphProjection, options: NodeSimilarityOptions) -> Rows {
    let result = node_similarity(projection, options).unwrap();
    (0..result.first().len())
        .map(|row| {
            (
                result.first()[row],
                result.second()[row],
                result.similarity()[row],
            )
        })
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
fn node_similarity_matches_the_definition_row_for_row() {
    let mut random = Xorshift(0x2545_F491_4F6C_DD1D);
    let mut rows_checked = 0;
    for round in 0..1200 {
        let n = 1 + random.below(12);
        let count = random.below(4 * n);
        let edges: Vec<_> = (0..count)
            .map(|_| (random.below(n), random.below(n)))
            .collect();
        let weights: Vec<f64> = (0..count).map(|_| random.below(4) as f64).collect();
        let weights = (round % 2 == 1).then_some(&weights[..]);
        let options = NodeSimilarityOptions {
            metric: METRICS[round % 3],
            top_k: [1, 2, 3, 100][random.below(4)],
            top_n: [0, 0, 1, 5][random.below(4)],
            similarity_cutoff: [0.0, 0.0, 0.3, 0.5][random.below(4)],
            degree_cutoff: 1 + random.below(2),
            upper_degree_cutoff: [None, None, Some(3)][random.below(3)],
        };
        for orientation in ORIENTATIONS {
            let context = context();
            let projection = graph(n, &edges, weights, orientation, &context);
            let actual = run(&projection, options);
            let expected = by_definition(n, &edges, weights, orientation, options);
            assert_eq!(
                actual.len(),
                expected.len(),
                "{orientation:?} {options:?} {edges:?} {weights:?}"
            );
            for (a, e) in actual.iter().zip(&expected) {
                assert_eq!(
                    (a.0, a.1, a.2.to_bits()),
                    (e.0, e.1, e.2.to_bits()),
                    "{orientation:?} {options:?} {edges:?} {weights:?}: {a:?} vs {e:?}"
                );
            }
            rows_checked += actual.len();
        }
    }
    assert!(
        rows_checked > 10_000,
        "only {rows_checked} rows were compared"
    );
}

#[test]
fn node_similarity_states_its_textbook_values_and_its_set_semantics() {
    let context = context();
    // People 0,1,2 like items 3,4,5: 0 -> {3,4}, 1 -> {3,4,5}, 2 -> {5}.
    // The doubled 0->3 and the loop on 2 change nothing: these are sets.
    let edges = [
        (0, 3),
        (0, 3),
        (0, 4),
        (1, 3),
        (1, 4),
        (1, 5),
        (2, 5),
        (2, 2),
    ];
    let projection = graph(6, &edges, None, Orientation::Outgoing, &context);
    let with = |metric| {
        run(
            &projection,
            NodeSimilarityOptions {
                metric,
                ..Default::default()
            },
        )
    };
    let third = 1.0 / 3.0;
    assert_eq!(
        with(SimilarityMetric::Jaccard),
        [
            (0, 1, 2.0 / 3.0),
            (1, 0, 2.0 / 3.0),
            (1, 2, third),
            (2, 1, third)
        ]
    );
    assert_eq!(
        with(SimilarityMetric::Overlap),
        [(0, 1, 1.0), (1, 0, 1.0), (1, 2, 1.0), (2, 1, 1.0)]
    );
    let cosine = with(SimilarityMetric::Cosine);
    assert_eq!(cosine[0].2, 2.0 / (2.0f64.sqrt() * 3.0f64.sqrt()));

    // topK is per node1, so a pair can survive from one side only.
    let top = run(
        &projection,
        NodeSimilarityOptions {
            top_k: 1,
            ..Default::default()
        },
    );
    assert_eq!(top, [(0, 1, 2.0 / 3.0), (1, 0, 2.0 / 3.0), (2, 1, third)]);
    // topN orders by similarity, then node1, then node2.
    let best = run(
        &projection,
        NodeSimilarityOptions {
            top_n: 3,
            ..Default::default()
        },
    );
    assert_eq!(best, [(0, 1, 2.0 / 3.0), (1, 0, 2.0 / 3.0), (1, 2, third)]);

    // Weighted Jaccard sums the smaller weight over the larger.
    let weighted = graph(
        3,
        &[(0, 2), (1, 2), (1, 2)],
        Some(&[1.0, 1.0, 2.0]),
        Orientation::Outgoing,
        &context,
    );
    // 0 -> {2: 1}, 1 -> {2: 3}: min 1 over max 3.
    assert_eq!(
        run(&weighted, NodeSimilarityOptions::default()),
        [(0, 1, third), (1, 0, third)]
    );
}

#[test]
fn node_similarity_rejects_options_that_mean_nothing() {
    let context = context();
    let projection = graph(2, &[(0, 1)], None, Orientation::Outgoing, &context);
    let held = context.usage().unwrap().live_bytes;
    for options in [
        NodeSimilarityOptions {
            top_k: 0,
            ..Default::default()
        },
        NodeSimilarityOptions {
            similarity_cutoff: 1.5,
            ..Default::default()
        },
        NodeSimilarityOptions {
            similarity_cutoff: f64::NAN,
            ..Default::default()
        },
        NodeSimilarityOptions {
            degree_cutoff: 0,
            ..Default::default()
        },
        NodeSimilarityOptions {
            degree_cutoff: 3,
            upper_degree_cutoff: Some(2),
            ..Default::default()
        },
    ] {
        assert!(matches!(
            node_similarity(&projection, options),
            Err(AlgorithmError::InvalidArguments(_))
        ));
    }
    assert_eq!(context.usage().unwrap().live_bytes, held);
}

fn scrambled(n: usize, edges: usize) -> Vec<(usize, usize)> {
    let mut random = Xorshift(0x9E37_79B9_7F4A_7C15);
    (0..edges)
        .map(|_| (random.below(n), random.below(n).pow(2) / n))
        .collect()
}

#[test]
fn node_similarity_is_identical_at_any_pool_width_and_charges_the_same_work() {
    let edges = scrambled(600, 4000);
    let weights: Vec<f64> = (0..edges.len()).map(|i| (1 + i % 5) as f64 / 3.0).collect();
    for metric in METRICS {
        let run_with = |threads: usize| {
            let pool = rayon::ThreadPoolBuilder::new()
                .num_threads(threads)
                .build()
                .unwrap();
            pool.install(|| {
                let context = context();
                let projection =
                    graph(600, &edges, Some(&weights), Orientation::Outgoing, &context);
                let before = context.usage().unwrap().work_units;
                let rows: Vec<_> = run(
                    &projection,
                    NodeSimilarityOptions {
                        metric,
                        top_k: 5,
                        ..Default::default()
                    },
                )
                .into_iter()
                .map(|(a, b, s)| (a, b, s.to_bits()))
                .collect();
                (rows, context.usage().unwrap().work_units - before)
            })
        };
        let first = run_with(1);
        assert!(first.0.len() > 1000);
        // Both directions of a pair carry the same bits.
        let lookup: BTreeMap<_, _> = first.0.iter().map(|&(a, b, s)| ((a, b), s)).collect();
        for (&(a, b), s) in &lookup {
            if let Some(back) = lookup.get(&(b, a)) {
                assert_eq!(s, back);
            }
        }
        for threads in [2, 3, 8] {
            assert_eq!(run_with(threads), first, "{threads} threads, {metric:?}");
        }
    }
}

#[test]
fn node_similarity_observes_cancellation_and_budget_and_releases_scratch() {
    // A hub everyone points at: the quadratic case the work budget must stop.
    let edges: Vec<_> = (1..3000).map(|node| (node, 0)).collect();
    let context = context();
    let projection = graph(3000, &edges, None, Orientation::Outgoing, &context);
    let projection_work = context.usage().unwrap().work_units;
    let held = context.usage().unwrap().live_bytes;
    context.cancel().unwrap();
    assert!(matches!(
        node_similarity(&projection, NodeSimilarityOptions::default()),
        Err(AlgorithmError::Cancelled)
    ));
    assert_eq!(context.usage().unwrap().live_bytes, held);

    let tight = ExecutionContext::new(limits(projection_work + 1_000_000)).unwrap();
    let projection = graph(3000, &edges, None, Orientation::Outgoing, &tight);
    let held = tight.usage().unwrap().live_bytes;
    assert!(matches!(
        node_similarity(&projection, NodeSimilarityOptions::default()),
        Err(AlgorithmError::BudgetExceeded {
            resource: "work",
            ..
        })
    ));
    assert_eq!(tight.usage().unwrap().live_bytes, held);
}
