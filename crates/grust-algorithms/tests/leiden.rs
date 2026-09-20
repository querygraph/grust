//! Leiden: every community connected, modularity honest, structure recovered.

use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, LeidenOptions,
    LouvainOptions, Orientation, ProjectionEdge, SnapshotIdentity, leiden, louvain,
};

const ORIENTATIONS: [Orientation; 3] = [
    Orientation::Undirected,
    Orientation::Outgoing,
    Orientation::Incoming,
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

type Edges = Vec<(usize, usize, f64)>;

fn graph(
    n: usize,
    edges: &Edges,
    orientation: Orientation,
    context: &ExecutionContext,
) -> GraphProjection {
    GraphProjection::from_topology(
        SnapshotIdentity::new("g".into(), "r".into(), "reader".into()).unwrap(),
        (0..n).map(|i| format!("n{i}").into()).collect(),
        edges
            .iter()
            .enumerate()
            .map(|(ordinal, &(source, target, _))| ProjectionEdge {
                source,
                target,
                ordinal,
                id: None,
            })
            .collect(),
        Some(edges.iter().map(|e| e.2).collect()),
        orientation,
        context,
    )
    .unwrap()
}

fn matrix(n: usize, edges: &Edges, orientation: Orientation) -> Vec<Vec<f64>> {
    let mut a = vec![vec![0.0; n]; n];
    for &(s, t, w) in edges {
        match orientation {
            Orientation::Undirected => {
                a[s][t] += w;
                a[t][s] += w;
            }
            Orientation::Outgoing => a[s][t] += w,
            Orientation::Incoming => a[t][s] += w,
        }
    }
    a
}

/// Q = (1/M) Σ_ij [A_ij − γ k_out_i k_in_j / M] δ(c_i, c_j), over the dense matrix.
fn modularity(a: &[Vec<f64>], communities: &[usize], gamma: f64) -> f64 {
    let n = a.len();
    let total: f64 = a.iter().flatten().sum();
    if total == 0.0 {
        return 0.0;
    }
    let k_out: Vec<f64> = a.iter().map(|row| row.iter().sum()).collect();
    let k_in: Vec<f64> = (0..n).map(|j| a.iter().map(|row| row[j]).sum()).collect();
    let mut q = 0.0;
    for i in 0..n {
        for j in 0..n {
            if communities[i] == communities[j] {
                q += a[i][j] - gamma * k_out[i] * k_in[j] / total;
            }
        }
    }
    q / total
}

fn optimum(a: &[Vec<f64>]) -> f64 {
    fn go(a: &[Vec<f64>], labels: &mut Vec<usize>, used: usize, best: &mut f64) {
        if labels.len() == a.len() {
            *best = best.max(modularity(a, labels, 1.0));
            return;
        }
        for label in 0..=used {
            labels.push(label);
            go(a, labels, used.max(label + 1), best);
            labels.pop();
        }
    }
    let mut best = f64::NEG_INFINITY;
    go(a, &mut Vec::new(), 0, &mut best);
    best
}

/// Communities that are not connected through positive-weight arcs, either way.
fn disconnected(n: usize, edges: &Edges, communities: &[usize]) -> usize {
    let mut parent: Vec<usize> = (0..n).collect();
    fn find(parent: &mut [usize], mut x: usize) -> usize {
        while parent[x] != x {
            parent[x] = parent[parent[x]];
            x = parent[x];
        }
        x
    }
    for &(s, t, w) in edges {
        if w > 0.0 && communities[s] == communities[t] {
            let (a, b) = (find(&mut parent, s), find(&mut parent, t));
            parent[a] = b;
        }
    }
    // A connected community has exactly one root among its members.
    let mut roots = vec![0usize; n];
    for v in 0..n {
        if find(&mut parent, v) == v {
            roots[communities[v]] += 1;
        }
    }
    roots.iter().filter(|&&count| count > 1).count()
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

fn random_edges(random: &mut Xorshift, n: usize, count: usize) -> Edges {
    (0..count)
        .map(|_| {
            // Zero weights too: such an arc must attach nothing.
            (random.below(n), random.below(n), random.below(5) as f64)
        })
        .collect()
}

#[test]
fn every_community_is_connected_and_the_modularity_is_the_partitions_own() {
    let mut random = Xorshift(0x2545_F491_4F6C_DD1D);
    for round in 0..1500 {
        let n = 1 + random.below(40);
        let count = random.below(3 * n);
        let edges = random_edges(&mut random, n, count);
        let options = LeidenOptions {
            seed: (round % 2 == 0).then_some(round as u64),
            resolution: [1.0, 1.0, 0.5, 2.0][round % 4],
            ..Default::default()
        };
        for orientation in ORIENTATIONS {
            let context = context();
            let result = leiden(&graph(n, &edges, orientation, &context), options).unwrap();
            let communities = result.communities();
            let what = format!("{orientation:?} {options:?} {edges:?}");
            assert_eq!(disconnected(n, &edges, communities), 0, "{what}");
            let a = matrix(n, &edges, orientation);
            let truth = modularity(&a, communities, options.resolution);
            assert!((result.modularity() - truth).abs() < 1e-12, "{what}");
            let singletons: Vec<usize> = (0..n).collect();
            assert!(
                truth >= modularity(&a, &singletons, options.resolution) - 1e-12,
                "{what}: below where it started"
            );
            for (node, &community) in communities.iter().enumerate() {
                assert!(community <= node && communities[community] == community);
            }
        }
    }
}

#[test]
fn leiden_never_exceeds_the_true_optimum_and_often_reaches_it() {
    let mut random = Xorshift(0x9E37_79B9_7F4A_7C15);
    let (mut runs, mut optimal) = (0, 0);
    for _ in 0..120 {
        let n = 4 + random.below(4);
        let count = 4 + random.below(9);
        let edges = random_edges(&mut random, n, count);
        for orientation in ORIENTATIONS {
            let context = context();
            let result = leiden(
                &graph(n, &edges, orientation, &context),
                LeidenOptions::default(),
            )
            .unwrap();
            let best = optimum(&matrix(n, &edges, orientation));
            assert!(
                result.modularity() <= best + 1e-12,
                "{orientation:?} {edges:?}"
            );
            runs += 1;
            optimal += usize::from(result.modularity() >= best - 1e-12);
        }
    }
    // A heuristic, so not always; but a refinement that merged too little would
    // show up here as a collapse.
    assert!(2 * optimal > runs, "optimal in only {optimal} of {runs}");
}

#[test]
fn leiden_recovers_planted_cliques_in_every_orientation() {
    let mut edges = Edges::new();
    for base in [0, 6, 12, 18] {
        for a in base..base + 6 {
            for b in base..base + 6 {
                if a < b {
                    edges.push((a, b, 1.0));
                    edges.push((b, a, 1.0));
                }
            }
        }
    }
    // A ring of single bridges between the cliques.
    for base in [0, 6, 12, 18] {
        edges.push((base, (base + 6) % 24, 1.0));
    }
    let expected: Vec<usize> = (0..24).map(|node| node / 6 * 6).collect();
    for orientation in ORIENTATIONS {
        for seed in [None, Some(3), Some(11)] {
            let context = context();
            let result = leiden(
                &graph(24, &edges, orientation, &context),
                LeidenOptions {
                    seed,
                    ..Default::default()
                },
            )
            .unwrap();
            assert_eq!(result.communities(), expected, "{orientation:?} {seed:?}");
            assert!(result.converged());
        }
    }
}

#[test]
fn leiden_handles_the_degenerate_graphs_and_rejects_bad_options() {
    let context = context();
    for (n, edges) in [
        (0, vec![]),
        (1, vec![]),
        (3, vec![]),
        (2, vec![(0, 1, 0.0)]),
    ] {
        let result = leiden(
            &graph(n, &edges, Orientation::Undirected, &context),
            LeidenOptions::default(),
        )
        .unwrap();
        assert_eq!(result.communities(), (0..n).collect::<Vec<_>>());
        assert_eq!(result.modularity(), 0.0);
        assert!(result.converged());
    }
    assert!(matches!(
        leiden(
            &graph(2, &vec![(0, 1, 1.0)], Orientation::Undirected, &context),
            LeidenOptions {
                max_levels: 0,
                ..Default::default()
            }
        ),
        Err(AlgorithmError::InvalidArguments(_))
    ));
}

#[test]
fn leiden_is_reproducible_and_stays_connected_on_a_larger_graph() {
    let mut random = Xorshift(0xD1B5_4A32_D192_ED03);
    let n = 3000;
    let mut edges = Edges::new();
    // Thirty loose groups of a hundred, sparsely joined.
    for _ in 0..24_000 {
        let group = random.below(30) * 100;
        edges.push((group + random.below(100), group + random.below(100), 1.0));
    }
    for _ in 0..1500 {
        edges.push((random.below(n), random.below(n), 1.0));
    }
    let run = |threads: usize, seed| {
        let context = context().with_concurrency(threads).unwrap();
        let projection = graph(n, &edges, Orientation::Undirected, &context);
        let options = LouvainOptions {
            seed,
            ..Default::default()
        };
        let result = leiden(&projection, options).unwrap();
        let plain = louvain(&projection, options).unwrap();
        (
            result.communities().to_vec(),
            result.modularity().to_bits(),
            plain.modularity(),
        )
    };
    let first = run(1, Some(5));
    assert_eq!(run(8, Some(5)), first);
    assert_eq!(disconnected(n, &edges, &first.0), 0);
    let modularity = f64::from_bits(first.1);
    // The planted structure is found, and Leiden is in Louvain's neighbourhood.
    assert!(modularity > 0.8, "{modularity}");
    assert!(
        (modularity - first.2).abs() < 0.05,
        "{modularity} vs {}",
        first.2
    );
}

#[test]
fn leiden_observes_cancellation_and_budget_and_releases_scratch() {
    let mut random = Xorshift(0x9E37_79B9_7F4A_7C15);
    let edges = random_edges(&mut random, 2000, 12_000);
    let context = context();
    let projection = graph(2000, &edges, Orientation::Outgoing, &context);
    let projection_work = context.usage().unwrap().work_units;
    let held = context.usage().unwrap().live_bytes;
    context.cancel().unwrap();
    assert!(matches!(
        leiden(&projection, LeidenOptions::default()),
        Err(AlgorithmError::Cancelled)
    ));
    assert_eq!(context.usage().unwrap().live_bytes, held);

    let tight = ExecutionContext::new(limits(projection_work + 40_000)).unwrap();
    let projection = graph(2000, &edges, Orientation::Outgoing, &tight);
    let held = tight.usage().unwrap().live_bytes;
    assert!(matches!(
        leiden(&projection, LeidenOptions::default()),
        Err(AlgorithmError::BudgetExceeded {
            resource: "work",
            ..
        })
    ));
    assert_eq!(tight.usage().unwrap().live_bytes, held);
}
