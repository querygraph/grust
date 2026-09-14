use super::*;

fn sample_graph() -> Graph {
    let mut builder = Graph::builder();
    let _ = builder
        .node("Person", "person-1")
        .prop("name", "Ada")
        .finish();
    let _ = builder
        .node("Talk", "talk-1")
        .prop("title", "Analytical Engine")
        .finish();
    let _ = builder
        .edge("PRESENTS", "person-1", "talk-1")
        .prop("source", "schedule")
        .finish();
    builder.build()
}

#[test]
fn bootstrap_creates_universal_turso_tables() {
    let config = TursoConfig::default();
    let sql = bootstrap_sql(&config, "\"grust_nodes\"", "\"grust_edges\"").unwrap();

    assert!(sql.contains("PRAGMA foreign_keys = ON"));
    assert!(sql.contains("CREATE TABLE IF NOT EXISTS \"grust_nodes\""));
    assert!(sql.contains("CREATE TABLE IF NOT EXISTS \"grust_edges\""));
    assert!(sql.contains("props TEXT NOT NULL"));
    assert!(sql.contains("identity_key text NOT NULL DEFAULT ''"));
    assert!(sql.contains("PRIMARY KEY (from_id, label, to_id, identity_key)"));
}

#[test]
fn schema_creates_json_views_and_indexes() {
    let config = TursoConfig::default();
    let schema = GraphSchema::builder()
        .node(
            "Person",
            vec![
                Field::required("name", FieldType::String),
                Field::optional("age", FieldType::Int),
            ],
        )
        .edge(
            "WORKS_ON",
            vec![Label::new("Person")],
            vec![Label::new("Project")],
            vec![Field::required("since", FieldType::Int)],
        )
        .build();

    let sql = turso_schema_sql(&config, "\"grust_nodes\"", "\"grust_edges\"", &schema).unwrap();

    assert!(sql.contains("CREATE VIEW IF NOT EXISTS \"grust_node_person\""));
    assert!(sql.contains("json_extract(props, '$.name.value') AS \"name\""));
    assert!(sql.contains("CAST(json_extract(props, '$.age.value') AS INTEGER) AS \"age\""));
    assert!(sql.contains("CREATE VIEW IF NOT EXISTS \"grust_edge_works_on\""));
    assert!(sql.contains("\"grust_node_person_age_idx\""));
    assert!(sql.contains("\"grust_edge_works_on_since_idx\""));
}

#[test]
fn mutation_batch_sql_wraps_ordered_mutations_in_transaction() {
    let mutations = vec![
        GraphMutation::UpsertNode(Node::new("Person", "person-1", Props::new())),
        GraphMutation::UpsertNode(Node::new("Talk", "talk-1", Props::new())),
        GraphMutation::UpsertEdge(Edge::new("PRESENTS", "person-1", "talk-1", Props::new())),
        GraphMutation::PatchNode {
            id: NodeId::new("person-1"),
            props: Props::from([("name".to_string(), Value::from("Ada"))]),
        },
        GraphMutation::DeleteEdge {
            from: NodeId::new("person-1"),
            label: Label::new("PRESENTS"),
            to: NodeId::new("talk-1"),
        },
        GraphMutation::DeleteNode(NodeId::new("person-1")),
    ];
    let sql = apply_mutations_sql("\"grust_nodes\"", "\"grust_edges\"", &mutations).unwrap();

    assert!(sql.starts_with("BEGIN;\n"));
    assert!(sql.ends_with(";\nCOMMIT"));
    assert!(sql.contains("INSERT INTO \"grust_nodes\""));
    assert!(sql.contains("INSERT INTO \"grust_edges\""));
    assert!(sql.contains("UPDATE \"grust_nodes\" SET props = json_patch(props,"));
    assert!(sql.contains("DELETE FROM \"grust_edges\" WHERE from_id = 'person-1'"));
    assert!(sql.contains("DELETE FROM \"grust_nodes\" WHERE id = 'person-1'"));
}

