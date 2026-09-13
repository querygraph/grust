#![cfg(all(
    feature = "algorithms",
    feature = "cypher",
    feature = "memory",
    feature = "turso"
))]

//! Explicit local execution over two independently captured backend snapshots.
//! Capture/index allocation belongs to the caller, outside the query allowance.

use grust_algorithm_procedures::register_algorithms;
use grust_core::{Edge, GraphAdminStore, GraphStore, Node, Props, TypedGraphIndex, Value};
use grust_cypher::procedures::{LocalSnapshot, RegistryBuilder, SnapshotIdentity};
use grust_cypher::{CypherParameters, PreparedProcedureQuery, ReadQueryPolicy};
use grust_memory::MemoryGraphStore;
use grust_turso::{TursoConfig, TursoGraphStore};

async fn load(store: &impl GraphStore) {
    for id in ["a", "b", "c", "isolate"] {
        store
            .put_node(&Node::new("N", id, Props::new()))
            .await
            .unwrap();
    }
    for (from, to, cost) in [("a", "b", 2.0), ("b", "c", 0.5)] {
        store
            .put_edge(&Edge::new(
                "R",
                from,
                to,
                [("cost".into(), Value::Float(cost))],
            ))
            .await
            .unwrap();
    }
}

fn check(plan: &PreparedProcedureQuery, index: &TypedGraphIndex, revision: &str) {
    let identity =
        SnapshotIdentity::new("selected".into(), revision.into(), "reader".into()).unwrap();
    let policy = ReadQueryPolicy {
        allow_read_procedures: true,
        allow_graph_selection: true,
        require_match: false,
        max_intermediate_bytes: 128 * 1024,
        ..ReadQueryPolicy::default()
    };
    let result = plan
        .execute_snapshot_bounded(
            LocalSnapshot::new(index.graph(), &identity),
            &CypherParameters::new(),
            &policy,
        )
        .unwrap();
    assert_eq!(result.rows, vec![vec![Value::Float(2.5)]]);
    let denied = ReadQueryPolicy {
        allow_read_procedures: false,
        ..policy
    };
    assert!(
        plan.execute_snapshot_bounded(
            LocalSnapshot::new(index.graph(), &identity),
            &CypherParameters::new(),
            &denied,
        )
        .is_err()
    );
}

#[tokio::test]
async fn memory_and_private_turso_snapshots_run_the_same_pinned_plan() {
    let mut builder = RegistryBuilder::default();
    register_algorithms(&mut builder).unwrap();
    let plan = PreparedProcedureQuery::prepare(
        "selected",
        "USE selected CALL grust.algorithms.dijkstra('a', {weightProperty: 'cost'}) YIELD nodeId, distance WHERE nodeId = 'c' RETURN distance LIMIT 1",
        &builder.build(),
    ).unwrap();
    let memory = MemoryGraphStore::new();
    // A private in-memory Turso database has no independent external writers.
    // The adapter serializes its own snapshot reads and writes under one gate.
    let turso = TursoGraphStore::connect(TursoConfig::default())
        .await
        .unwrap();
    turso.bootstrap().await.unwrap();
    load(&memory).await;
    load(&turso).await;
    let memory_snapshot = memory.indexed_snapshot().unwrap();
    let turso_snapshot = turso.indexed_snapshot().await.unwrap();
    check(&plan, &memory_snapshot, "memory-before-write");
    check(&plan, &turso_snapshot, "turso-before-write");
    let shortcut = Edge::new("R", "a", "c", [("cost".into(), Value::Float(0.25))]);
    memory.put_edge(&shortcut).await.unwrap();
    turso.put_edge(&shortcut).await.unwrap();
    // Existing immutable capabilities retain their old data after store writes.
    check(&plan, &memory_snapshot, "memory-before-write");
    check(&plan, &turso_snapshot, "turso-before-write");
    assert_eq!(memory.indexed_snapshot().unwrap().graph().edges.len(), 3);
    assert_eq!(
        turso.indexed_snapshot().await.unwrap().graph().edges.len(),
        3
    );
}
