//! Link prediction against the paper definitions, recomputed pair by pair from
//! the test's own edge list. Nothing here shares code with the kernel.

use grust_algorithms::{
    AlgorithmError, CandidatePairs, ExecutionContext, ExecutionLimits, GraphProjection,
    LinkCandidates, LinkMetric, LinkPredictionOptions, NodeProperties, NodeSimilarityOptions,
    Orientation, ProjectionOptions, PropertyKind, PropertyRequest, SimilarityMetric,
    SnapshotIdentity, link_prediction, node_similarity,
};
use grust_core::{Edge, Graph, Node, Props, Value};
use std::collections::BTreeSet;

const METRICS: [LinkMetric; 6] = [
    LinkMetric::CommonNeighbors,
    LinkMetric::AdamicAdar,
    LinkMetric::ResourceAllocation,
    LinkMetric::PreferentialAttachment,
    LinkMetric::TotalNeighbors,
    LinkMetric::SameCommunity,
];

fn limits(work_units: usize) -> ExecutionLimits {
    ExecutionLimits {
        memory_bytes: 256 * 1024 * 1024,
        work_units,
        batch_rows: 1024,
        deadline: None,
    }
}

fn context() -> ExecutionContext {
    ExecutionContext::new(limits(2_000_000_000)).unwrap()
}

/// Nodes `n0..`, each with community `c`; one `R` edge per pair in `edges`.
fn build(n: usize, edges: &[(usize, usize)], communities: &[i64]) -> Graph {
    Graph::new(
        (0..n)
            .map(|i| {
                Node::new(
                    "N",
                    format!("n{i}"),
                    Props::from([("c".to_string(), Value::Int(communities[i]))]),
                )
            })
            .collect(),
        edges
            .iter()
            .map(|&(a, b)| Edge::new("R", format!("n{a}"), format!("n{b}"), Props::new()))
            .collect(),
    )
}

fn project(graph: &Graph, orientation: Orientation, context: &ExecutionContext) -> GraphProjection {
    GraphProjection::from_graph(
        graph,
        SnapshotIdentity::new("g".into(), "r".into(), "reader".into()).unwrap(),
        ProjectionOptions {
            orientation,
            ..Default::default()
        },
        context,
    )
    .unwrap()
}

fn communities_of(graph: &Graph, projection: &GraphProjection) -> NodeProperties {
    NodeProperties::from_graph(
        graph,
        projection,
        &[PropertyRequest::required("c", PropertyKind::Integer)],
    )
    .unwrap()
}

type Rows = Vec<(usize, usize, f64)>;

/// Run one metric; `communities` is passed for `SameCommunity` only.
fn run(
    projection: &GraphProjection,
    properties: &NodeProperties,
    metric: LinkMetric,
    candidates: LinkCandidates<'_>,
) -> Rows {
    let result = link_prediction(
        projection,
        LinkPredictionOptions {
            metric,
            candidates,
            communities: (metric == LinkMetric::SameCommunity).then_some((properties, "c")),
        },
    )
    .unwrap();
    (0..result.first().len())
        .map(|row| {
            (
                result.first()[row],
                result.second()[row],
                result.scores()[row],
            )
        })
        .collect()
}

/// Neighbour sets from the edge list: distinct, loops dropped, both directions.
fn neighbour_sets(n: usize, edges: &[(usize, usize)]) -> Vec<BTreeSet<usize>> {
    let mut sets = vec![BTreeSet::new(); n];
    for &(a, b) in edges {
        if a != b {
            sets[a].insert(b);
            sets[b].insert(a);
        }
    }
    sets
}