#[test]
fn traversal_sql_builds_exact_out_step() {
    let traversal = Traversal::from_node("person-1")
        .out("PRESENTS")
        .to("Talk")
        .limit(10);

    let sql = traversal_sql("\"grust_nodes\"", "\"grust_edges\"", &traversal).unwrap();

    assert!(sql.contains("JOIN \"grust_edges\" e0 ON e0.from_id = n0.id"));
    assert!(sql.contains("AND e0.label = 'PRESENTS'"));
    assert!(sql.contains("JOIN \"grust_nodes\" n1 ON n1.id = e0.to_id"));
    assert!(sql.contains("AND n1.label = 'Talk'"));
    assert!(sql.contains("WHERE n0.id = 'person-1'"));
    assert!(sql.contains("LIMIT 10"));
}

#[test]
fn rejects_invalid_table_prefix() {
    assert!(validate_identifier("grust_1").is_ok());
    assert!(validate_identifier("1grust").is_err());
    assert!(validate_identifier("grust-nodes").is_err());
}

#[tokio::test]
async fn in_memory_put_read_traverse_schema_and_mutations() {
    let store = TursoGraphStore::in_memory()
        .await
        .expect("open Turso store");
    store.bootstrap().await.expect("bootstrap Turso tables");
    store.clear().await.expect("clear Turso tables");
    store
        .apply_schema(
            &GraphSchema::builder()
                .node("Person", vec![Field::required("name", FieldType::String)])
                .node("Talk", vec![Field::required("title", FieldType::String)])
                .edge(
                    "PRESENTS",
                    vec![Label::new("Person")],
                    vec![Label::new("Talk")],
                    vec![Field::required("source", FieldType::String)],
                )
                .build(),
        )
        .await
        .expect("apply Turso schema");

    let graph = sample_graph();
    let report = store.put_graph(&graph).await.expect("write graph");
    assert_eq!(report.nodes, 2);
    assert_eq!(report.edges, 1);

    let fetched = store
        .get_node(&NodeId::new("talk-1"))
        .await
        .expect("read node")
        .expect("talk node missing");
    assert_eq!(fetched.label, Label::new("Talk"));

    let by_property = store
        .traverse(Traversal {
            start: Start::NodesByProperty {
                label: Label::new("Person"),
                key: "name".to_string(),
                value: Value::from("Ada"),
            },
            steps: Vec::new(),
            limit: None,
        })
        .await
        .expect("property start");
    assert_eq!(by_property.len(), 1);
    assert_eq!(by_property[0].id, NodeId::new("person-1"));

    let talks = store
        .traverse(Traversal::from_node("person-1").out("PRESENTS").to("Talk"))
        .await
        .expect("traverse");
    assert_eq!(talks.len(), 1);
    assert_eq!(talks[0].id, NodeId::new("talk-1"));

    store
        .apply_mutations(&[
            GraphMutation::PatchNode {
                id: NodeId::new("person-1"),
                props: Props::from([("role".to_string(), Value::from("engineer"))]),
            },
            GraphMutation::DeleteEdge {
                from: NodeId::new("person-1"),
                label: Label::new("PRESENTS"),
                to: NodeId::new("talk-1"),
            },
        ])
        .await
        .expect("apply mutations");

    let person = store
        .get_node(&NodeId::new("person-1"))
        .await
        .expect("read patched node")
        .expect("person node missing");
    assert_eq!(person.props.get("role"), Some(&Value::from("engineer")));
    let edges = store
        .get_edges(EdgeQuery {
            from: Some(NodeId::new("person-1")),
            to: Some(NodeId::new("talk-1")),
            label: Some(Label::new("PRESENTS")),
        })
        .await
        .expect("read deleted edges");
    assert!(edges.is_empty());
}

#[tokio::test]
async fn cypher_mutation_executor_patches_matching_nodes() {
    let store = TursoGraphStore::in_memory()
        .await
        .expect("open Turso store");
    store.bootstrap().await.expect("bootstrap Turso tables");
    store.put_graph(&sample_graph()).await.expect("write graph");

    let report = store
        .execute_cypher_mutation_plan(&GraphMutationPlan::new(vec![
            GraphMutationPlanOp::PatchMatchingNodes {
                label: Some(Label::new("Person")),
                props: Props::from([("id".to_string(), Value::from("person-1"))]),
                predicates: Vec::new(),
                patch: Props::from([("querygraph_ready".to_string(), Value::from(true))]),
                cardinality: GraphMutationCardinality::SingleIdentity,
            },
        ]))
        .await
        .expect("execute matched-node patch");

    assert_eq!(report.matched_rows, 1);
    assert_eq!(report.node_patches, 1);
    assert_eq!(report.changed_nodes, 1);
    let person = store
        .get_node(&NodeId::new("person-1"))
        .await
        .expect("read patched node")
        .expect("person node missing");
    assert_eq!(
        person.props.get("querygraph_ready"),
        Some(&Value::from(true))
    );
}

