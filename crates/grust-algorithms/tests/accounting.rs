//! Kernels under every accounting mode.
//!
//! Turning accounting off must change what an execution checks, never what a
//! kernel computes: every result here is compared bit for bit against the
//! counted run at the same width, sequentially and at one, two and sixteen
//! workers. The graph is large enough that the parallel paths run; the
//! PageRank comparison below checks that, since a fixture that stayed
//! sequential would make the parallel half of this file vacuous.

use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use grust_algorithms::{
    Accounting, AlgorithmError, BetweennessOptions, ExecutionContext, ExecutionLimits,
    GraphProjection, Interruption, Orientation, PageRank, PageRankOptions, ProjectionEdge,
    RankVariant, SnapshotIdentity, WorkAccounting, WorkCount, betweenness, bfs, degree,
    multi_source_bfs, pagerank, weakly_connected_components,
};

const NODES: usize = 60_000;
const EDGES: usize = 300_000;

const UNINTERRUPTIBLE: Accounting = Accounting {
    work: WorkAccounting::Counted,
    interruption: Interruption::Disabled,
};
const MODES: [Accounting; 4] = [
    Accounting::COUNTED,
    Accounting::WORK_UNCOUNTED,
    UNINTERRUPTIBLE,
    Accounting::UNCHECKED,
];
/// `None` never asks for threads and runs the sequential kernels.
const WIDTHS: [Option<usize>; 4] = [None, Some(1), Some(2), Some(16)];

fn context(
    accounting: Accounting,
    workers: Option<usize>,
    deadline: Option<Instant>,
) -> ExecutionContext {
    let context = ExecutionContext::with_accounting(
        ExecutionLimits {
            memory_bytes: 1 << 30,
            work_units: usize::MAX,
            batch_rows: 8192,
            deadline,
        },
        accounting,
    )
    .expect("valid limits");
    match workers {
        Some(workers) => context.with_concurrency(workers).expect("not yet shared"),
        None => context,
    }
}

fn graph(context: ExecutionContext, weighted: bool) -> GraphProjection {
    try_graph(context, weighted).expect("projection")
}

/// A permutation cycle plus skewed pseudo-random chords, as in `parallel.rs`.
fn try_graph(
    context: ExecutionContext,
    weighted: bool,
) -> grust_algorithms::Result<GraphProjection> {
    let nodes = (0..NODES).map(|id| id.to_string().into()).collect();
    let mut state = 0x2545_F491_4F6C_DD1Du64;
    let mut random = move || {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        state
    };
    let edges = (0..EDGES)
        .map(|ordinal| {
            let (source, target) = if ordinal < NODES {
                (ordinal, (ordinal + 1) % NODES)
            } else {
                let source = (random() % (NODES as u64 / 16)) as usize;
                (source, (random() % NODES as u64) as usize)
            };
            ProjectionEdge {
                source,
                target,
                ordinal,
                id: None,
            }
        })
        .collect();
    let weights = weighted.then(|| (0..EDGES).map(|index| 1.0 + (index % 7) as f64).collect());
    GraphProjection::from_topology(
        SnapshotIdentity::new("accounting".into(), "r1".into(), "tests".into()).expect("identity"),
        nodes,
        edges,
        weights,
        Orientation::Outgoing,
        &context,
    )
}

fn bits(result: &PageRank) -> Vec<u64> {
    float_bits(result.values())
}

const PAGERANK: PageRankOptions<'static> = PageRankOptions {
    variant: RankVariant::PageRank,
    damping: 0.85,
    tolerance: 1e-10,
    max_iterations: 100,
    personalization: None,
};

/// Everything one run produces, in a form compared exactly.
#[derive(Debug, PartialEq)]
struct Results {
    pagerank: Vec<u64>,
    pagerank_iterations: usize,
    pagerank_residual: u64,
    weighted_pagerank: Vec<u64>,
    counts: Vec<u64>,
    strengths: Option<Vec<u64>>,
    distances: Vec<u64>,
    multi_distances: Vec<u64>,
    components: Vec<usize>,
}

