//! Kernels under every accounting mode.
//!
//! Turning accounting off must change what an execution checks, never what a
//! kernel computes: every result here is compared bit for bit against the
//! counted run at the same width, sequentially and at one, two and sixteen
//! workers. The graph is large enough that the parallel paths run; the
//! PageRank comparison below checks that, since a fixture that stayed
//! sequential would make the parallel half of this file vacuous.

use std::time::{Duration, Instant};

use grust_algorithms::{
    Accounting, AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, Interruption,
    Orientation, PageRank, PageRankOptions, ProjectionEdge, SnapshotIdentity, WorkAccounting,
    WorkCount, bfs, degree, multi_source_bfs, pagerank, weakly_connected_components,
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

/// Unbounded PageRank: it stops only when something stops it.
const ENDLESS: PageRankOptions<'static> = PageRankOptions {
    damping: 0.85,
    tolerance: 0.0,
    max_iterations: usize::MAX,
    personalization: None,
};

#[test]
fn a_running_kernel_with_uncounted_work_can_still_be_cancelled() {
    for workers in [None, Some(2), Some(16)] {
        let projection = graph(context(Accounting::WORK_UNCOUNTED, workers, None), false);
        let execution = projection.execution().clone();
        let started = Instant::now();
        let outcome = std::thread::scope(|scope| {
            scope.spawn(|| {
                // Long enough that the kernel is past its entry checkpoint and
                // inside its iterations on any reasonable host.
                std::thread::sleep(Duration::from_millis(200));
                execution.cancel().expect("cancellation is accepted");
            });
            pagerank(&projection, ENDLESS)
        });
        assert!(
            matches!(outcome, Err(AlgorithmError::Cancelled)),
            "{workers:?} workers: {:?}",
            outcome.map(|rank| rank.iterations())
        );
        assert!(started.elapsed() >= Duration::from_millis(200));
    }
}

#[test]
fn a_running_kernel_with_uncounted_work_still_meets_its_deadline() {
    for workers in [None, Some(2), Some(16)] {
        let deadline = Instant::now() + Duration::from_millis(300);
        let projection = graph(
            context(Accounting::WORK_UNCOUNTED, workers, Some(deadline)),
            false,
        );
        let outcome = pagerank(&projection, ENDLESS);
        assert!(
            matches!(outcome, Err(AlgorithmError::DeadlineExceeded)),
            "{workers:?} workers: {:?}",
            outcome.map(|rank| rank.iterations())
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
