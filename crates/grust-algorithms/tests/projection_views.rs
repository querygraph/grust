//! A cached projection run on a query's own execution.
//!
//! `GraphProjection::with_execution` makes a view that shares the projection's
//! data and runs kernels on another execution: the projection's owner or a
//! descendant of it. These tests pin what that means: which executions are
//! allowed; that state the projection keeps, the transpose, is the owner's
//! whichever view builds it; that each view is cancelled, deadlined and charged
//! on its own; and that a kernel on a view computes, to the bit, what it
//! computes on the owner.
//!
//! The PageRank fixture is `tests/child_context.rs`'s chord graph, large enough
//! to reach the parallel pull, which reads the transpose.

use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use grust_algorithms::{
    AlgorithmError, ChildLimits, ExecutionContext, ExecutionLimits, GraphProjection,
    LabelPropagationOptions, Orientation, PageRankOptions, ProjectionEdge, SnapshotIdentity,
    label_propagation, pagerank,
};

const NODES: usize = 120_000;
const EDGES: usize = 600_000;
const ITERATIONS: usize = 25;

fn root() -> ExecutionContext {
    ExecutionContext::new(ExecutionLimits {
        memory_bytes: 1 << 30,
        work_units: usize::MAX,
        batch_rows: 8192,
        deadline: None,
    })
    .expect("valid limits")
}

fn chord(nodes: usize, edges: usize, context: &ExecutionContext) -> GraphProjection {
    let mut state = 0x2545_F491_4F6C_DD1Du64;
    let mut random = move || {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        state
    };
    let edges = (0..edges)
        .map(|ordinal| {
            let (source, target) = if ordinal < nodes {
                (ordinal, (ordinal + 1) % nodes)
            } else {
                let source = (random() % (nodes as u64 / 16)) as usize;
                (source, (random() % nodes as u64) as usize)
            };
            ProjectionEdge {
                source,
                target,
                ordinal,
                id: None,
            }
        })
        .collect();
    GraphProjection::from_topology(
        SnapshotIdentity::new("views".into(), "r1".into(), "tests".into()).expect("identity"),
        (0..nodes).map(|id| id.to_string().into()).collect(),
        edges,
        None,
        Orientation::Outgoing,
        context,
    )
    .expect("projection")
}

fn project(context: &ExecutionContext) -> GraphProjection {
    chord(NODES, EDGES, context)
}

fn live(context: &ExecutionContext) -> usize {
    context.usage().expect("usage").live_bytes
}

fn work(context: &ExecutionContext) -> usize {
    context
        .usage()
        .expect("usage")
        .counted_work()
        .expect("counted")
}

fn options(iterations: usize) -> PageRankOptions<'static> {
    PageRankOptions {
        max_iterations: iterations,
        tolerance: 0.0,
        ..Default::default()
    }
}

/// Scores, iterations and residual as bits.
type Bits = (Vec<u64>, usize, u64);

fn rank(graph: &GraphProjection, iterations: usize) -> Result<Bits, AlgorithmError> {
    let result = pagerank(graph, options(iterations))?;
    Ok((
        result.values().iter().map(|s| s.to_bits()).collect(),
        result.iterations(),
        result.residual().to_bits(),
    ))
}

/// Two calls, as a cached projection sees them: the first may build the
/// transpose, the second reads it. Each call's bits and the work it charged.
fn twice(graph: &GraphProjection) -> [(Bits, usize); 2] {
    let context = graph.execution();
    let call = || {
        let before = work(context);
        let bits = rank(graph, ITERATIONS).expect("pagerank");
        (bits, work(context) - before)
    };
    [call(), call()]
}

fn child_at(parent: &ExecutionContext, workers: Option<usize>) -> ExecutionContext {
    parent
        .child(ChildLimits {
            concurrency: workers,
            ..ChildLimits::default()
        })
        .expect("child")
}

