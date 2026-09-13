use super::*;
use grust_core::{Edge, Graph, Node, Props};

fn registry() -> ProcedureRegistry {
    let mut builder = RegistryBuilder::default();
    register_builtins(&mut builder).expect("built-in definitions are valid");
    builder.build()
}

fn collect(name: &str, args: Vec<Value>, graph: Option<&Graph>, batch_rows: usize) -> Vec<Value> {
    let registry = registry();
    let procedure = registry.resolve(name).expect("built-in exists");
    let execution = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 16 * 1024,
        work_units: 1000,
        batch_rows,
        deadline: None,
    })
    .expect("limits");
    let identity = SnapshotIdentity::new("test".into(), "v1".into(), "reader".into()).unwrap();
    let mut cursor = procedure
        .open(
            args,
            Invocation {
                snapshot: graph.map(|graph| LocalSnapshot::new(graph, &identity)),
                cache: None,
                execution: &execution,
            },
        )
        .expect("valid invocation");
    let mut values = Vec::new();
    while let Some(batch) = cursor.next_batch().expect("valid batch") {
        assert!(batch.rows().len() <= batch_rows);
        values.extend(batch.rows().iter().map(|row| row[0].clone()));
    }
    assert_eq!(execution.usage().expect("usage").live_bytes, 0);
    values
}

#[test]
fn range_answers_are_independent_of_batch_size() {
    for batch_rows in [1, 2, 3, 32] {
        for (args, expected) in [
            (vec![0, 5], vec![0, 1, 2, 3, 4, 5]),
            (vec![5, 0, -2], vec![5, 3, 1]),
            (vec![0, 5, -1], vec![]),
            (vec![5, 0], vec![]),
            (vec![i64::MAX - 1, i64::MAX], vec![i64::MAX - 1, i64::MAX]),
            (vec![0, i64::MIN, i64::MIN], vec![0, i64::MIN]),
        ] {
            assert_eq!(
                collect(
                    "TVF.RANGE",
                    args.into_iter().map(Value::Int).collect(),
                    None,
                    batch_rows
                ),
                expected.into_iter().map(Value::Int).collect::<Vec<_>>()
            );
        }
    }
}

#[test]
fn range_full_integer_domain_can_be_dropped_after_one_bounded_batch() {
    let registry = registry();
    let procedure = registry.resolve("tvf.range").expect("range");
    let execution = context(1024);
    let mut cursor = procedure
        .open(
            vec![Value::Int(i64::MIN), Value::Int(i64::MAX)],
            Invocation {
                snapshot: None,
                cache: None,
                execution: &execution,
            },
        )
        .expect("bounded cursor");
    let batch = cursor
        .next_batch()
        .expect("first batch")
        .expect("not empty");
    assert_eq!(
        batch.rows(),
        &[vec![Value::Int(i64::MIN)], vec![Value::Int(i64::MIN + 1)]]
    );
    drop(cursor);
    assert!(execution.usage().expect("usage").live_bytes > 0);
    drop(batch);
    assert_eq!(execution.usage().expect("usage").live_bytes, 0);
}

#[test]
fn range_zero_step_is_an_error_before_consumption() {
    let registry = registry();
    let procedure = registry.resolve("tvf.range").expect("range");
    let execution = context(4096);
    assert!(matches!(
        procedure.open(
            vec![Value::Int(0), Value::Int(1), Value::Int(0)],
            Invocation {
                snapshot: None,
                cache: None,
                execution: &execution
            }
        ),
        Err(ProcedureError::InvalidArguments(_))
    ));
}

#[test]
fn catalog_keeps_sorted_distinct_labels_types_and_property_keys() {
    let graph = Graph::new(
        vec![
            Node::new("Z", "a", Props::from([("z".into(), Value::Null)])),
            Node::new("A", "b", Props::from([("a".into(), Value::Int(1))])),
            Node::new("Z", "c", Props::new()),
        ],
        vec![
            Edge::new("LOOP", "a", "a", Props::from([("a".into(), Value::Int(2))])),
            Edge::new("LINK", "a", "b", Props::new()),
        ],
    );
    for batch in [1, 3, 32] {
        assert_eq!(
            collect("db.labels", vec![], Some(&graph), batch),
            vec![Value::from("A"), Value::from("Z")]
        );
        assert_eq!(
            collect("db.relationshipTypes", vec![], Some(&graph), batch),
            vec![Value::from("LINK"), Value::from("LOOP")]
        );
        assert_eq!(
            collect("db.propertyKeys", vec![], Some(&graph), batch),
            vec![Value::from("a"), Value::from("id"), Value::from("z")]
        );
    }
}

#[test]
fn keys_preserves_existing_null_and_serialized_element_semantics() {
    for batch in [1, 3] {
        assert!(collect("tvf.keys", vec![Value::Null], None, batch).is_empty());
        assert_eq!(
            collect(
                "tvf.keys",
                vec![Value::Json(serde_json::json!({"z": null, "a": 1}))],
                None,
                batch
            ),
            vec![Value::from("a"), Value::from("z")]
        );
        assert_eq!(
            collect(
                "tvf.keys",
                vec![Value::Json(
                    serde_json::json!({"id": "n", "props": {"x": null}})
                )],
                None,
                batch
            ),
            vec![Value::from("x")]
        );
    }
}

#[test]
fn graph_free_catalog_invocation_is_explicitly_unsupported() {
    let registry = registry();
    let procedure = registry.resolve("db.labels").expect("catalog");
    let execution = context(4096);
    assert!(matches!(
        procedure.open(
            vec![],
            Invocation {
                snapshot: None,
                cache: None,
                execution: &execution
            }
        ),
        Err(ProcedureError::Unsupported(_))
    ));
}
