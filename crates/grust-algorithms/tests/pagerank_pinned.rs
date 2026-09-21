//! PageRank's scores and work accounting, pinned to the bit.
//!
//! The digests below were produced by the kernel as it stood before the
//! unweighted pull hoisted each source's `score / out-degree` out of the arc
//! loop and before the push loop stopped charging once per arc (origin/main
//! 0eba09e). Both changes promise the same bits and the same budget behaviour,
//! so any drift in a score, an iteration count, a residual, the work charged or
//! the unit at which a budget refuses fails here. Scores are compared through
//! `f64::to_bits`, never approximately.
//!
//! Each fixture also asserts which kernel it reached. The push loop and the pull
//! charge different totals, so the work units one call charges identify the path
//! exactly; a fixture that silently stayed on the sequential path cannot pass as
//! a test of the parallel one.

use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, Orientation, PageRank,
    PageRankOptions, ProjectionEdge, SnapshotIdentity, pagerank,
};

fn context(workers: Option<usize>, work_units: usize) -> ExecutionContext {
    let context = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 1 << 30,
        work_units,
        batch_rows: 8192,
        deadline: None,
    })
    .expect("valid limits");
    match workers {
        Some(workers) => context.with_concurrency(workers).expect("not yet shared"),
        None => context,
    }
}

fn project(
    context: &ExecutionContext,
    nodes: usize,
    arcs: Vec<(usize, usize)>,
    weights: Option<Vec<f64>>,
) -> Result<GraphProjection, AlgorithmError> {
    let edges = arcs
        .into_iter()
        .enumerate()
        .map(|(ordinal, (source, target))| ProjectionEdge {
            source,
            target,
            ordinal,
            id: None,
        })
        .collect();
    GraphProjection::from_topology(
        SnapshotIdentity::new("pinned".into(), "r1".into(), "tests".into()).expect("identity"),
        (0..nodes).map(|id| id.to_string().into()).collect(),
        edges,
        weights,
        Orientation::Outgoing,
        context,
    )
}

fn xorshift(seed: u64) -> impl FnMut() -> u64 {
    let mut state = seed;
    move || {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        state
    }
}

/// `tests/parallel.rs`'s graph: a permutation cycle plus chords biased to low
/// rows, so a few sources have very high out-degree.
fn chords(weighted: bool) -> (usize, Vec<(usize, usize)>, Option<Vec<f64>>) {
    const NODES: usize = 120_000;
    const EDGES: usize = 600_000;
    let mut random = xorshift(0x2545_F491_4F6C_DD1D);
    let arcs = (0..EDGES)
        .map(|ordinal| {
            if ordinal < NODES {
                (ordinal, (ordinal + 1) % NODES)
            } else {
                let source = (random() % (NODES as u64 / 16)) as usize;
                (source, (random() % NODES as u64) as usize)
            }
        })
        .collect();
    let weights = weighted.then(|| (0..EDGES).map(|index| 1.0 + (index % 7) as f64).collect());
    (NODES, arcs, weights)
}

/// `tests/parallel.rs`'s dangling graph: half the nodes have no out-arcs.
fn dangling() -> (usize, Vec<(usize, usize)>, Option<Vec<f64>>) {
    const N: usize = 200_000;
    let mut next = xorshift(0x9E37_79B9_7F4A_7C15);
    let arcs = (0..3 * N)
        .map(|_| {
            let source = (next() % (N as u64 / 2)) as usize;
            let target = next() % N as u64;
            (source, (target * target / N as u64) as usize)
        })
        .collect();
    (N, arcs, None)
}

fn fnv(state: &mut u64, word: u64) {
    for byte in word.to_le_bytes() {
        *state ^= u64::from(byte);
        *state = state.wrapping_mul(0x0000_0100_0000_01B3);
    }
}

fn digest(result: &PageRank) -> u64 {
    let mut state = 0xCBF2_9CE4_8422_2325;
    for score in result.values() {
        fnv(&mut state, score.to_bits());
    }
    fnv(&mut state, result.iterations() as u64);
    fnv(&mut state, result.residual().to_bits());
    fnv(&mut state, u64::from(result.converged()));
    state
}

const ITERATIONS: usize = 25;