#[tokio::test]
async fn cypher_mutation_plan_rejects_before_writing_any_operation() {
    let store = TursoGraphStore::in_memory()
        .await
        .expect("open Turso store");
    store.bootstrap().await.expect("bootstrap Turso tables");

    let inserted = Node::new("Person", "must-not-commit", Props::new());
    let error = store
        .execute_cypher_mutation_plan(&GraphMutationPlan::new(vec![
            GraphMutationPlanOp::UpsertNode {
                kind: GraphMutationPlanKind::Create,
                node: inserted.clone(),
            },
            GraphMutationPlanOp::DeleteMatchingNodes {
                label: Some(Label::new("Person")),
                props: Props::new(),
                predicates: Vec::new(),
                cardinality: GraphMutationCardinality::UnboundedMany,
            },
        ]))
        .await
        .expect_err("unsupported trailing operation must reject the whole plan");

    assert!(error.to_string().contains("matched node deletes"));
    assert!(
        store
            .get_node(&inserted.id)
            .await
            .expect("read after rejected plan")
            .is_none(),
        "a rejected transactional Cypher plan must not commit its prefix"
    );
}

#[tokio::test]
async fn cypher_mutation_plan_preserves_order_inside_transaction() {
    let store = TursoGraphStore::in_memory()
        .await
        .expect("open Turso store");
    store.bootstrap().await.expect("bootstrap Turso tables");

    let inserted = Node::new("Person", "ordered-person", Props::new());
    let report = store
        .execute_cypher_mutation_plan(&GraphMutationPlan::new(vec![
            GraphMutationPlanOp::UpsertNode {
                kind: GraphMutationPlanKind::Create,
                node: inserted.clone(),
            },
            GraphMutationPlanOp::PatchMatchingNodes {
                label: Some(Label::new("Person")),
                props: Props::from([("id".to_string(), Value::from("ordered-person"))]),
                predicates: Vec::new(),
                patch: Props::from([("ready".to_string(), Value::from(true))]),
                cardinality: GraphMutationCardinality::SingleIdentity,
            },
        ]))
        .await
        .expect("execute ordered mutation plan");

    assert_eq!(report.matched_rows, 1);
    let stored = store
        .get_node(&inserted.id)
        .await
        .expect("read ordered node")
        .expect("ordered node missing");
    assert_eq!(stored.props.get("ready"), Some(&Value::from(true)));

    let rollback_node = Node::new("Person", "must-roll-back", Props::new());
    let failed = store
        .execute_cypher_mutation_plan(&GraphMutationPlan::new(vec![
            GraphMutationPlanOp::UpsertNode {
                kind: GraphMutationPlanKind::Create,
                node: rollback_node.clone(),
            },
            GraphMutationPlanOp::UpsertEdge {
                kind: GraphMutationPlanKind::Create,
                edge: Edge::new(
                    "PRESENTS",
                    rollback_node.id.clone(),
                    "missing-endpoint",
                    Props::new(),
                ),
            },
        ]))
        .await;
    assert!(failed.is_err(), "the missing endpoint must reject the plan");
    assert!(
        store
            .get_node(&rollback_node.id)
            .await
            .expect("read after rollback")
            .is_none(),
        "a failed plan must roll back its valid prefix"
    );
}

#[tokio::test]
async fn next_call_rolls_back_an_abandoned_transaction() {
    let store = TursoGraphStore::in_memory()
        .await
        .expect("open Turso store");
    store.bootstrap().await.expect("bootstrap Turso tables");
    let cancelled_node = Node::new("Person", "cancelled-plan", Props::new());

    {
        let _gate = store.lock_connection().await.expect("lock connection");
        store
            .transaction_needs_rollback
            .store(true, Ordering::Release);
        store
            .execute_unlocked("BEGIN")
            .await
            .expect("begin simulated cancelled plan");
        store
            .execute_unlocked(
                &upsert_nodes_sql(&store.nodes_table(), std::slice::from_ref(&cancelled_node))
                    .expect("lower simulated cancelled write"),
            )
            .await
            .expect("write simulated cancelled prefix");
        // Dropping the gate while the recovery marker remains set simulates a
        // future being aborted after a successful statement but before COMMIT.
    }

    assert!(
        store
            .get_node(&cancelled_node.id)
            .await
            .expect("read after cancellation recovery")
            .is_none(),
        "the next caller must roll back an abandoned transaction"
    );
    assert!(
        !store.transaction_needs_rollback.load(Ordering::Acquire),
        "successful recovery must clear the transaction marker"
    );
}

