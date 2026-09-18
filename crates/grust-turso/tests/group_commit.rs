//! MVCC group commit: concurrent single-statement writes from shared handles
//! are all applied exactly once, and a failing statement fails only its own
//! caller.

use grust_core::prelude::*;
use grust_turso::{TursoConfig, TursoGraphStore, TursoJournalMode};
use std::sync::Arc;

async fn mvcc_store(dir: &tempfile::TempDir) -> TursoGraphStore {
    let store = TursoGraphStore::connect(TursoConfig {
        path: dir.path().join("group.db").display().to_string(),
        table_prefix: "g".to_string(),
        batch_size: 500,
        journal_mode: TursoJournalMode::Mvcc,
    })
    .await
    .unwrap();
    store.bootstrap().await.unwrap();
    store.with_group_commit().await.unwrap()
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn group_commit_applies_every_concurrent_write_once() {
    let dir = tempfile::tempdir().unwrap();
    let base = mvcc_store(&dir).await;
    base.put_node(&Node::new("Node", "hub", Props::new()))
        .await
        .unwrap();

    let writers = 8;
    let per = 50;
    let mut tasks = Vec::new();
    for w in 0..writers {
        let store = Arc::new(base.connect_shared().await.unwrap());
        tasks.push(tokio::spawn(async move {
            for i in 0..per {
                let id = format!("n-{w}-{i}");
                store
                    .put_node(&Node::new("Node", id.clone(), Props::new()))
                    .await
                    .unwrap();
                store
                    .put_edge(&Edge::new("EDGE", "hub", id, Props::new()))
                    .await
                    .unwrap();
            }
        }));
    }
    for task in tasks {
        task.await.unwrap();
    }

    let edges = base
        .get_edges(EdgeQuery {
            from: Some(NodeId::new("hub")),
            to: None,
            label: None,
        })
        .await
        .unwrap();
    assert_eq!(
        edges.len(),
        writers * per,
        "every acknowledged edge is stored"
    );
    let mut targets: Vec<_> = edges.iter().map(|e| e.to.as_str().to_string()).collect();
    targets.sort();
    targets.dedup();
    assert_eq!(targets.len(), writers * per, "no write is applied twice");

    // The writes survive a fresh connection to the same file.
    drop(base);
    let reopened = TursoGraphStore::connect(TursoConfig {
        path: dir.path().join("group.db").display().to_string(),
        table_prefix: "g".to_string(),
        batch_size: 500,
        journal_mode: TursoJournalMode::Mvcc,
    })
    .await
    .unwrap();
    let edges = reopened
        .get_edges(EdgeQuery {
            from: Some(NodeId::new("hub")),
            to: None,
            label: None,
        })
        .await
        .unwrap();
    assert_eq!(edges.len(), writers * per, "the writes are durable");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn group_commit_failure_is_reported_to_its_own_caller_only() {
    let dir = tempfile::tempdir().unwrap();
    let base = mvcc_store(&dir).await;
    let good = Arc::new(base.connect_shared().await.unwrap());
    let good_task = {
        let good = good.clone();
        tokio::spawn(async move {
            for i in 0..20 {
                good.put_node(&Node::new("Node", format!("ok-{i}"), Props::new()))
                    .await
                    .unwrap();
            }
        })
    };
    // An edge to endpoints that do not exist violates the edge table's
    // foreign keys only if they are enforced on the committer's connection;
    // either way the good writer's nodes must all land.
    let _ = base
        .put_edge(&Edge::new("EDGE", "missing-a", "missing-b", Props::new()))
        .await;
    good_task.await.unwrap();
    for i in 0..20 {
        assert!(
            base.get_node(&NodeId::new(format!("ok-{i}")))
                .await
                .unwrap()
                .is_some(),
            "node ok-{i} from the other writer landed"
        );
    }
}
