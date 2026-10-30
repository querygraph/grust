//! Spark file-schema merging for already normalized Arrow schemas.
//!
//! This is distinct from value coercion and per-file requested-schema mapping.
//! In particular, equal Arrow storage does not imply equal Spark TIME types.

use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use arrow_schema::extension::{EXTENSION_TYPE_METADATA_KEY, EXTENSION_TYPE_NAME_KEY};
use arrow_schema::{DataType, Field, FieldRef, Fields, IntervalUnit, Schema, TimeUnit};
use datafusion_common::{Result, not_impl_err, plan_datafusion_err, plan_err};
use sail_common::spec::{self, SparkIntervalMetadata, SparkTimeMetadata};

use crate::variant::is_variant_storage_field;

/// Merge normalized Spark file schemas, retaining left field order and metadata.
///
/// Matching fields combine nullability. Right-only fields retain their metadata
/// and nullability. Interval qualifier union updates only its type metadata;
/// ordinary metadata and schema-level metadata come from the left schema.
///
/// Spark 4.2.1 applies the requested case policy at the root, then merges matched
/// field types with case-sensitive nested STRUCT matching. Duplicate-name
/// validation is a separate relation-level step, using the original case policy
/// recursively, even when only one schema was inferred. This function does not
/// perform that step. Case-insensitive Unicode/default-locale parity is not
/// established; lowercase matching here is qualified for ASCII names.
///
/// Inputs must use the canonical types emitted by the ORC logical schema bridge:
/// microsecond timestamps with a common display timezone, annotated nanosecond
/// TIME, and ordinary Spark primitives/STRUCT/LIST/MAP. Unannotated year-month
/// and microsecond day-time intervals have their full default qualifiers.
/// Semantic metadata is validated throughout both trees before any merge,
/// including equal or unmatched fields. Unsupported extensions are diagnosed,
/// rather than merged as their storage types. No values are cast or widened.
pub fn merge_spark_file_schemas(
    left: &Schema,
    right: &Schema,
    root_case_sensitive: bool,
) -> Result<Schema> {
    validate_fields(left.fields())?;
    validate_fields(right.fields())?;
    Ok(Schema::new_with_metadata(
        merge_fields(left.fields(), right.fields(), root_case_sensitive)?,
        left.metadata().clone(),
    ))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SemanticType {
    Physical,
    Time(SparkTimeMetadata),
    Interval(SparkIntervalMetadata),
}

fn semantic_type(field: &Field) -> Result<SemanticType> {
    let invalid = |error| {
        plan_datafusion_err!(
            "Invalid Spark type metadata for field '{}': {error}",
            field.name()
        )
    };
    let time = field
        .metadata()
        .get(spec::SAIL_SPARK_TIME_METADATA_KEY)
        .map(|value| SparkTimeMetadata::from_json(value).map_err(invalid))
        .transpose()?;
    let interval = field
        .metadata()
        .get(spec::SAIL_SPARK_INTERVAL_METADATA_KEY)
        .map(|value| SparkIntervalMetadata::from_json(value).map_err(invalid))
        .transpose()?;
    if time.is_some() && interval.is_some() {
        return plan_err!(
            "Conflicting Spark TIME and interval metadata for field '{}'",
            field.name()
        );
    }
    if let Some(time) = time {
        if field.data_type() != &DataType::Time64(TimeUnit::Nanosecond) {
            return plan_err!(
                "Spark TIME metadata requires Time64(Nanosecond) for field '{}'",
                field.name()
            );
        }
        return Ok(SemanticType::Time(time));
    }
    if let Some(interval) = interval {
        let expected = match interval {
            SparkIntervalMetadata::YearMonth { .. } => DataType::Interval(IntervalUnit::YearMonth),
            SparkIntervalMetadata::DayTime { .. } => DataType::Duration(TimeUnit::Microsecond),
        };
        if field.data_type() != &expected {
            return plan_err!(
                "Spark interval metadata requires {expected} for field '{}'",
                field.name()
            );
        }
        return Ok(SemanticType::Interval(interval));
    }
    let unit = match field.data_type() {
        DataType::Time64(TimeUnit::Nanosecond) => {
            return plan_err!(
                "Spark TIME precision metadata is required for field '{}'",
                field.name()
            );
        }
        DataType::Interval(IntervalUnit::YearMonth) => spec::IntervalUnit::YearMonth,
        DataType::Duration(TimeUnit::Microsecond) => spec::IntervalUnit::DayTime,
        _ => return Ok(SemanticType::Physical),
    };
    let interval = SparkIntervalMetadata::try_new(unit, None, None)
        .map_err(invalid)?
        .ok_or_else(|| {
            plan_datafusion_err!(
                "Missing Spark interval qualifiers for field '{}'",
                field.name()
            )
        })?;
    Ok(SemanticType::Interval(interval))
}

fn validate_fields(fields: &Fields) -> Result<()> {
    for field in fields {
        validate_field(field)?;
    }
    Ok(())
}

fn validate_field(field: &Field) -> Result<()> {
    if field
        .metadata()
        .contains_key(spec::SAIL_SPARK_UDT_METADATA_KEY)
    {
        return not_impl_err!(
            "Spark file schema merge does not support UDT field '{}'",
            field.name()
        );
    }
    if field.metadata().contains_key(EXTENSION_TYPE_NAME_KEY)
        || field.metadata().contains_key(EXTENSION_TYPE_METADATA_KEY)
        || is_variant_storage_field(field)
    {
        return not_impl_err!(
            "Spark file schema merge does not support extension or Variant field '{}'",
            field.name()
        );
    }
    semantic_type(field)?;
    match field.data_type() {
        DataType::Struct(fields) => validate_fields(fields),
        DataType::List(element) => validate_field(element),
        DataType::Map(entries, _) => {
            map_fields(entries)?;
            validate_field(entries)
        }
        DataType::Null
        | DataType::Boolean
        | DataType::Int8
        | DataType::Int16
        | DataType::Int32
        | DataType::Int64
        | DataType::Float32
        | DataType::Float64
        | DataType::Utf8
        | DataType::Binary
        | DataType::Date32
        | DataType::Time64(TimeUnit::Nanosecond)
        | DataType::Timestamp(TimeUnit::Microsecond, _)
        | DataType::Interval(IntervalUnit::YearMonth | IntervalUnit::MonthDayNano)
        | DataType::Duration(TimeUnit::Microsecond) => Ok(()),
        DataType::Decimal128(precision, scale)
            if (1..=38).contains(precision) && i16::from(*scale) <= i16::from(*precision) =>
        {
            Ok(())
        }
        other => not_impl_err!(
            "Spark file schema merge requires a normalized supported type for field '{}', found {other}",
            field.name()
        ),
    }
}

fn map_fields(entries: &Field) -> Result<&Fields> {
    let DataType::Struct(fields) = entries.data_type() else {
        return plan_err!("Spark map entries must be a STRUCT");
    };
    if fields.len() != 2 || entries.is_nullable() || fields[0].is_nullable() {
        return plan_err!(
            "Spark map requires non-null entries with one non-null key and one value"
        );
    }
    Ok(fields)
}

fn normalized_name(name: &str, case_sensitive: bool) -> String {
    if case_sensitive {
        name.to_string()
    } else {
        name.to_lowercase()
    }
}

fn merge_fields(left: &Fields, right: &Fields, case_sensitive: bool) -> Result<Fields> {
    let right_by_name: HashMap<_, _> = right
        .iter()
        .map(|field| (normalized_name(field.name(), case_sensitive), field))
        .collect();
    let left_names: HashSet<_> = left
        .iter()
        .map(|field| normalized_name(field.name(), case_sensitive))
        .collect();
    let mut fields = Vec::with_capacity(left.len() + right.len());
    for field in left {
        fields.push(
            match right_by_name.get(&normalized_name(field.name(), case_sensitive)) {
                Some(other) => merge_field(field, other)?,
                None => Arc::clone(field),
            },
        );
    }
    fields.extend(
        right
            .iter()
            .filter(|field| !left_names.contains(&normalized_name(field.name(), case_sensitive)))
            .cloned(),
    );
    Ok(fields.into())
}

fn merge_field(left: &Field, right: &Field) -> Result<FieldRef> {
    let left_semantic = semantic_type(left)?;
    let right_semantic = semantic_type(right)?;
    let mut field = left
        .clone()
        .with_nullable(left.is_nullable() || right.is_nullable());
    match (left_semantic, right_semantic) {
        (SemanticType::Physical, SemanticType::Physical) => {
            field = field.with_data_type(merge_type(left.data_type(), right.data_type())?);
        }
        (SemanticType::Time(left_time), SemanticType::Time(right_time))
            if left_time == right_time => {}
        (SemanticType::Interval(left_interval), SemanticType::Interval(right_interval)) => {
            let Some(interval) = left_interval.wider(right_interval) else {
                return incompatible(left, right, left_semantic, right_semantic);
            };
            if interval != left_interval {
                field.metadata_mut().insert(
                    spec::SAIL_SPARK_INTERVAL_METADATA_KEY.to_string(),
                    interval.to_json().map_err(|error| {
                        plan_datafusion_err!("Invalid merged Spark interval: {error}")
                    })?,
                );
            }
        }
        _ => return incompatible(left, right, left_semantic, right_semantic),
    }
    Ok(Arc::new(field))
}

fn incompatible(
    left: &Field,
    right: &Field,
    left_semantic: SemanticType,
    right_semantic: SemanticType,
) -> Result<FieldRef> {
    plan_err!(
        "Cannot merge incompatible Spark file types for field '{}': {} ({left_semantic:?}) and {} ({right_semantic:?})",
        left.name(),
        left.data_type(),
        right.data_type()
    )
}

fn merge_type(left: &DataType, right: &DataType) -> Result<DataType> {
    Ok(match (left, right) {
        (DataType::Struct(left), DataType::Struct(right)) => {
            // Spark StructType.merge resets the policy when merging matched field types.
            DataType::Struct(merge_fields(left, right, true)?)
        }
        (DataType::List(left), DataType::List(right)) => DataType::List(merge_field(left, right)?),
        (DataType::Map(left, sorted), DataType::Map(right, _)) => {
            let left_fields = map_fields(left)?;
            let right_fields = map_fields(right)?;
            let fields = vec![
                merge_field(&left_fields[0], &right_fields[0])?,
                merge_field(&left_fields[1], &right_fields[1])?,
            ];
            DataType::Map(
                Arc::new(
                    left.as_ref()
                        .clone()
                        .with_data_type(DataType::Struct(fields.into())),
                ),
                *sorted,
            )
        }
        (
            DataType::Decimal128(left_precision, left_scale),
            DataType::Decimal128(right_precision, right_scale),
        ) if left_scale == right_scale => {
            DataType::Decimal128(*left_precision.max(right_precision), *left_scale)
        }
        _ if left == right => left.clone(),
        _ => return plan_err!("Cannot merge incompatible Spark file types {left} and {right}"),
    })
}

#[cfg(test)]
#[path = "schema_merge_tests.rs"]
mod tests;