#[tokio::test]
async fn mvcc_journal_mode_enables_concurrent_writes_and_round_trips() {
    // Unit: TursoJournalMode::Mvcc enables MVCC on a fresh database via
    // `PRAGMA journal_mode = mvcc` and supports `BEGIN CONCURRENT` writers.
    let path = std::env::temp_dir().join(format!("grust_turso_mvcc_{}.db", std::process::id()));
    let _ = std::fs::remove_file(&path);

    let config = TursoConfig {
        path: path.to_string_lossy().into_owned(),
        journal_mode: TursoJournalMode::Mvcc,
        ..TursoConfig::default()
    };
    let store = TursoGraphStore::connect(config)
        .await
        .expect("open MVCC Turso store");

    // MVCC is actually active — the engine reports the header mode.
    let mode = store
        .query_scalar_text("PRAGMA journal_mode")
        .await
        .expect("read journal_mode");
    assert_eq!(mode.as_deref(), Some("mvcc"));

    // The MVCC concurrent-writer transaction syntax is accepted.
    store
        .execute("BEGIN CONCURRENT")
        .await
        .expect("begin concurrent");
    store.execute("COMMIT").await.expect("commit concurrent");

    // End-to-end write/read works under MVCC.
    store.bootstrap().await.expect("bootstrap MVCC tables");
    let report = store.put_graph(&sample_graph()).await.expect("write graph");
    assert_eq!(report.nodes, 2);
    assert_eq!(report.edges, 1);
    let fetched = store
        .get_node(&NodeId::new("person-1"))
        .await
        .expect("read node")
        .expect("person node missing");
    assert_eq!(fetched.label, Label::new("Person"));

    let _ = std::fs::remove_file(&path);
}

#[tokio::test]
async fn default_journal_mode_is_wal() {
    // Default config leaves the engine in its WAL default (no MVCC).
    let store = TursoGraphStore::in_memory()
        .await
        .expect("open Turso store");
    let mode = store
        .query_scalar_text("PRAGMA journal_mode")
        .await
        .expect("read journal_mode");
    assert_eq!(mode.as_deref(), Some("wal"));
}

#[test]
fn is_mvcc_conflict_detects_retryable_errors() {
    // Retryable MVCC conflicts (engine LimboError Display strings).
    assert!(is_mvcc_conflict(&GrustError::Backend(
        "Turso command failed: Write-write conflict: BEGIN CONCURRENT".into()
    )));
    assert!(is_mvcc_conflict(&GrustError::Backend(
        "Database is busy".into()
    )));
    assert!(is_mvcc_conflict(&GrustError::Backend(
        "Conflict: busy snapshot".into()
    )));
    // Non-conflict errors are not retried.
    assert!(!is_mvcc_conflict(&GrustError::Backend(
        "near \"FROM\": syntax error".into()
    )));
}

