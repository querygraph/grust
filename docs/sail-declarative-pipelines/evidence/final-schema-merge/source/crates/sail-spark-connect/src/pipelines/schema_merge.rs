use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use sail_common::spec;

use crate::error::{SparkResult, StructuredSparkError};

#[path = "schema_merge_sql.rs"]
mod sql;

/// Spark 4.2.1's SchemaMergingUtils delegates to StructType.merge. Field order
/// and metadata come from the left schema; matching fields merge their types
/// and nullability. Arrow's merge also merges metadata and promotes Null types,
/// which would change the pipeline's declared-schema compatibility contract.
pub(super) fn merge_fields(left: &spec::Fields, right: &spec::Fields) -> SparkResult<spec::Fields> {
    let right_by_name: HashMap<_, _> = right.iter().map(|field| (&field.name, field)).collect();
    let left_names: HashSet<_> = left.iter().map(|field| &field.name).collect();
    let mut fields = Vec::with_capacity(left.len() + right.len());
    for field in left {
        let merged = match right_by_name.get(&field.name) {
            Some(other) => Arc::new(spec::Field {
                // StructType.merge reports the enclosing field types when a
                // recursive merge fails, rather than its innermost leaf.
                data_type: merge_type(&field.data_type, &other.data_type)
                    .or_else(|_| incompatible(&field.data_type, &other.data_type))?,
                nullable: field.nullable || other.nullable,
                ..field.as_ref().clone()
            }),
            None => Arc::clone(field),
        };
        fields.push(merged);
    }
    fields.extend(
        right
            .iter()
            .filter(|field| !left_names.contains(&field.name))
            .cloned(),
    );
    Ok(fields.into())
}

fn merge_type(left: &spec::DataType, right: &spec::DataType) -> SparkResult<spec::DataType> {
    use spec::DataType;

    if left == right {
        return Ok(left.clone());
    }
    Ok(match (left, right) {
        (DataType::Struct { fields: left }, DataType::Struct { fields: right }) => {
            DataType::Struct {
                fields: merge_fields(left, right)?,
            }
        }
        (
            DataType::List {
                data_type: left,
                nullable: left_nullable,
            },
            DataType::List {
                data_type: right,
                nullable: right_nullable,
            },
        ) => DataType::List {
            data_type: Box::new(merge_type(left, right)?),
            nullable: *left_nullable || *right_nullable,
        },
        (
            DataType::Map {
                key_type: left_key,
                value_type: left_value,
                value_type_nullable: left_nullable,
                keys_sorted,
            },
            DataType::Map {
                key_type: right_key,
                value_type: right_value,
                value_type_nullable: right_nullable,
                ..
            },
        ) => DataType::Map {
            key_type: Box::new(merge_type(left_key, right_key)?),
            value_type: Box::new(merge_type(left_value, right_value)?),
            value_type_nullable: *left_nullable || *right_nullable,
            keys_sorted: *keys_sorted,
        },
        (
            DataType::Decimal128 {
                precision: left_precision,
                scale: left_scale,
            },
            DataType::Decimal128 {
                precision: right_precision,
                scale: right_scale,
            },
        ) if left_scale == right_scale => DataType::Decimal128 {
            precision: *left_precision.max(right_precision),
            scale: *left_scale,
        },
        (
            DataType::Interval {
                interval_unit: left_unit,
                start_field: left_start,
                end_field: left_end,
            },
            DataType::Interval {
                interval_unit: right_unit,
                start_field: right_start,
                end_field: right_end,
            },
        ) if left_unit == right_unit => {
            let (default_start, default_end) = match left_unit {
                spec::IntervalUnit::YearMonth => (
                    spec::IntervalFieldType::Year,
                    spec::IntervalFieldType::Month,
                ),
                spec::IntervalUnit::DayTime => (
                    spec::IntervalFieldType::Day,
                    spec::IntervalFieldType::Second,
                ),
                spec::IntervalUnit::MonthDayNano => return incompatible(left, right),
            };
            let left_end = left_end.unwrap_or(left_start.unwrap_or(default_end));
            let right_end = right_end.unwrap_or(right_start.unwrap_or(default_end));
            DataType::Interval {
                interval_unit: *left_unit,
                start_field: Some(
                    left_start
                        .unwrap_or(default_start)
                        .min(right_start.unwrap_or(default_start)),
                ),
                end_field: Some(left_end.max(right_end)),
            }
        }
        (
            DataType::UserDefined {
                jvm_class: Some(left_class),
                ..
            },
            DataType::UserDefined {
                jvm_class: Some(right_class),
                ..
            },
        ) if left_class == right_class => left.clone(),
        _ => return incompatible(left, right),
    })
}

