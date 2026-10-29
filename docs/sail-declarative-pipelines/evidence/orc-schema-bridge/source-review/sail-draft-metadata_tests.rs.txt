#![expect(clippy::unwrap_used)]

use std::collections::HashMap;

use arrow::array::{Int32Array, Int64Array, PrimitiveArray, StringArray};
use arrow::buffer::{NullBuffer, OffsetBuffer};
use arrow::datatypes::{
    ArrowPrimitiveType, DurationMicrosecondType, IntervalUnit, IntervalYearMonthType, Schema,
    Time64NanosecondType, TimestampMicrosecondType,
};
use sail_common::spec;

use super::*;

fn bridge(physical: Vec<Field>, logical: Vec<Field>) -> OrcSchemaBridge {
    OrcSchemaBridge {
        physical: Arc::new(Schema::new(physical)),
        logical: Arc::new(Schema::new(logical)),
    }
}

fn time_field(name: &str, precision: i32) -> Field {
    Field::new(name, DataType::Time64(TimeUnit::Nanosecond), true).with_metadata(HashMap::from([(
        spec::SAIL_SPARK_TIME_METADATA_KEY.to_string(),
        spec::SparkTimeMetadata::try_new(precision)
            .unwrap()
            .to_json()
            .unwrap(),
    )]))
}

fn interval_field(name: &str, interval: spec::SparkIntervalMetadata) -> Field {
    let data_type = match interval {
        spec::SparkIntervalMetadata::YearMonth { .. } => {
            DataType::Interval(IntervalUnit::YearMonth)
        }
        spec::SparkIntervalMetadata::DayTime { .. } => DataType::Duration(TimeUnit::Microsecond),
    };
    Field::new(name, data_type, true).with_metadata(HashMap::from([(
        spec::SAIL_SPARK_INTERVAL_METADATA_KEY.to_string(),
        interval.to_json().unwrap(),
    )]))
}

fn values<T: ArrowPrimitiveType>(array: &ArrayRef) -> Vec<Option<T::Native>> {
    array
        .as_any()
        .downcast_ref::<PrimitiveArray<T>>()
        .unwrap()
        .iter()
        .collect()
}

#[test]
fn time_preserves_nanoseconds_and_nulls_for_every_declared_precision() -> Result<()> {
    // Fractions are deliberately present even for TIME(0): the declaration
    // must not truncate the actual nanoseconds written by Spark's string cast.
    let expected = vec![
        Some(3_723_123_456_789),
        None,
        Some(0),
        Some(86_399_999_999_999),
    ];
    for precision in 0..=6 {
        let logical = time_field("t", precision);
        let bridge = bridge(
            vec![Field::new("t", DataType::Int64, true)],
            vec![logical.clone()],
        );
        let input = RecordBatch::try_new(
            bridge.physical.clone(),
            vec![Arc::new(Int64Array::from(expected.clone()))],
        )?;
        let output = bridge.adapt_batch(input)?;
        assert_eq!(values::<Time64NanosecondType>(output.column(0)), expected);
        assert_eq!(output.schema().field(0), &logical);
        assert_eq!(output.num_rows(), 4);
    }
    Ok(())
}

#[test]
fn ntz_and_intervals_preserve_native_values_and_qualifiers() -> Result<()> {
    let year_month = interval_field(
        "ym",
        spec::SparkIntervalMetadata::YearMonth {
            start_field: spec::YearMonthIntervalField::Year,
            end_field: spec::YearMonthIntervalField::Month,
        },
    );
    let day_time = interval_field(
        "dt",
        spec::SparkIntervalMetadata::DayTime {
            start_field: spec::DayTimeIntervalField::Hour,
            end_field: spec::DayTimeIntervalField::Second,
        },
    );
    let bridge = bridge(
        vec![
            Field::new("ntz", DataType::Int64, true),
            Field::new("ym", DataType::Int32, true),
            Field::new("dt", DataType::Int64, true),
        ],
        vec![
            Field::new(
                "ntz",
                DataType::Timestamp(TimeUnit::Microsecond, None),
                true,
            ),
            year_month.clone(),
            day_time.clone(),
        ],
    );
    let ntz = vec![Some(-1), Some(1_234_567), None, Some(0)];
    let ym = vec![Some(-14), None, Some(25), Some(0)];
    let dt = vec![Some(-3_600_000_001), Some(1), None, Some(0)];
    let input = RecordBatch::try_new(
        bridge.physical.clone(),
        vec![
            Arc::new(Int64Array::from(ntz.clone())),
            Arc::new(Int32Array::from(ym.clone())),
            Arc::new(Int64Array::from(dt.clone())),
        ],
    )?;
    let output = bridge.adapt_batch(input)?;
    assert_eq!(values::<TimestampMicrosecondType>(output.column(0)), ntz);
    assert_eq!(values::<IntervalYearMonthType>(output.column(1)), ym);
    assert_eq!(values::<DurationMicrosecondType>(output.column(2)), dt);
    assert_eq!(output.schema().field(1), &year_month);
    assert_eq!(output.schema().field(2), &day_time);
    Ok(())
}

