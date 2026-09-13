use grust_algorithm_procedures::register_algorithms;
use grust_core::{Edge, Graph, Node, Props, Value};
use grust_procedures::{
    ExecutionContext, ExecutionLimits, Invocation, InvocationCache, LocalSnapshot,
    ProcedureRegistry, RegistryBuilder, SnapshotIdentity,
};

fn distance(
    registry: &ProcedureRegistry,
    snapshot: LocalSnapshot<'_>,
    context: &ExecutionContext,
    cache: &InvocationCache,
    source: &str,
    options: serde_json::Value,
) -> Option<f64> {
    let procedure = registry.resolve("grust.algorithms.bfs").unwrap();
    let mut cursor = procedure
        .open(
            vec![Value::String(source.into()), Value::Json(options)],
            Invocation {
                snapshot: Some(snapshot),
                cache: Some(cache),
                execution: context,
            },
        )
        .unwrap();
    let mut result = None;
    while let Some(batch) = cursor.next_batch().unwrap() {
        for row in batch.rows() {
            if matches!(&row[0], Value::String(id) if id == "b") {
                result = match row[1] {
                    Value::Float(value) => Some(value),
                    Value::Null => None,
                    _ => panic!("distance schema"),
                };
            }
        }
    }
    result
}

#[test]
fn projection_reuse_preserves_correlation_options_revision_and_principal() {
    let graph = Graph::new(
        vec![
            Node::new("N", "a", Props::new()),
            Node::new("N", "b", Props::new()),
        ],
        vec![Edge::new("R", "a", "b", Props::new())],
    );
    let context = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 128 * 1024,
        work_units: usize::MAX,
        batch_rows: 2,
        deadline: None,
    })
    .unwrap();
    let cache = InvocationCache::new(context.clone());
    let mut builder = RegistryBuilder::default();
    register_algorithms(&mut builder).unwrap();
    let registry = builder.build();
    let identity = SnapshotIdentity::new("g".into(), "r1".into(), "reader-one".into()).unwrap();
    let snapshot = LocalSnapshot::new(&graph, &identity);
    assert_eq!(
        distance(
            &registry,
            snapshot,
            &context,
            &cache,
            "a",
            serde_json::json!({})
        ),
        Some(1.0)
    );
    let first = context.usage().unwrap();
    assert_eq!(
        distance(
            &registry,
            snapshot,
            &context,
            &cache,
            "b",
            serde_json::json!({})
        ),
        Some(0.0)
    );
    let second = context.usage().unwrap();
    assert_eq!(first.live_bytes, second.live_bytes);
    assert!(second.work_units - first.work_units < first.work_units);
    assert_eq!(
        distance(
            &registry,
            snapshot,
            &context,
            &cache,
            "a",
            serde_json::json!({"orientation": "incoming"})
        ),
        None
    );
    assert!(context.usage().unwrap().live_bytes > second.live_bytes);
    for (revision, principal) in [("r2", "reader-one"), ("r1", "reader-two")] {
        let identity =
            SnapshotIdentity::new("g".into(), revision.into(), principal.into()).unwrap();
        let before = context.usage().unwrap().live_bytes;
        assert_eq!(
            distance(
                &registry,
                LocalSnapshot::new(&graph, &identity),
                &context,
                &cache,
                "a",
                serde_json::json!({})
            ),
            Some(1.0)
        );
        assert!(context.usage().unwrap().live_bytes > before);
    }
    drop(cache);
    assert_eq!(context.usage().unwrap().live_bytes, 0);
}
