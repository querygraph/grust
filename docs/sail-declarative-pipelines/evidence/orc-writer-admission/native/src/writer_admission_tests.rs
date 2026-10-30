use std::io::{self, Write};
use std::sync::{
    atomic::{AtomicUsize, Ordering},
    Arc,
};

use arrow::array::{ArrayRef, BooleanArray, Int64Array, RecordBatch, StringArray};
use arrow::datatypes::{DataType, Field, Schema, TimeUnit};
use bytes::Bytes;

use super::ArrowWriterBuilder;
use crate::ArrowReaderBuilder;

struct CountWrites(Arc<AtomicUsize>);

impl Write for CountWrites {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        self.0.fetch_add(1, Ordering::SeqCst);
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

#[test]
fn rejects_unsupported_later_field_before_any_output() {
    for data_type in [
        DataType::Null,
        DataType::UInt8,
        DataType::UInt16,
        DataType::UInt32,
        DataType::UInt64,
        DataType::Decimal128(12, 2),
        DataType::List(Arc::new(Field::new("item", DataType::Int64, true))),
        DataType::Struct(vec![Field::new("child", DataType::Utf8, true)].into()),
        DataType::Timestamp(TimeUnit::Microsecond, Some("America/New_York".into())),
        DataType::Timestamp(TimeUnit::Microsecond, Some("Etc/UTC".into())),
        DataType::Time64(TimeUnit::Nanosecond),
    ] {
        let calls = Arc::new(AtomicUsize::new(0));
        let schema = Arc::new(Schema::new(vec![
            Field::new("valid", DataType::Int64, true),
            Field::new("rejected", data_type.clone(), true),
        ]));
        let error = ArrowWriterBuilder::new(CountWrites(calls.clone()), schema)
            .try_build()
            .err()
            .expect("unsupported field must return an error");
        assert!(error.to_string().contains("rejected"));
        assert!(error.to_string().contains(&format!("{data_type:?}")));
        assert_eq!(calls.load(Ordering::SeqCst), 0);
    }
}

#[test]
fn rejects_zero_batch_size_before_any_output() {
    let calls = Arc::new(AtomicUsize::new(0));
    let schema = Arc::new(Schema::new(vec![Field::new("id", DataType::Int64, true)]));
    let error = ArrowWriterBuilder::new(CountWrites(calls.clone()), schema)
        .with_batch_size(0)
        .try_build()
        .err()
        .expect("zero batch size must return an error");
    assert!(error.to_string().contains("batch size"));
    assert_eq!(calls.load(Ordering::SeqCst), 0);
}

#[test]
fn admitted_physical_types_can_finish_an_empty_file() {
    let mut types = vec![
        DataType::Float32,
        DataType::Float64,
        DataType::Int8,
        DataType::Int16,
        DataType::Int32,
        DataType::Int64,
        DataType::Date32,
        DataType::Utf8,
        DataType::LargeUtf8,
        DataType::Binary,
        DataType::LargeBinary,
        DataType::Boolean,
    ];
    for unit in [
        TimeUnit::Second,
        TimeUnit::Millisecond,
        TimeUnit::Microsecond,
        TimeUnit::Nanosecond,
    ] {
        types.push(DataType::Timestamp(unit, None));
        types.push(DataType::Timestamp(unit, Some("UTC".into())));
    }
    for data_type in types {
        let schema = Arc::new(Schema::new(vec![Field::new("value", data_type, true)]));
        let mut bytes = vec![];
        ArrowWriterBuilder::new(&mut bytes, schema)
            .try_build()
            .unwrap()
            .close()
            .unwrap();
        let batches = ArrowReaderBuilder::try_new(Bytes::from(bytes))
            .unwrap()
            .build()
            .collect::<std::result::Result<Vec<_>, _>>()
            .unwrap();
        assert_eq!(batches.iter().map(RecordBatch::num_rows).sum::<usize>(), 0);
    }
}

#[test]
fn admitted_nullable_batches_survive_multiple_stripes() {
    let schema = Arc::new(Schema::new(vec![
        Field::new("id", DataType::Int64, true),
        Field::new("name", DataType::Utf8, true),
        Field::new("flag", DataType::Boolean, true),
    ]));
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            Arc::new(Int64Array::from(vec![Some(7), None, Some(-9)])) as ArrayRef,
            Arc::new(StringArray::from(vec![Some("alpha"), None, Some("beta")])),
            Arc::new(BooleanArray::from(vec![Some(true), Some(false), None])),
        ],
    )
    .unwrap();
    let mut bytes = vec![];
    let mut writer = ArrowWriterBuilder::new(&mut bytes, schema.clone())
        .with_batch_size(1)
        .with_stripe_byte_size(1)
        .try_build()
        .unwrap();
    writer.write(&batch).unwrap();
    writer.write(&batch).unwrap();
    writer.close().unwrap();
    let actual = ArrowReaderBuilder::try_new(Bytes::from(bytes))
        .unwrap()
        .build()
        .collect::<std::result::Result<Vec<_>, _>>()
        .unwrap();
    let actual = arrow::compute::concat_batches(&schema, actual.iter()).unwrap();
    let expected = arrow::compute::concat_batches(&schema, [&batch, &batch]).unwrap();
    assert_eq!(actual, expected);
}