fn run(accounting: Accounting, workers: Option<usize>) -> Results {
    let plain = graph(context(accounting, workers, None), false);
    let weighted = graph(context(accounting, workers, None), true);
    let rank = pagerank(&plain, PAGERANK).expect("pagerank");
    let weighted_rank = pagerank(&weighted, PAGERANK).expect("weighted pagerank");
    let degrees = degree(&weighted).expect("degree");
    let sources: Vec<String> = ["0", "7", "4242"].iter().map(|id| id.to_string()).collect();
    let results = Results {
        pagerank: bits(&rank),
        pagerank_iterations: rank.iterations(),
        pagerank_residual: rank.residual().to_bits(),
        weighted_pagerank: bits(&weighted_rank),
        counts: degrees.counts().iter().map(|&count| count as u64).collect(),
        strengths: degrees.strengths().map(float_bits),
        distances: float_bits(bfs(&plain, "0").expect("bfs").values()),
        multi_distances: float_bits(multi_source_bfs(&plain, &sources).expect("msbfs").values()),
        components: weakly_connected_components(&plain)
            .expect("wcc")
            .values()
            .to_vec(),
    };
    // Each mode reports itself, and never reports a zero it did not count.
    let usage = plain.execution().usage().expect("usage");
    assert_eq!(usage.accounting, accounting);
    match accounting.work {
        WorkAccounting::Counted => {
            assert!(matches!(usage.work_units, WorkCount::Counted(units) if units > 0))
        }
        WorkAccounting::Disabled => assert_eq!(usage.work_units, WorkCount::NotCounted),
    }
    results
}

fn float_bits(values: &[f64]) -> Vec<u64> {
    values.iter().map(|value| value.to_bits()).collect()
}

#[test]
fn results_are_bit_identical_in_every_accounting_mode_at_every_width() {
    for workers in WIDTHS {
        let counted = run(Accounting::COUNTED, workers);
        for accounting in &MODES[1..] {
            assert!(
                run(*accounting, workers) == counted,
                "{accounting} differs from counted at {workers:?} workers"
            );
        }
    }
}

#[test]
fn the_fixture_reaches_the_parallel_kernels_with_accounting_off() {
    // The sequential PageRank pushes and the parallel one pulls, so they sum in
    // different orders and differ in low bits. If these were equal, the "16
    // workers" runs above would have been sequential runs under another name.
    let sequential = pagerank(
        &graph(context(Accounting::UNCHECKED, None, None), false),
        PAGERANK,
    )
    .expect("sequential");
    let parallel = pagerank(
        &graph(context(Accounting::UNCHECKED, Some(16), None), false),
        PAGERANK,
    )
    .expect("parallel");
    assert_ne!(bits(&sequential), bits(&parallel));
}

/// Exact betweenness on the fixture: a kernel that cannot finish on a test's
/// timescale at any width these tests use.
///
/// Its work is fixed by the graph, not by convergence. Every node reaches every
/// other along the permutation cycle, so each of the `NODES` single-source
/// passes charges `1 + outdegree` for every node twice, forward and back:
/// `2 · NODES · (NODES + EDGES)` = 4.32e10 units on any host. A ten-core
/// laptop's uncounted release build runs 2.3e8 units a second on one worker
/// and 1.3e9 on sixteen, so the run would take about 190 s and 33 s. Even one
/// unit per cycle at 5 GHz on each of sixteen workers, which no core reaches
/// with a dependent load per arc, would need 0.54 s; the tests below stop it
/// within milliseconds of seeing it start, or at a deadline a few hundred
/// milliseconds after the build. PageRank at tolerance zero is not such a
/// kernel: it stops when the residual is exactly zero, and floating-point
/// PageRank reaches that, on this fixture in 264 iterations at sixteen workers.
const EXACT: BetweennessOptions = BetweennessOptions {
    sampling_size: None,
    seed: 0,
    normalized: false,
};

/// Exact betweenness, which only cancellation or a deadline ends in time.
/// `Ok(())` means it finished, which is the failure these tests look for.
fn endless(projection: &GraphProjection) -> Result<(), AlgorithmError> {
    betweenness(projection, EXACT).map(drop)
}

