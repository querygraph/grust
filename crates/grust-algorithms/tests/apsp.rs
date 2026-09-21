//! All-pairs shortest paths against per-source `dijkstra`, and the property
//! that makes the kernel usable at all: it streams, so memory does not grow with
//! the n² pairs it produces.

use grust_algorithms::{
    AlgorithmError, AllPairsOptions, AllPairsShortestPaths, ExecutionContext, ExecutionLimits,
    GraphProjection, Orientation, ProjectionEdge, SnapshotIdentity, all_pairs_shortest_paths,
    dijkstra,
};

const ORIENTATIONS: [Orientation; 3] = [
    Orientation::Outgoing,
    Orientation::Incoming,
    Orientation::Undirected,
];

fn context_with(memory_bytes: usize, work_units: usize, batch_rows: usize) -> ExecutionContext {
    ExecutionContext::new(ExecutionLimits {
        memory_bytes,
        work_units,
        batch_rows,
        deadline: None,
    })
    .unwrap()
}

fn context() -> ExecutionContext {
    context_with(256 * 1024 * 1024, 2_000_000_000, 1024)
}

fn topology(
    n: usize,
    edges: &[(usize, usize)],
    weights: Option<&[f64]>,
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
        weights.map(<[f64]>::to_vec),
        orientation,
        context,
    )
    .unwrap()
}

fn drain(mut pairs: AllPairsShortestPaths) -> Vec<(usize, usize, f64)> {
    let mut out = Vec::new();
    while let Some(pair) = pairs.next_pair().unwrap() {
        out.push((pair.source, pair.target, pair.distance));
    }
    out
}

fn all(graph: &GraphProjection) -> Vec<(usize, usize, f64)> {
    drain(all_pairs_shortest_paths(graph, AllPairsOptions::default()).unwrap())
}

