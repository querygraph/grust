use std::error::Error;

use super::*;
use crate::column_change::validate_field_names;
use crate::variant::variant_metadata_field;

type TestResult<T = ()> = std::result::Result<T, Box<dyn Error>>;

fn metadata(pairs: &[(&str, &str)]) -> HashMap<String, String> {
    pairs
        .iter()
        .map(|(key, value)| (key.to_string(), value.to_string()))
        .collect()
}

fn time(name: &str, precision: i32, nullable: bool) -> TestResult<Field> {
    Ok(
        Field::new(name, DataType::Time64(TimeUnit::Nanosecond), nullable).with_metadata(
            HashMap::from([(
                spec::SAIL_SPARK_TIME_METADATA_KEY.to_string(),
                SparkTimeMetadata::try_new(precision)?.to_json()?,
            )]),
        ),
    )
}

fn interval(name: &str, value: SparkIntervalMetadata, nullable: bool) -> TestResult<Field> {
    let data_type = match value {
        SparkIntervalMetadata::YearMonth { .. } => DataType::Interval(IntervalUnit::YearMonth),
        SparkIntervalMetadata::DayTime { .. } => DataType::Duration(TimeUnit::Microsecond),
    };
    Ok(
        Field::new(name, data_type, nullable).with_metadata(HashMap::from([(
            spec::SAIL_SPARK_INTERVAL_METADATA_KEY.to_string(),
            value.to_json()?,
        )])),
    )
}

fn map_type(key: Field, value: Field) -> DataType {
    DataType::Map(
        Arc::new(Field::new(
            "entries",
            DataType::Struct(vec![key, value].into()),
            false,
        )),
        false,
    )
}

fn containers(fields: Vec<Field>) -> [DataType; 3] {
    let structure = DataType::Struct(fields.into());
    [
        structure.clone(),
        DataType::List(Arc::new(Field::new("element", structure.clone(), true))),
        map_type(
            Field::new("key", DataType::Utf8, false),
            Field::new("value", structure, true),
        ),
    ]
}

fn single(data_type: DataType) -> Schema {
    Schema::new(vec![Field::new("nested", data_type, true)])
}

fn merge_error(left: &Schema, right: &Schema) -> TestResult<String> {
    Ok(merge_spark_file_schemas(left, right, false)
        .err()
        .ok_or("expected an incompatible schema")?
        .to_string())
}