#[test]
fn a_view_runs_only_on_its_owner_or_a_descendant() {
    let owner = root();
    let graph = chord(64, 256, &owner);
    let child = owner.child(ChildLimits::default()).expect("child");
    let grandchild = child.child(ChildLimits::default()).expect("grandchild");
    for allowed in [&owner, &child, &grandchild] {
        let view = graph.with_execution(allowed).expect("allowed");
        // The same owner, and the view runs where it was asked to.
        assert!(view.owner().is_within(&owner) && owner.is_within(view.owner()));
        assert!(view.execution().is_within(allowed) && allowed.is_within(view.execution()));
        // A view of a view is judged against the owner, not the view.
        graph
            .with_execution(&child)
            .expect("view")
            .with_execution(&grandchild)
            .expect("re-viewed");
    }

    let stranger = root();
    let strangers_child = stranger.child(ChildLimits::default()).expect("child");
    for refused in [&stranger, &strangers_child] {
        let error = graph.with_execution(refused).err().expect("refused");
        assert!(
            matches!(&error, AlgorithmError::InvalidArguments(message) if message.contains("descendant")),
            "{error:?}"
        );
    }

    // A projection built on a child: neither its parent nor its sibling is
    // within it, so neither may run it.
    let owner_child = owner.child(ChildLimits::default()).expect("child");
    let sibling = owner.child(ChildLimits::default()).expect("sibling");
    let on_child = chord(64, 256, &owner_child);
    for refused in [&owner, &sibling] {
        assert!(matches!(
            on_child.with_execution(refused),
            Err(AlgorithmError::InvalidArguments(_))
        ));
    }
    on_child
        .with_execution(&owner_child.child(ChildLimits::default()).expect("child"))
        .expect("a child of the owner");
}

#[test]
fn the_transpose_is_the_owners_whichever_view_builds_it() {
    // What the transpose costs, measured where one execution does everything.
    let (transpose_bytes, transpose_work) = {
        let context = root();
        let graph = chord(4096, 32_768, &context);
        let (bytes, units) = (live(&context), work(&context));
        graph.prepare_incoming().expect("transpose");
        (live(&context) - bytes, work(&context) - units)
    };
    // The transpose really is proportional to the arcs: at least its target
    // array, which is four bytes an arc since the CSR narrowed targets to
    // `u32` — it was a word an arc, and this bound said `size_of::<usize>()`.
    assert!(transpose_bytes > 32_768 * 4);

    let owner = root();
    let graph = chord(4096, 32_768, &owner);
    let projection_bytes = live(&owner);
    let owner_work = work(&owner);

    // A query whose work budget runs out inside the build: it fails, nothing
    // is kept, and every byte the build admitted is back with the owner.
    let starved = owner
        .child(ChildLimits {
            work_units: transpose_work / 2,
            ..ChildLimits::default()
        })
        .expect("child");
    let error = graph
        .with_execution(&starved)
        .expect("view")
        .prepare_incoming()
        .expect_err("the build does not fit the query's work budget");
    assert!(
        matches!(
            error,
            AlgorithmError::BudgetExceeded {
                resource: "work",
                ..
            }
        ),
        "{error:?}"
    );
    assert_eq!(
        live(&owner),
        projection_bytes,
        "a failed build keeps nothing"
    );
    drop(starved);

    // A query with a memory sub-limit far below the transpose can still build
    // it: the transpose is not the query's memory.
    let query = owner
        .child(ChildLimits {
            memory_bytes: Some(1),
            ..ChildLimits::default()
        })
        .expect("child");
    let view = graph.with_execution(&query).expect("view");
    view.prepare_incoming().expect("admitted by the owner");
    assert_eq!(live(&query), 0, "the query holds none of the transpose");
    assert_eq!(query.usage().expect("usage").peak_bytes, 0);
    assert_eq!(work(&query), transpose_work, "the query paid for the build");
    assert_eq!(work(&owner), owner_work, "the owner charged no work");
    assert_eq!(live(&owner), projection_bytes + transpose_bytes);
    drop(view);
    drop(query);

    // A kernel through another child's view uses the transpose now kept,
    // builds nothing, and returns every byte it admitted.
    let query = owner.child(ChildLimits::default()).expect("child");
    let view = graph.with_execution(&query).expect("view");
    let result = label_propagation(&view, LabelPropagationOptions::default()).expect("kernel");
    assert!(live(&query) > 0, "the result is the query's");
    drop(result);
    assert_eq!(live(&query), 0);
    drop(view);
    drop(query);
    assert_eq!(
        live(&owner),
        projection_bytes + transpose_bytes,
        "the transpose outlives every query"
    );

    // Released when the projection is, and not before.
    drop(graph);
    assert_eq!(live(&owner), 0);
}

