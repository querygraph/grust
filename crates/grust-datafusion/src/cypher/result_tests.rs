use super::*;
use datafusion::arrow::{
    array::{ArrayRef, BooleanArray, Float64Array, Int64Array, NullArray, StringArray},
    datatypes::Field,
    record_batch::RecordBatch,
};
use std::sync::Arc;

#[test]
fn decoding_preserves_names_nulls_and_exact_scalar_values() {
    let arrays: Vec<ArrayRef> = vec![
        Arc::new(Int64Array::from(vec![Some(i64::MIN), Some(i64::MAX), None])),
        Arc::new(StringArray::from(vec![Some(""), Some("λ\n\""), None])),
        Arc::new(BooleanArray::from(vec![Some(true), Some(false), None])),
        Arc::new(NullArray::new(3)),
    ];
    let schema = Arc::new(Schema::new(
        arrays
            .iter()
            .map(|array| Field::new("duplicate.name", array.data_type().clone(), true))
            .collect::<Vec<_>>(),
    ));
    let batch = RecordBatch::try_new(schema, arrays).unwrap();
    let table = decode_result_batch(&batch).unwrap();
    assert_eq!(table.columns, vec!["duplicate.name"; 4]);
    assert_eq!(
        table.rows,
        vec![
            vec![
                Value::Int(i64::MIN),
                Value::String("".into()),
                Value::Bool(true),
                Value::Null
            ],
            vec![
                Value::Int(i64::MAX),
                Value::String("λ\n\"".into()),
                Value::Bool(false),
                Value::Null
            ],
            vec![Value::Null; 4],
        ]
    );
    let sliced = decode_result_batch(&batch.slice(1, 1)).unwrap();
    assert_eq!(sliced.rows, vec![table.rows[1].clone()]);
    let empty = decode_result_batch(&batch.slice(0, 0)).unwrap();
    assert_eq!(empty.columns, table.columns);
    assert!(empty.rows.is_empty());
}

#[test]
fn decoding_does_not_coerce_unsupported_result_types() {
    let batch = RecordBatch::try_new(
        Arc::new(Schema::new(vec![Field::new(
            "value",
            DataType::Float64,
            true,
        )])),
        vec![Arc::new(Float64Array::from(vec![1.5]))],
    )
    .unwrap();
    assert!(decode_result_batch(&batch).is_err());
}

#[test]
fn admitted_decoding_charges_only_the_slice_and_retains_cumulative_usage() {
    use grust_procedures::{ExecutionContext, ExecutionLimits};
    let batch = RecordBatch::try_new(
        Arc::new(Schema::new(vec![Field::new("s", DataType::Utf8, true)])),
        vec![Arc::new(StringArray::from(vec![
            Some("outside"),
            Some("λ"),
            None,
            Some(""),
        ]))],
    )
    .unwrap()
    .slice(1, 3);
    let bytes = std::mem::size_of::<String>()
        + 1
        + 3 * (std::mem::size_of::<Vec<Value>>() + std::mem::size_of::<Value>())
        + 2;
    let context = |memory_bytes| {
        ExecutionContext::new(ExecutionLimits {
            memory_bytes,
            work_units: 0,
            batch_rows: 1024,
            deadline: None,
        })
        .unwrap()
    };
    let exact = context(bytes);
    let table = decode_result_batch_with_context(&batch, &exact).unwrap();
    assert_eq!(table, decode_result_batch(&batch).unwrap());
    drop(table);
    assert!(decode_result_batch_with_context(&batch, &exact).is_err());
    assert!(decode_result_batch_with_context(&batch, &context(bytes - 1)).is_err());
    let cancelled = context(bytes);
    cancelled.cancel().unwrap();
    assert!(decode_result_batch_with_context(&batch, &cancelled).is_err());
}