#[tokio::test]
async fn mvcc_apply_mutations_batch_round_trips() {
    // The MVCC apply_mutations path runs the batch as one BEGIN CONCURRENT
    // transaction (via execute_concurrent) and round-trips.
    let path =
        std::env::temp_dir().join(format!("grust_turso_mvcc_batch_{}.db", std::process::id()));
    let _ = std::fs::remove_file(&path);
    let store = TursoGraphStore::connect(TursoConfig {
        path: path.to_string_lossy().into_owned(),
        journal_mode: TursoJournalMode::Mvcc,
        ..TursoConfig::default()
    })
    .await
    .expect("open MVCC store");
    store.bootstrap().await.expect("bootstrap");

    let muts = vec![
        GraphMutation::UpsertNode(Node::new("Person", "p1", Props::new())),
        GraphMutation::UpsertNode(Node::new("Person", "p2", Props::new())),
        GraphMutation::DeleteNode(NodeId::new("p1")),
    ];
    store
        .apply_mutations(&muts)
        .await
        .expect("mvcc batch apply");

    assert!(
        store
            .get_node(&NodeId::new("p1"))
            .await
            .expect("read p1")
            .is_none(),
        "p1 should have been deleted in the batch"
    );
    assert!(
        store
            .get_node(&NodeId::new("p2"))
            .await
            .expect("read p2")
            .is_some(),
        "p2 should have been upserted in the batch"
    );

    let _ = std::fs::remove_file(&path);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn mvcc_concurrent_writers_resolve_conflicts_via_retry() {
    // Two MVCC connections write overlapping keys concurrently; the BEGIN
    // CONCURRENT path's conflict retry makes both writers succeed (no surfaced
    // write-write conflict) and every key lands.
    let path = std::env::temp_dir().join(format!("grust_turso_conc_{}.db", std::process::id()));
    let _ = std::fs::remove_file(&path);
    let cfg = || TursoConfig {
        path: path.to_string_lossy().into_owned(),
        journal_mode: TursoJournalMode::Mvcc,
        ..TursoConfig::default()
    };

    let writer = TursoGraphStore::connect(cfg())
        .await
        .expect("open writer 1");
    writer.bootstrap().await.expect("bootstrap");
    let writer2 = TursoGraphStore::connect(cfg())
        .await
        .expect("open writer 2");

    let h1 = tokio::spawn(async move {
        for i in 0..10 {
            writer
                .put_node(&Node::new("Person", format!("k{i}"), Props::new()))
                .await
                .expect("writer 1 put");
        }
    });
    let h2 = tokio::spawn(async move {
        for i in 0..10 {
            writer2
                .put_node(&Node::new("Person", format!("k{i}"), Props::new()))
                .await
                .expect("writer 2 put");
        }
    });
    h1.await.expect("writer 1 task");
    h2.await.expect("writer 2 task");

    let verify = TursoGraphStore::connect(cfg()).await.expect("open verify");
    for i in 0..10 {
        assert!(
            verify
                .get_node(&NodeId::new(format!("k{i}")))
                .await
                .expect("read")
                .is_some(),
            "key k{i} missing after concurrent MVCC writers"
        );
    }
    let _ = std::fs::remove_file(&path);
}

#[tokio::test]
async fn resident_snapshot_reflects_the_store_and_every_write_drops_it() {
    let store = TursoGraphStore::in_memory().await.unwrap();
    store.bootstrap().await.unwrap();
    let mut builder = GraphBuilder::new();
    let a = builder.node("Person", "a").finish();
    let b = builder.node("Person", "b").finish();
    let c = builder.node("City", "c").finish();
    let _ = builder.edge("KNOWS", &a, &b).finish();
    let _ = builder.edge("LIVES_IN", &a, &c).finish();
    store.put_graph(&builder.build()).await.unwrap();

    let first = store.indexed_snapshot().await.unwrap();
    let again = store.indexed_snapshot().await.unwrap();
    assert!(
        std::sync::Arc::ptr_eq(&first, &again),
        "the snapshot is shared until a write"
    );
    let graph = store.read_graph().await.unwrap();
    assert_eq!(first.graph().nodes.len(), graph.nodes.len());
    assert_eq!(first.graph().edges.len(), graph.edges.len());
    let a_slot = first.vertex_index("a").expect("a is indexed");
    assert_eq!(first.outgoing(a_slot, "KNOWS").len(), 1);
    assert_eq!(first.outgoing(a_slot, "LIVES_IN").len(), 1);

    let edge = Edge::new("KNOWS", "b", "c", Props::default());
    store.put_edge(&edge).await.unwrap();
    let rebuilt = store.indexed_snapshot().await.unwrap();
    assert!(
        !std::sync::Arc::ptr_eq(&first, &rebuilt),
        "a write invalidates the snapshot"
    );
    assert_eq!(rebuilt.graph().edges.len(), 3);
    assert_eq!(
        first.graph().edges.len(),
        2,
        "an already returned snapshot stays immutable"
    );

    store
        .delete_edge(&"b".into(), &"KNOWS".into(), &"c".into())
        .await
        .unwrap();
    let after_delete = store.indexed_snapshot().await.unwrap();
    assert_eq!(after_delete.graph().edges.len(), 2);
}

#[tokio::test]
async fn mvcc_put_graph_commits_in_groups_and_keeps_every_row() {
    let config = TursoConfig {
        journal_mode: TursoJournalMode::Mvcc,
        batch_size: 7,
        ..TursoConfig::default()
    };
    let store = TursoGraphStore::connect(config).await.unwrap();
    store.bootstrap().await.unwrap();
    // Enough batches to span several commit groups.
    let n = 7 * MVCC_LOAD_COMMIT_STATEMENTS * 3 + 5;
    let nodes: Vec<_> = (0..=n)
        .map(|i| Node::new("N", format!("n{i}"), Props::new()))
        .collect();
    let edges: Vec<_> = (0..n)
        .map(|i| Edge::new("E", format!("n{i}"), format!("n{}", i + 1), Props::new()))
        .collect();
    let report = store.put_graph(&Graph::new(nodes, edges)).await.unwrap();
    assert_eq!(report.edges, n);
    let all = store.get_edges(EdgeQuery::default()).await.unwrap();
    assert_eq!(all.len(), n);
}

fn weight(v: i64) -> Props {
    let mut props = Props::new();
    props.insert("v".into(), Value::Int(v));
    props
}

/// A load whose later rows rewrite earlier ones: a re-put node, repeated
/// id-less edges between one pair, and edges whose ids are missing, empty,
/// plain and prefix-like, one of them re-put.
fn rewriting_graph() -> Graph {
    let nodes = vec![
        Node::new("A", "n1", weight(1)),
        Node::new("A", "n2", Props::new()),
        Node::new("B", "n3", Props::new()),
        Node::new("C", "n1", weight(2)),
    ];
    let edges = vec![
        Edge::new("E", "n1", "n2", weight(1)),
        Edge::new("E", "n1", "n2", weight(2)),
        Edge::new("E", "n1", "n2", weight(3)).with_id(""),
        Edge::new("E", "n1", "n2", weight(4)).with_id("a"),
        Edge::new("E", "n1", "n2", weight(5)).with_id("id:a"),
        Edge::new("E", "n1", "n2", weight(6)).with_id("a"),
        Edge::new("F", "n2", "n3", Props::new()),
        Edge::new("E", "n3", "n1", weight(7)),
        Edge::new("E", "n3", "n1", weight(8)),
    ];
    Graph::new(nodes, edges)
}

async fn raw_rows(store: &TursoGraphStore) -> Vec<Vec<Option<String>>> {
    let mut rows = store
        .run_text_rows(
            &format!(
                "SELECT id, label, props FROM {} ORDER BY id",
                store.nodes_table()
            ),
            3,
        )
        .await
        .unwrap();
    rows.extend(
        store
            .run_text_rows(
                &format!(
                    "SELECT id, from_id, to_id, label, props, identity_key FROM {}
                     ORDER BY from_id, label, to_id, identity_key",
                    store.edges_table()
                ),
                6,
            )
            .await
            .unwrap(),
    );
    rows
}

#[tokio::test]
async fn prepared_bulk_load_writes_exactly_the_rows_of_the_sql_text_upserts() {
    for journal_mode in [TursoJournalMode::Wal, TursoJournalMode::Mvcc] {
        for batch_size in [2, 500] {
            let config = TursoConfig {
                journal_mode,
                batch_size,
                ..TursoConfig::default()
            };
            let graph = rewriting_graph();

            let prepared = TursoGraphStore::connect(config.clone()).await.unwrap();
            prepared.bootstrap().await.unwrap();
            prepared.put_graph(&graph).await.unwrap();

            let text = TursoGraphStore::connect(config).await.unwrap();
            text.bootstrap().await.unwrap();
            let mut statements = Vec::new();
            for chunk in graph.nodes.chunks(batch_size) {
                statements.push(upsert_nodes_sql(&text.nodes_table(), chunk).unwrap());
            }
            for chunk in graph.edges.chunks(batch_size) {
                statements.push(upsert_edges_sql(&text.edges_table(), chunk).unwrap());
            }
            text.execute_transaction(&statements, journal_mode == TursoJournalMode::Mvcc)
                .await
                .unwrap();

            let expected = raw_rows(&text).await;
            assert_eq!(
                raw_rows(&prepared).await,
                expected,
                "{journal_mode:?} batch {batch_size}"
            );
            // Three nodes, then the edges: one id-less n1->n2, ids "", "a",
            // "id:a", the F edge and one id-less n3->n1.
            assert_eq!(expected.len(), 3 + 6, "{journal_mode:?} batch {batch_size}");
        }
    }
}