#[test]
fn a_kernel_on_a_view_builds_the_transpose_for_the_owner() {
    // As above, with the transpose built inside a kernel on a child's view,
    // the path a cached projection's first in-arc query takes.
    let owner = root();
    let graph = chord(4096, 32_768, &owner);
    let projection_bytes = live(&owner);
    let query = owner.child(ChildLimits::default()).expect("child");
    let view = graph.with_execution(&query).expect("view");
    let result = label_propagation(&view, LabelPropagationOptions::default()).expect("kernel");
    drop(result);
    assert_eq!(live(&query), 0, "the query holds none of the transpose");
    let held = live(&owner);
    assert!(held > projection_bytes, "the owner holds the transpose");
    drop(view);
    drop(query);
    assert_eq!(live(&owner), held, "and keeps it after the query is gone");
    let before = live(&owner);
    graph.prepare_incoming().expect("kept");
    assert_eq!(live(&owner), before, "nothing is built again");
    drop(graph);
    assert_eq!(live(&owner), 0, "released with the projection");
}

#[test]
fn a_kernel_on_a_view_is_the_kernel_on_the_owner_sequentially() {
    let owner = root();
    let expected = twice(&project(&owner));
    let graph = project(&owner);
    let child = child_at(&owner, None);
    let owner_work = work(&owner);
    assert_eq!(
        twice(&graph.with_execution(&child).expect("view")),
        expected
    );
    assert_eq!(work(&owner), owner_work, "the view charged the child");
    // And on the owner through a view of itself.
    assert_eq!(
        twice(&project(&owner).with_execution(&owner).expect("view")),
        expected
    );
}

#[cfg(feature = "parallel")]
#[test]
fn a_kernel_on_a_view_is_the_kernel_on_the_owner_at_every_width() {
    for workers in [1, 4] {
        let reference = root().with_concurrency(workers).expect("unshared");
        let expected = twice(&project(&reference));
        let owner = root();
        let graph = project(&owner);
        let owner_work = work(&owner);
        let child = child_at(&owner, Some(workers));
        let got = twice(&graph.with_execution(&child).expect("view"));
        // The first call built the transpose through the view: same bits, and
        // the same work, since the build is charged to whoever runs it.
        assert!(got == expected, "{workers} workers differ from the owner");
        assert_eq!(work(&owner), owner_work, "every unit went to the child");
        assert!(live(&owner) > 0);
    }
}