#[test]
fn a_running_kernel_with_uncounted_work_can_still_be_cancelled() {
    for workers in [None, Some(2), Some(16)] {
        let projection = graph(context(Accounting::WORK_UNCOUNTED, workers, None), false);
        let execution = projection.execution().clone();
        // What the projection holds. The kernel reserves its first buffer after
        // its entry checkpoint, so memory above this means it is running.
        let built = execution.usage().expect("usage").live_bytes;
        let returned = AtomicBool::new(false);
        let (outcome, seen_running) = std::thread::scope(|scope| {
            let observer = scope.spawn(|| {
                while !returned.load(Ordering::Acquire) {
                    if execution.usage().expect("usage").live_bytes > built {
                        execution.cancel().expect("cancellation is accepted");
                        return true;
                    }
                    std::thread::yield_now();
                }
                false
            });
            let outcome = endless(&projection);
            returned.store(true, Ordering::Release);
            (outcome, observer.join().expect("observer"))
        });
        assert!(
            seen_running,
            "{workers:?} workers: the kernel returned {outcome:?} before it was seen running"
        );
        assert!(
            matches!(outcome, Err(AlgorithmError::Cancelled)),
            "{workers:?} workers: stopped by {outcome:?}, not by cancellation"
        );
    }
}

#[test]
fn a_running_kernel_with_uncounted_work_still_meets_its_deadline() {
    for workers in [None, Some(2), Some(16)] {
        // A deadline is fixed when its execution is created, and a projection
        // is built inside the execution it belongs to, so the build spends from
        // the deadline: nothing can set one after it. The window has to cover
        // the build, and a fixed 300 ms once did not, on a burstable host
        // running four test binaries at once. So a throwaway build times this
        // machine under its present load, and the window is four of those plus
        // a quarter of a second. The kernel cannot finish inside that at any
        // width (see `EXACT`), so only this edge of the window needs a margin.
        let started = Instant::now();
        drop(graph(
            context(Accounting::WORK_UNCOUNTED, workers, None),
            false,
        ));
        let build = started.elapsed();
        let deadline = Instant::now() + build * 4 + Duration::from_millis(250);
        let projection = graph(
            context(Accounting::WORK_UNCOUNTED, workers, Some(deadline)),
            false,
        );
        assert!(
            Instant::now() < deadline,
            "{workers:?} workers: the build spent the whole deadline, so this \
             would test the projection rather than the kernel"
        );
        let outcome = endless(&projection);
        assert!(
            matches!(outcome, Err(AlgorithmError::DeadlineExceeded)),
            "{workers:?} workers: stopped by {outcome:?}, not by the deadline"
        );
    }
}

#[test]
fn an_unchecked_kernel_cannot_be_cancelled_and_says_so() {
    let projection = graph(context(Accounting::UNCHECKED, Some(2), None), false);
    assert!(matches!(
        projection.execution().cancel(),
        Err(AlgorithmError::Unsupported(_))
    ));
    // The refused cancellation left nothing behind: the kernel runs to the
    // same answer as a counted run.
    let unchecked = pagerank(&projection, PAGERANK).expect("unchecked pagerank");
    let counted = pagerank(
        &graph(context(Accounting::COUNTED, Some(2), None), false),
        PAGERANK,
    )
    .expect("counted pagerank");
    assert_eq!(bits(&unchecked), bits(&counted));
}

#[test]
fn memory_admission_still_refuses_a_projection_that_does_not_fit() {
    for accounting in MODES {
        let context = ExecutionContext::with_accounting(
            ExecutionLimits {
                memory_bytes: 64 * 1024,
                work_units: usize::MAX,
                batch_rows: 8192,
                deadline: None,
            },
            accounting,
        )
        .expect("valid limits");
        let refused = try_graph(context, false).map(|_| ());
        assert!(
            matches!(
                refused,
                Err(AlgorithmError::BudgetExceeded {
                    resource: "memory",
                    ..
                })
            ),
            "{accounting}: {refused:?}"
        );
    }
}
