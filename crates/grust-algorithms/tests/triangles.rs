//! Triangles and clustering coefficients against an O(n^3) definition.

use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, Orientation,
    ProjectionEdge, SnapshotIdentity, TriangleOptions, triangles,
};

fn context() -> ExecutionContext {
    ExecutionContext::new(ExecutionLimits {
        memory_bytes: 64 * 1024 * 1024,
        work_units: 200_000_000,
        batch_rows: 1024,
        deadline: None,
    })
    .unwrap()
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

/// The definition: a triangle is three distinct, pairwise adjacent nodes.
/// Adjacency is a yes-or-no matrix, so multiplicity and loops cannot matter.
fn by_definition(n: usize, edges: &[(usize, usize)]) -> (Vec<i64>, Vec<Option<f64>>, i64) {
    let mut adjacent = vec![vec![false; n]; n];
    for &(a, b) in edges {
        if a != b {
            adjacent[a][b] = true;
            adjacent[b][a] = true;
        }
    }
    let mut counts = vec![0i64; n];
    let mut total = 0;
    for a in 0..n {
        for b in a + 1..n {
            for c in b + 1..n {
                if adjacent[a][b] && adjacent[b][c] && adjacent[a][c] {
                    total += 1;
                    for corner in [a, b, c] {
                        counts[corner] += 1;
                    }
                }
            }
        }
    }
    let coefficients = (0..n)
        .map(|v| {
            let d = adjacent[v].iter().filter(|&&x| x).count() as f64;
            (d >= 2.0).then(|| 2.0 * counts[v] as f64 / (d * (d - 1.0)))
        })
        .collect();
    (counts, coefficients, total)
}

fn assert_matches(n: usize, edges: &[(usize, usize)]) {
    let context = context();
    let result = triangles(
        &graph(n, edges, Orientation::Undirected, &context),
        TriangleOptions::default(),
    )
    .unwrap();
    let (counts, coefficients, total) = by_definition(n, edges);
    assert_eq!(result.triangles(), counts, "{edges:?}");
    assert_eq!(result.triangle_count(), total, "{edges:?}");
    for (v, expected) in coefficients.iter().enumerate() {
        match expected {
            Some(value) => assert!(
                (result.coefficients()[v] - value).abs() < 1e-12,
                "{edges:?}"
            ),
            None => assert!(result.coefficients()[v].is_nan(), "{edges:?}"),
        }
    }
}

#[test]
fn triangles_match_an_independent_oracle() {
    // Every simple graph on six nodes: 2^15 = 32,768.
    let pairs: Vec<(usize, usize)> = (0..6)
        .flat_map(|a| (a + 1..6).map(move |b| (a, b)))
        .collect();
    for code in 0..1usize << pairs.len() {
        let edges: Vec<_> = pairs
            .iter()
            .enumerate()
            .filter(|(bit, _)| code >> bit & 1 == 1)
            .map(|(_, &pair)| pair)
            .collect();
        assert_matches(6, &edges);
    }
}

#[test]
fn triangles_state_multigraph_and_self_loop_semantics() {
    // Every four-node multigraph with multiplicity 0..=2, in both edge
    // directions, with loops: the simple graph underneath decides.
    let pairs = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)];
    for code in 0..3usize.pow(6) {
        let mut edges = vec![(0, 0), (3, 3)];
        let mut rest = code;
        for &(a, b) in &pairs {
            for copy in 0..rest % 3 {
                edges.push(if copy == 0 { (a, b) } else { (b, a) });
            }
            rest /= 3;
        }
        assert_matches(4, &edges);
    }
    // One triangle drawn with doubled edges and loops is still one triangle.
    let context = context();
    let doubled = [(0, 1), (1, 0), (1, 2), (1, 2), (2, 0), (0, 0), (2, 2)];
    let result = triangles(
        &graph(3, &doubled, Orientation::Undirected, &context),
        TriangleOptions::default(),
    )
    .unwrap();
    assert_eq!(result.triangles(), [1, 1, 1]);
    assert_eq!(result.triangle_count(), 1);
    assert_eq!(result.coefficients(), [1.0, 1.0, 1.0]);
}

#[test]
fn triangles_handle_empty_single_node_and_isolates() {
    let context = context();
    let empty = triangles(
        &graph(0, &[], Orientation::Undirected, &context),
        TriangleOptions::default(),
    )
    .unwrap();
    assert!(empty.triangles().is_empty());
    assert_eq!(empty.triangle_count(), 0);
    assert_eq!(empty.average_coefficient(), 0.0);

    // A triangle with a pendant, plus an isolate.
    let result = triangles(
        &graph(
            5,
            &[(0, 1), (1, 2), (2, 0), (2, 3)],
            Orientation::Undirected,
            &context,
        ),
        TriangleOptions::default(),
    )
    .unwrap();
    assert_eq!(result.triangles(), [1, 1, 1, 0, 0]);
    assert_eq!(result.coefficients()[0], 1.0);
    assert!((result.coefficients()[2] - 1.0 / 3.0).abs() < 1e-12);
    assert!(result.coefficients()[3].is_nan() && result.coefficients()[4].is_nan());
    assert!((result.average_coefficient() - (1.0 + 1.0 + 1.0 / 3.0) / 3.0).abs() < 1e-12);
}

