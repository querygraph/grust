//! The parallel paths against the sequential ones, on a graph large enough to
//! cross the threshold where kernels use threads at all.
//!
//! Two properties per kernel. Against one thread: the same answer, exactly for
//! integers and identifiers, within a stated tolerance where the parallel path
//! sums floats in a different order. Against itself at two and sixteen threads:
//! bit-for-bit identical, because a result that moves with the thread count is
//! a result nobody can reproduce.

use grust_algorithms::{
    ExecutionContext, ExecutionLimits, GraphProjection, Orientation, PageRankOptions,
    ProjectionEdge, SnapshotIdentity, bfs, degree, multi_source_bfs, pagerank,
    weakly_connected_components,
};

const NODES: usize = 120_000;
const EDGES: usize = 600_000;

fn context(workers: usize) -> ExecutionContext {
    ExecutionContext::new(ExecutionLimits {
        memory_bytes: 1 << 30,
        work_units: usize::MAX,
        batch_rows: 8192,
        deadline: None,
    })
    .expect("valid limits")
    .with_concurrency(workers)
    .expect("not yet shared")
}

/// A deterministic graph: a permutation cycle so every node has a successor,
/// plus pseudo-random chords from a fixed linear congruential sequence, so the
/// degree distribution is skewed enough that a naive split would be unbalanced.
fn graph(workers: usize, weighted: bool) -> GraphProjection {
    let context = context(workers);
    let nodes = (0..NODES).map(|id| id.to_string().into()).collect();
    let mut edges = Vec::with_capacity(EDGES);
    let mut state = 0x2545_F491_4F6C_DD1Du64;
    let mut random = move || {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        state
    };
    for ordinal in 0..EDGES {
        let (source, target) = if ordinal < NODES {
            (ordinal, (ordinal + 1) % NODES)
        } else {
            // Bias sources towards low rows, giving a few very high degrees.
            let source = (random() % (NODES as u64 / 16)) as usize;
            (source, (random() % NODES as u64) as usize)
        };
        edges.push(ProjectionEdge {
            source,
            target,
            ordinal,
            id: None,
        });
    }
    let weights = weighted.then(|| (0..EDGES).map(|index| 1.0 + (index % 7) as f64).collect());
    GraphProjection::from_topology(
        SnapshotIdentity::new("parallel".into(), "r1".into(), "tests".into()).expect("identity"),
        nodes,
        edges,
        weights,
        Orientation::Outgoing,
        &context,
    )
    .expect("projection")
}

#[test]
fn degree_is_identical_at_every_thread_count() {
    let sequential = degree(&graph(1, true)).expect("sequential degree");
    for workers in [2, 16] {
        let parallel = degree(&graph(workers, true)).expect("parallel degree");
        assert_eq!(parallel.counts(), sequential.counts(), "{workers} threads");
        // Each node sums its own arcs in CSR order on both paths, so weighted
        // strengths are bit-for-bit equal, not merely close.
        assert_eq!(
            parallel.strengths(),
            sequential.strengths(),
            "{workers} threads"
        );
    }
}

#[test]
fn pagerank_agrees_with_the_sequential_push_and_does_not_move_with_threads() {
    let options = PageRankOptions {
        damping: 0.85,
        tolerance: 1e-10,
        max_iterations: 100,
        personalization: None,
    };
    let sequential = pagerank(&graph(1, false), options).expect("sequential pagerank");
    let two = pagerank(&graph(2, false), options).expect("pagerank at two threads");
    let sixteen = pagerank(&graph(16, false), options).expect("pagerank at sixteen threads");

    // The parallel path pulls into each target instead of pushing out of each
    // source, so the same distribution is summed in a different order. Scores
    // agree to far better than any reported precision; the mass still sums to one.
    for (node, (&pushed, &pulled)) in sequential.values().iter().zip(sixteen.values()).enumerate() {
        assert!(
            (pushed - pulled).abs() <= 1e-12 + 1e-9 * pushed.abs(),
            "node {node}: push {pushed} against pull {pulled}"
        );
    }
    let total: f64 = sixteen.values().iter().sum();
    assert!((total - 1.0).abs() < 1e-9, "mass {total}");
    assert_eq!(sequential.converged(), sixteen.converged());

    // Thread count changes nothing at all.
    assert_eq!(two.values(), sixteen.values());
    assert_eq!(two.iterations(), sixteen.iterations());
    assert_eq!(two.residual(), sixteen.residual());
}

