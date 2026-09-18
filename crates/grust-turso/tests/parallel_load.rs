//! `set_mvcc_load_parallelism`: an MVCC `put_graph` split across concurrent
//! writers stores exactly the rows of the graph, once each, and leaves the
//! store serving ordinary writes.

use grust_core::prelude::*;
use grust_turso::{TursoConfig, TursoGraphStore, TursoJournalMode};

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn a_parallel_mvcc_load_stores_every_row_once() {
    let dir = tempfile::tempdir().unwrap();
    let store = TursoGraphStore::connect(TursoConfig {
        path: dir.path().join("parallel.db").display().to_string(),
        table_prefix: "p".to_string(),
        batch_size: 100,
        journal_mode: TursoJournalMode::Mvcc,
    })
    .await
    .unwrap();
    store.bootstrap().await.unwrap();
    store.set_mvcc_load_parallelism(4);

    let nodes: Vec<Node> = (0..3000)
        .map(|i| Node::new("Node", format!("n{i}"), Props::new()))
        .collect();
    let edges: Vec<Edge> = (0..5000)
        .map(|i| {
            Edge::new(
                "EDGE",
                format!("n{}", i % 3000),
                format!("n{}", (i * 7 + 1) % 3000),
                Props::new(),
            )
        })
        .collect();
    let mut expected: Vec<(String, String)> = edges
        .iter()
        .map(|e| (e.from.as_str().to_string(), e.to.as_str().to_string()))
        .collect();
    expected.sort();
    expected.dedup();

    // Vertices, then edges, as the harness loads.
    store
        .put_graph(&Graph::new(nodes, Vec::new()))
        .await
        .unwrap();
    store
        .put_graph(&Graph::new(Vec::new(), edges))
        .await
        .unwrap();

    for i in (0..3000).step_by(97) {
        assert!(
            store
                .get_node(&NodeId::new(format!("n{i}")))
                .await
                .unwrap()
                .is_some(),
            "node n{i} landed"
        );
    }
    let mut stored = Vec::new();
    for i in 0..3000 {
        for e in store
            .get_edges(EdgeQuery {
                from: Some(NodeId::new(format!("n{i}"))),
                to: None,
                label: None,
            })
            .await
            .unwrap()
        {
            stored.push((e.from.as_str().to_string(), e.to.as_str().to_string()));
        }
    }
    stored.sort();
    assert_eq!(stored, expected, "every edge stored exactly once");

    store
        .put_node(&Node::new("Node", "after", Props::new()))
        .await
        .unwrap();
    assert!(
        store
            .get_node(&NodeId::new("after"))
            .await
            .unwrap()
            .is_some()
    );
}