#[test]
fn preserves_left_order_metadata_and_unmatched_nullability() -> TestResult {
    let left_value = Field::new("Value", DataType::Int32, false).with_metadata(metadata(&[
        ("comment", "left"),
        (spec::SPARK_METADATA_JSON_KEY, r#"{"a":1}"#),
    ]));
    let left_only = Field::new("left_only", DataType::Utf8, false)
        .with_metadata(metadata(&[("source", "left")]));
    let right_only = Field::new("right_only", DataType::Binary, false)
        .with_metadata(metadata(&[("source", "right")]));
    let left = Schema::new_with_metadata(
        vec![left_value.clone(), left_only.clone()],
        metadata(&[("version", "left")]),
    );
    let right = Schema::new_with_metadata(
        vec![
            right_only.clone(),
            Field::new("value", DataType::Int32, true).with_metadata(metadata(&[
                ("comment", "right"),
                ("right_only_metadata", "discard"),
            ])),
        ],
        metadata(&[("version", "right"), ("right_schema_metadata", "discard")]),
    );
    let expected = Schema::new_with_metadata(
        vec![left_value.with_nullable(true), left_only, right_only],
        left.metadata().clone(),
    );
    assert_eq!(merge_spark_file_schemas(&left, &right, false)?, expected);
    Ok(())
}

#[test]
fn root_case_policy_does_not_reject_equal_unicode_names() -> TestResult {
    let left = Schema::new(vec![Field::new("Value", DataType::Int32, false)]);
    let right = Schema::new(vec![Field::new("value", DataType::Int32, true)]);
    assert_eq!(
        merge_spark_file_schemas(&left, &right, true)?,
        Schema::new(vec![left.field(0).clone(), right.field(0).clone(),])
    );
    assert_eq!(
        merge_spark_file_schemas(&left, &right, false)?,
        Schema::new(vec![left.field(0).clone().with_nullable(true)])
    );
    let unicode = Schema::new(vec![Field::new("東京", DataType::Int32, true)]);
    assert_eq!(
        merge_spark_file_schemas(&unicode, &unicode, false)?,
        unicode
    );
    Ok(())
}

#[test]
fn nested_case_merge_and_recursive_duplicate_validation_are_separate() -> TestResult {
    // Retained Spark 4.2.1 file/direct-JVM oracle: root CI coalesces, while
    // nested STRUCT/ARRAY-element/MAP-value STRUCT names merge case-sensitively.
    let upper = Field::new("Value", DataType::Int32, true);
    let lower = Field::new("value", DataType::Int32, true);
    for ((left, right), expected) in containers(vec![upper.clone()])
        .into_iter()
        .zip(containers(vec![lower.clone()]))
        .zip(containers(vec![upper.clone(), lower.clone()]))
    {
        let merged = merge_spark_file_schemas(&single(left), &single(right), false)?;
        assert_eq!(merged, single(expected));
        assert!(validate_field_names(merged.fields(), false).is_err());
        validate_field_names(merged.fields(), true)?;
        // A single inferred schema still needs the independent relation check.
        assert_eq!(
            merge_spark_file_schemas(&merged, &Schema::empty(), false)?,
            merged
        );
    }
    Ok(())
}

#[test]
fn time_precision_is_semantic_at_root_and_in_containers() -> TestResult {
    let left = Schema::new(vec![time("clock", 3, false)?]);
    let nullable = Schema::new(vec![time("clock", 3, true)?]);
    assert_eq!(merge_spark_file_schemas(&left, &nullable, true)?, nullable);
    let right = Schema::new(vec![time("clock", 6, true)?]);
    assert_eq!(left.field(0).data_type(), right.field(0).data_type());
    assert!(merge_error(&left, &right)?.contains("incompatible"));
    let mut element = time("left_element", 3, false)?;
    element
        .metadata_mut()
        .insert("comment".into(), "left".into());
    let left = single(DataType::List(Arc::new(element.clone())));
    let right = single(DataType::List(Arc::new(time("element", 3, true)?)));
    assert_eq!(
        merge_spark_file_schemas(&left, &right, false)?,
        single(DataType::List(Arc::new(element.with_nullable(true))))
    );
    for (left, right) in containers(vec![time("clock", 0, true)?])
        .into_iter()
        .zip(containers(vec![time("clock", 3, true)?]))
    {
        assert!(merge_error(&single(left), &single(right))?.contains("incompatible"));
    }
    let keys = |precision| -> TestResult<Schema> {
        Ok(single(map_type(
            time("key", precision, false)?,
            Field::new("value", DataType::Int32, true),
        )))
    };
    assert!(merge_error(&keys(0)?, &keys(6)?)?.contains("incompatible"));
    Ok(())
}

#[test]
fn interval_union_retains_left_user_metadata_and_supports_default_qualifiers() -> TestResult {
    use spec::{DayTimeIntervalField as D, YearMonthIntervalField as Y};
    let cases = [
        (
            SparkIntervalMetadata::YearMonth {
                start_field: Y::Year,
                end_field: Y::Year,
            },
            SparkIntervalMetadata::YearMonth {
                start_field: Y::Month,
                end_field: Y::Month,
            },
            SparkIntervalMetadata::YearMonth {
                start_field: Y::Year,
                end_field: Y::Month,
            },
        ),
        (
            SparkIntervalMetadata::DayTime {
                start_field: D::Hour,
                end_field: D::Minute,
            },
            SparkIntervalMetadata::DayTime {
                start_field: D::Day,
                end_field: D::Second,
            },
            SparkIntervalMetadata::DayTime {
                start_field: D::Day,
                end_field: D::Second,
            },
        ),
    ];
    for (left_interval, right_interval, expected_interval) in cases {
        let mut left = interval("duration", left_interval, false)?;
        left.metadata_mut().insert("comment".into(), "left".into());
        let right = interval("duration", right_interval, true)?;
        let mut expected = interval("duration", expected_interval, true)?;
        expected
            .metadata_mut()
            .insert("comment".into(), "left".into());
        assert_eq!(
            merge_spark_file_schemas(
                &Schema::new(vec![left.clone()]),
                &Schema::new(vec![right]),
                true
            )?,
            Schema::new(vec![expected.clone()])
        );
        let default = Field::new("duration", left.data_type().clone(), true);
        assert_eq!(
            merge_spark_file_schemas(
                &Schema::new(vec![left]),
                &Schema::new(vec![default.clone()]),
                true
            )?,
            Schema::new(vec![expected])
        );
        // Full default on the left already describes the union; retain its metadata.
        assert_eq!(
            merge_spark_file_schemas(
                &Schema::new(vec![default.clone()]),
                &Schema::new(vec![interval("duration", left_interval, false)?]),
                true
            )?,
            Schema::new(vec![default])
        );
    }
    let year = interval("duration", cases[0].0, true)?;
    let day = interval("duration", cases[1].0, true)?;
    assert!(
        merge_error(
            &Schema::new(vec![year.clone()]),
            &Schema::new(vec![day.clone()])
        )?
        .contains("incompatible")
    );
    assert!(
        merge_error(
            &single(DataType::List(Arc::new(year))),
            &single(DataType::List(Arc::new(day)))
        )?
        .contains("incompatible")
    );
    Ok(())
}

#[test]
fn decimal_precision_is_the_only_numeric_merge_promotion() -> TestResult {
    let decimal = |precision, scale| single(DataType::Decimal128(precision, scale));
    assert_eq!(
        merge_spark_file_schemas(&decimal(8, 2), &decimal(12, 2), true)?,
        decimal(12, 2)
    );
    for (left, right) in [
        (DataType::Decimal128(8, 2), DataType::Decimal128(12, 3)),
        (DataType::Int32, DataType::Int64),
        (DataType::Float32, DataType::Float64),
        (DataType::Null, DataType::Int32),
        (
            DataType::Timestamp(TimeUnit::Microsecond, None),
            DataType::Timestamp(TimeUnit::Microsecond, Some("UTC".into())),
        ),
    ] {
        assert!(
            merge_error(&single(left.clone()), &single(right.clone()))?.contains("incompatible")
        );
        assert!(merge_error(&single(right), &single(left))?.contains("incompatible"));
    }
    Ok(())
}

#[test]
fn invalid_semantic_metadata_is_checked_in_equal_nested_and_unmatched_fields() -> TestResult {
    let bad_time = Field::new("clock", DataType::Time64(TimeUnit::Nanosecond), true).with_metadata(
        metadata(&[(spec::SAIL_SPARK_TIME_METADATA_KEY, r#"{"precision":9}"#)]),
    );
    let mismatched_time = time("clock", 3, true)?.with_data_type(DataType::Int64);
    let malformed_interval =
        Field::new("duration", DataType::Duration(TimeUnit::Microsecond), true).with_metadata(
            metadata(&[(
                spec::SAIL_SPARK_INTERVAL_METADATA_KEY,
                r#"{"unit":"dayTime","startField":"second","endField":"day"}"#,
            )]),
        );
    let mut conflict = time("clock", 3, true)?;
    conflict.metadata_mut().insert(
        spec::SAIL_SPARK_INTERVAL_METADATA_KEY.into(),
        r#"{"unit":"yearMonth","startField":"year","endField":"month"}"#.into(),
    );
    for invalid in [
        bad_time,
        mismatched_time,
        malformed_interval,
        conflict,
        Field::new("clock", DataType::Time64(TimeUnit::Nanosecond), true),
    ] {
        let schema = Schema::new(vec![invalid.clone()]);
        assert!(merge_error(&schema, &schema)?.contains("metadata"));
        assert!(merge_error(&Schema::empty(), &schema)?.contains("metadata"));
        assert!(merge_error(&schema, &Schema::empty())?.contains("metadata"));
        let nested = single(DataType::List(Arc::new(invalid)));
        assert!(merge_error(&nested, &nested)?.contains("metadata"));
    }
    let year = interval(
        "key",
        SparkIntervalMetadata::YearMonth {
            start_field: spec::YearMonthIntervalField::Year,
            end_field: spec::YearMonthIntervalField::Month,
        },
        false,
    )?
    .with_data_type(DataType::Int32);
    let nested = single(map_type(year, Field::new("value", DataType::Int32, true)));
    assert!(merge_error(&Schema::empty(), &nested)?.contains("metadata requires"));
    Ok(())
}

#[test]
fn extensions_cannot_merge_as_equal_ordinary_storage() -> TestResult {
    let udt = Field::new("value", DataType::Int32, true).with_metadata(metadata(&[(
        spec::SAIL_SPARK_UDT_METADATA_KEY,
        r#"{"jvmClass":"Example"}"#,
    )]));
    let geo = Field::new("value", DataType::Binary, true).with_metadata(metadata(&[
        (EXTENSION_TYPE_NAME_KEY, "geoarrow.wkb"),
        (EXTENSION_TYPE_METADATA_KEY, "{}"),
    ]));
    let variant = Field::new(
        "value",
        DataType::Struct(
            vec![
                variant_metadata_field(DataType::Binary, false),
                Field::new("value", DataType::Binary, false),
            ]
            .into(),
        ),
        true,
    );
    assert!(is_variant_storage_field(&variant));
    for field in [udt, geo, variant] {
        let schema = Schema::new(vec![field.clone()]);
        assert!(merge_error(&schema, &schema)?.contains("does not support"));
        let nested = single(DataType::List(Arc::new(field)));
        assert!(merge_error(&Schema::empty(), &nested)?.contains("does not support"));
    }
    Ok(())
}

#[test]
fn map_roles_preserve_left_fields_and_merge_semantics_positionally() -> TestResult {
    use spec::YearMonthIntervalField as Y;
    let year = SparkIntervalMetadata::YearMonth {
        start_field: Y::Year,
        end_field: Y::Year,
    };
    let month = SparkIntervalMetadata::YearMonth {
        start_field: Y::Month,
        end_field: Y::Month,
    };
    let both = SparkIntervalMetadata::YearMonth {
        start_field: Y::Year,
        end_field: Y::Month,
    };
    let mut left_key = time("left_key", 3, false)?;
    left_key
        .metadata_mut()
        .insert("key_metadata".into(), "left".into());
    let mut left_value = interval("left_value", year, false)?;
    left_value
        .metadata_mut()
        .insert("value_metadata".into(), "left".into());
    let entries = |key, value| {
        Field::new(
            "left_entries",
            DataType::Struct(vec![key, value].into()),
            false,
        )
        .with_metadata(metadata(&[("entries_metadata", "left")]))
    };
    let left = single(DataType::Map(
        Arc::new(entries(left_key.clone(), left_value.clone())),
        true,
    ));
    let right = single(map_type(
        time("key", 3, false)?,
        interval("value", month, true)?,
    ));
    left_value = left_value.with_nullable(true);
    left_value.metadata_mut().insert(
        spec::SAIL_SPARK_INTERVAL_METADATA_KEY.into(),
        both.to_json()?,
    );
    let expected = single(DataType::Map(Arc::new(entries(left_key, left_value)), true));
    assert_eq!(merge_spark_file_schemas(&left, &right, false)?, expected);
    Ok(())
}

#[test]
fn malformed_map_shape_fails_even_when_unmatched() -> TestResult {
    let good_key = Field::new("key", DataType::Int32, false);
    let value = Field::new("value", DataType::Utf8, true);
    let entries = [
        Field::new("entries", DataType::Int32, false),
        Field::new(
            "entries",
            DataType::Struct(vec![good_key.clone()].into()),
            false,
        ),
        Field::new(
            "entries",
            DataType::Struct(vec![good_key.clone().with_nullable(true), value.clone()].into()),
            false,
        ),
        Field::new(
            "entries",
            DataType::Struct(vec![good_key, value].into()),
            true,
        ),
    ];
    for entries in entries {
        let schema = single(DataType::Map(Arc::new(entries), false));
        assert!(merge_error(&Schema::empty(), &schema)?.contains("Spark map"));
    }
    Ok(())
}