fn fixed_iterations() -> PageRankOptions<'static> {
    PageRankOptions {
        max_iterations: ITERATIONS,
        // Zero tolerance runs every iteration, so the work charged is a closed
        // formula of the graph and identifies the kernel that ran.
        tolerance: 0.0,
        ..Default::default()
    }
}

#[derive(Debug, PartialEq, Eq)]
enum Path {
    Push,
    Pull,
}

/// Run twice on one projection. The second call is measured, so a transpose
/// built lazily by the first is not in its work; both must agree to the bit.
fn run(
    workers: Option<usize>,
    (nodes, arcs, weights): (usize, Vec<(usize, usize)>, Option<Vec<f64>>),
) -> (u64, Path) {
    let context = context(workers, usize::MAX);
    let m = arcs.len();
    let weighted = weights.is_some();
    let graph = project(&context, nodes, arcs, weights).expect("projection");
    let first = pagerank(&graph, fixed_iterations()).expect("pagerank");
    let before = context
        .usage()
        .expect("usage")
        .counted_work()
        .expect("counted");
    let second = pagerank(&graph, fixed_iterations()).expect("pagerank");
    let charged = context
        .usage()
        .expect("usage")
        .counted_work()
        .expect("counted")
        - before;
    assert_eq!(digest(&first), digest(&second), "a rerun moved");
    assert_eq!(second.iterations(), ITERATIONS);

    // Every weight in these fixtures is positive, so no row with arcs is
    // dangling and every arc is charged on every pass that visits arcs.
    let (n, k) = (nodes, ITERATIONS);
    let push = 6 * n + 2 * m + k * (4 * n + m);
    let pull = 2 * n + if weighted { n + 2 * m } else { 0 } + k * (3 * n + m);
    assert_ne!(push, pull);
    let path = if charged == push {
        Path::Push
    } else if charged == pull {
        Path::Pull
    } else {
        panic!("charged {charged}, neither push {push} nor pull {pull}");
    };
    (digest(&second), path)
}

// Digests produced at origin/main 0eba09e, before either kernel change.
const CHORDS_PUSH: u64 = 0x47a9_e230_b420_1b4a;
#[cfg(feature = "parallel")]
const CHORDS_PULL: u64 = 0xb510_c73b_29a1_f439;
const CHORDS_WEIGHTED_PUSH: u64 = 0x134d_8a37_85b6_8a34;
#[cfg(feature = "parallel")]
const CHORDS_WEIGHTED_PULL: u64 = 0x45be_6e06_23a5_4756;
const DANGLING_PUSH: u64 = 0x12d7_143a_6595_b083;
#[cfg(feature = "parallel")]
const DANGLING_PULL: u64 = 0xc53f_6913_91de_b2d0;
const SMALL_WEIGHTED: [u64; 3] = [
    0xeaed_42d7_fee9_662a,
    0x735c_8063_781e_c5c6,
    0x04cf_ab03_d17f_bbe7,
];
const PUSH_BUDGETS: [u64; 2] = [0x6a41_7bb2_d619_2ef5, 0x072e_7128_972a_c7c8];
#[cfg(feature = "parallel")]
const PULL_BUDGETS: u64 = 0x28c6_c837_8b34_77a9;

#[test]
fn unweighted_scores_are_the_pinned_bits_on_both_paths_at_every_width() {
    let (digest, path) = run(None, chords(false));
    assert_eq!(
        path,
        Path::Push,
        "concurrency unset must take the push loop"
    );
    println!("CHORDS_PUSH = {digest:#018x}");
    assert_eq!(digest, CHORDS_PUSH);
    #[cfg(feature = "parallel")]
    for workers in [1, 2, 16] {
        let (digest, path) = run(Some(workers), chords(false));
        assert_eq!(path, Path::Pull, "{workers} workers must reach the pull");
        println!("CHORDS_PULL@{workers} = {digest:#018x}");
        assert_eq!(digest, CHORDS_PULL, "{workers} workers");
    }
}