/// The metric by its paper definition; `(u, u)` is zero, as NetworKit returns.
fn by_definition(
    sets: &[BTreeSet<usize>],
    communities: &[i64],
    metric: LinkMetric,
    u: usize,
    v: usize,
) -> f64 {
    if u == v {
        return 0.0;
    }
    let common: Vec<usize> = sets[u].intersection(&sets[v]).copied().collect();
    match metric {
        LinkMetric::CommonNeighbors => common.len() as f64,
        LinkMetric::AdamicAdar => common
            .iter()
            .map(|&w| 1.0 / (sets[w].len() as f64).ln())
            .sum(),
        LinkMetric::ResourceAllocation => common.iter().map(|&w| 1.0 / sets[w].len() as f64).sum(),
        LinkMetric::PreferentialAttachment => (sets[u].len() * sets[v].len()) as f64,
        LinkMetric::TotalNeighbors => sets[u].union(&sets[v]).count() as f64,
        LinkMetric::SameCommunity => f64::from(u8::from(communities[u] == communities[v])),
    }
}

/// Pairs u < v, not adjacent, with a common neighbour: distance exactly two.
fn distance_two(sets: &[BTreeSet<usize>]) -> Vec<(usize, usize)> {
    let n = sets.len();
    let mut pairs = Vec::new();
    for u in 0..n {
        for v in u + 1..n {
            if !sets[u].contains(&v) && sets[u].intersection(&sets[v]).next().is_some() {
                pairs.push((u, v));
            }
        }
    }
    pairs
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
fn link_prediction_matches_an_independent_oracle() {
    let mut random = Xorshift(0x9E37_79B9_7F4A_7C15);
    // What the fixtures reached, so a vacuous run cannot pass.
    let (mut sums_of_two, mut parallels, mut loops, mut isolates, mut rows) = (0, 0, 0, 0, 0);
    for _ in 0..400 {
        let n = 1 + random.below(10);
        let count = random.below(3 * n);
        let edges: Vec<_> = (0..count)
            .map(|_| (random.below(n), random.below(n)))
            .collect();
        let communities: Vec<i64> = (0..n).map(|_| [-3, 8, 1 << 40][random.below(3)]).collect();
        let sets = neighbour_sets(n, &edges);
        loops += edges.iter().filter(|(a, b)| a == b).count();
        parallels += edges.len() - edges.iter().collect::<BTreeSet<_>>().len();
        isolates += sets.iter().filter(|set| set.is_empty()).count();

        let graph = build(n, &edges, &communities);
        let context = context();
        let projection = project(&graph, Orientation::Undirected, &context);
        let properties = communities_of(&graph, &projection);
        // Every ordered pair, self-pairs and adjacent pairs included.
        let every: Vec<_> = (0..n).flat_map(|u| (0..n).map(move |v| (u, v))).collect();
        let explicit = CandidatePairs::from_rows(&projection, &every).unwrap();
        let expected_two = distance_two(&sets);
        for metric in METRICS {
            let what = format!("{metric:?} n={n} {edges:?} {communities:?}");
            let expected: Rows = every
                .iter()
                .map(|&(u, v)| (u, v, by_definition(&sets, &communities, metric, u, v)))
                .collect();
            // Bit-for-bit: the definition sums shared neighbours in ascending
            // order, and so must the kernel.
            let got = run(
                &projection,
                &properties,
                metric,
                LinkCandidates::Pairs(&explicit),
            );
            assert_eq!(got, expected, "explicit {what}");
            let expected: Rows = expected_two
                .iter()
                .map(|&(u, v)| (u, v, by_definition(&sets, &communities, metric, u, v)))
                .collect();
            let got = run(
                &projection,
                &properties,
                metric,
                LinkCandidates::DistanceTwo,
            );
            assert_eq!(got, expected, "distance two {what}");
            rows += got.len();
        }
        sums_of_two += expected_two
            .iter()
            .filter(|&&(u, v)| sets[u].intersection(&sets[v]).count() >= 2)
            .count();
    }
    assert!(rows > 5_000, "only {rows} distance-two rows");
    assert!(sums_of_two > 100, "only {sums_of_two} multi-term sums");
    assert!(parallels > 100 && loops > 100 && isolates > 100);
}

#[test]
fn link_prediction_states_hand_computed_values_and_edge_cases() {
    // Leaves 0 and 1 hang off hub 2; 2 - 3 - 4; 5 is isolated.
    // N(0) = N(1) = {2}, N(2) = {0, 1, 3}, N(3) = {2, 4}, N(4) = {3}, N(5) = {}.
    let edges = [(0, 2), (1, 2), (2, 3), (3, 4)];
    let communities = [1, 1, 1, 2, 2, 1];
    let graph = build(6, &edges, &communities);
    let context = context();
    let projection = project(&graph, Orientation::Undirected, &context);
    let properties = communities_of(&graph, &projection);
    let at_two = |metric| {
        run(
            &projection,
            &properties,
            metric,
            LinkCandidates::DistanceTwo,
        )
    };
    let pairs = [(0, 1), (0, 3), (1, 3), (2, 4)];
    let with = |scores: [f64; 4]| -> Rows {
        pairs
            .iter()
            .zip(scores)
            .map(|(&(u, v), s)| (u, v, s))
            .collect()
    };
    let (ln2, ln3) = (2f64.ln(), 3f64.ln());
    assert_eq!(at_two(LinkMetric::CommonNeighbors), with([1.0; 4]));
    // Degree-one endpoints are fine: only the shared neighbour's degree
    // counts, and a shared neighbour has at least the two endpoints.
    assert_eq!(
        at_two(LinkMetric::AdamicAdar),
        with([1.0 / ln3, 1.0 / ln3, 1.0 / ln3, 1.0 / ln2])
    );
    assert_eq!(
        at_two(LinkMetric::ResourceAllocation),
        with([1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0, 0.5])
    );
    assert_eq!(
        at_two(LinkMetric::PreferentialAttachment),
        with([1.0, 2.0, 2.0, 3.0])
    );
    assert_eq!(
        at_two(LinkMetric::TotalNeighbors),
        with([1.0, 2.0, 2.0, 3.0])
    );
    assert_eq!(
        at_two(LinkMetric::SameCommunity),
        with([1.0, 0.0, 0.0, 0.0])
    );

    // Explicit pairs: (3, 3) is the self-pair whose naive Adamic-Adar divides
    // by ln |N(4)| = ln 1 = 0; (5, 0) and (5, 5) involve the isolate; (0, 2)
    // is adjacent, so each is in the other's union.
    let explicit = CandidatePairs::from_ids(
        &projection,
        &["n3", "n5", "n5", "n0"],
        &["n3", "n0", "n5", "n2"],
    )
    .unwrap();
    let scores = |metric| -> Vec<f64> {
        run(
            &projection,
            &properties,
            metric,
            LinkCandidates::Pairs(&explicit),
        )
        .into_iter()
        .map(|row| row.2)
        .collect()
    };
    assert_eq!(scores(LinkMetric::CommonNeighbors), [0.0, 0.0, 0.0, 0.0]);
    assert_eq!(scores(LinkMetric::AdamicAdar), [0.0, 0.0, 0.0, 0.0]);
    assert_eq!(scores(LinkMetric::ResourceAllocation), [0.0, 0.0, 0.0, 0.0]);
    assert_eq!(
        scores(LinkMetric::PreferentialAttachment),
        [0.0, 0.0, 0.0, 3.0]
    );
    assert_eq!(scores(LinkMetric::TotalNeighbors), [0.0, 1.0, 0.0, 4.0]);
    // Self-pairs are zero even for a community a node trivially shares.
    assert_eq!(scores(LinkMetric::SameCommunity), [0.0, 1.0, 0.0, 1.0]);
}

#[test]
fn link_prediction_states_multigraph_and_self_loop_semantics() {
    // The same graph as above with a doubled edge, a loop on the hub and a
    // loop on the isolate: neighbour sets, so no score moves, and 5 is still
    // an isolate with no candidate.
    let simple = [(0, 2), (1, 2), (2, 3), (3, 4)];
    let multi = [
        (0, 2),
        (2, 0),
        (0, 2),
        (1, 2),
        (2, 3),
        (3, 4),
        (2, 2),
        (5, 5),
    ];
    let communities = [1, 1, 1, 2, 2, 1];
    let context = context();
    let every: Vec<_> = (0..6).flat_map(|u| (0..6).map(move |v| (u, v))).collect();
    let score_all = |edges: &[(usize, usize)]| {
        let graph = build(6, edges, &communities);
        let projection = project(&graph, Orientation::Undirected, &context);
        let properties = communities_of(&graph, &projection);
        let pairs = CandidatePairs::from_rows(&projection, &every).unwrap();
        METRICS
            .iter()
            .map(|&metric| {
                (
                    run(
                        &projection,
                        &properties,
                        metric,
                        LinkCandidates::DistanceTwo,
                    ),
                    run(
                        &projection,
                        &properties,
                        metric,
                        LinkCandidates::Pairs(&pairs),
                    ),
                )
            })
            .collect::<Vec<_>>()
    };
    assert_eq!(score_all(&multi), score_all(&simple));

    // The same sets as `nodeSimilarity`: on the multigraph, its Jaccard is
    // common neighbours over total neighbours, pair for pair.
    let graph = build(6, &multi, &communities);
    let projection = project(&graph, Orientation::Undirected, &context);
    let properties = communities_of(&graph, &projection);
    let similar = node_similarity(
        &projection,
        NodeSimilarityOptions {
            metric: SimilarityMetric::Jaccard,
            top_k: 100,
            ..Default::default()
        },
    )
    .unwrap();
    let rows: Vec<_> = similar
        .first()
        .iter()
        .zip(similar.second())
        .map(|(&a, &b)| (a, b))
        .collect();
    assert!(rows.len() >= 8, "{rows:?}");
    let pairs = CandidatePairs::from_rows(&projection, &rows).unwrap();
    let common = run(
        &projection,
        &properties,
        LinkMetric::CommonNeighbors,
        LinkCandidates::Pairs(&pairs),
    );
    let total = run(
        &projection,
        &properties,
        LinkMetric::TotalNeighbors,
        LinkCandidates::Pairs(&pairs),
    );
    for (index, &jaccard) in similar.similarity().iter().enumerate() {
        assert_eq!(
            jaccard,
            common[index].2 / total[index].2,
            "{:?}",
            rows[index]
        );
    }
}

#[test]
fn link_prediction_handles_empty_single_node_and_isolates() {
    let context = context();
    for (n, edges) in [
        (0, vec![]),
        (1, vec![]),
        (1, vec![(0, 0)]),
        (4, vec![(1, 1)]),
    ] {
        let communities = vec![0; n];
        let graph = build(n, &edges, &communities);
        let projection = project(&graph, Orientation::Undirected, &context);
        let properties = communities_of(&graph, &projection);
        for metric in METRICS {
            assert!(
                run(
                    &projection,
                    &properties,
                    metric,
                    LinkCandidates::DistanceTwo
                )
                .is_empty()
            );
        }
        let empty = CandidatePairs::from_rows(&projection, &[]).unwrap();
        assert!(empty.is_empty());
        assert!(
            run(
                &projection,
                &properties,
                LinkMetric::AdamicAdar,
                LinkCandidates::Pairs(&empty)
            )
            .is_empty()
        );
    }
    // A path of two edges has one candidate; a single edge has none, because
    // its ends are adjacent.
    let graph = build(3, &[(0, 1), (1, 2)], &[0, 0, 0]);
    let projection = project(&graph, Orientation::Undirected, &context);
    let properties = communities_of(&graph, &projection);
    assert_eq!(
        run(
            &projection,
            &properties,
            LinkMetric::CommonNeighbors,
            LinkCandidates::DistanceTwo
        ),
        [(0, 2, 1.0)]
    );
    let graph = build(2, &[(0, 1)], &[0, 0]);
    let projection = project(&graph, Orientation::Undirected, &context);
    let properties = communities_of(&graph, &projection);
    assert!(
        run(
            &projection,
            &properties,
            LinkMetric::CommonNeighbors,
            LinkCandidates::DistanceTwo
        )
        .is_empty()
    );
}

#[test]
fn link_prediction_rejects_invalid_options_without_leaking_admission() {
    let context = context();
    let graph = build(3, &[(0, 1), (1, 2)], &[0, 0, 1]);
    let projection = project(&graph, Orientation::Undirected, &context);
    let properties = communities_of(&graph, &projection);
    let other = project(&graph, Orientation::Undirected, &context);
    let other_properties = communities_of(&graph, &other);
    let foreign = CandidatePairs::from_rows(&other, &[(0, 2)]).unwrap();
    let numbers = NodeProperties::from_graph(
        &graph,
        &projection,
        &[PropertyRequest::required("c", PropertyKind::Number)],
    )
    .unwrap();
    let held = context.usage().unwrap().live_bytes;

    let refused = |graph: &GraphProjection, options: LinkPredictionOptions<'_>| -> String {
        match link_prediction(graph, options) {
            Err(AlgorithmError::InvalidArguments(message)) => message,
            Err(other) => panic!("{other}"),
            Ok(_) => panic!("accepted"),
        }
    };
    // Directed projections are refused, naming the orientation to use.
    for orientation in [Orientation::Outgoing, Orientation::Incoming] {
        let directed = project(&graph, orientation, &context);
        assert!(refused(&directed, LinkPredictionOptions::default()).contains("undirected"));
    }
    let same = LinkMetric::SameCommunity;
    assert!(
        refused(
            &projection,
            LinkPredictionOptions {
                metric: same,
                ..Default::default()
            }
        )
        .contains("sameCommunity")
    );
    assert!(
        refused(
            &projection,
            LinkPredictionOptions {
                communities: Some((&properties, "c")),
                ..Default::default()
            }
        )
        .contains("only metric sameCommunity")
    );
    assert!(
        refused(
            &projection,
            LinkPredictionOptions {
                metric: same,
                communities: Some((&other_properties, "c")),
                ..Default::default()
            }
        )
        .contains("another projection")
    );
    assert!(
        refused(
            &projection,
            LinkPredictionOptions {
                metric: same,
                communities: Some((&numbers, "c")),
                ..Default::default()
            }
        )
        .contains("integer")
    );
    assert!(
        refused(
            &projection,
            LinkPredictionOptions {
                candidates: LinkCandidates::Pairs(&foreign),
                ..Default::default()
            }
        )
        .contains("another projection")
    );
    assert_eq!(context.usage().unwrap().live_bytes, held);

    let error = |result: Result<CandidatePairs, AlgorithmError>| match result {
        Err(AlgorithmError::InvalidArguments(message)) => message,
        Err(other) => panic!("{other}"),
        Ok(_) => panic!("accepted"),
    };
    assert!(error(CandidatePairs::from_ids(&projection, &["n0"], &["n9"])).contains("n9"));
    assert!(
        error(CandidatePairs::from_ids(
            &projection,
            &["n0"],
            &["n1", "n2"]
        ))
        .contains("length")
    );
    assert!(error(CandidatePairs::from_rows(&projection, &[(0, 3)])).contains("outside"));
    assert_eq!(context.usage().unwrap().live_bytes, held);
}

