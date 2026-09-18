//! Feasibility probe: can a database loaded in WAL mode be reopened as MVCC?
//! If it can, a bulk load could run at WAL speed and the store then serve
//! MVCC's concurrent writers. The test records what the engine does either
//! way; it only asserts correctness when the reopen succeeds.

use grust_core::prelude::*;
use grust_turso::{TursoConfig, TursoGraphStore, TursoJournalMode};
use std::sync::Arc;

fn config(path: &std::path::Path, mode: TursoJournalMode) -> TursoConfig {
    TursoConfig {
        path: path.display().to_string(),
        table_prefix: "w".to_string(),
        batch_size: 500,
        journal_mode: mode,
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn a_wal_loaded_database_reopened_as_mvcc() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("convert.db");

    let wal = TursoGraphStore::connect(config(&path, TursoJournalMode::Wal))
        .await
        .unwrap();
    wal.bootstrap().await.unwrap();
    let nodes: Vec<Node> = (0..200)
        .map(|i| Node::new("Node", format!("n{i}"), Props::new()))
        .collect();
    let edges: Vec<Edge> = (1..200)
        .map(|i| Edge::new("EDGE", "n0", format!("n{i}"), Props::new()))
        .collect();
    wal.put_graph(&Graph::new(nodes, edges)).await.unwrap();
    drop(wal);

    let reopened = TursoGraphStore::connect(config(&path, TursoJournalMode::Mvcc)).await;
    let mvcc = match reopened {
        Err(err) => {
            eprintln!("WAL -> MVCC reopen refused: {err}");
            return;
        }
        Ok(store) => store,
    };
    eprintln!("WAL -> MVCC reopen accepted");
    let before = mvcc
        .get_edges(EdgeQuery {
            from: Some(NodeId::new("n0")),
            to: None,
            label: None,
        })
        .await
        .unwrap();
    assert_eq!(
        before.len(),
        199,
        "every WAL-loaded edge reads back under MVCC"
    );

    let mvcc = Arc::new(mvcc.with_group_commit().await.unwrap());
    let mut tasks = Vec::new();
    for w in 0..4 {
        let store = Arc::new(mvcc.connect_shared().await.unwrap());
        tasks.push(tokio::spawn(async move {
            for i in 0..25 {
                let id = format!("m{w}-{i}");
                store
                    .put_node(&Node::new("Node", id.clone(), Props::new()))
                    .await
                    .unwrap();
                store
                    .put_edge(&Edge::new("EDGE", "n0", id, Props::new()))
                    .await
                    .unwrap();
            }
        }));
    }
    for task in tasks {
        task.await.unwrap();
    }
    let after = mvcc
        .get_edges(EdgeQuery {
            from: Some(NodeId::new("n0")),
            to: None,
            label: None,
        })
        .await
        .unwrap();
    assert_eq!(
        after.len(),
        299,
        "concurrent MVCC writes land on the converted store"
    );
}
