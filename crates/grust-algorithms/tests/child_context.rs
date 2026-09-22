//! A kernel run on a child execution is the kernel run on a root, to the bit:
//! a child changes whose budget memory is admitted from and whose counter work
//! is charged to, and nothing a kernel computes.
//!
//! The fixture is `tests/pagerank_pinned.rs`'s chord graph, which is large
//! enough to reach the parallel pull at every width; the work each call charges
//! identifies which loop ran, so neither side can pass on the sequential path
//! alone.

use grust_algorithms::{
    ChildLimits, ExecutionContext, ExecutionLimits, GraphProjection, Orientation, PageRankOptions,
    ProjectionEdge, SnapshotIdentity, pagerank,
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

fn project(context: &ExecutionContext) -> GraphProjection {
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
    GraphProjection::from_topology(
        SnapshotIdentity::new("child".into(), "r1".into(), "tests".into()).expect("identity"),
        (0..NODES).map(|id| id.to_string().into()).collect(),
        edges,
        None,
        Orientation::Outgoing,
        context,
    )
    .expect("projection")
}

/// Scores, iterations and residual as bits, and the work one call charged.
fn run(context: &ExecutionContext) -> (Vec<u64>, usize, u64, usize) {
    let graph = project(context);
    let options = || PageRankOptions {
        max_iterations: ITERATIONS,
        tolerance: 0.0,
        ..Default::default()
    };
    // The first call builds any transpose; the second is the one measured.
    pagerank(&graph, options()).expect("pagerank");
    let work = || {
        context
            .usage()
            .expect("usage")
            .counted_work()
            .expect("counted")
    };
    let before = work();
    let result = pagerank(&graph, options()).expect("pagerank");
    let charged = work() - before;
    (
        result
            .values()
            .iter()
            .map(|score| score.to_bits())
            .collect(),
        result.iterations(),
        result.residual().to_bits(),
        charged,
    )
}

/// `tests/pagerank_pinned.rs`'s closed forms for the two loops' work.
fn push_work() -> usize {
    6 * NODES + 2 * EDGES + ITERATIONS * (4 * NODES + EDGES)
}

#[test]
fn a_kernel_on_a_child_is_the_kernel_on_a_root_sequentially() {
    let on_root = run(&root());
    assert_eq!(on_root.3, push_work(), "the sequential push loop");
    let parent = root();
    let child = parent.child(ChildLimits::default()).expect("child");
    assert_eq!(run(&child), on_root);
    assert_eq!(parent.usage().expect("usage").live_bytes, 0);
}

#[cfg(feature = "parallel")]
#[test]
fn a_kernel_on_racing_children_is_the_kernel_on_a_root_at_every_width() {
    let pull_work = 2 * NODES + ITERATIONS * (3 * NODES + EDGES);
    for workers in [1, 4] {
        let on_root = run(&root().with_concurrency(workers).expect("unshared"));
        assert_eq!(
            on_root.3, pull_work,
            "{workers} workers must reach the pull"
        );
        // Siblings on their own threads, each with its own work budget and
        // concurrency, drawing on one parent's memory at the same time.
        let parent = root();
        // One sibling also has a memory sub-limit of its own, the other path
        // through admission.
        let children: Vec<ExecutionContext> = (0..3)
            .map(|index| {
                parent
                    .child(ChildLimits {
                        memory_bytes: (index == 0).then_some(1 << 29),
                        concurrency: Some(workers),
                        ..ChildLimits::default()
                    })
                    .expect("child")
            })
            .collect();
        let results: Vec<_> = std::thread::scope(|scope| {
            let runs: Vec<_> = children
                .iter()
                .map(|child| scope.spawn(move || run(child)))
                .collect();
            runs.into_iter()
                .map(|run| run.join().expect("child run"))
                .collect()
        });
        for (index, result) in results.iter().enumerate() {
            assert!(
                *result == on_root,
                "child {index} at {workers} workers differs from the root"
            );
        }
        for child in &children {
            let usage = child.usage().expect("usage");
            assert_eq!(usage.live_bytes, 0);
            assert!(usage.peak_bytes > 0, "the child admitted its projection");
        }
        let usage = parent.usage().expect("usage");
        assert_eq!(usage.live_bytes, 0, "every child's bytes came back");
        assert_eq!(
            usage.counted_work(),
            Some(0),
            "work stays with the children"
        );
    }
}
