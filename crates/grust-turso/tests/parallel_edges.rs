//! Parallel edges: the Turso store keeps edges with distinct ids apart, as
//! grust-memory and LanceDB do, while an edge without an id still replaces
//! the earlier one between the same endpoints with the same label.

use grust_core::prelude::*;
use grust_turso::{TursoConfig, TursoGraphStore};

async fn store() -> TursoGraphStore {
    let store = TursoGraphStore::connect(TursoConfig::default())
        .await
        .expect("store");
    store.bootstrap().await.expect("bootstrap");
    for id in ["p1", "p2", "p3"] {
        store
            .put_node(&Node::new("Person", id, Props::new()))
            .await
            .expect("node");
    }
    store
}

async fn out_edges(store: &TursoGraphStore, from: &str) -> Vec<Edge> {
    let mut edges = store
        .get_edges(EdgeQuery {
            from: Some(NodeId::new(from)),
            to: None,
            label: None,
        })
        .await
        .expect("edges");
    edges.sort_by(|a, b| a.id.cmp(&b.id));
    edges
}

#[tokio::test]
async fn edges_with_distinct_ids_between_the_same_endpoints_are_all_kept() {
    let s = store().await;
    let graph = Graph::new(
        vec![],
        vec![
            Edge::new("KNOWS", "p3", "p2", Props::new()).with_id("q1"),
            Edge::new("KNOWS", "p3", "p2", Props::new()).with_id("q2"),
        ],
    );
    s.put_graph(&graph).await.expect("put_graph");
    let ids: Vec<_> = out_edges(&s, "p3")
        .await
        .into_iter()
        .map(|e| e.id.expect("id").as_str().to_string())
        .collect();
    assert_eq!(ids, vec!["q1", "q2"]);
}

#[tokio::test]
async fn an_edge_without_an_id_still_replaces_the_earlier_one() {
    let s = store().await;
    let mut props = Props::new();
    props.insert("w".to_string(), Value::Int(1));
    s.put_edge(&Edge::new("KNOWS", "p1", "p2", props.clone()))
        .await
        .expect("first");
    props.insert("w".to_string(), Value::Int(2));
    s.put_edge(&Edge::new("KNOWS", "p1", "p2", props))
        .await
        .expect("second");
    let edges = out_edges(&s, "p1").await;
    assert_eq!(edges.len(), 1);
    assert_eq!(edges[0].props.get("w"), Some(&Value::Int(2)));
}

#[tokio::test]
async fn re_putting_an_edge_id_updates_that_edge_in_place() {
    let s = store().await;
    s.put_edge(&Edge::new("KNOWS", "p3", "p2", Props::new()).with_id("q1"))
        .await
        .expect("q1");
    s.put_edge(&Edge::new("KNOWS", "p3", "p2", Props::new()).with_id("q2"))
        .await
        .expect("q2");
    let mut props = Props::new();
    props.insert("w".to_string(), Value::Int(7));
    s.put_edge(&Edge::new("KNOWS", "p3", "p2", props).with_id("q1"))
        .await
        .expect("q1 again");
    let edges = out_edges(&s, "p3").await;
    assert_eq!(edges.len(), 2);
    assert_eq!(edges[0].props.get("w"), Some(&Value::Int(7)));
}

