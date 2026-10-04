//! Real Parquet bytes through Sail's metadata and scan boundary. This module
//! deliberately does not call the mitigation helper, so it also runs unchanged
//! against the parent revision as a regression reproduction.
use std::sync::Arc;

use bytes::Bytes;
use datafusion::arrow::array::{Array, ArrayRef, Float64Array, Int64Array};
use datafusion::arrow::compute::{cast, concat};
use datafusion::arrow::datatypes::{DataType, Field, Schema};
use datafusion::arrow::record_batch::RecordBatch;
use datafusion::execution::context::SessionContext;
use datafusion::execution::object_store::ObjectStoreUrl;
use datafusion::parquet::arrow::ArrowWriter;
use datafusion::parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use datafusion::physical_plan::collect;
use datafusion_common::parsers::CompressionTypeVariant;
use datafusion_common::stats::Precision;
use datafusion_common::{Constraints, ScalarValue};
use datafusion_datasource::file_groups::FileGroup;
use datafusion_datasource::source::DataSourceExec;
use datafusion_datasource::{PartitionedFile, TableSchema};
use object_store::memory::InMemory;
use object_store::path::Path;
use object_store::{ObjectStore, ObjectStoreExt};

use super::ParquetFormatFactory;
use crate::listing::source::{FormatFactory, ListingScanInput, ReadFormat};

async fn roundtrip(input: ArrayRef) -> (ArrayRef, datafusion_common::Statistics) {
    let schema = Arc::new(Schema::new(vec![Field::new(
        "value",
        input.data_type().clone(),
        true,
    )]));
    let batch = RecordBatch::try_new(Arc::clone(&schema), vec![Arc::clone(&input)]).unwrap();
    let mut bytes = Vec::new();
    let mut writer = ArrowWriter::try_new(&mut bytes, Arc::clone(&schema), None).unwrap();
    writer.write(&batch).unwrap();
    writer.close().unwrap();
    let bytes = Bytes::from(bytes);
    // Independent decoder proves the writer retained the input values.
    let decoded = ParquetRecordBatchReaderBuilder::try_new(bytes.clone())
        .unwrap()
        .build()
        .unwrap()
        .collect::<Result<Vec<_>, _>>()
        .unwrap();
    let decoded = concat(
        &decoded
            .iter()
            .map(|b| b.column(0).as_ref())
            .collect::<Vec<_>>(),
    )
    .unwrap();
    assert_values(&input, &decoded);

    let ctx = SessionContext::new();
    let state = ctx.state();
    let store: Arc<dyn ObjectStore> = Arc::new(InMemory::new());
    let path = Path::from("values.parquet");
    store.put(&path, bytes.into()).await.unwrap();
    let object = store.head(&path).await.unwrap();
    let url = ObjectStoreUrl::parse("memory://float-statistics").unwrap();
    ctx.runtime_env()
        .register_object_store(url.as_ref(), Arc::clone(&store));
    let format = ParquetFormatFactory::read(&state, vec![]).unwrap();
    let meta = format
        .infer_file_meta(
            &state,
            &store,
            &object,
            Arc::clone(&schema),
            CompressionTypeVariant::UNCOMPRESSED,
        )
        .await
        .unwrap();
    let statistics = meta.statistics;
    let file = PartitionedFile::from(object).with_statistics(Arc::new(statistics.clone()));
    let config = format
        .scan(
            &state,
            ListingScanInput {
                object_store_url: url,
                file_groups: vec![FileGroup::new(vec![file])],
                constraints: Constraints::default(),
                projection: Some(vec![0]),
                limit: None,
                preserve_order: false,
                output_ordering: vec![],
                statistics: statistics.clone(),
                output_partitioning: None,
                schema: TableSchema::builder(schema).build(),
                compression: CompressionTypeVariant::UNCOMPRESSED,
            },
        )
        .await
        .unwrap();
    let output = collect(DataSourceExec::from_data_source(config), ctx.task_ctx())
        .await
        .unwrap();
    let output = concat(
        &output
            .iter()
            .map(|b| b.column(0).as_ref())
            .collect::<Vec<_>>(),
    )
    .unwrap();
    (output, statistics)
}

fn assert_values(expected: &ArrayRef, actual: &ArrayRef) {
    assert_eq!(expected.len(), actual.len());
    assert_eq!(expected.data_type(), actual.data_type());
    // Widen floats (and dictionary floats) to compare NaNs and signed zero.
    let expected = cast(expected, &DataType::Float64).unwrap();
    let actual = cast(actual, &DataType::Float64).unwrap();
    let expected = expected.as_any().downcast_ref::<Float64Array>().unwrap();
    let actual = actual.as_any().downcast_ref::<Float64Array>().unwrap();
    for i in 0..expected.len() {
        assert_eq!(expected.is_null(i), actual.is_null(i), "row {i}");
        if expected.is_valid(i) {
            if expected.value(i).is_nan() {
                assert!(
                    actual.value(i).is_nan(),
                    "row {i}: NaN became {}",
                    actual.value(i)
                );
            } else {
                assert_eq!(
                    expected.value(i).to_bits(),
                    actual.value(i).to_bits(),
                    "row {i}"
                );
            }
        }
    }
}

#[tokio::test]
async fn parquet_float_values_survive_statistics() {
    for data_type in [DataType::Float16, DataType::Float32, DataType::Float64] {
        for values in [
            vec![Some(f64::NAN), Some(0.5)],
            vec![Some(0.5), Some(f64::NAN)],
            vec![Some(0.5), Some(0.5)],
            vec![Some(-0.0), Some(0.0)],
            vec![Some(0.5), None],
            vec![None, None],
        ] {
            let input = cast(&Float64Array::from(values), &data_type).unwrap();
            let (actual, statistics) = roundtrip(Arc::clone(&input)).await;
            assert_values(&input, &actual);
            assert_eq!(statistics.num_rows, Precision::Exact(2));
            assert_eq!(
                statistics.column_statistics[0].null_count,
                Precision::Exact(input.null_count())
            );
        }
    }
}

#[tokio::test]
async fn parquet_dictionary_float_values_survive_statistics() {
    for value_type in [DataType::Float16, DataType::Float32, DataType::Float64] {
        let data_type = DataType::Dictionary(Box::new(DataType::Int32), Box::new(value_type));
        let input = cast(
            &Float64Array::from(vec![Some(f64::NAN), Some(0.5), None]),
            &data_type,
        )
        .unwrap();
        let (actual, _) = roundtrip(Arc::clone(&input)).await;
        assert_values(&input, &actual);
    }
}

#[tokio::test]
async fn parquet_integer_bounds_and_all_null_counts_survive() {
    let input: ArrayRef = Arc::new(Int64Array::from(vec![7, 7]));
    let (actual, statistics) = roundtrip(Arc::clone(&input)).await;
    assert_eq!(actual.as_ref(), input.as_ref());
    assert_eq!(
        statistics.column_statistics[0].min_value,
        Precision::Exact(ScalarValue::Int64(Some(7)))
    );
    assert_eq!(
        statistics.column_statistics[0].max_value,
        Precision::Exact(ScalarValue::Int64(Some(7)))
    );
    let input: ArrayRef = Arc::new(Float64Array::from(vec![None, None]));
    let (actual, statistics) = roundtrip(input).await;
    assert_eq!(actual.null_count(), 2);
    assert_eq!(statistics.num_rows, Precision::Exact(2));
    assert_eq!(
        statistics.column_statistics[0].null_count,
        Precision::Exact(2)
    );
}