#[test]
fn link_prediction_observes_cancellation_and_budget_and_releases_scratch() {
    // A star: every two leaves are at distance two, the quadratic case.
    let edges: Vec<_> = (1..3000).map(|leaf| (0, leaf)).collect();
    let communities = vec![0; 3000];
    let graph = build(3000, &edges, &communities);
    let context = context();
    let projection = project(&graph, Orientation::Undirected, &context);
    let held = context.usage().unwrap().live_bytes;
    context.cancel().unwrap();
    assert!(matches!(
        link_prediction(&projection, LinkPredictionOptions::default()),
        Err(AlgorithmError::Cancelled)
    ));
    assert_eq!(context.usage().unwrap().live_bytes, held);

    // Unbudgeted, a smaller star finishes: 299 leaves choose two, and the
    // output grows past its first admission several times on the way.
    let small: Vec<_> = (1..300).map(|leaf| (0, leaf)).collect();
    let probe = context_with(2_000_000_000);
    let star = project(
        &build(300, &small, &communities[..300]),
        Orientation::Undirected,
        &probe,
    );
    let result = link_prediction(&star, LinkPredictionOptions::default()).unwrap();
    assert_eq!(result.scores().len(), 299 * 298 / 2);
    assert!(result.scores().iter().all(|&score| score == 1.0));
    let projection_work = {
        let probe = context_with(2_000_000_000);
        project(&graph, Orientation::Undirected, &probe);
        probe.usage().unwrap().work_units
    };

    let tight = context_with(projection_work + 1_000_000);
    let projection = project(&graph, Orientation::Undirected, &tight);
    let held = tight.usage().unwrap().live_bytes;
    assert!(matches!(
        link_prediction(&projection, LinkPredictionOptions::default()),
        Err(AlgorithmError::BudgetExceeded {
            resource: "work",
            ..
        })
    ));
    assert_eq!(tight.usage().unwrap().live_bytes, held);
}

