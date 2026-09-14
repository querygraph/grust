use super::*;
use datafusion::{
    arrow::{array::StringArray, datatypes::Field, record_batch::RecordBatch},
    datasource::MemTable,
    execution::context::SessionContext,
};
use std::sync::Arc;

#[tokio::test]
async fn output_limits_count_complete_json_across_batches() {
    let schema = Arc::new(Schema::new(vec![Field::new("x", DataType::Utf8, true)]));
    let batches = [vec![Some("λ\n\"")], vec![None], vec![Some("")]]
        .into_iter()
        .map(|values| {
            RecordBatch::try_new(
                Arc::clone(&schema),
                vec![Arc::new(StringArray::from(values))],
            )
            .unwrap()
        })
        .collect::<Vec<_>>();
    let context = SessionContext::new_with_config(
        datafusion::execution::context::SessionConfig::new().with_batch_size(1),
    );
    let input = context
        .read_table(Arc::new(MemTable::try_new(schema, vec![batches]).unwrap()))
        .unwrap();
    use futures::TryStreamExt;
    let chunks = input
        .clone()
        .execute_stream()
        .await
        .unwrap()
        .try_collect::<Vec<_>>()
        .await
        .unwrap();
    assert!(
        chunks.len() > 1,
        "exercise cumulative accounting across emitted batches"
    );
    let expected_rows = vec![
        vec![Value::String("λ\n\"".into())],
        vec![Value::Null],
        vec![Value::String("".into())],
    ];
    let encoded =
        serde_json::to_vec(&serde_json::json!({"columns": ["x"], "rows": expected_rows})).unwrap();
    let result = collect_result(input.clone(), 3, encoded.len())
        .await
        .unwrap();
    assert_eq!(result.columns, ["x"]);
    assert_eq!(result.rows, expected_rows);
    assert!(
        collect_result(input.clone(), 3, encoded.len() - 1)
            .await
            .is_err()
    );
    assert!(collect_result(input.clone(), 2, usize::MAX).await.is_err());
    let empty = input.limit(0, Some(0)).unwrap();
    let empty_bytes = serde_json::to_vec(&serde_json::json!({"columns": ["x"], "rows": []}))
        .unwrap()
        .len();
    assert!(
        collect_result(empty.clone(), 0, empty_bytes)
            .await
            .unwrap()
            .rows
            .is_empty()
    );
    assert!(collect_result(empty, 0, empty_bytes - 1).await.is_err());
}