#[test]
fn nested_lists_and_duplicate_struct_names_adapt_positionally() -> Result<()> {
    let physical_fields = vec![
        Field::new("duplicate", DataType::Int64, true),
        Field::new("duplicate", DataType::Int64, true),
    ]
    .into();
    let ntz = vec![Some(1), Some(2), None, Some(-4)];
    let time = vec![Some(5), Some(6), Some(7), None];
    let structs = StructArray::try_new(
        physical_fields,
        vec![
            Arc::new(Int64Array::from(ntz.clone())),
            Arc::new(Int64Array::from(time.clone())),
        ],
        Some(NullBuffer::from(vec![true, false, true, true])),
    )?;
    let list = ListArray::try_new(
        Arc::new(Field::new("item", structs.data_type().clone(), true)),
        OffsetBuffer::new(vec![0i32, 2, 2, 3, 4].into()),
        Arc::new(structs.clone()),
        Some(NullBuffer::from(vec![true, false, true, true])),
    )?;
    let logical_fields = vec![
        Field::new(
            "duplicate",
            DataType::Timestamp(TimeUnit::Microsecond, None),
            true,
        ),
        time_field("duplicate", 0),
    ]
    .into();
    let logical = Field::new(
        "nested",
        DataType::List(Arc::new(Field::new(
            "item",
            DataType::Struct(logical_fields),
            true,
        ))),
        true,
    );
    let bridge = bridge(
        vec![Field::new("nested", list.data_type().clone(), true)],
        vec![logical],
    );
    for source in [list.clone(), list.slice(1, 3)] {
        let input = RecordBatch::try_new(bridge.physical.clone(), vec![Arc::new(source.clone())])?;
        let output = bridge.adapt_batch(input)?;
        let result = output
            .column(0)
            .as_any()
            .downcast_ref::<ListArray>()
            .unwrap();
        assert_eq!(result.value_offsets(), source.value_offsets());
        assert_eq!(result.nulls(), source.nulls());
        assert_eq!(result.len(), source.len());
        let result = result
            .values()
            .as_any()
            .downcast_ref::<StructArray>()
            .unwrap();
        assert_eq!(result.nulls(), structs.nulls());
        assert_eq!(values::<TimestampMicrosecondType>(result.column(0)), ntz);
        assert_eq!(values::<Time64NanosecondType>(result.column(1)), time);
        assert_eq!(result.fields()[0].name(), "duplicate");
        assert_eq!(result.fields()[1].name(), "duplicate");
        assert_eq!(
            result.fields()[1].metadata(),
            time_field("duplicate", 0).metadata()
        );
    }
    Ok(())
}

