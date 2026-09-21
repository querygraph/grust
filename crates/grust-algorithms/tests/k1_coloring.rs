//! k1-colouring: the colouring property, hand-checkable graphs, and limits.
//!
//! The oracle here is a property, not a second implementation: a colouring is
//! right when no edge joins equal colours and no more than `Δ + 1` colours are
//! used. Both are read off the edge list the fixture was built from, never off
//! anything the kernel computed.

use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, K1ColoringOptions,
    Orientation, ProjectionEdge, SnapshotIdentity, k1_coloring,
};
use std::collections::BTreeSet;

fn limits(work_units: usize) -> ExecutionLimits {
    ExecutionLimits {
        memory_bytes: 64 * 1024 * 1024,
        work_units,
        batch_rows: 1024,
        deadline: None,
    }
}

fn context() -> ExecutionContext {
    ExecutionContext::new(limits(500_000_000)).unwrap()
}

fn graph(
    n: usize,
    edges: &[(usize, usize)],
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
        None,
        orientation,
        context,
    )
    .unwrap()
}

fn coloring(
    n: usize,
    edges: &[(usize, usize)],
    options: K1ColoringOptions,
) -> (Vec<i64>, bool, i64) {
    let context = context();
    let result = k1_coloring(&graph(n, edges, Orientation::Undirected, &context), options).unwrap();
    (
        result.colors().to_vec(),
        result.converged(),
        result.color_count(),
    )
}

/// The maximum number of *distinct* neighbours of any node, self-loops
/// excluded, straight from the edge list. Parallel edges are one neighbour, so
/// this is the Δ the `Δ + 1` bound is stated over — a stricter bound than
/// counting incident arcs would give.
fn max_degree(n: usize, edges: &[(usize, usize)]) -> usize {
    let mut neighbours = vec![BTreeSet::new(); n];
    for &(a, b) in edges {
        if a != b {
            neighbours[a].insert(b);
            neighbours[b].insert(a);
        }
    }
    neighbours.iter().map(BTreeSet::len).max().unwrap_or(0)
}

