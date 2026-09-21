//! Louvain against a dense-matrix modularity and the brute-force optimum.

use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, LouvainOptions,
    Orientation, ProjectionEdge, SnapshotIdentity, louvain,
};

fn context() -> ExecutionContext {
    ExecutionContext::new(ExecutionLimits {
        memory_bytes: 64 * 1024 * 1024,
        work_units: 500_000_000,
        batch_rows: 1024,
        deadline: None,
    })
    .unwrap()
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

/// The adjacency matrix the orientation defines. Undirected: symmetric, and a
/// loop of weight w is 2w on the diagonal (Newman). Directed: A[i][j] is the
/// weight of arcs i -> j as traversed, so `Incoming` transposes.
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

/// Q = (1/M) Σ_ij [A_ij − γ k_out_i k_in_j / M] δ(c_i, c_j), straight from the
/// papers, over the dense matrix. Shares nothing with the kernel.
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

/// The best modularity over every partition, by restricted-growth strings.
fn optimum(a: &[Vec<f64>], gamma: f64) -> f64 {
    fn go(a: &[Vec<f64>], gamma: f64, labels: &mut Vec<usize>, used: usize, best: &mut f64) {
        if labels.len() == a.len() {
            *best = best.max(modularity(a, labels, gamma));
            return;
        }
        for label in 0..=used {
            labels.push(label);
            go(a, gamma, labels, used.max(label + 1), best);
            labels.pop();
        }
    }
    let mut best = f64::NEG_INFINITY;
    go(a, gamma, &mut Vec::new(), 0, &mut best);
    best
}

fn pseudo_random_edges(n: usize, count: usize, seed: u64) -> Edges {
    let mut state = seed | 1;
    let mut next = move || {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        state
    };
    (0..count)
        .map(|_| {
            let s = (next() % n as u64) as usize;
            let t = (next() % n as u64) as usize;
            (s, t, 1.0 + (next() % 4) as f64)
        })
        .collect()
}

#[test]
fn louvain_matches_an_independent_oracle() {
    // On many small graphs, loops and parallel edges included, in every
    // orientation: the reported modularity is the partition's true modularity;
    // it is at least where the search started (singletons) and never above the
    // true optimum. Louvain is a heuristic, so equality with the optimum is not
    // asserted here.
    for orientation in [
        Orientation::Undirected,
        Orientation::Outgoing,
        Orientation::Incoming,
    ] {
        for seed in 1..60u64 {
            let n = 4 + (seed % 4) as usize;
            let edges = pseudo_random_edges(n, 4 + (seed % 9) as usize, seed * 7919);
            let context = context();
            let result = louvain(
                &graph(n, &edges, orientation, &context),
                LouvainOptions::default(),
            )
            .unwrap();
            let a = matrix(n, &edges, orientation);
            let truth = modularity(&a, result.communities(), 1.0);
            assert!(
                (result.modularity() - truth).abs() < 1e-12,
                "{orientation:?} seed {seed}: reported {} true {truth}",
                result.modularity()
            );
            let singletons: Vec<usize> = (0..n).collect();
            assert!(
                truth >= modularity(&a, &singletons, 1.0) - 1e-12,
                "{orientation:?} {seed}"
            );
            assert!(truth <= optimum(&a, 1.0) + 1e-12, "{orientation:?} {seed}");
            // Canonical ids: a community is named by its smallest member.
            for (node, &community) in result.communities().iter().enumerate() {
                assert!(community <= node);
                assert_eq!(result.communities()[community], community);
            }
        }
    }
}

fn two_cliques() -> Edges {
    let mut edges = Vec::new();
    for base in [0, 5] {
        for a in 0..5 {
            for b in a + 1..5 {
                edges.push((base + a, base + b, 1.0));
            }
        }
    }
    edges.push((4, 5, 1.0));
    edges
}

#[test]
fn louvain_recovers_planted_structure_and_reaches_the_optimum_there() {
    let context = context();
    let edges = two_cliques();
    let result = louvain(
        &graph(10, &edges, Orientation::Undirected, &context),
        LouvainOptions::default(),
    )
    .unwrap();
    assert_eq!(result.communities(), [0, 0, 0, 0, 0, 5, 5, 5, 5, 5]);
    assert!(result.converged());
    assert!(result.levels() >= 1);
    // All 115,975 partitions of ten nodes: here the heuristic is exactly optimal.
    let a = matrix(10, &edges, Orientation::Undirected);
    assert!((result.modularity() - optimum(&a, 1.0)).abs() < 1e-12);

    // Directed: two 4-cycles joined by one arc.
    let mut directed: Edges = Vec::new();
    for base in [0, 4] {
        for i in 0..4 {
            directed.push((base + i, base + (i + 1) % 4, 1.0));
        }
    }
    directed.push((3, 4, 1.0));
    for orientation in [Orientation::Outgoing, Orientation::Incoming] {
        let result = louvain(
            &graph(8, &directed, orientation, &context),
            LouvainOptions::default(),
        )
        .unwrap();
        assert_eq!(
            result.communities(),
            [0, 0, 0, 0, 4, 4, 4, 4],
            "{orientation:?}"
        );
    }
}

#[test]
fn louvain_states_multigraph_and_self_loop_semantics() {
    let context = context();
    // Two nodes, a loop on each, one edge between. A = [[2,1],[1,2]], M = 6.
    // Apart: Q = 2*(2/6 - (3/6)^2) = 1/6. Together: Q = 6/6 - 1 = 0.
    // A loop counted once instead of twice would make "together" win.
    let edges: Edges = vec![(0, 0, 1.0), (1, 1, 1.0), (0, 1, 1.0)];
    let result = louvain(
        &graph(2, &edges, Orientation::Undirected, &context),
        LouvainOptions::default(),
    )
    .unwrap();
    assert_eq!(result.communities(), [0, 1]);
    assert!((result.modularity() - 1.0 / 6.0).abs() < 1e-12);

    // Parallel edges add up: three unit edges behave as one edge of weight 3.
    let parallel: Edges = vec![
        (0, 1, 1.0),
        (0, 1, 1.0),
        (1, 0, 1.0),
        (1, 2, 1.0),
        (2, 3, 3.0),
    ];
    let merged: Edges = vec![(0, 1, 3.0), (1, 2, 1.0), (2, 3, 3.0)];
    let a = louvain(
        &graph(4, &parallel, Orientation::Undirected, &context),
        LouvainOptions::default(),
    )
    .unwrap();
    let b = louvain(
        &graph(4, &merged, Orientation::Undirected, &context),
        LouvainOptions::default(),
    )
    .unwrap();
    assert_eq!(a.communities(), b.communities());
    assert_eq!(a.communities(), [0, 0, 2, 2]);
    assert!((a.modularity() - b.modularity()).abs() < 1e-12);
}

#[test]
fn louvain_handles_empty_single_node_isolates_and_weightless_graphs() {
    let context = context();
    let empty = louvain(
        &graph(0, &vec![], Orientation::Undirected, &context),
        LouvainOptions::default(),
    )
    .unwrap();
    assert!(empty.communities().is_empty());
    assert_eq!(empty.modularity(), 0.0);
    assert!(empty.converged());

    let isolates = louvain(
        &graph(3, &vec![], Orientation::Outgoing, &context),
        LouvainOptions::default(),
    )
    .unwrap();
    assert_eq!(isolates.communities(), [0, 1, 2]);
    assert_eq!(isolates.modularity(), 0.0);

    // All weights zero: no structure to find, nothing divides by zero.
    let weightless: Edges = vec![(0, 1, 0.0), (1, 2, 0.0)];
    let result = louvain(
        &graph(3, &weightless, Orientation::Undirected, &context),
        LouvainOptions::default(),
    )
    .unwrap();
    assert_eq!(result.communities(), [0, 1, 2]);
    assert_eq!(result.modularity(), 0.0);

    // An edge plus an isolate: the isolate stays alone.
    let result = louvain(
        &graph(3, &vec![(0, 1, 1.0)], Orientation::Undirected, &context),
        LouvainOptions::default(),
    )
    .unwrap();
    assert_eq!(result.communities(), [0, 0, 2]);
}

#[test]
fn resolution_moves_between_components_and_singletons() {
    let context = context();
    let edges = two_cliques();
    let projection = graph(10, &edges, Orientation::Undirected, &context);
    // gamma = 0 rewards only internal weight: each connected component merges.
    let merged = louvain(
        &projection,
        LouvainOptions {
            resolution: 0.0,
            ..Default::default()
        },
    )
    .unwrap();
    assert!(merged.communities().iter().all(|&c| c == 0));
    // A very large gamma makes every merge a loss.
    let apart = louvain(
        &projection,
        LouvainOptions {
            resolution: 1e6,
            ..Default::default()
        },
    )
    .unwrap();
    assert_eq!(apart.communities(), (0..10).collect::<Vec<_>>());
    assert_eq!(apart.levels(), 0);
}

#[test]
fn louvain_is_deterministic_under_a_fixed_seed_and_any_pool_width() {
    let edges = pseudo_random_edges(300, 1500, 99);
    let run = |seed: Option<u64>, threads: usize| {
        let context = context().with_concurrency(threads).unwrap();
        let projection = graph(300, &edges, Orientation::Undirected, &context);
        let result = louvain(
            &projection,
            LouvainOptions {
                seed,
                ..Default::default()
            },
        )
        .unwrap();
        (result.communities().to_vec(), result.modularity().to_bits())
    };
    assert_eq!(run(None, 1), run(None, 8));
    assert_eq!(run(Some(7), 1), run(Some(7), 8));
    assert_eq!(run(Some(7), 1), run(Some(7), 1));
    // Different visiting orders are allowed to find different partitions; each
    // must still be a real improvement over singletons.
    let (_, q) = run(Some(8), 1);
    assert!(f64::from_bits(q) > 0.2);
}

#[test]
fn louvain_rejects_invalid_options_without_leaking_admission() {
    let context = context();
    let projection = graph(3, &vec![(0, 1, 1.0)], Orientation::Undirected, &context);
    let held = context.usage().unwrap().live_bytes;
    for options in [
        LouvainOptions {
            resolution: -1.0,
            ..Default::default()
        },
        LouvainOptions {
            resolution: f64::NAN,
            ..Default::default()
        },
        LouvainOptions {
            tolerance: -1e-9,
            ..Default::default()
        },
        LouvainOptions {
            max_levels: 0,
            ..Default::default()
        },
        LouvainOptions {
            max_iterations: 0,
            ..Default::default()
        },
    ] {
        assert!(matches!(
            louvain(&projection, options),
            Err(AlgorithmError::InvalidArguments(_))
        ));
        assert_eq!(context.usage().unwrap().live_bytes, held);
    }
}

#[test]
fn louvain_observes_cancellation_and_budget_and_releases_scratch() {
    let edges = pseudo_random_edges(500, 4000, 5);
    let context = context();
    let projection = graph(500, &edges, Orientation::Undirected, &context);
    let projection_work = context.usage().unwrap().counted_work().expect("counted");
    let held = context.usage().unwrap().live_bytes;
    context.cancel().unwrap();
    assert!(matches!(
        louvain(&projection, LouvainOptions::default()),
        Err(AlgorithmError::Cancelled)
    ));
    assert_eq!(context.usage().unwrap().live_bytes, held);

    let tight = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 64 * 1024 * 1024,
        work_units: projection_work + 12_000,
        batch_rows: 1024,
        deadline: None,
    })
    .unwrap();
    let projection = graph(500, &edges, Orientation::Undirected, &tight);
    let held = tight.usage().unwrap().live_bytes;
    assert!(matches!(
        louvain(&projection, LouvainOptions::default()),
        Err(AlgorithmError::BudgetExceeded {
            resource: "work",
            ..
        })
    ));
    assert_eq!(tight.usage().unwrap().live_bytes, held);
}