#[test]
fn pagerank_keeps_the_sequential_path_for_weighted_projections() {
    let options = PageRankOptions::default();
    let sequential = pagerank(&graph(1, true), options).expect("sequential pagerank");
    let parallel = pagerank(&graph(16, true), options).expect("pagerank at sixteen threads");
    // Weighted projections take the push kernel on both paths, so the numbers
    // are identical rather than merely close.
    assert_eq!(parallel.values(), sequential.values());
    assert_eq!(parallel.iterations(), sequential.iterations());
}

#[test]
fn breadth_first_distances_are_identical_at_every_thread_count() {
    let sequential = bfs(&graph(1, false), "0").expect("sequential bfs");
    let sources: Vec<String> = ["0", "7", "4242"].iter().map(|id| id.to_string()).collect();
    let sequential_multi = multi_source_bfs(&graph(1, false), &sources).expect("sequential");
    for workers in [2, 16] {
        let parallel = bfs(&graph(workers, false), "0").expect("parallel bfs");
        assert_eq!(parallel.values(), sequential.values(), "{workers} threads");
        let parallel_multi =
            multi_source_bfs(&graph(workers, false), &sources).expect("parallel multi-source");
        assert_eq!(
            parallel_multi.values(),
            sequential_multi.values(),
            "{workers} threads"
        );
    }
}

#[test]
fn components_are_identical_at_every_thread_count() {
    let sequential = weakly_connected_components(&graph(1, false)).expect("sequential wcc");
    for workers in [2, 16] {
        let parallel = weakly_connected_components(&graph(workers, false)).expect("parallel wcc");
        assert_eq!(parallel.values(), sequential.values(), "{workers} threads");
    }
}

// --- Review reproduction (catalog agent, 2026-09-20). Fails at 8d7fb95. ---

/// Half the nodes have no out-arcs, so the dangling mass is a long float sum.
/// Folding per-chunk sums in order fixes their order, not their grouping: if the
/// chunk length depends on the worker count, so do the low bits of every score.
#[test]
fn pagerank_is_bit_identical_at_every_worker_count_with_dangling_nodes() {
    const N: usize = 200_000;
    let run = |workers: usize| {
        let context = context(workers);
        let mut state = 0x9E37_79B9_7F4A_7C15u64;
        let mut next = move || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            state
        };
        let edges = (0..3 * N)
            .map(|ordinal| {
                let source = (next() % (N as u64 / 2)) as usize;
                let target = next() % N as u64;
                ProjectionEdge {
                    source,
                    target: (target * target / N as u64) as usize,
                    ordinal,
                    id: None,
                }
            })
            .collect();
        let graph = GraphProjection::from_topology(
            SnapshotIdentity::new("g".into(), "r".into(), "reader".into()).unwrap(),
            (0..N).map(|id| id.to_string().into()).collect(),
            edges,
            None,
            Orientation::Outgoing,
            &context,
        )
        .unwrap();
        let result = pagerank(
            &graph,
            PageRankOptions {
                max_iterations: 40,
                tolerance: 1e-12,
                ..Default::default()
            },
        )
        .unwrap();
        let bits: Vec<u64> = result.values().iter().map(|v| v.to_bits()).collect();
        (bits, result.iterations(), result.residual().to_bits())
    };
    let one = run(1);
    for workers in [2, 4, 16] {
        let other = run(workers);
        let differing = one.0.iter().zip(&other.0).filter(|(a, b)| a != b).count();
        assert_eq!(
            differing, 0,
            "{differing} of {N} scores differ between 1 and {workers} workers"
        );
        assert_eq!(
            (one.1, one.2),
            (other.1, other.2),
            "iterations or residual moved at {workers} workers"
        );
    }
}
