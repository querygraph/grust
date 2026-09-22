//! PageRank with `f32` scores: the same kernel at a second precision.
//!
//! Four properties. The `f32` path is bit-identical at every worker count on
//! fixtures large enough to reach the parallel pull, and charges exactly the
//! work the `f64` path charges. Its scores agree with the `f64` kernel's, and
//! both agree with the recurrence written out again densely, within bounds
//! stated with their reasons. And it converges at tolerance 1e-8 on a
//! dangling-free graph with an iteration count that does not move with the
//! worker count. The `f64` kernel's own bits are pinned in
//! `tests/pagerank_pinned.rs`; this file does not repeat that.

use grust_algorithms::{
    ExecutionContext, ExecutionLimits, GraphProjection, Orientation, PageRank, PageRankOptions,
    ProjectionEdge, Score, SnapshotIdentity, pagerank, pagerank_f32,
};

fn context(workers: Option<usize>) -> ExecutionContext {
    let context = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 1 << 30,
        work_units: usize::MAX,
        batch_rows: 8192,
        deadline: None,
    })
    .expect("valid limits");
    match workers {
        Some(workers) => context.with_concurrency(workers).expect("not yet shared"),
        None => context,
    }
}

type Fixture = (usize, Vec<(usize, usize)>, Option<Vec<f64>>);