/// The oracle: a proper colouring within the greedy bound.
fn assert_proper(n: usize, edges: &[(usize, usize)], colors: &[i64], note: &str) {
    assert_eq!(colors.len(), n, "{note}: one colour per node");
    for &(a, b) in edges {
        assert!(
            a == b || colors[a] != colors[b],
            "{note}: edge {a}-{b} joins colour {}",
            colors[a]
        );
    }
    let distinct: BTreeSet<i64> = colors.iter().copied().collect();
    assert!(
        distinct.len() <= max_degree(n, edges) + 1,
        "{note}: {} colours for max degree {}",
        distinct.len(),
        max_degree(n, edges)
    );
    assert!(colors.iter().all(|&color| color >= 0), "{note}: negative");
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
fn k1_coloring_matches_an_independent_oracle() {
    let mut random = Xorshift(0x2545_F491_4F6C_DD1D);
    let mut converged_runs = 0;
    for round in 0..3000 {
        let n = 1 + random.below(12);
        let count = random.below(3 * n);
        let edges: Vec<_> = (0..count)
            .map(|_| (random.below(n), random.below(n)))
            .collect();
        let seed = (round % 3 == 0).then_some(round as u64);
        // Enough passes that a small graph always finishes; n bounds them.
        let (colors, converged, color_count) = coloring(
            n,
            &edges,
            K1ColoringOptions {
                max_iterations: n,
                seed,
            },
        );
        assert_proper(n, &edges, &colors, &format!("{n} {edges:?} {seed:?}"));
        assert!(converged, "n passes suffice: {edges:?}");
        converged_runs += 1;
        let distinct: BTreeSet<i64> = colors.iter().copied().collect();
        assert_eq!(color_count, distinct.len() as i64);
    }
    assert_eq!(converged_runs, 3000);
}

#[test]
fn hand_computed_graphs_take_the_colours_inspection_gives() {
    // A triangle needs three colours, a path two, a star two, K4 four.
    let triangle = [(0, 1), (1, 2), (2, 0)];
    let (colors, _, count) = coloring(3, &triangle, K1ColoringOptions::default());
    assert_eq!(colors, [0, 1, 2]);
    assert_eq!(count, 3);

    let path = [(0, 1), (1, 2), (2, 3), (3, 4)];
    let (colors, _, count) = coloring(5, &path, K1ColoringOptions::default());
    assert_eq!(colors, [0, 1, 0, 1, 0]);
    assert_eq!(count, 2);

    let star = [(0, 1), (0, 2), (0, 3), (0, 4)];
    let (colors, _, count) = coloring(5, &star, K1ColoringOptions::default());
    assert_eq!(colors, [0, 1, 1, 1, 1]);
    assert_eq!(count, 2);

    let k4: Vec<_> = (0..4)
        .flat_map(|a| (a + 1..4).map(move |b| (a, b)))
        .collect();
    let (colors, _, count) = coloring(4, &k4, K1ColoringOptions::default());
    assert_eq!(colors, [0, 1, 2, 3]);
    assert_eq!(count, 4);
    assert_proper(4, &k4, &colors, "K4");

    // Two components are coloured independently, each from zero.
    let disconnected = [(0, 1), (1, 2), (2, 0), (3, 4)];
    let (colors, converged, count) = coloring(6, &disconnected, K1ColoringOptions::default());
    assert_eq!(colors, [0, 1, 2, 0, 1, 0]);
    assert!(converged);
    assert_eq!(count, 3);
    assert_proper(6, &disconnected, &colors, "two components");
}

#[test]
fn k1_coloring_states_multigraph_and_self_loop_semantics() {
    // Three parallel edges are the one constraint their endpoints already
    // impose; a self-loop is not a constraint at all, and does not stop the
    // run converging.
    let edges = [(0, 1), (0, 1), (0, 1), (2, 2), (1, 2)];
    let (colors, converged, count) = coloring(3, &edges, K1ColoringOptions::default());
    assert_eq!(colors, [0, 1, 0]);
    assert!(converged);
    assert_eq!(count, 2);
    assert_proper(3, &edges, &colors, "multigraph");

    // A loop on every node of a triangle changes nothing.
    let looped = [(0, 1), (1, 2), (2, 0), (0, 0), (1, 1), (2, 2)];
    let (looped_colors, converged, _) = coloring(3, &looped, K1ColoringOptions::default());
    assert_eq!(looped_colors, [0, 1, 2]);
    assert!(converged);

    // Direction is rejected, not symmetrized.
    for orientation in [Orientation::Outgoing, Orientation::Incoming] {
        let context = context();
        assert!(matches!(
            k1_coloring(
                &graph(3, &[(0, 1), (1, 2)], orientation, &context),
                K1ColoringOptions::default()
            ),
            Err(AlgorithmError::InvalidArguments(_))
        ));
    }
}

#[test]
fn k1_coloring_handles_empty_single_node_and_isolates() {
    let (colors, converged, count) = coloring(0, &[], K1ColoringOptions::default());
    assert!(colors.is_empty() && converged);
    assert_eq!(count, 0);

    let (colors, converged, count) = coloring(1, &[], K1ColoringOptions::default());
    assert_eq!(colors, [0]);
    assert!(converged);
    assert_eq!(count, 1);

    // A single node carrying a loop is still colour zero.
    let (colors, converged, _) = coloring(1, &[(0, 0)], K1ColoringOptions::default());
    assert_eq!(colors, [0]);
    assert!(converged);

    // Isolates all take colour zero alongside a coloured component.
    let edges = [(0, 1)];
    let (colors, converged, count) = coloring(4, &edges, K1ColoringOptions::default());
    assert_eq!(colors, [0, 1, 0, 0]);
    assert!(converged);
    assert_eq!(count, 2);
}

/// A wheel-like graph whose row order needs several passes to settle: every
/// node starts at colour zero, so the first pass conflicts widely.
fn dense_ring(n: usize) -> Vec<(usize, usize)> {
    let mut edges = Vec::new();
    for node in 0..n {
        edges.push((node, (node + 1) % n));
        edges.push((node, (node + 2) % n));
        edges.push((node, (node + 3) % n));
    }
    edges
}

#[test]
fn k1_coloring_is_deterministic_under_a_fixed_seed() {
    let edges = dense_ring(500);
    let run = |seed| {
        coloring(
            500,
            &edges,
            K1ColoringOptions {
                max_iterations: 500,
                seed,
            },
        )
    };
    let first = run(Some(7));
    assert_eq!(run(Some(7)), first, "same seed, same colouring");
    assert_eq!(run(None), run(None), "row order is reproducible too");
    let other = run(Some(8));
    assert_ne!(other.0, first.0, "another seed, another priority order");
    for (colors, note) in [
        (&first.0, "seed 7"),
        (&other.0, "seed 8"),
        (&run(None).0, "row"),
    ] {
        assert_proper(500, &edges, colors, note);
    }

    // The pool width is not an input: the kernel is sequential, so this only
    // pins that no future change smuggles thread order into the result.
    let wide = ExecutionContext::new(limits(500_000_000))
        .unwrap()
        .with_concurrency(8)
        .unwrap();
    let result = k1_coloring(
        &graph(500, &edges, Orientation::Undirected, &wide),
        K1ColoringOptions {
            max_iterations: 500,
            seed: Some(7),
        },
    )
    .unwrap();
    assert_eq!(result.colors(), first.0);
}

#[test]
fn an_iteration_cap_stops_the_run_and_reports_it() {
    // One pass over a triangle: every node reads its neighbours at colour zero
    // and stays at colour zero, so the pass ends conflicted.
    let triangle = [(0, 1), (1, 2), (2, 0)];
    let context = context();
    let capped = k1_coloring(
        &graph(3, &triangle, Orientation::Undirected, &context),
        K1ColoringOptions {
            max_iterations: 1,
            seed: None,
        },
    )
    .unwrap();
    assert_eq!(capped.colors(), [0, 0, 0]);
    assert_eq!((capped.iterations(), capped.converged()), (1, false));

    let settled = k1_coloring(
        &graph(3, &triangle, Orientation::Undirected, &context),
        K1ColoringOptions {
            max_iterations: 10,
            seed: None,
        },
    )
    .unwrap();
    assert_eq!(settled.colors(), [0, 1, 2]);
    assert_eq!((settled.iterations(), settled.converged()), (3, true));
}

#[test]
fn k1_coloring_rejects_invalid_options_without_leaking_admission() {
    let context = context();
    let projection = graph(3, &[(0, 1)], Orientation::Undirected, &context);
    let after_projection = context.usage().unwrap().live_bytes;
    assert!(matches!(
        k1_coloring(
            &projection,
            K1ColoringOptions {
                max_iterations: 0,
                seed: None
            }
        ),
        Err(AlgorithmError::InvalidArguments(_))
    ));
    assert_eq!(context.usage().unwrap().live_bytes, after_projection);

    // A signed projection is refused: colouring reads no weight, and accepting
    // one would suggest the negative weights had been taken into account.
    let signed = GraphProjection::from_signed_topology(
        SnapshotIdentity::new("g".into(), "r".into(), "reader".into()).unwrap(),
        (0..2).map(|i| format!("n{i}").into()).collect(),
        vec![ProjectionEdge {
            source: 0,
            target: 1,
            ordinal: 0,
            id: None,
        }],
        vec![-1.0],
        Orientation::Undirected,
        &context,
    )
    .unwrap();
    assert!(matches!(
        k1_coloring(&signed, K1ColoringOptions::default()),
        Err(AlgorithmError::InvalidArguments(_))
    ));
}

#[test]
fn k1_coloring_observes_cancellation_and_budget_and_releases_scratch() {
    let edges = dense_ring(2000);
    let context = context();
    let projection = graph(2000, &edges, Orientation::Undirected, &context);
    let projection_work = context.usage().unwrap().counted_work().expect("counted");
    context.cancel().unwrap();
    assert!(matches!(
        k1_coloring(&projection, K1ColoringOptions::default()),
        Err(AlgorithmError::Cancelled)
    ));

    let tight = ExecutionContext::new(limits(projection_work + 2_000)).unwrap();
    let projection = graph(2000, &edges, Orientation::Undirected, &tight);
    assert!(matches!(
        k1_coloring(&projection, K1ColoringOptions::default()),
        Err(AlgorithmError::BudgetExceeded {
            resource: "work",
            ..
        })
    ));
    drop(projection);
    assert_eq!(tight.usage().unwrap().live_bytes, 0);
}
