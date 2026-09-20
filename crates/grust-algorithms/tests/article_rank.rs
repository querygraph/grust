//! ArticleRank against an independent recomputation, and against PageRank.
//!
//! The oracle is the iteration written out again in the test, densely and
//! without the kernel's scaling or chunking, so agreement means the kernel
//! computes the stated recurrence rather than that two copies of the same code
//! agree. The second test states the property ArticleRank exists for: a citation
//! from a node that cites little is worth less than PageRank makes it.

use grust_algorithms::{
    ExecutionContext, ExecutionLimits, GraphProjection, Orientation, PageRankOptions,
    ProjectionEdge, RankVariant, SnapshotIdentity, pagerank,
};

fn context(workers: Option<usize>) -> ExecutionContext {
    let context = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 64 * 1024 * 1024,
        work_units: usize::MAX,
        batch_rows: 128,
        deadline: None,
    })
    .expect("valid limits");
    match workers {
        Some(workers) => context.with_concurrency(workers).expect("not yet shared"),
        None => context,
    }
}

fn graph(n: usize, edges: &[(usize, usize)], context: &ExecutionContext) -> GraphProjection {
    GraphProjection::from_topology(
        SnapshotIdentity::new("article".into(), "1".into(), "reader".into()).expect("identity"),
        (0..n).map(|id| id.to_string().into()).collect(),
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
        Orientation::Outgoing,
        context,
    )
    .expect("projection")
}

/// The recurrence, written out again: dangling rows redistribute through the
/// teleport term, and a source divides by its out-degree plus the mean
/// out-degree over every node.
fn oracle(n: usize, edges: &[(usize, usize)], damping: f64, iterations: usize) -> Vec<f64> {
    let mut out_degree = vec![0.0f64; n];
    for &(source, _) in edges {
        out_degree[source] += 1.0;
    }
    let mean: f64 = out_degree.iter().sum::<f64>() / n as f64;
    let mut scores = vec![1.0 / n as f64; n];
    for _ in 0..iterations {
        let dangling: f64 = (0..n)
            .filter(|&node| out_degree[node] == 0.0)
            .map(|node| scores[node])
            .sum();
        let base = ((1.0 - damping) + damping * dangling) / n as f64;
        let mut next = vec![base; n];
        for &(source, target) in edges {
            next[target] += damping * scores[source] / (out_degree[source] + mean);
        }
        scores = next;
    }
    scores
}

/// A citation graph: node 0 is cited by a prolific citer and by a node that
/// cites only once, node 5 is cited only by the prolific one, and nodes 8 and 9
/// cite nothing at all so the dangling term is exercised.
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

#[test]
fn article_rank_matches_an_independent_recomputation() {
    let context = context(None);
    let graph = graph(NODES, &EDGES, &context);
    // A fixed iteration count rather than a tolerance, so the oracle can run the
    // same number of rounds instead of guessing when the kernel stopped.
    let options = PageRankOptions {
        variant: RankVariant::ArticleRank,
        damping: 0.85,
        tolerance: 0.0,
        max_iterations: 40,
        personalization: None,
    };
    let result = pagerank(&graph, options).expect("article rank");
    let expected = oracle(NODES, &EDGES, 0.85, 40);
    for (node, (&got, &want)) in result.values().iter().zip(&expected).enumerate() {
        assert!(
            (got - want).abs() <= 1e-12 + 1e-9 * want.abs(),
            "node {node}: kernel {got} against oracle {want}"
        );
    }
    // ArticleRank's inflated divisor means a source passes on less than all of
    // its score, so the scores sum to less than one. Stating it here keeps
    // anyone from reading the magnitudes as probabilities.
    let total: f64 = result.values().iter().sum();
    assert!(
        total < 1.0,
        "article rank mass {total} should stay under one"
    );
}

#[test]
fn article_rank_damps_what_a_sparse_citer_confers() {
    // Two citers with identical scores, because neither is cited by anyone: node
    // 0 cites only node 2, node 1 cites node 3 and four others. Under PageRank
    // node 2 receives its citer's whole score and node 3 receives a fifth of an
    // equal score, so node 2 leads node 3 by five. ArticleRank adds the mean
    // out-degree to both divisors, which costs the sparse citer proportionally
    // more, so node 2's lead shrinks. That is the whole point of the variant.
    const N: usize = 8;
    const EDGES: [(usize, usize); 6] = [(0, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7)];
    let context = context(None);
    let graph = graph(N, &EDGES, &context);
    let ranks = |variant| {
        pagerank(
            &graph,
            PageRankOptions {
                variant,
                damping: 0.85,
                tolerance: 0.0,
                max_iterations: 80,
                personalization: None,
            },
        )
        .expect("ranks")
    };
    let page = ranks(RankVariant::PageRank);
    let article = ranks(RankVariant::ArticleRank);
    let lead = |scores: &[f64]| {
        // Both nodes also hold the teleport and dangling share every node gets;
        // the citation is what is above node 4's score, an uncited sibling of
        // node 3 receiving the same share from node 1.
        let floor = scores[0].min(scores[1]);
        (scores[2] - floor) / (scores[3] - floor)
    };
    let (page_lead, article_lead) = (lead(page.values()), lead(article.values()));
    assert!(
        page_lead > 4.9 && page_lead < 5.1,
        "PageRank should give node 2 five times node 3's citation, got {page_lead}"
    );
    assert!(
        article_lead < page_lead - 1.0,
        "ArticleRank should damp the sparse citer: {article_lead} against {page_lead}"
    );
    // Damping, not reshuffling: node 2 still leads node 3 under both.
    assert!(article.values()[2] > article.values()[3]);
    assert!(page.values()[2] > page.values()[3]);
}

#[test]
fn article_rank_is_the_same_at_every_worker_count() {
    // Large enough to cross the parallel floor, so the pull kernel runs.
    const N: usize = 60_000;
    let edges: Vec<(usize, usize)> = (0..300_000)
        .map(|index| {
            let source = (index * 7919) % (N / 2);
            let target = (index * 104_729) % N;
            (source, target)
        })
        .collect();
    let options = PageRankOptions {
        variant: RankVariant::ArticleRank,
        damping: 0.85,
        tolerance: 1e-12,
        max_iterations: 50,
        personalization: None,
    };
    let bits = |workers: Option<usize>| -> (Vec<u64>, usize) {
        let context = context(workers);
        let graph = graph(N, &edges, &context);
        let result = pagerank(&graph, options).expect("article rank");
        (
            result
                .values()
                .iter()
                .map(|score| score.to_bits())
                .collect(),
            result.iterations(),
        )
    };
    let one = bits(Some(1));
    for workers in [2, 16] {
        assert_eq!(bits(Some(workers)), one, "at {workers} workers");
    }
    // And the sequential push agrees with the parallel pull to the tolerance the
    // two summation orders allow.
    let (sequential, iterations) = {
        let context = context(None);
        let graph = graph(N, &edges, &context);
        let result = pagerank(&graph, options).expect("article rank");
        (result.values().to_vec(), result.iterations())
    };
    assert_eq!(iterations, one.1);
    for (node, (&pushed, &pulled)) in sequential
        .iter()
        .zip(
            one.0
                .iter()
                .map(|bits| f64::from_bits(*bits))
                .collect::<Vec<_>>()
                .iter(),
        )
        .enumerate()
    {
        assert!(
            (pushed - pulled).abs() <= 1e-12 + 1e-9 * pushed.abs(),
            "node {node}: push {pushed} against pull {pulled}"
        );
    }
}