fn project(context: &ExecutionContext, (nodes, arcs, weights): &Fixture) -> GraphProjection {
    let edges = arcs
        .iter()
        .enumerate()
        .map(|(ordinal, &(source, target))| ProjectionEdge {
            source,
            target,
            ordinal,
            id: None,
        })
        .collect();
    GraphProjection::from_topology(
        SnapshotIdentity::new("f32".into(), "r1".into(), "tests".into()).expect("identity"),
        (0..*nodes).map(|id| id.to_string().into()).collect(),
        edges,
        weights.clone(),
        Orientation::Outgoing,
        context,
    )
    .expect("projection")
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

/// `tests/parallel.rs`'s graph: a permutation cycle, so no node is dangling,
/// plus chords biased to low rows, so a few sources have very high out-degree.
fn chords(weighted: bool) -> Fixture {
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

/// `tests/parallel.rs`'s dangling graph: half the nodes have no out-arcs, so
/// the dangling mass is a long reduction at every iteration.
fn dangling() -> Fixture {
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

/// Whether a fixture is large enough for an execution that asks for workers
/// to take the pull rather than the sequential push: the kernel's own rule.
fn reaches_the_pull((nodes, arcs, _): &Fixture) -> bool {
    (nodes + arcs.len()) * 2 >= 1 << 14
}

fn charged(context: &ExecutionContext) -> usize {
    context
        .usage()
        .expect("usage")
        .counted_work()
        .expect("counted")
}

/// Everything a run produces, comparable exactly. Scores are compared through
/// their bits, widened to `f64` for `f32`, which is exact.
fn exact<F: Score>(result: &PageRank<F>) -> (Vec<u64>, usize, u64, bool) {
    (
        result
            .values()
            .iter()
            .map(|score| score.to_f64().to_bits())
            .collect(),
        result.iterations(),
        result.residual().to_bits(),
        result.converged(),
    )
}

const ITERATIONS: usize = 25;

/// Every iteration runs, so the work charged is a closed formula of the graph
/// and identifies the path taken; `tests/pagerank_pinned.rs` states it.
fn fixed_iterations() -> PageRankOptions<'static> {
    PageRankOptions {
        max_iterations: ITERATIONS,
        tolerance: 0.0,
        ..Default::default()
    }
}

/// Run both precisions on one projection each, on a fresh execution each, and
/// return the `f32` result exactly, with the work each precision charged.
fn both(workers: Option<usize>, fixture: &Fixture) -> ((Vec<u64>, usize, u64, bool), usize, usize) {
    let context = context(workers);
    let graph = project(&context, fixture);
    // The transpose is built lazily by the first pull; the calls measured
    // below both find it built.
    let _ = pagerank(&graph, fixed_iterations()).expect("warm");
    let before = charged(&context);
    let double = pagerank(&graph, fixed_iterations()).expect("f64");
    let double_work = charged(&context) - before;
    let before = charged(&context);
    let single = pagerank_f32(&graph, fixed_iterations()).expect("f32");
    let single_work = charged(&context) - before;
    assert_eq!(double.iterations(), ITERATIONS);
    assert_eq!(single.iterations(), ITERATIONS);
    (exact(&single), single_work, double_work)
}

#[test]
fn f32_scores_are_bit_identical_at_every_worker_count_and_charge_what_f64_charges() {
    for (label, fixture) in [
        ("chords", chords(false)),
        ("weighted chords", chords(true)),
        ("dangling", dangling()),
    ] {
        assert!(reaches_the_pull(&fixture), "{label} would stay sequential");
        let (n, m) = (fixture.0, fixture.1.len());
        let weighted = fixture.2.is_some();
        let push = 6 * n + 2 * m + ITERATIONS * (4 * n + m);
        let pull = 2 * n + if weighted { n + 2 * m } else { 0 } + ITERATIONS * (3 * n + m);

        // The sequential push: the same work at either precision.
        let (_, single_work, double_work) = both(None, &fixture);
        assert_eq!(double_work, push, "{label}: f64 did not take the push");
        assert_eq!(
            single_work, push,
            "{label}: f32 charged other than the push"
        );

        // The pull at one worker, and then at two, three and sixteen: the
        // same bits, the same iteration count, the same residual, the same
        // work, every time.
        let (one, single_work, double_work) = both(Some(1), &fixture);
        assert_eq!(double_work, pull, "{label}: f64 did not take the pull");
        assert_eq!(
            single_work, pull,
            "{label}: f32 charged other than the pull"
        );
        for workers in [2, 3, 16] {
            let (other, single_work, double_work) = both(Some(workers), &fixture);
            assert_eq!(double_work, pull, "{label} at {workers} workers");
            assert_eq!(single_work, pull, "{label} at {workers} workers");
            let differing = one.0.iter().zip(&other.0).filter(|(a, b)| a != b).count();
            assert_eq!(
                differing, 0,
                "{label}: {differing} of {n} f32 scores differ between 1 and {workers} workers"
            );
            assert_eq!(
                (one.1, one.2, one.3),
                (other.1, other.2, other.3),
                "{label}: iterations, residual or convergence moved at {workers} workers"
            );
        }
    }
}

/// The recurrence written out again, densely and in `f64`, without the
/// kernel's scaling, chunking or pull: dangling rows redistribute through the
/// teleport term and a source divides by its out-degree.
fn oracle(n: usize, edges: &[(usize, usize)], damping: f64, iterations: usize) -> Vec<f64> {
    let mut out_degree = vec![0.0f64; n];
    for &(source, _) in edges {
        out_degree[source] += 1.0;
    }
    let mut scores = vec![1.0 / n as f64; n];
    for _ in 0..iterations {
        let dangling: f64 = (0..n)
            .filter(|&node| out_degree[node] == 0.0)
            .map(|node| scores[node])
            .sum();
        let base = ((1.0 - damping) + damping * dangling) / n as f64;
        let mut next = vec![base; n];
        for &(source, target) in edges {
            next[target] += damping * scores[source] / out_degree[source];
        }
        scores = next;
    }
    scores
}

/// `tests/article_rank.rs`'s citation graph: nodes 8 and 9 cite nothing, so
/// the dangling term is exercised.
const EDGES: [(usize, usize); 12] = [
    (1, 0),
    (1, 2),
    (1, 3),
    (1, 4),
    (1, 5),
    (2, 0),
    (3, 6),
    (4, 6),
    (6, 7),
    (7, 6),
    (5, 0),
    (0, 6),
];
const NODES: usize = 10;

/// `f32` keeps 24 significant bits, so each rounding is within 2^-24 ≈ 6e-8
/// of the value, relative. The iteration contracts by the damping factor, so
/// the roundings of every iteration accumulate to at most `1 / (1 - 0.85)`,
/// under seven, times one iteration's, and scores are below one: a few times
/// 1e-7 absolute. 1e-5 is more than twenty times that and far under any
/// difference that would mean the wrong recurrence was computed, which is
/// what these bounds exist to detect.
const F32_ABSOLUTE: f64 = 1e-5;

#[test]
fn f32_and_f64_agree_with_each_other_and_with_the_recurrence() {
    let context = context(None);
    let fixture = (NODES, EDGES.to_vec(), None);
    let graph = project(&context, &fixture);
    let options = PageRankOptions {
        tolerance: 0.0,
        max_iterations: 40,
        ..Default::default()
    };
    let double = pagerank(&graph, options).expect("f64");
    let single = pagerank_f32(&graph, options).expect("f32");
    let expected = oracle(NODES, &EDGES, 0.85, 40);
    for (node, &want) in expected.iter().enumerate() {
        let got = double.values()[node];
        assert!(
            (got - want).abs() <= 1e-12 + 1e-9 * want.abs(),
            "node {node}: f64 kernel {got} against oracle {want}"
        );
        let got = f64::from(single.values()[node]);
        assert!(
            (got - want).abs() <= F32_ABSOLUTE,
            "node {node}: f32 kernel {got} against oracle {want}"
        );
    }
    let mass: f64 = single.values().iter().map(|&score| f64::from(score)).sum();
    assert!((mass - 1.0).abs() <= F32_ABSOLUTE, "f32 mass {mass}");

    // On the large fixture, against the f64 kernel, which `tests/parallel.rs`
    // checks against its own push loop. Scores there are near 1e-5, so the
    // bound is relative, with an absolute floor for the smallest; the
    // observed worst case is 7.3e-7 relative, a dozen ulps, consistent with a
    // handful of roundings per score per iteration and the contraction
    // above. 1e-5 leaves an order of magnitude and still catches a wrong
    // recurrence, which is off by far more than rounding.
    let fixture = chords(false);
    let context = self::context(Some(1));
    let graph = project(&context, &fixture);
    let double = pagerank(&graph, fixed_iterations()).expect("f64");
    let single = pagerank_f32(&graph, fixed_iterations()).expect("f32");
    let mut worst = 0.0f64;
    for (node, (&want, &got)) in double.values().iter().zip(single.values()).enumerate() {
        let got = f64::from(got);
        let relative = (got - want).abs() / want.abs();
        worst = worst.max(relative);
        assert!(
            (got - want).abs() <= 1e-12 + 1e-5 * want.abs(),
            "node {node}: f32 {got} against f64 {want}"
        );
    }
    println!("worst f32 relative difference on chords: {worst:e}");
}

/// At tolerance 1e-8 on a graph with no dangling node, both precisions
/// converge within the iteration limit, and the `f32` iteration count and
/// residual are the same bits at one, two, three and sixteen workers: the
/// determinism a benchmark row needs. The counts are recorded, not compared:
/// the `f32` residual is a sum of rounded moves, which tracks the `f64`
/// residual to a few percent on this fixture (observed 8.97e-9 against
/// 8.60e-9, both stopping at 93), but the weighted form of the same fixture
/// stops at 94 against 93, and a fixture with many dangling nodes needs about
/// twice the iterations at `f32`, so neither order is a property to assert.
///
/// At tolerance zero both precisions reach an exact fixed point of their
/// rounded iteration on this fixture, which is also recorded: an `f32` ulp is
/// 2^29 `f64` ulps, so the `f32` scores fall still earlier (observed 147
/// iterations against 261 on the pull).
#[test]
fn both_precisions_converge_at_1e_8_and_f32_s_count_is_the_same_at_every_width() {
    let fixture = chords(false);
    let (n, arcs, _) = &fixture;
    let mut out_degree = vec![0usize; *n];
    for &(source, _) in arcs {
        out_degree[source] += 1;
    }
    assert!(
        out_degree.iter().all(|&degree| degree > 0),
        "the fixture must have no dangling node"
    );
    for tolerance in [1e-8, 0.0] {
        let options = PageRankOptions {
            tolerance,
            max_iterations: 1000,
            ..Default::default()
        };
        let mut pulled: Option<(usize, u64)> = None;
        for workers in [None, Some(1), Some(2), Some(3), Some(16)] {
            let context = context(workers);
            let graph = project(&context, &fixture);
            let double = pagerank(&graph, options).expect("f64");
            let single = pagerank_f32(&graph, options).expect("f32");
            println!(
                "tolerance {tolerance:e}, workers {workers:?}: f64 {} iterations, residual {:e}; f32 {} iterations, residual {:e}",
                double.iterations(),
                double.residual(),
                single.iterations(),
                single.residual()
            );
            assert!(double.converged(), "f64 did not converge at {tolerance:e}");
            assert!(single.converged(), "f32 did not converge at {tolerance:e}");
            assert!(single.iterations() < options.max_iterations);
            if tolerance == 0.0 {
                assert_eq!(single.residual(), 0.0);
                assert_eq!(double.residual(), 0.0);
            }
            // The push and the pull sum in different orders and may stop at
            // different iterations; the pull must not move with its width.
            if workers.is_some() {
                let count = (single.iterations(), single.residual().to_bits());
                match pulled {
                    None => pulled = Some(count),
                    Some(first) => assert_eq!(
                        first, count,
                        "the f32 count or residual moved at {workers:?} workers"
                    ),
                }
            }
        }
    }
}
