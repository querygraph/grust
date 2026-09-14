//! The resident snapshot answers every read exactly as the direct filtered
//! scans do, and never serves rows older than the tables.
use crate::*;

async fn pair(
    dir: &std::path::Path,
    bulk_batch_size: usize,
) -> (LanceDbGraphStore, LanceDbGraphStore) {
    let config = LanceDbConfig {
        uri: dir.display().to_string(),
        table_prefix: "snap".to_string(),
        batch_size: 2,
        bulk_batch_size,
    };
    let fast = LanceDbGraphStore::connect(config.clone()).await.unwrap();
    fast.bootstrap().await.unwrap();
    fast.clear().await.unwrap();
    let direct = LanceDbGraphStore::connect(config)
        .await
        .unwrap()
        .with_read_snapshot(false);
    (fast, direct)
}

/// Several labels, props, explicit ids on parallel edges, a self-loop, an
/// edge to a vertex with no node row, and ids that need quoting.
fn mixed_graph() -> Graph {
    let mut builder = Graph::builder();
    for i in 0..40 {
        let label = if i % 3 == 0 { "A" } else { "B" };
        let _ = builder
            .node(label, format!("n{i}"))
            .prop("rank", i as i64)
            .prop("name", if i % 5 == 0 { "five" } else { "other" })
            .finish();
    }
    let _ = builder.node("A", "o'brien").finish();
    for i in 0..40 {
        for step in [1, 3, 7] {
            let label = if (i + step) % 2 == 0 { "X" } else { "Y" };
            let _ = builder
                .edge(label, format!("n{i}"), format!("n{}", (i * step + 1) % 40))
                .finish();
        }
    }
    let _ = builder.edge("X", "n4", "n4").prop("w", 2i64).finish();
    let _ = builder.edge("X", "n5", "ghost").finish();
    let _ = builder.edge("Y", "o'brien", "n1").finish();
    let _ = builder.edge("X", "n1", "o'brien").finish();
    let mut graph = builder.build();
    graph
        .edges
        .push(Edge::new("X", "n2", "n9", Props::new()).with_id("p-1"));
    graph
        .edges
        .push(Edge::new("X", "n2", "n9", Props::new()).with_id("p-2"));
    graph
}

fn traversals() -> Vec<Traversal> {
    let mut all = Vec::new();
    for id in ["n0", "n1", "n4", "n5", "o'brien", "ghost", "missing"] {
        all.push(Traversal::from_node(id));
        all.push(Traversal::from_node(id).out("X"));
        all.push(Traversal::from_node(id).in_("Y"));
        all.push(Traversal::from_node(id).both("X").to("B"));
        all.push(Traversal::from_node(id).out("X").out("Y").to("A"));
        all.push(Traversal::from_node(id).both("X").both("Y").limit(3));
        all.push(Traversal::from_node(id).out("NONE"));
        all.push(Traversal::from_node(id).out("X").to("NONE"));
    }
    all.push(Traversal {
        start: Start::NodesByLabel(Label::new("A")),
        steps: Vec::new(),
        limit: Some(4),
    });
    all.push(Traversal {
        start: Start::NodesByLabel(Label::new("B")),
        steps: vec![Step {
            direction: Direction::Out,
            edge: Some(Label::new("Y")),
            node: None,
        }],
        limit: None,
    });
    all.push(Traversal {
        start: Start::NodesByProperty {
            label: Label::new("A"),
            key: "name".into(),
            value: Value::from("five"),
        },
        steps: vec![Step {
            direction: Direction::Both,
            edge: None,
            node: None,
        }],
        limit: Some(5),
    });
    all
}

fn edge_queries() -> Vec<EdgeQuery> {
    let ids = ["n0", "n2", "n4", "n9", "o'brien", "ghost", "missing"];
    let mut all = vec![EdgeQuery::default()];
    for label in [None, Some("X"), Some("Y"), Some("NONE")] {
        let label = label.map(Label::new);
        all.push(EdgeQuery {
            label: label.clone(),
            ..Default::default()
        });
        for from in ids {
            all.push(EdgeQuery {
                from: Some(NodeId::new(from)),
                to: None,
                label: label.clone(),
            });
            all.push(EdgeQuery {
                from: None,
                to: Some(NodeId::new(from)),
                label: label.clone(),
            });
            for to in ids {
                all.push(EdgeQuery {
                    from: Some(NodeId::new(from)),
                    to: Some(NodeId::new(to)),
                    label: label.clone(),
                });
            }
        }
    }
    all
}