async fn migration_case(unreleased_identity_column: bool) {
    let dir = tempfile::tempdir().expect("tempdir");
    let path = dir.path().join("legacy.db").to_string_lossy().to_string();
    {
        let db = turso::Builder::new_local(&path).build().await.expect("db");
        let conn = db.connect().expect("conn");
        let (column, key, insert_column, insert_value) = if unreleased_identity_column {
            (
                "id_key TEXT NOT NULL DEFAULT '',",
                ", id_key",
                ", id_key",
                ", 'old'",
            )
        } else {
            ("", "", "", "")
        };
        conn.execute_batch(&format!(
            "CREATE TABLE grust_nodes (id text PRIMARY KEY, label text NOT NULL, props TEXT NOT NULL DEFAULT '{{}}');
             CREATE TABLE grust_edges (
                id text,
                from_id text NOT NULL REFERENCES grust_nodes(id) ON DELETE CASCADE,
                to_id text NOT NULL REFERENCES grust_nodes(id) ON DELETE CASCADE,
                label text NOT NULL,
                props TEXT NOT NULL DEFAULT '{{}}',
                {column}
                PRIMARY KEY (from_id, label, to_id{key})
             );
             CREATE INDEX grust_edges_from_idx ON grust_edges(from_id);
             CREATE INDEX grust_edges_to_idx ON grust_edges(to_id);
             INSERT INTO grust_nodes VALUES ('p1', 'Person', '{{}}'), ('p2', 'Person', '{{}}');
             INSERT INTO grust_edges (id, from_id, to_id, label, props{insert_column})
                 VALUES ('old', 'p1', 'p2', 'KNOWS', '{{}}'{insert_value});"
        )).await.expect("legacy schema");
        if unreleased_identity_column {
            conn.execute_batch(
                "INSERT INTO grust_edges VALUES ('id:old', 'p1', 'p2', 'KNOWS', '{}', 'id:old');",
            )
            .await
            .expect("prefix-like raw identity");
        }
    }
    let original_count = if unreleased_identity_column { 2 } else { 1 };
    let store = TursoGraphStore::connect(TursoConfig {
        path,
        ..TursoConfig::default()
    })
    .await
    .expect("store");
    store.bootstrap().await.expect("bootstrap migrates");
    store
        .bootstrap()
        .await
        .expect("a second bootstrap is a no-op");
    let edges = out_edges(&store, "p1").await;
    assert_eq!(
        edges.len(),
        original_count,
        "old rows survive the migration"
    );
    assert!(
        edges
            .iter()
            .any(|e| e.id.as_ref().is_some_and(|id| id.as_str() == "old"))
    );
    store
        .put_graph(&Graph::new(
            vec![],
            vec![
                Edge::new("KNOWS", "p1", "p2", Props::new()).with_id("n1"),
                Edge::new("KNOWS", "p1", "p2", Props::new()).with_id("n2"),
            ],
        ))
        .await
        .expect("parallel edges after the migration");
    assert_eq!(out_edges(&store, "p1").await.len(), original_count + 2);
    let mut props = Props::new();
    props.insert("updated".into(), Value::Bool(true));
    store
        .put_edge(&Edge::new("KNOWS", "p1", "p2", props).with_id("old"))
        .await
        .expect("update migrated id");
    let edges = out_edges(&store, "p1").await;
    assert_eq!(
        edges.len(),
        original_count + 2,
        "re-putting a migrated id must not duplicate it"
    );
    assert_eq!(
        edges
            .iter()
            .find(|e| e.id.as_ref().is_some_and(|id| id.as_str() == "old"))
            .unwrap()
            .props
            .get("updated"),
        Some(&Value::Bool(true))
    );
}

#[tokio::test]
async fn a_database_with_the_old_edge_key_is_migrated_and_keeps_its_rows() {
    migration_case(false).await;
}

#[tokio::test]
async fn an_unreleased_identity_layout_preserves_migrated_ids() {
    migration_case(true).await;
}

#[tokio::test]
async fn missing_empty_and_prefix_like_ids_are_distinct() {
    let s = store().await;
    let mut edges = vec![Edge::new("KNOWS", "p1", "p2", Props::new())];
    for id in ["", "x", "id:x"] {
        edges.push(Edge::new("KNOWS", "p1", "p2", Props::new()).with_id(id));
    }
    s.put_graph(&Graph::new(vec![], edges))
        .await
        .expect("distinct identities");
    let found = out_edges(&s, "p1").await;
    assert_eq!(found.len(), 4);
    assert_eq!(
        found
            .iter()
            .map(|e| e.id.as_ref().map(|id| id.as_str()))
            .collect::<Vec<_>>(),
        vec![None, Some(""), Some("id:x"), Some("x")]
    );
}