#[test]
fn weighted_scores_are_the_pinned_bits_on_both_paths_at_every_width() {
    let (digest, path) = run(None, chords(true));
    assert_eq!(path, Path::Push);
    println!("CHORDS_WEIGHTED_PUSH = {digest:#018x}");
    assert_eq!(digest, CHORDS_WEIGHTED_PUSH);
    #[cfg(feature = "parallel")]
    for workers in [1, 2, 16] {
        let (digest, path) = run(Some(workers), chords(true));
        assert_eq!(path, Path::Pull, "{workers} workers must reach the pull");
        println!("CHORDS_WEIGHTED_PULL@{workers} = {digest:#018x}");
        assert_eq!(digest, CHORDS_WEIGHTED_PULL, "{workers} workers");
    }
}

#[test]
fn dangling_scores_are_the_pinned_bits_on_both_paths_at_every_width() {
    let (digest, path) = run(None, dangling());
    assert_eq!(path, Path::Push);
    println!("DANGLING_PUSH = {digest:#018x}");
    assert_eq!(digest, DANGLING_PUSH);
    #[cfg(feature = "parallel")]
    for workers in [1, 2, 16] {
        let (digest, path) = run(Some(workers), dangling());
        assert_eq!(path, Path::Pull, "{workers} workers must reach the pull");
        println!("DANGLING_PULL@{workers} = {digest:#018x}");
        assert_eq!(digest, DANGLING_PULL, "{workers} workers");
    }
}

/// `tests/weighted.rs`'s fixture: two f64::MAX parallel arcs and a zero-weight
/// row, which is dangling although it has an arc. Too small to go parallel at
/// any width, so this pins the push loop only.
#[test]
fn the_small_weighted_fixture_is_the_pinned_bits() {
    let personalization = [f64::MAX, 0.0, f64::MAX];
    let options = [
        PageRankOptions::default(),
        PageRankOptions {
            damping: 0.0,
            personalization: Some(&personalization),
            ..Default::default()
        },
        PageRankOptions {
            max_iterations: 1,
            tolerance: 0.0,
            ..Default::default()
        },
    ];
    for workers in [None, Some(16)] {
        let context = context(workers, usize::MAX);
        let graph = project(
            &context,
            3,
            vec![(0, 1), (0, 1), (1, 0)],
            Some(vec![f64::MAX, f64::MAX, 0.0]),
        )
        .expect("projection");
        for (index, options) in options.iter().enumerate() {
            let digest = digest(&pagerank(&graph, *options).expect("pagerank"));
            println!("SMALL_WEIGHTED[{index}] = {digest:#018x}");
            assert_eq!(digest, SMALL_WEIGHTED[index], "options {index}");
        }
    }
}

/// Every budget from nothing to one past what the run needs: whether the run
/// succeeds, and the work the execution has charged when it stops. The digest
/// pins the unit at which a budget refuses, not only whether it does.
fn budget_sweep(
    workers: Option<usize>,
    nodes: usize,
    arcs: &[(usize, usize)],
    weights: Option<&[f64]>,
    budgets: impl Iterator<Item = usize>,
) -> (u64, usize) {
    let mut state = 0xCBF2_9CE4_8422_2325;
    let mut smallest_success = usize::MAX;
    for budget in budgets {
        let context = context(workers, budget);
        let outcome = match project(&context, nodes, arcs.to_vec(), weights.map(<[f64]>::to_vec)) {
            Err(AlgorithmError::BudgetExceeded { .. }) => 1,
            Err(other) => panic!("projection at {budget}: {other}"),
            Ok(graph) => match pagerank(
                &graph,
                PageRankOptions {
                    max_iterations: 3,
                    tolerance: 0.0,
                    ..Default::default()
                },
            ) {
                Ok(result) => {
                    smallest_success = smallest_success.min(budget);
                    digest(&result)
                }
                Err(AlgorithmError::BudgetExceeded { resource, .. }) => {
                    assert_eq!(resource, "work");
                    2
                }
                Err(other) => panic!("pagerank at {budget}: {other}"),
            },
        };
        fnv(&mut state, budget as u64);
        fnv(&mut state, outcome);
        fnv(
            &mut state,
            context
                .usage()
                .expect("usage")
                .counted_work()
                .expect("counted") as u64,
        );
    }
    (state, smallest_success)
}

