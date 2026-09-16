//! `put_graph` accepts an edge whose endpoint node is not stored, the way the
//! Memory reference does, on every load path alike: WAL, a single MVCC
//! writer, and parallel MVCC writers. Foreign keys are switched off for the
//! load only; a single-edge write afterwards still meets the schema's
//! `REFERENCES nodes(id)`, so serving stays strict.

use grust_core::prelude::*;
use grust_turso::{TursoConfig, TursoGraphStore, TursoJournalMode};

/// 300 nodes, a star of edges out of `n0`, and one edge to a node that is
/// never stored. Big enough that a store with several writers takes the
/// parallel path (it needs at least `2 * batch_size` rows).
fn graph_with_a_dangling_edge() -> Graph {
    let nodes: Vec<Node> = (0..300)
        .map(|i| Node::new("Node", format!("n{i}"), Props::new()))
        .collect();
    let mut edges: Vec<Edge> = (1..300)
        .map(|i| Edge::new("EDGE", "n0", format!("n{i}"), Props::new()))
        .collect();
    edges.push(Edge::new("EDGE", "n0", "ghost", Props::new()));
    Graph::new(nodes, edges)
}

async fn load_and_check(mode: TursoJournalMode, writers: usize, dir: &tempfile::TempDir) {
    let store = TursoGraphStore::connect(TursoConfig {
        path: dir
            .path()
            .join(format!("dangling-{mode:?}-{writers}.db"))
            .display()
            .to_string(),
        table_prefix: "d".to_string(),
        batch_size: 50,
        journal_mode: mode,
    })
    .await
    .unwrap();
    store.bootstrap().await.unwrap();
    store.set_mvcc_load_parallelism(writers);

    let report = store
        .put_graph(&graph_with_a_dangling_edge())
        .await
        .unwrap_or_else(|e| panic!("{mode:?} x{writers}: load with a dangling edge failed: {e}"));
    assert_eq!(
        report.edges, 300,
        "{mode:?} x{writers}: every edge reported"
    );

    let out = store
        .get_edges(EdgeQuery {
            from: Some(NodeId::new("n0")),
            to: None,
            label: None,
        })
        .await
        .unwrap();
    assert_eq!(
        out.len(),
        300,
        "{mode:?} x{writers}: the dangling edge is stored too"
    );
    assert!(
        out.iter().any(|e| e.to.as_str() == "ghost"),
        "{mode:?} x{writers}: the edge to the unstored node reads back"
    );
    assert!(
        store
            .get_node(&NodeId::new("ghost"))
            .await
            .unwrap()
            .is_none(),
        "{mode:?} x{writers}: the endpoint exists only as an edge end"
    );

    // Foreign keys are back on: a single-edge write to a missing node is
    // refused, as before this change.
    let strict = store
        .put_edge(&Edge::new("EDGE", "n0", "ghost2", Props::new()))
        .await;
    assert!(
        strict.is_err(),
        "{mode:?} x{writers}: serving writes still enforce REFERENCES nodes(id)"
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn a_dangling_edge_loads_the_same_on_every_path() {
    let dir = tempfile::tempdir().unwrap();
    load_and_check(TursoJournalMode::Wal, 1, &dir).await;
    load_and_check(TursoJournalMode::Mvcc, 1, &dir).await;
    load_and_check(TursoJournalMode::Mvcc, 4, &dir).await;
}
