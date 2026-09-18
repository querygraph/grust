//! A load into empty tables takes the plain-INSERT path; duplicate keys
//! inside that load must still end as one row per key, through the upsert
//! replay. Both journal modes, since both take the same batch path.

use grust_core::prelude::*;
use grust_turso::{TursoConfig, TursoGraphStore, TursoJournalMode};

async fn load_with_duplicates(mode: TursoJournalMode, dir: &tempfile::TempDir) {
    let store = TursoGraphStore::connect(TursoConfig {
        path: dir
            .path()
            .join(format!("dup-{mode:?}.db"))
            .display()
            .to_string(),
        table_prefix: "d".to_string(),
        batch_size: 50,
        journal_mode: mode,
    })
    .await
    .unwrap();
    store.bootstrap().await.unwrap();

    // 300 distinct ids, each appearing twice, and the second copy carries the
    // props the store must end up with.
    let mut nodes = Vec::new();
    for round in 0..2 {
        for i in 0..300 {
            let mut props = Props::new();
            props.insert("round".to_string(), Value::from(round as i64));
            nodes.push(Node::new("Node", format!("n{i}"), props));
        }
    }
    let mut edges = Vec::new();
    for round in 0..2 {
        for i in 1..300 {
            let mut props = Props::new();
            props.insert("round".to_string(), Value::from(round as i64));
            edges.push(Edge::new("EDGE", "n0", format!("n{i}"), props));
        }
    }
    store.put_graph(&Graph::new(nodes, edges)).await.unwrap();

    for i in [0usize, 7, 299] {
        let node = store
            .get_node(&NodeId::new(format!("n{i}")))
            .await
            .unwrap()
            .expect("node stored once");
        assert_eq!(
            node.props.get("round"),
            Some(&Value::from(1i64)),
            "{mode:?}: the last write of n{i} wins"
        );
    }
    let out = store
        .get_edges(EdgeQuery {
            from: Some(NodeId::new("n0")),
            to: None,
            label: None,
        })
        .await
        .unwrap();
    assert_eq!(out.len(), 299, "{mode:?}: one edge per key, not two");
    assert!(
        out.iter()
            .all(|e| e.props.get("round") == Some(&Value::from(1i64))),
        "{mode:?}: the last write of each edge wins"
    );

    // A second load, now that the tables are not empty, still merges.
    store
        .put_graph(&Graph::new(
            vec![Node::new("Node", "n0", Props::new())],
            Vec::new(),
        ))
        .await
        .unwrap();
    assert!(store.get_node(&NodeId::new("n0")).await.unwrap().is_some());
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_fresh_load_with_duplicate_keys_stores_one_row_per_key() {
    let dir = tempfile::tempdir().unwrap();
    load_with_duplicates(TursoJournalMode::Wal, &dir).await;
    load_with_duplicates(TursoJournalMode::Mvcc, &dir).await;
}