fn context_with(work_units: usize) -> ExecutionContext {
    ExecutionContext::new(limits(work_units)).unwrap()
}

#[cfg(feature = "arrow")]
#[test]
fn link_prediction_arrow_batches_keep_bounds_and_admission() {
    use arrow_array::{Array, Float64Array, RecordBatch, StringArray};
    use std::sync::Arc;

    let context = ExecutionContext::new(ExecutionLimits {
        batch_rows: 2,
        ..limits(10_000_000)
    })
    .unwrap();
    let graph = build(5, &[(0, 1), (1, 2), (2, 3), (3, 4)], &[0; 5]);
    let projection = project(&graph, Orientation::Undirected, &context);
    let batch = |first: Vec<Option<&str>>, second: Vec<Option<&str>>| {
        RecordBatch::try_from_iter([
            ("a", Arc::new(StringArray::from(first)) as _),
            ("b", Arc::new(StringArray::from(second)) as _),
        ])
        .unwrap()
    };
    // Two batches, read in order: pairs 0-2, 1-3, 0-4.
    let batches = [
        batch(vec![Some("n0"), Some("n1")], vec![Some("n2"), Some("n3")]),
        batch(vec![Some("n0")], vec![Some("n4")]),
    ];
    let pairs = CandidatePairs::from_arrow_batches(&projection, &batches, "a", "b").unwrap();
    assert_eq!(pairs.first(), [0, 1, 0]);
    assert_eq!(pairs.second(), [2, 3, 4]);
    let nulls = [batch(vec![Some("n0")], vec![None])];
    assert!(matches!(
        CandidatePairs::from_arrow_batches(&projection, &nulls, "a", "b"),
        Err(AlgorithmError::InvalidArguments(_))
    ));
    assert!(CandidatePairs::from_arrow_batches(&projection, &batches, "a", "missing").is_err());

    let held = context.usage().unwrap().live_bytes;
    let mut cursor = link_prediction(
        &projection,
        LinkPredictionOptions {
            candidates: LinkCandidates::Pairs(&pairs),
            ..Default::default()
        },
    )
    .unwrap()
    .into_table()
    .unwrap()
    .into_arrow_results();
    assert!(context.usage().unwrap().live_bytes > held);
    let mut rows = Vec::new();
    while let Some(batch) = cursor.next_batch().unwrap() {
        let batch = batch.record_batch();
        assert!(batch.num_rows() <= 2);
        let names: Vec<_> = batch
            .schema()
            .fields()
            .iter()
            .map(|field| field.name().clone())
            .collect();
        assert_eq!(names, ["node1", "node2", "score"]);
        let column = |index: usize| {
            batch
                .column(index)
                .as_any()
                .downcast_ref::<StringArray>()
                .unwrap()
                .clone()
        };
        let (a, b) = (column(0), column(1));
        let score = batch
            .column(2)
            .as_any()
            .downcast_ref::<Float64Array>()
            .unwrap();
        for row in 0..batch.num_rows() {
            rows.push((
                a.value(row).to_string(),
                b.value(row).to_string(),
                score.value(row),
            ));
        }
    }
    assert_eq!(
        rows,
        [
            ("n0".into(), "n2".into(), 1.0),
            ("n1".into(), "n3".into(), 1.0),
            ("n0".into(), "n4".into(), 0.0),
        ]
    );
    drop(cursor);
    drop(pairs);
    assert!(context.usage().unwrap().live_bytes < held);
}