#[test]
fn maps_translate_native_names_without_losing_offsets_or_nulls() -> Result<()> {
    let keys: ArrayRef = Arc::new(StringArray::from(vec!["a", "b", "c"]));
    let expected = vec![Some(10), None, Some(-20)];
    let entries = StructArray::try_new(
        vec![
            Field::new("keys", DataType::Utf8, false),
            Field::new("values", DataType::Int64, true),
        ]
        .into(),
        vec![keys.clone(), Arc::new(Int64Array::from(expected.clone()))],
        None,
    )?;
    let map = MapArray::try_new(
        Arc::new(Field::new("entries", entries.data_type().clone(), false)),
        OffsetBuffer::new(vec![0i32, 2, 2, 3, 3].into()),
        entries,
        Some(NullBuffer::from(vec![true, false, true, true])),
        false,
    )?;
    let logical_entries = Field::new(
        spec::SAIL_MAP_FIELD_NAME,
        DataType::Struct(
            vec![
                Field::new(spec::SAIL_MAP_KEY_FIELD_NAME, DataType::Utf8, false),
                Field::new(
                    spec::SAIL_MAP_VALUE_FIELD_NAME,
                    DataType::Timestamp(TimeUnit::Microsecond, None),
                    true,
                ),
            ]
            .into(),
        ),
        false,
    );
    let bridge = bridge(
        vec![Field::new("m", map.data_type().clone(), true)],
        vec![Field::new(
            "m",
            DataType::Map(Arc::new(logical_entries), false),
            true,
        )],
    );
    for source in [map.clone(), map.slice(1, 3)] {
        let input = RecordBatch::try_new(bridge.physical.clone(), vec![Arc::new(source.clone())])?;
        let output = bridge.adapt_batch(input)?;
        let result = output
            .column(0)
            .as_any()
            .downcast_ref::<MapArray>()
            .unwrap();
        assert_eq!(result.value_offsets(), source.value_offsets());
        assert_eq!(result.nulls(), source.nulls());
        assert_eq!(result.len(), source.len());
        let last = result.len() - 1;
        assert!(result.is_valid(last));
        assert_eq!(result.value_length(last), 0);
        assert_eq!(result.keys().as_ref(), keys.as_ref());
        assert_eq!(
            values::<TimestampMicrosecondType>(result.values()),
            expected
        );
        assert_eq!(
            result.entries().fields()[0].name(),
            spec::SAIL_MAP_KEY_FIELD_NAME
        );
        assert_eq!(
            result.entries().fields()[1].name(),
            spec::SAIL_MAP_VALUE_FIELD_NAME
        );
        assert!(!result.entries().fields()[0].is_nullable());
        assert!(result.entries().fields()[1].is_nullable());
    }
    Ok(())
}

#[test]
fn projection_keeps_schema_and_data_order_including_duplicate_columns() -> Result<()> {
    let bridge = bridge(
        vec![
            Field::new("t", DataType::Int64, true),
            Field::new("s", DataType::Utf8, true),
        ],
        vec![time_field("t", 3), Field::new("s", DataType::Utf8, true)],
    );
    let input = RecordBatch::try_new(
        bridge.physical.clone(),
        vec![
            Arc::new(Int64Array::from(vec![Some(1_234_567_890), None])),
            Arc::new(StringArray::from(vec![Some("first"), None])),
        ],
    )?;
    // This is an already-projected decoded batch. Native ORC projection itself
    // is a file-order set; final request ordering/repetition is a separate step.
    let indices = [1, 0, 1, 0];
    let projected = bridge.project(&indices)?;
    let output = projected.adapt_batch(input.project(&indices)?)?;
    assert_eq!(
        output.schema().fields(),
        bridge.logical.project(&indices)?.fields()
    );
    assert_eq!(output.num_columns(), 4);
    assert_eq!(output.column(0).as_ref(), input.column(1).as_ref());
    assert_eq!(output.column(2).as_ref(), input.column(1).as_ref());
    for index in [1, 3] {
        assert_eq!(
            values::<Time64NanosecondType>(output.column(index)),
            vec![Some(1_234_567_890), None]
        );
        assert_eq!(
            output.schema().field(index).metadata(),
            time_field("t", 3).metadata()
        );
    }
    assert!(bridge.project(&[2]).is_err());
    assert!(projected.adapt_batch(input).is_err());
    Ok(())
}

#[test]
fn empty_projection_preserves_rows_and_empty_batches_keep_logical_types() -> Result<()> {
    let bridge = bridge(
        vec![Field::new("t", DataType::Int64, true)],
        vec![time_field("t", 6)],
    );
    for row_count in [0, 3] {
        let input = RecordBatch::try_new(
            bridge.physical.clone(),
            vec![Arc::new(Int64Array::from(vec![None; row_count]))],
        )?;
        let projected = bridge.project(&[])?;
        let output = projected.adapt_batch(input.project(&[])?)?;
        assert_eq!(output.num_rows(), row_count);
        assert_eq!(output.num_columns(), 0);
        let output = bridge.adapt_batch(input)?;
        assert_eq!(output.num_rows(), row_count);
        assert_eq!(output.column(0).len(), row_count);
        assert_eq!(output.column(0).null_count(), row_count);
        assert_eq!(
            output.column(0).data_type(),
            &DataType::Time64(TimeUnit::Nanosecond)
        );
        assert_eq!(
            output.schema().field(0).metadata(),
            time_field("t", 6).metadata()
        );
    }
    Ok(())
}

