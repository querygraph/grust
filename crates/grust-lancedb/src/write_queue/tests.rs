use super::*;

#[test]
fn last_row_per_key_wins_in_queue_order() {
    let rows = vec![("a", 1), ("b", 1), ("a", 2), ("c", 1), ("b", 2)];
    let kept = last_per_key(rows, |row| Ok(row.0.to_string())).unwrap();
    assert_eq!(kept, vec![("a", 2), ("c", 1), ("b", 2)]);
}

async fn store(dir: &std::path::Path) -> crate::LanceDbGraphStore {
    let store = crate::LanceDbGraphStore::connect(crate::LanceDbConfig {
        uri: dir.display().to_string(),
        table_prefix: "queue".to_string(),
        batch_size: 500,
        bulk_batch_size: 50_000,
    })
    .await
    .unwrap();
    store.bootstrap().await.unwrap();
    store
}

/// A4's pattern: writers on clones of one store attach new nodes and
/// edges to one hub at once. Every accepted write is durable exactly
/// once, seen by this store and by another connection, with and without
/// a merge-key index, and across the periodic compactions.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn concurrent_writers_on_clones_commit_every_row_once() {
    for indexed in [false, true] {
        let dir = tempfile::tempdir().unwrap();
        let store = store(dir.path()).await;
        if indexed {
            let mut graph = Graph::default();
            graph.nodes.push(Node::new("V", "hub", Props::new()));
            for i in 0..50 {
                graph
                    .nodes
                    .push(Node::new("V", format!("v{i}"), Props::new()));
                graph
                    .edges
                    .push(Edge::new("E", "hub", format!("v{i}"), Props::new()));
            }
            store.put_graph(&graph).await.unwrap();
        }
        let initial = if indexed { 50 } else { 0 };
        let writers = (0..8)
            .map(|w| {
                let store = store.clone();
                tokio::spawn(async move {
                    for i in 0..20 {
                        let id = format!("hot-{w}-{i}");
                        store
                            .put_node(&Node::new("V", id.clone(), Props::new()))
                            .await
                            .unwrap();
                        store
                            .put_edge(&Edge::new("E", "hub", id, Props::new()))
                            .await
                            .unwrap();
                    }
                })
            })
            .collect::<Vec<_>>();
        for writer in writers {
            writer.await.unwrap();
        }
        let hub_edges = EdgeQuery {
            from: Some(NodeId::new("hub")),
            ..Default::default()
        };
        let other = crate::LanceDbGraphStore::connect(store.config().clone())
            .await
            .unwrap()
            .with_read_snapshot(false);
        for reader in [&store, &other] {
            let edges = reader.get_edges(hub_edges.clone()).await.unwrap();
            assert_eq!(edges.len(), initial + 160, "indexed: {indexed}");
            let targets = edges
                .iter()
                .map(|edge| edge.to.as_str().to_owned())
                .collect::<std::collections::HashSet<_>>();
            assert_eq!(targets.len(), edges.len(), "indexed: {indexed}");
            for w in 0..8 {
                for i in 0..20 {
                    let id = NodeId::new(format!("hot-{w}-{i}"));
                    assert!(reader.get_node(&id).await.unwrap().is_some());
                }
            }
        }
    }
}

/// Writers that upsert the same node at once leave one row holding one
/// of the values written, as sequential upserts would.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn concurrent_upserts_of_one_key_leave_one_row() {
    let dir = tempfile::tempdir().unwrap();
    let store = store(dir.path()).await;
    let writers = (0..8i64)
        .map(|w| {
            let store = store.clone();
            tokio::spawn(async move {
                for i in 0..10i64 {
                    let mut node = Node::new("V", "same", Props::new());
                    node.props.insert("by".into(), Value::Int(w * 100 + i));
                    store.put_node(&node).await.unwrap();
                    store
                        .put_edge(&Edge::new("E", "same", "same", Props::new()))
                        .await
                        .unwrap();
                }
            })
        })
        .collect::<Vec<_>>();
    for writer in writers {
        writer.await.unwrap();
    }
    let direct = store.clone().with_read_snapshot(false);
    let nodes = direct
        .traverse(Traversal {
            start: Start::NodesByLabel(Label::new("V")),
            steps: Vec::new(),
            limit: None,
        })
        .await
        .unwrap();
    assert_eq!(nodes.len(), 1);
    assert!(matches!(nodes[0].props.get("by"), Some(Value::Int(_))));
    assert_eq!(
        direct.get_edges(EdgeQuery::default()).await.unwrap().len(),
        1
    );
}