async fn assert_same_answers(fast: &LanceDbGraphStore, direct: &LanceDbGraphStore) {
    // Two reads at the same versions build the snapshot.
    fast.get_node(&NodeId::new("n0")).await.unwrap();
    fast.get_node(&NodeId::new("n0")).await.unwrap();
    assert!(
        fast.reads.current.read().unwrap().is_some(),
        "the second read at unchanged versions builds the snapshot"
    );
    for query in edge_queries() {
        assert_eq!(
            fast.get_edges(query.clone()).await.unwrap(),
            direct.get_edges(query.clone()).await.unwrap(),
            "{query:?}"
        );
    }
    for traversal in traversals() {
        assert_eq!(
            fast.traverse(traversal.clone()).await.unwrap(),
            direct.traverse(traversal.clone()).await.unwrap(),
            "{traversal:?}"
        );
        assert_eq!(
            fast.traverse_ids(traversal.clone()).await.unwrap(),
            direct.traverse_ids(traversal.clone()).await.unwrap(),
            "{traversal:?}"
        );
    }
    let ids = ["n9", "n1", "ghost", "n9", "o'brien", "n30"]
        .map(NodeId::new)
        .to_vec();
    assert_eq!(
        fast.get_nodes(&ids).await.unwrap(),
        direct.get_nodes(&ids).await.unwrap()
    );
    for id in ["n3", "ghost", "o'brien"] {
        let id = NodeId::new(id);
        assert_eq!(
            fast.get_node(&id).await.unwrap(),
            direct.get_node(&id).await.unwrap()
        );
    }
}

#[tokio::test]
async fn snapshot_reads_match_direct_scans_over_many_fragments() {
    let dir = tempfile::tempdir().unwrap();
    // Seven-row bulk writes leave many fragments before compaction.
    let (fast, direct) = pair(dir.path(), 7).await;
    fast.put_graph(&mixed_graph()).await.unwrap();
    assert_same_answers(&fast, &direct).await;
}

#[tokio::test]
async fn snapshot_reads_match_direct_scans_after_incremental_writes() {
    let dir = tempfile::tempdir().unwrap();
    let (fast, direct) = pair(dir.path(), 50_000).await;
    let graph = mixed_graph();
    for node in &graph.nodes {
        fast.put_node(node).await.unwrap();
    }
    for edge in &graph.edges {
        fast.put_edge(edge).await.unwrap();
    }
    // An update rewrites a row in place of the old one.
    fast.put_node(&Node::new("B", "n1", [("rank".into(), Value::Int(-1))]))
        .await
        .unwrap();
    assert_same_answers(&fast, &direct).await;
}

#[tokio::test]
async fn a_resident_snapshot_never_hides_a_later_write() {
    let dir = tempfile::tempdir().unwrap();
    let (fast, other) = pair(dir.path(), 50_000).await;
    fast.put_graph(&mixed_graph()).await.unwrap();
    let out = |store: LanceDbGraphStore| async move {
        store
            .get_edges(EdgeQuery {
                from: Some(NodeId::new("n0")),
                ..Default::default()
            })
            .await
            .unwrap()
            .len()
    };
    let before = out(fast.clone()).await;
    assert_eq!(out(fast.clone()).await, before);
    assert!(fast.reads.current.read().unwrap().is_some());

    // A write through this store, then one through another connection.
    fast.put_edge(&Edge::new("X", "n0", "n39", Props::new()))
        .await
        .unwrap();
    assert_eq!(out(fast.clone()).await, before + 1);
    assert_eq!(out(fast.clone()).await, before + 1);
    other
        .put_edge(&Edge::new("X", "n0", "n38", Props::new()))
        .await
        .unwrap();
    assert_eq!(out(fast.clone()).await, before + 2);
    other
        .put_node(&Node::new("A", "n0", [("rank".into(), Value::Int(99))]))
        .await
        .unwrap();
    let node = fast.get_node(&NodeId::new("n0")).await.unwrap().unwrap();
    assert_eq!(node.props.get("rank"), Some(&Value::Int(99)));

    fast.clear().await.unwrap();
    assert!(fast.reads.current.read().unwrap().is_none());
    assert_eq!(out(fast.clone()).await, 0);
}