#[test]
fn decoded_schema_mismatch_is_rejected_before_adaptation() -> Result<()> {
    let bridge = bridge(
        vec![Field::new("t", DataType::Int64, true)],
        vec![time_field("t", 6)],
    );
    let wrong = Arc::new(Schema::new(vec![Field::new(
        "other",
        DataType::Int64,
        true,
    )]));
    let batch = RecordBatch::try_new(wrong, vec![Arc::new(Int64Array::from(vec![1]))])?;
    let error = bridge.adapt_batch(batch).unwrap_err().to_string();
    assert!(
        error.contains("does not match the physical schema"),
        "{error}"
    );
    Ok(())
}

#[test]
fn naive_ltz_timestamps_are_rejected_recursively() -> Result<()> {
    let array: ArrayRef = Arc::new(PrimitiveArray::<TimestampMicrosecondType>::from(vec![
        Some(-1),
        None,
        Some(1_234_567),
    ]));
    let target = Field::new(
        "t",
        DataType::Timestamp(TimeUnit::Microsecond, Some("UTC".into())),
        true,
    );
    let error = adapt_array(&array, &target).unwrap_err().to_string();
    assert!(
        error.contains("explicit native reader timezone decoding"),
        "{error}"
    );
    let source = StructArray::try_new(
        vec![Field::new("t", array.data_type().clone(), true)].into(),
        vec![array],
        Some(NullBuffer::from(vec![true, false, true])),
    )?;
    let target = Field::new("nested", DataType::Struct(vec![target].into()), true);
    let error = adapt_array(&(Arc::new(source) as ArrayRef), &target)
        .unwrap_err()
        .to_string();
    assert!(
        error.contains("explicit native reader timezone decoding"),
        "{error}"
    );
    Ok(())
}

#[test]
fn instant_timestamps_relabel_without_changing_sliced_values() -> Result<()> {
    let expected = vec![Some(-1), None, Some(1_234_567)];
    let source = PrimitiveArray::<TimestampMicrosecondType>::from(vec![
        Some(0),
        Some(-1),
        None,
        Some(1_234_567),
        Some(9),
    ])
    .with_timezone("UTC")
    .slice(1, 3);
    let target = Field::new(
        "t",
        DataType::Timestamp(TimeUnit::Microsecond, Some("America/Los_Angeles".into())),
        true,
    );
    let bridge = bridge(
        vec![Field::new("t", source.data_type().clone(), true)],
        vec![target.clone()],
    );
    let output = bridge.adapt_batch(RecordBatch::try_new(
        bridge.physical.clone(),
        vec![Arc::new(source)],
    )?)?;
    assert_eq!(output.schema().field(0), &target);
    assert_eq!(
        values::<TimestampMicrosecondType>(output.column(0)),
        expected
    );
    Ok(())
}

#[test]
fn sliced_struct_preserves_parent_nulls_and_non_time_siblings() -> Result<()> {
    let text: ArrayRef = Arc::new(StringArray::from(vec![
        "before",
        "first",
        "null parent",
        "last",
    ]));
    let source = StructArray::try_new(
        vec![
            Field::new("t", DataType::Int64, true),
            Field::new("s", DataType::Utf8, true),
        ]
        .into(),
        vec![
            Arc::new(Int64Array::from(vec![
                Some(9),
                Some(1_234_567),
                None,
                Some(86_399_999_999_999),
            ])),
            text.clone(),
        ],
        Some(NullBuffer::from(vec![true, true, false, true])),
    )?
    .slice(1, 3);
    let target = Field::new(
        "nested",
        DataType::Struct(vec![time_field("t", 0), Field::new("s", DataType::Utf8, true)].into()),
        true,
    );
    let result = adapt_array(&(Arc::new(source.clone()) as ArrayRef), &target)?;
    let result = result.as_any().downcast_ref::<StructArray>().unwrap();
    assert_eq!(result.len(), 3);
    assert_eq!(result.nulls(), source.nulls());
    assert_eq!(
        values::<Time64NanosecondType>(result.column(0)),
        vec![Some(1_234_567), None, Some(86_399_999_999_999)]
    );
    assert_eq!(result.column(1).as_ref(), text.slice(1, 3).as_ref());
    assert_eq!(result.fields()[0].metadata(), time_field("t", 0).metadata());
    Ok(())
}
