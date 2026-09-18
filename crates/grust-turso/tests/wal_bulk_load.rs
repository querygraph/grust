//! `set_bulk_load_via_wal`: an MVCC store's `put_graph` loads through WAL and
//! the store is back in MVCC afterwards (concurrent BEGIN CONCURRENT writers,
//! which WAL would refuse, all land).

use grust_core::prelude::*;
use grust_turso::{TursoConfig, TursoGraphStore, TursoJournalMode};
use std::sync::Arc;

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn an_mvcc_bulk_load_through_wal_keeps_every_row_and_mvcc_writers() {
    let dir = tempfile::tempdir().unwrap();
    let store = TursoGraphStore::connect(TursoConfig {
        path: dir.path().join("walload.db").display().to_string(),
        table_prefix: "b".to_string(),
        batch_size: 500,
        journal_mode: TursoJournalMode::Mvcc,
    })
    .await
    .unwrap();
    store.bootstrap().await.unwrap();
    let store = store.with_group_commit().await.unwrap();
    store.set_bulk_load_via_wal(true);

    let nodes: Vec<Node> = (0..1000)
        .map(|i| Node::new("Node", format!("n{i}"), Props::new()))
        .collect();
    let edges: Vec<Edge> = (1..1000)
        .map(|i| Edge::new("EDGE", "n0", format!("n{i}"), Props::new()))
        .collect();
    // Two calls, as the harness loads: vertices, then edges.
    store
        .put_graph(&Graph::new(nodes, Vec::new()))
        .await
        .unwrap();
    store
        .put_graph(&Graph::new(Vec::new(), edges))
        .await
        .unwrap();

    let hub = EdgeQuery {
        from: Some(NodeId::new("n0")),
        to: None,
        label: None,
    };
    assert_eq!(store.get_edges(hub.clone()).await.unwrap().len(), 999);

    let mut tasks = Vec::new();
    for w in 0..4 {
        let handle = Arc::new(store.connect_shared().await.unwrap());
        tasks.push(tokio::spawn(async move {
            for i in 0..25 {
                handle
                    .put_edge(&Edge::new("EDGE", "n0", format!("n{}", 1 + w * 25 + i), {
                        let mut p = Props::new();
                        p.insert("w".to_string(), Value::from(w as i64));
                        p
                    }))
                    .await
                    .unwrap();
            }
        }));
    }
    for task in tasks {
        task.await.unwrap();
    }
    // The upserts touched existing edges (same keys), so the count is
    // unchanged and every one of them succeeded under BEGIN CONCURRENT.
    assert_eq!(store.get_edges(hub).await.unwrap().len(), 999);
}
