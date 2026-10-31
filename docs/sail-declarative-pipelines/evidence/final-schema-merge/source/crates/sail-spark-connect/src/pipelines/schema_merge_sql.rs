//! Spark DataType.sql / DataTypeErrorsBase.toSQLType for schema merge errors.
//! Keep semantic precision, nested nullability, identifier case and comments;
//! uppercasing an Arrow simpleString would discard or change those properties.
use sail_common::spec;

use crate::error::{SparkError, SparkResult};

pub(super) fn quoted_type(data_type: &spec::DataType) -> SparkResult<String> {
    if let spec::DataType::UserDefined { sql_type, .. } = data_type {
        return Ok(format!("UDT({})", quoted_type(sql_type)?));
    }
    Ok(format!("\"{}\"", sql_type(data_type)?))
}

fn sql_type(data_type: &spec::DataType) -> SparkResult<String> {
    use spec::DataType as D;
    Ok(match data_type {
        D::Null => "VOID".into(),
        D::Boolean => "BOOLEAN".into(),
        D::Int8 => "TINYINT".into(),
        D::Int16 => "SMALLINT".into(),
        D::Int32 => "INT".into(),
        D::Int64 => "BIGINT".into(),
        D::Float32 => "FLOAT".into(),
        D::Float64 => "DOUBLE".into(),
        D::Binary
        | D::LargeBinary
        | D::BinaryView
        | D::FixedSizeBinary { .. }
        | D::ConfiguredBinary => "BINARY".into(),
        D::Utf8 | D::LargeUtf8 | D::Utf8View => "STRING".into(),
        D::ConfiguredUtf8 { utf8_type } => match utf8_type {
            spec::Utf8Type::Configured => "STRING".into(),
            spec::Utf8Type::Char { length } => format!("CHAR({length})"),
            spec::Utf8Type::VarChar { length } => format!("VARCHAR({length})"),
        },
        D::Date32 => "DATE".into(),
        D::Timestamp { timestamp_type, .. } => match timestamp_type {
            spec::TimestampType::Configured => {
                return Err(SparkError::internal(
                    "unresolved timestamp type in schema merge",
                ));
            }
            spec::TimestampType::WithLocalTimeZone => "TIMESTAMP".into(),
            spec::TimestampType::WithoutTimeZone => "TIMESTAMP_NTZ".into(),
        },
        D::Time { precision } => format!("TIME({precision})"),
        D::Time32 { time_unit } | D::Time64 { time_unit } => format!(
            "TIME({})",
            match time_unit {
                spec::TimeUnit::Second => 0,
                spec::TimeUnit::Millisecond => 3,
                spec::TimeUnit::Microsecond => 6,
                spec::TimeUnit::Nanosecond => 9,
            }
        ),
        D::Decimal128 { precision, scale } | D::Decimal256 { precision, scale } => {
            format!("DECIMAL({precision},{scale})")
        }
        D::Interval {
            interval_unit,
            start_field,
            end_field,
        } => {
            use spec::{IntervalFieldType as F, IntervalUnit as U};
            let (start, end) = match interval_unit {
                U::MonthDayNano => return Ok("INTERVAL".into()),
                U::YearMonth => (F::Year, F::Month),
                U::DayTime => (F::Day, F::Second),
            };
            let end = end_field.unwrap_or(start_field.unwrap_or(end));
            let start = start_field.unwrap_or(start);
            if start == end {
                format!("INTERVAL {start:?}").to_ascii_uppercase()
            } else {
                format!("INTERVAL {start:?} TO {end:?}").to_ascii_uppercase()
            }
        }
        D::Duration {
            time_unit: spec::TimeUnit::Microsecond,
        } => "INTERVAL DAY TO SECOND".into(),
        D::List { data_type, .. }
        | D::LargeList { data_type, .. }
        | D::FixedSizeList { data_type, .. } => format!("ARRAY<{}>", sql_type(data_type)?),
        D::Map {
            key_type,
            value_type,
            ..
        } => format!("MAP<{}, {}>", sql_type(key_type)?, sql_type(value_type)?),
        D::Struct { fields } => format!(
            "STRUCT<{}>",
            fields
                .iter()
                .map(|field| {
                    let name = &field.name;
                    let simple = !name.is_empty()
                        && name.bytes().enumerate().all(|(i, c)| {
                            c.is_ascii_alphabetic() || c == b'_' || (i > 0 && c.is_ascii_digit())
                        });
                    let name = if simple {
                        name.clone()
                    } else {
                        format!("`{}`", name.replace('`', "``"))
                    };
                    let nullability = if field.nullable { "" } else { " NOT NULL" };
                    let metadata = field
                        .metadata
                        .iter()
                        .find(|(key, _)| key == spec::SPARK_METADATA_JSON_KEY)
                        .map(|(_, value)| serde_json::from_str::<serde_json::Value>(value))
                        .transpose()?;
                    let comment = metadata
                        .as_ref()
                        .and_then(|value| value.get("comment"))
                        .and_then(|value| value.as_str())
                        .map(|comment| format!(" COMMENT '{}'", comment.replace('\'', "\\'")))
                        .unwrap_or_default();
                    Ok(format!(
                        "{name}: {}{nullability}{comment}",
                        sql_type(&field.data_type)?
                    ))
                })
                .collect::<SparkResult<Vec<_>>>()?
                .join(", ")
        ),
        D::UserDefined {
            sql_type: underlying,
            ..
        } => sql_type(underlying)?,
        D::Variant => "VARIANT".into(),
        D::Geometry { srid } | D::Geography { srid, .. } => {
            let name = if matches!(data_type, D::Geometry { .. }) {
                "GEOMETRY"
            } else {
                "GEOGRAPHY"
            };
            let srid = if *srid == -1 {
                "ANY".into()
            } else {
                srid.to_string()
            };
            format!("{name}({srid})")
        }
        // These Arrow-only types have no Spark SQL DataType representation.
        D::UInt8
        | D::UInt16
        | D::UInt32
        | D::UInt64
        | D::Float16
        | D::Date64
        | D::Duration { .. }
        | D::Union { .. }
        | D::Dictionary { .. } => {
            return Err(SparkError::unsupported(format!(
                "Spark SQL type for {data_type:?}"
            )));
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::proto::data_type::parse_spark_data_type;

    #[test]
    fn sql_types_preserve_nested_semantics() -> SparkResult<()> {
        for (ddl, expected) in [
            ("array<int>", "\"ARRAY<INT>\""),
            ("map<string,decimal(8,2)>", "\"MAP<STRING, DECIMAL(8,2)>\""),
            (
                "struct<`a`` B`:array<int> not null, x:string>",
                "\"STRUCT<`a`` B`: ARRAY<INT> NOT NULL, x: STRING>\"",
            ),
            ("time(3)", "\"TIME(3)\""),
            ("interval hour to second", "\"INTERVAL HOUR TO SECOND\""),
            ("interval month", "\"INTERVAL MONTH\""),
            ("timestamp_ntz", "\"TIMESTAMP_NTZ\""),
        ] {
            assert_eq!(
                quoted_type(&parse_spark_data_type(ddl)?)?,
                expected,
                "{ddl}"
            );
        }
        Ok(())
    }

    #[test]
    fn struct_error_type_retains_comment_case_and_escapes_quotes() -> SparkResult<()> {
        let data_type = spec::DataType::Struct {
            fields: vec![std::sync::Arc::new(spec::Field {
                name: "Mixed`Name".into(),
                data_type: spec::DataType::Int32,
                nullable: false,
                metadata: vec![(
                    spec::SPARK_METADATA_JSON_KEY.into(),
                    serde_json::json!({"comment":"A'b"}).to_string(),
                )],
            })]
            .into(),
        };
        assert_eq!(
            quoted_type(&data_type)?,
            "\"STRUCT<`Mixed``Name`: INT NOT NULL COMMENT 'A\\'b'>\""
        );
        Ok(())
    }

    #[test]
    fn nested_merge_reports_enclosing_field_types_in_original_order() -> SparkResult<()> {
        for (left, right) in [
            ("array<int>", "array<string>"),
            ("struct<x:int>", "struct<x:string>"),
        ] {
            for (left, right) in [(left, right), (right, left)] {
                let left = parse_spark_data_type(left)?;
                let right = parse_spark_data_type(right)?;
                let make = |data_type| {
                    vec![std::sync::Arc::new(spec::Field {
                        name: "id".into(),
                        data_type,
                        nullable: true,
                        metadata: vec![],
                    })]
                    .into()
                };
                let error = super::super::merge_fields(&make(left.clone()), &make(right.clone()));
                let Some(SparkError::Structured(error)) = error.err() else {
                    return Err(SparkError::internal("expected structured merge error"));
                };
                assert_eq!(error.parameters["left"], quoted_type(&left)?);
                assert_eq!(error.parameters["right"], quoted_type(&right)?);
            }
        }
        Ok(())
    }
}