#[test]
fn max_degree_leaves_hubs_and_their_triangles_out() {
    let context = context();
    // Node 0 is a hub closing triangles 0-1-2 and 0-3-4; 5-6-7 stands alone.
    let edges = [
        (0, 1),
        (0, 2),
        (1, 2),
        (0, 3),
        (0, 4),
        (3, 4),
        (5, 6),
        (6, 7),
        (7, 5),
    ];
    let result = triangles(
        &graph(8, &edges, Orientation::Undirected, &context),
        TriangleOptions {
            max_degree: Some(2),
        },
    )
    .unwrap();
    assert_eq!(result.triangles(), [-1, 0, 0, 0, 0, 1, 1, 1]);
    assert!(result.coefficients()[0].is_nan());
    assert_eq!(result.triangle_count(), 1);
}

#[test]
fn triangles_reject_directed_projections_without_leaking_admission() {
    for orientation in [Orientation::Outgoing, Orientation::Incoming] {
        let context = context();
        let projection = graph(3, &[(0, 1), (1, 2), (2, 0)], orientation, &context);
        let held = context.usage().unwrap().live_bytes;
        assert!(matches!(
            triangles(&projection, TriangleOptions::default()),
            Err(AlgorithmError::InvalidArguments(message)) if message.contains("undirected")
        ));
        assert_eq!(context.usage().unwrap().live_bytes, held);
    }
}

/// A deterministic pseudo-random graph with hubs, so blocks are uneven.
fn scrambled(n: usize, edges: usize) -> Vec<(usize, usize)> {
    let mut state = 0x9E37_79B9_7F4A_7C15u64;
    let mut next = move || {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        state
    };
    (0..edges)
        .map(|_| {
            let a = (next() % n as u64) as usize;
            // Squaring skews endpoints toward low rows: a few heavy nodes.
            let b = ((next() % n as u64).pow(2) / n as u64) as usize;
            (a, b)
        })
        .collect()
}

#[test]
fn triangles_are_identical_at_any_pool_width_and_charge_the_same_work() {
    let edges = scrambled(400, 6000);
    let run = |threads: usize| {
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .build()
            .unwrap();
        pool.install(|| {
            let context = context();
            let projection = graph(400, &edges, Orientation::Undirected, &context);
            let before = context.usage().unwrap().work_units;
            let result = triangles(&projection, TriangleOptions::default()).unwrap();
            let work = context.usage().unwrap().work_units - before;
            (result.triangles().to_vec(), result.triangle_count(), work)
        })
    };
    let (counts, total, work) = run(1);
    assert!(total > 0, "the fixture should contain triangles");
    let (expected, _, expected_total) = by_definition(400, &edges);
    assert_eq!(counts, expected);
    assert_eq!(total, expected_total);
    for threads in [2, 3, 8] {
        let (other, other_total, other_work) = run(threads);
        assert_eq!(other, counts, "{threads} threads");
        assert_eq!(other_total, total);
        // Block buffers aside, the counted work is the graph's, not the pool's.
        assert_eq!(other_work, work, "{threads} threads charged differently");
    }
}

#[test]
fn triangles_observe_cancellation_and_budget_and_release_scratch() {
    let edges = scrambled(300, 5000);
    let context = context();
    let projection = graph(300, &edges, Orientation::Undirected, &context);
    let projection_work = context.usage().unwrap().work_units;
    let held = context.usage().unwrap().live_bytes;
    context.cancel().unwrap();
    assert!(matches!(
        triangles(&projection, TriangleOptions::default()),
        Err(AlgorithmError::Cancelled)
    ));
    assert_eq!(context.usage().unwrap().live_bytes, held);

    let tight = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 64 * 1024 * 1024,
        work_units: projection_work + 20_000,
        batch_rows: 1024,
        deadline: None,
    })
    .unwrap();
    let projection = graph(300, &edges, Orientation::Undirected, &tight);
    let held = tight.usage().unwrap().live_bytes;
    assert!(matches!(
        triangles(&projection, TriangleOptions::default()),
        Err(AlgorithmError::BudgetExceeded {
            resource: "work",
            ..
        })
    ));
    assert_eq!(tight.usage().unwrap().live_bytes, held);
}