/// The oracle: `dijkstra` called once per source, independently, keeping the
/// finite distances. It shares nothing with the kernel but `dijkstra` itself.
fn oracle(graph: &GraphProjection, sources: &[usize]) -> Vec<(usize, usize, f64)> {
    let mut expected = Vec::new();
    for &source in sources {
        let distances = dijkstra(graph, &format!("n{source}")).unwrap();
        for (target, &distance) in distances.values().iter().enumerate() {
            if distance.is_finite() {
                expected.push((source, target, distance));
            }
        }
    }
    expected
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
fn all_pairs_shortest_paths_matches_an_independent_oracle() {
    let mut random = Xorshift(0x9E37_79B9_7F4A_7C15);
    let (mut pairs, mut subsets) = (0usize, 0usize);
    for _ in 0..400 {
        let n = 1 + random.below(12);
        let count = random.below(3 * n + 1);
        let edges: Vec<_> = (0..count)
            .map(|_| (random.below(n), random.below(n)))
            .collect();
        // Halves are exact in binary, and zero weights make ties, so equality
        // is the right comparison and the tie order is exercised.
        let weights: Vec<f64> = (0..count).map(|_| random.below(9) as f64 / 2.0).collect();
        for orientation in ORIENTATIONS {
            let what = format!("{orientation:?} n={n} {edges:?} {weights:?}");
            let context = context();
            let graph = topology(n, &edges, Some(&weights), orientation, &context);
            let every: Vec<usize> = (0..n).collect();
            let found = all(&graph);
            assert_eq!(found, oracle(&graph, &every), "{what}");
            pairs += found.len();

            // A random subset, named out of order, selects exactly those sources.
            let mut chosen: Vec<usize> = (0..n).filter(|_| random.below(2) == 0).collect();
            let names: Vec<String> = chosen.iter().rev().map(|row| format!("n{row}")).collect();
            let found = drain(
                all_pairs_shortest_paths(
                    &graph,
                    AllPairsOptions {
                        source_nodes: Some(&names),
                    },
                )
                .unwrap(),
            );
            chosen.sort_unstable();
            assert_eq!(found, oracle(&graph, &chosen), "{what} sources {names:?}");
            subsets += usize::from(!chosen.is_empty() && chosen.len() < n);
        }
    }
    // The fixtures reach the cases they claim to: many pairs, proper subsets.
    assert!(pairs > 20_000, "{pairs}");
    assert!(subsets > 500, "{subsets}");
}

#[test]
fn all_pairs_shortest_paths_hand_computed_cases() {
    let context = context();
    let out = |edges: &[(usize, usize)], n| {
        all(&topology(n, edges, None, Orientation::Outgoing, &context))
    };
    // A directed path 0 -> 1 -> 2: each node reaches itself and what follows.
    assert_eq!(
        out(&[(0, 1), (1, 2)], 3),
        vec![
            (0, 0, 0.0),
            (0, 1, 1.0),
            (0, 2, 2.0),
            (1, 1, 0.0),
            (1, 2, 1.0),
            (2, 2, 0.0),
        ]
    );
    // An undirected star on 0: leaves are two apart.
    let star = all(&topology(
        4,
        &[(0, 1), (0, 2), (0, 3)],
        None,
        Orientation::Undirected,
        &context,
    ));
    assert_eq!(star.len(), 16);
    for &(source, target, distance) in &star {
        let expected = match (source, target) {
            _ if source == target => 0.0,
            (0, _) | (_, 0) => 1.0,
            _ => 2.0,
        };
        assert_eq!(distance, expected, "{source}->{target}");
    }
    // Two components {0, 1} and {2, 3}, undirected: the 8 cross-component
    // pairs are omitted, not reported as null or infinite.
    let split = all(&topology(
        4,
        &[(0, 1), (2, 3)],
        None,
        Orientation::Undirected,
        &context,
    ));
    assert_eq!(split.len(), 8);
    assert!(
        split
            .iter()
            .all(|&(s, t, d)| (s < 2) == (t < 2) && d.is_finite())
    );
    // A single node reaches itself; an empty graph has no pairs.
    assert_eq!(out(&[], 1), vec![(0, 0, 0.0)]);
    assert_eq!(out(&[], 0), vec![]);
}

#[test]
fn all_pairs_shortest_paths_states_multigraph_and_self_loop_semantics() {
    let context = context();
    // Parallel edges 0 -> 1 at 5 and 2: the cheaper one counts. A self-loop of
    // weight 0 on 1 changes nothing and adds no pair.
    let graph = topology(
        2,
        &[(0, 1), (0, 1), (1, 1)],
        Some(&[5.0, 2.0, 0.0]),
        Orientation::Outgoing,
        &context,
    );
    assert_eq!(all(&graph), vec![(0, 0, 0.0), (0, 1, 2.0), (1, 1, 0.0)]);

    // Fewest hops is not shortest: 0 -> 3 directly costs 10, while
    // 0 -> 1 -> 2 -> 3 costs 1 + 1 + 1.
    let graph = topology(
        4,
        &[(0, 3), (0, 1), (1, 2), (2, 3)],
        Some(&[10.0, 1.0, 1.0, 1.0]),
        Orientation::Outgoing,
        &context,
    );
    let found = all(&graph);
    assert!(found.contains(&(0, 3, 3.0)), "{found:?}");
    assert!(found.contains(&(1, 3, 2.0)), "{found:?}");
}

#[test]
fn all_pairs_shortest_paths_rejects_invalid_options_without_leaking_admission() {
    let context = context();
    let graph = topology(3, &[(0, 1)], None, Orientation::Outgoing, &context);
    let held = context.usage().unwrap().live_bytes;
    let unknown = ["n0".to_string(), "nobody".to_string()];
    let twice = ["n2".to_string(), "n0".to_string(), "n2".to_string()];
    for (ids, says) in [(&unknown[..], "nobody"), (&twice[..], "n2 more than once")] {
        let error = all_pairs_shortest_paths(
            &graph,
            AllPairsOptions {
                source_nodes: Some(ids),
            },
        )
        .err()
        .expect("invalid sourceNodes accepted");
        match error {
            AlgorithmError::InvalidArguments(message) => {
                assert!(message.contains(says), "{message}")
            }
            other => panic!("{other}"),
        }
        assert_eq!(context.usage().unwrap().live_bytes, held);
    }
    // An empty selection is valid and selects nothing.
    let none: [String; 0] = [];
    let pairs = all_pairs_shortest_paths(
        &graph,
        AllPairsOptions {
            source_nodes: Some(&none),
        },
    )
    .unwrap();
    assert_eq!(drain(pairs), vec![]);
    assert_eq!(context.usage().unwrap().live_bytes, held);

    // A projection that admits negative weights is refused, as by `dijkstra`.
    let signed = GraphProjection::from_signed_topology(
        SnapshotIdentity::new("g".into(), "r".into(), "reader".into()).unwrap(),
        vec!["a".into(), "b".into()],
        vec![ProjectionEdge {
            source: 0,
            target: 1,
            ordinal: 0,
            id: None,
        }],
        vec![-1.0],
        Orientation::Outgoing,
        &context,
    )
    .unwrap();
    let held = context.usage().unwrap().live_bytes;
    match all_pairs_shortest_paths(&signed, AllPairsOptions::default()) {
        Err(AlgorithmError::InvalidArguments(message)) => {
            assert!(message.contains("signed projection"), "{message}")
        }
        Err(other) => panic!("{other}"),
        Ok(_) => panic!("ran on a signed projection"),
    }
    assert_eq!(context.usage().unwrap().live_bytes, held);
}

/// A directed ring: every node reaches every other, so n² pairs.
fn ring(n: usize, context: &ExecutionContext) -> GraphProjection {
    let edges: Vec<_> = (0..n).map(|i| (i, (i + 1) % n)).collect();
    topology(n, &edges, None, Orientation::Outgoing, context)
}

#[test]
fn all_pairs_shortest_paths_observes_cancellation_and_budget_and_releases_scratch() {
    // Cancellation mid-stream fails the next pull, releases the workspace, and
    // leaves the cursor terminally failed.
    let cancelled = context();
    let graph = ring(64, &cancelled);
    let held = cancelled.usage().unwrap().live_bytes;
    let mut pairs = all_pairs_shortest_paths(&graph, AllPairsOptions::default()).unwrap();
    assert!(
        cancelled.usage().unwrap().live_bytes > held,
        "workspace admitted"
    );
    for _ in 0..100 {
        pairs.next_pair().unwrap().unwrap();
    }
    cancelled.cancel().unwrap();
    assert!(matches!(pairs.next_pair(), Err(AlgorithmError::Cancelled)));
    assert_eq!(
        cancelled.usage().unwrap().live_bytes,
        held,
        "scratch released"
    );
    assert!(matches!(
        pairs.next_pair(),
        Err(AlgorithmError::CursorFailed)
    ));

    // A work budget stops a run partway, after pairs have already streamed out:
    // the first rows do not wait for the last source.
    let (build, full) = {
        let context = context();
        let graph = ring(64, &context);
        let build = context.usage().unwrap().work_units;
        assert_eq!(all(&graph).len(), 64 * 64);
        (build, context.usage().unwrap().work_units - build)
    };
    let context = context_with(256 * 1024 * 1024, build + full / 2, 1024);
    let graph = ring(64, &context);
    let held = context.usage().unwrap().live_bytes;
    let mut pairs = all_pairs_shortest_paths(&graph, AllPairsOptions::default()).unwrap();
    let mut produced = 0usize;
    let error = loop {
        match pairs.next_pair() {
            Ok(Some(_)) => produced += 1,
            Ok(None) => panic!("finished within half its work"),
            Err(error) => break error,
        }
    };
    assert!(
        matches!(error, AlgorithmError::BudgetExceeded { .. }),
        "{error}"
    );
    assert!(produced > 64 && produced < 64 * 64, "{produced}");
    assert_eq!(
        context.usage().unwrap().live_bytes,
        held,
        "scratch released"
    );
}

#[test]
fn all_pairs_shortest_paths_charges_work_per_pair_produced() {
    // One source on a ring of n reaches n nodes. Pulling the other n - 1 pairs
    // and finishing costs exactly one unit per pair plus one per reached node
    // reset: 2n - 1. Measured after the cursor is dropped, when its work meter
    // has handed back what it held in advance.
    let n = 300;
    let work = |pull_all: bool| {
        let context = context();
        let graph = ring(n, &context);
        let before = context.usage().unwrap().work_units;
        let only = ["n7".to_string()];
        let mut pairs = all_pairs_shortest_paths(
            &graph,
            AllPairsOptions {
                source_nodes: Some(&only),
            },
        )
        .unwrap();
        let first = pairs.next_pair().unwrap().unwrap();
        assert_eq!((first.source, first.target), (7, 0));
        if pull_all {
            let mut count = 1;
            while pairs.next_pair().unwrap().is_some() {
                count += 1;
            }
            assert_eq!(count, n);
        }
        drop(pairs);
        context.usage().unwrap().work_units - before
    };
    assert_eq!(work(true) - work(false), 2 * n - 1);
}

#[test]
fn all_pairs_shortest_paths_peak_is_reached_before_the_first_pair_leaves() {
    // Stronger than a ratio: pulling pair by pair, the admitted peak after
    // the millionth pair is the peak after the first. Everything the kernel
    // will ever hold is admitted up front, and nothing grows.
    let context = context_with(1 << 30, usize::MAX, 1024);
    let graph = ring(1024, &context);
    let mut pairs = all_pairs_shortest_paths(&graph, AllPairsOptions::default()).unwrap();
    pairs.next_pair().unwrap().unwrap();
    let after_first = context.usage().unwrap().peak_bytes;
    let mut count = 1usize;
    while pairs.next_pair().unwrap().is_some() {
        count += 1;
    }
    assert_eq!(count, 1024 * 1024);
    assert_eq!(context.usage().unwrap().peak_bytes, after_first);
}

#[cfg(feature = "arrow")]
mod arrow {
    use super::*;
    use arrow_array::{Array, Float64Array, StringArray};

    /// Pull every batch, keeping them or dropping each as it arrives, and
    /// report the rows seen and the peak admitted bytes of the whole run,
    /// projection included.
    fn stream(n: usize, keep: bool, batch_rows: usize) -> (usize, usize) {
        let context = context_with(1 << 30, usize::MAX, batch_rows);
        let graph = ring(n, &context);
        let mut cursor = all_pairs_shortest_paths(&graph, AllPairsOptions::default())
            .unwrap()
            .into_arrow_results()
            .unwrap();
        let (mut rows, mut kept) = (0usize, Vec::new());
        while let Some(batch) = cursor.next_batch().unwrap() {
            rows += batch.record_batch().num_rows();
            if keep {
                kept.push(batch);
            }
        }
        (rows, context.usage().unwrap().peak_bytes)
    }

    #[test]
    fn all_pairs_shortest_paths_streams_in_memory_that_does_not_grow_with_the_output() {
        // Four times the nodes is sixteen times the pairs. A kernel that held
        // its output, or anything shaped like it, would need about sixteen
        // times the memory; a streaming one needs about four (its O(n)
        // workspace and projection), plus one fixed-size batch.
        let (small_rows, small_peak) = stream(256, false, 1024);
        let (large_rows, large_peak) = stream(1024, false, 1024);
        assert_eq!(small_rows, 256 * 256);
        assert_eq!(large_rows, 1024 * 1024);
        let ratio = large_peak as f64 / small_peak as f64;
        assert!(
            ratio < 5.0,
            "peak grew {ratio:.2}x: {small_peak} -> {large_peak}"
        );
        // And absolutely: the whole run's peak is below what the pairs alone
        // would occupy, at even eight bytes each.
        assert!(large_peak < large_rows * 8, "{large_peak}");

        // The control: a consumer that keeps every batch does see memory grow
        // like the output. This is what makes the assertion above able to fail
        // — the accounting observes output, so output held anywhere would show.
        let (_, small_kept) = stream(256, true, 1024);
        let (_, large_kept) = stream(1024, true, 1024);
        let kept_ratio = large_kept as f64 / small_kept as f64;
        assert!(
            kept_ratio > 12.0,
            "retained output grew only {kept_ratio:.2}x: {small_kept} -> {large_kept}"
        );
    }

    #[test]
    fn all_pairs_shortest_paths_arrow_batches_keep_bounds_and_admission() {
        let context = context_with(4 * 1024 * 1024, usize::MAX, 3);
        let graph = topology(
            3,
            &[(0, 1), (1, 2)],
            Some(&[2.5, 0.5]),
            Orientation::Outgoing,
            &context,
        );
        let mut cursor = all_pairs_shortest_paths(&graph, AllPairsOptions::default())
            .unwrap()
            .into_arrow_results()
            .unwrap();
        drop(graph);
        let mut batches = Vec::new();
        while let Some(batch) = cursor.next_batch().unwrap() {
            assert!(batch.record_batch().num_rows() <= 3);
            batches.push(batch);
        }
        // Six pairs in batches of three; the second spans two sources.
        assert_eq!(batches.len(), 2);
        let column = |index: usize, name: &str| {
            batches[index]
                .record_batch()
                .column_by_name(name)
                .unwrap()
                .clone()
        };
        let sources = column(1, "sourceNodeId");
        let names = sources.as_any().downcast_ref::<StringArray>().unwrap();
        assert_eq!(
            names.iter().flatten().collect::<Vec<_>>(),
            ["n1", "n1", "n2"]
        );
        let distances = column(0, "distance");
        let values = distances.as_any().downcast_ref::<Float64Array>().unwrap();
        assert_eq!(values.null_count(), 0);
        assert_eq!(values.values().as_ref(), &[0.0, 2.5, 3.0]);
        // Arrays share their batch's admission; these two clones hold it too.
        drop((sources, distances));
        // The cursor is done: only the retained batches stay admitted.
        drop(cursor);
        let retained: usize = batches.iter().map(|batch| batch.reserved_bytes()).sum();
        assert_eq!(context.usage().unwrap().live_bytes, retained);
        drop(batches);
        assert_eq!(context.usage().unwrap().live_bytes, 0);

        // No pairs at all still says what the columns are.
        let context = context_with(4 * 1024 * 1024, usize::MAX, 3);
        let graph = topology(2, &[], None, Orientation::Outgoing, &context);
        let none: [String; 0] = [];
        let mut cursor = all_pairs_shortest_paths(
            &graph,
            AllPairsOptions {
                source_nodes: Some(&none),
            },
        )
        .unwrap()
        .into_arrow_results()
        .unwrap();
        let empty = cursor.next_batch().unwrap().unwrap();
        assert_eq!(empty.record_batch().num_rows(), 0);
        let schema = empty.record_batch().schema();
        let names: Vec<_> = schema.fields().iter().map(|f| f.name().as_str()).collect();
        assert_eq!(names, ["sourceNodeId", "targetNodeId", "distance"]);
        assert!(cursor.next_batch().unwrap().is_none());
    }
}
