use super::*;
use grust_core::Value;

#[test]
fn storage_preserves_complex_properties_and_explicit_empty_ids() {
    let props = Props::from([("list".into(), Value::IntArray(vec![i64::MIN, i64::MAX]))]);
    let nodes = vec![Node::new("N", "α", props.clone())];
    assert_eq!(
        nodes_from_batch(&nodes_to_batch(&nodes).unwrap()).unwrap(),
        nodes
    );
    let edges = vec![Edge::new("E", "α", "α", props).with_id("")];
    assert_eq!(
        edges_from_batch(&edges_to_batch(&edges).unwrap()).unwrap(),
        edges
    );
}

#[test]
fn storage_rejects_null_identity_and_forged_edge_keys() {
    let schema = Arc::new(Schema::new(vec![
        Field::new("id", DataType::Utf8, true),
        Field::new("label", DataType::Utf8, false),
        Field::new("props", DataType::Utf8, false),
    ]));
    let batch = RecordBatch::try_new(
        schema,
        vec![
            Arc::new(StringArray::from(vec![None::<&str>])),
            Arc::new(StringArray::from(vec!["N"])),
            Arc::new(StringArray::from(vec!["{}"])),
        ],
    )
    .unwrap();
    assert!(matches!(
        nodes_from_batch(&batch),
        Err(GrustError::Serialization(_))
    ));
    let valid = edges_to_batch(&[Edge::new("E", "a", "b", Props::new())]).unwrap();
    let mut columns = valid.columns().to_vec();
    columns[0] = Arc::new(StringArray::from(vec!["forged"]));
    let invalid = RecordBatch::try_new(valid.schema(), columns).unwrap();
    assert!(matches!(
        edges_from_batch(&invalid),
        Err(GrustError::Serialization(_))
    ));
}