fn incompatible(left: &spec::DataType, right: &spec::DataType) -> SparkResult<spec::DataType> {
    let left = sql::quoted_type(left)?;
    let right = sql::quoted_type(right)?;
    Err(Box::new(StructuredSparkError {
        class: "org.apache.spark.SparkException".into(),
        condition: "CANNOT_MERGE_INCOMPATIBLE_DATA_TYPE".into(),
        sql_state: "42825".into(),
        message: format!("Failed to merge incompatible data types {left} and {right}. Please check the data types of the columns being merged and ensure that they are compatible. If necessary, consider casting the columns to compatible data types before attempting the merge. SQLSTATE: 42825"),
        parameters: HashMap::from([("left".into(), left), ("right".into(), right)]),
    }).into())
}

#[cfg(test)]
mod tests {
    use datafusion::arrow::datatypes as adt;

    use super::*;
    use crate::spark::connect::data_type::StructField;

    fn time_field(name: &str, precision: i32, nullable: bool) -> SparkResult<adt::Field> {
        Ok(adt::Field::new(
            name,
            adt::DataType::Time64(adt::TimeUnit::Nanosecond),
            nullable,
        )
        .with_metadata(HashMap::from([(
            spec::SAIL_SPARK_TIME_METADATA_KEY.to_string(),
            spec::SparkTimeMetadata::try_new(precision)?.to_json()?,
        )])))
    }

    fn fields(field: adt::Field) -> SparkResult<spec::Fields> {
        // Use the same Arrow -> Connect -> spec normalization as schema::spark_fields.
        Ok(vec![spec::FieldRef::try_from(StructField::try_from(field)?)?].into())
    }

    // Spark 4.2.1 StructType.merge preserves equal TIME precision and merges nullability;
    // different precisions are incompatible despite sharing Arrow nanosecond storage.
    #[test]
    fn time_merge_preserves_precision_and_combines_nullability() -> SparkResult<()> {
        let left = fields(time_field("clock", 3, false)?)?;
        let right = fields(time_field("clock", 3, true)?)?;

        assert_eq!(merge_fields(&left, &right)?, right);
        assert_eq!(merge_fields(&right, &left)?, right);
        assert_eq!(right[0].data_type, spec::DataType::Time { precision: 3 });
        Ok(())
    }

    #[test]
    fn time_merge_rejects_different_precision_with_identical_arrow_storage() -> SparkResult<()> {
        for (left_precision, right_precision) in [(0, 3), (3, 6), (1, 2)] {
            let left = time_field("clock", left_precision, false)?;
            let right = time_field("clock", right_precision, true)?;
            assert_eq!(left.data_type(), right.data_type());

            let left = fields(left)?;
            let right = fields(right)?;
            assert!(merge_fields(&left, &right).is_err());
            assert!(merge_fields(&right, &left).is_err());
        }
        Ok(())
    }

    #[test]
    fn time_merge_rejects_nested_precision_changes() -> SparkResult<()> {
        fn containers(precision: i32) -> SparkResult<[adt::DataType; 3]> {
            Ok([
                adt::DataType::List(Arc::new(time_field(
                    spec::SAIL_LIST_FIELD_NAME,
                    precision,
                    true,
                )?)),
                adt::DataType::Struct(vec![time_field("clock", precision, true)?].into()),
                adt::DataType::Map(
                    Arc::new(adt::Field::new(
                        spec::SAIL_MAP_FIELD_NAME,
                        adt::DataType::Struct(
                            vec![
                                adt::Field::new(
                                    spec::SAIL_MAP_KEY_FIELD_NAME,
                                    adt::DataType::Utf8,
                                    false,
                                ),
                                time_field(spec::SAIL_MAP_VALUE_FIELD_NAME, precision, true)?,
                            ]
                            .into(),
                        ),
                        false,
                    )),
                    false,
                ),
            ])
        }

        for (left_type, right_type) in containers(3)?.into_iter().zip(containers(6)?) {
            let left = fields(adt::Field::new("nested", left_type, true))?;
            let right = fields(adt::Field::new("nested", right_type, true))?;
            assert!(
                merge_fields(&left, &right).is_err(),
                "{left:?} vs {right:?}"
            );
        }
        Ok(())
    }

    #[test]
    fn time_merge_keeps_different_precisions_in_distinct_fields() -> SparkResult<()> {
        let left = fields(time_field("seconds", 0, false)?)?;
        let right = fields(time_field("micros", 6, true)?)?;
        let merged = merge_fields(&left, &right)?;
        let expected: spec::Fields = vec![Arc::clone(&left[0]), Arc::clone(&right[0])].into();

        assert_eq!(merged, expected);
        assert_eq!(merged[0].data_type, spec::DataType::Time { precision: 0 });
        assert_eq!(merged[1].data_type, spec::DataType::Time { precision: 6 });
        Ok(())
    }
}