/// A hub whose out-degree spans several charge chunks, a dangling node, a node
/// whose only arcs weigh zero, and a ring for the rest.
fn hub() -> (usize, Vec<(usize, usize)>, Vec<f64>) {
    const NODES: usize = 40;
    let mut random = xorshift(0xD1B5_4A32_D192_ED03);
    let mut arcs = Vec::new();
    for _ in 0..1300 {
        arcs.push((0, (random() % NODES as u64) as usize));
    }
    for node in 1..NODES - 2 {
        arcs.push((node, (node + 1) % NODES));
        arcs.push((node, (random() % NODES as u64) as usize));
    }
    // Node NODES - 2 has two arcs of zero weight; node NODES - 1 has none.
    let zero_row = arcs.len();
    arcs.push((NODES - 2, 0));
    arcs.push((NODES - 2, 5));
    let weights = (0..arcs.len())
        .map(|index| {
            if index >= zero_row {
                0.0
            } else {
                1.0 + (index % 5) as f64
            }
        })
        .collect();
    (NODES, arcs, weights)
}

/// The least budget a run fits in, by bisection: a run that fits in a budget
/// fits in every larger one.
fn smallest_budget(
    workers: Option<usize>,
    nodes: usize,
    arcs: &[(usize, usize)],
    weights: Option<&[f64]>,
) -> usize {
    let fits =
        |budget: usize| budget_sweep(workers, nodes, arcs, weights, budget..budget + 1).1 == budget;
    let (mut refused, mut smallest) = (0, 1 << 20);
    assert!(fits(smallest) && !fits(refused));
    while smallest - refused > 1 {
        let middle = refused + (smallest - refused) / 2;
        if fits(middle) {
            smallest = middle;
        } else {
            refused = middle;
        }
    }
    smallest
}

#[test]
fn the_push_loop_refuses_every_budget_at_the_pinned_unit() {
    let (nodes, arcs, weights) = hub();
    // Far below the parallel floor, so this is the push loop at any width.
    assert!((nodes + arcs.len()) * 2 < 1 << 14);
    for (index, weights) in [None, Some(weights.as_slice())].into_iter().enumerate() {
        let smallest = smallest_budget(None, nodes, &arcs, weights);
        // Every budget up to and past the least that fits.
        let (digest, again) = budget_sweep(None, nodes, &arcs, weights, 0..smallest + 64);
        assert_eq!(again, smallest);
        println!("PUSH_BUDGETS[{index}] = {digest:#018x} (smallest success {smallest})");
        assert_eq!(digest, PUSH_BUDGETS[index], "weights {index}");
    }
}

#[cfg(feature = "parallel")]
#[test]
fn the_pull_refuses_budgets_at_the_pinned_unit() {
    const NODES: usize = 3000;
    let mut random = xorshift(0x94D0_49BB_1331_11EB);
    let arcs: Vec<(usize, usize)> = (0..6000)
        .map(|_| {
            let source = (random() % (NODES as u64 / 4)) as usize;
            (source, (random() % NODES as u64) as usize)
        })
        .collect();
    assert!((NODES + arcs.len()) * 2 >= 1 << 14, "must reach the pull");
    // One worker: at more, the unit a refused run stops at depends on which
    // worker is refused, though whether it is refused does not.
    let smallest = smallest_budget(Some(1), NODES, &arcs, None);
    let sampled = (0..smallest + 64)
        .step_by(97)
        .chain(smallest.saturating_sub(64)..smallest + 64);
    let (digest, again) = budget_sweep(Some(1), NODES, &arcs, None, sampled);
    assert_eq!(again, smallest);
    println!("PULL_BUDGETS = {digest:#018x} (smallest success {smallest})");
    assert_eq!(digest, PULL_BUDGETS);
    for workers in [2, 16] {
        let refused = [smallest - 1, smallest];
        for (budget, fits) in refused.into_iter().zip([false, true]) {
            let context = context(Some(workers), budget);
            let graph = project(&context, NODES, arcs.clone(), None).expect("projection");
            let result = pagerank(
                &graph,
                PageRankOptions {
                    max_iterations: 3,
                    tolerance: 0.0,
                    ..Default::default()
                },
            );
            assert_eq!(result.is_ok(), fits, "{workers} workers at {budget}");
        }
    }
}