/// Two queries on one cached projection, each on its own child: one is
/// cancelled while both run, and the other finishes with the owner's answer.
/// `expected_work` is the survivor's work when the transpose was already
/// built; when it was not, either query may build it, and the survivor's work
/// then depends on which did. Returns whether the cancellation landed while
/// the survivor was still running, which the scheduler decides.
fn race_once(
    graph: &GraphProjection,
    workers: Option<usize>,
    expected: &Bits,
    expected_work: Option<usize>,
) -> bool {
    let owner = graph.owner();
    let owner_work = work(owner);
    let doomed = child_at(owner, workers);
    let survivor = child_at(owner, workers);
    let doomed_view = graph.with_execution(&doomed).expect("view");
    let survivor_view = graph.with_execution(&survivor).expect("view");
    let survivor_done = AtomicBool::new(false);
    let (doomed_result, survivor_result, overlapped) = std::thread::scope(|scope| {
        // Long enough never to finish before it is cancelled.
        let doomed_run = scope.spawn(|| rank(&doomed_view, 1_000_000));
        let survivor_run = scope.spawn(|| {
            let result = rank(&survivor_view, ITERATIONS);
            survivor_done.store(true, Ordering::Release);
            result
        });
        // Both have charged work: both kernels are under way.
        let started = Instant::now();
        while work(&doomed) == 0 || work(&survivor) == 0 {
            assert!(
                started.elapsed() < Duration::from_secs(120),
                "never started"
            );
            std::hint::spin_loop();
        }
        doomed.cancel().expect("cancel");
        let overlapped = !survivor_done.load(Ordering::Acquire);
        (
            doomed_run.join().expect("doomed"),
            survivor_run.join().expect("survivor"),
            overlapped,
        )
    });
    assert!(
        matches!(doomed_result, Err(AlgorithmError::Cancelled)),
        "{doomed_result:?}"
    );
    let survivor_result = survivor_result.expect("the survivor finishes");
    assert!(survivor_result == *expected, "the survivor's bits changed");
    if let Some(units) = expected_work {
        assert_eq!(
            work(&survivor),
            units,
            "the survivor's counter holds its own work and nothing else"
        );
    }
    assert_eq!(work(owner), owner_work, "neither query charged the owner");
    owner.checkpoint().expect("the owner is not cancelled");
    survivor.checkpoint().expect("nor is the sibling");
    overlapped
}

fn runs() -> usize {
    std::env::var("GRUST_VIEW_RACE_RUNS")
        .ok()
        .and_then(|runs| runs.parse().ok())
        .unwrap_or(2)
}

fn race(workers: Option<usize>) {
    let reference = match workers {
        Some(workers) => root().with_concurrency(workers).expect("unshared"),
        None => root(),
    };
    // The second call reads a transpose already built, as a cached
    // projection's would be, so its work is the kernel's alone.
    let [_, (expected, kernel_work)] = twice(&project(&reference));
    let owner = root();
    let runs = runs();
    let mut overlapped = 0;
    for run in 0..runs {
        // A fresh projection each run. Every other run builds its transpose
        // first; in the rest the two queries also race to build it through
        // their views.
        let graph = project(&owner);
        let prepared = run % 2 == 1;
        if prepared {
            graph.prepare_incoming().expect("transpose");
        }
        let expected_work = prepared.then_some(kernel_work);
        overlapped += usize::from(race_once(&graph, workers, &expected, expected_work));
        drop(graph);
        assert_eq!(live(&owner), 0, "run {run}: every byte came back");
    }
    eprintln!("workers {workers:?}: {runs} runs, cancelled while the survivor ran in {overlapped}");
}

#[test]
fn cancelling_one_query_leaves_another_on_the_same_projection_sequentially() {
    race(None);
}

#[cfg(feature = "parallel")]
#[test]
fn cancelling_one_query_leaves_another_on_the_same_projection_in_parallel() {
    race(Some(4));
}

#[test]
fn a_views_deadline_is_its_own() {
    let owner = root();
    let graph = project(&owner);
    let late = owner
        .child(ChildLimits {
            deadline: Some(Instant::now()),
            ..ChildLimits::default()
        })
        .expect("child");
    std::thread::sleep(Duration::from_millis(2));
    assert!(matches!(
        rank(&graph.with_execution(&late).expect("view"), ITERATIONS),
        Err(AlgorithmError::DeadlineExceeded)
    ));
    let on_time = owner.child(ChildLimits::default()).expect("child");
    rank(&graph.with_execution(&on_time).expect("view"), ITERATIONS).expect("unaffected");
    rank(&graph, ITERATIONS).expect("the owner is unaffected");

    // Cancelling the owner reaches every view of its projection.
    let query = owner.child(ChildLimits::default()).expect("child");
    let view = graph.with_execution(&query).expect("view");
    owner.cancel().expect("cancel");
    assert!(matches!(
        rank(&view, ITERATIONS),
        Err(AlgorithmError::Cancelled)
    ));
}
