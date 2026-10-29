use std::ops::{Div, Mul};
use std::sync::Arc;

use arrow::datatypes::{DataType, Field, Fields, IntervalUnit, TimeUnit};
use datafusion_common::{DFSchemaRef, ScalarValue};
use datafusion_expr::{ExprSchemable, ScalarUDF, cast, expr, lit, try_cast};
use sail_common::spec;
use sail_common::utils::datetime::time_unit_to_multiplier;
use sail_common_datafusion::extension::SessionExtensionAccessor;
use sail_common_datafusion::session::plan::PlanService;
use sail_common_datafusion::utils::items::ItemTaker;
use sail_common_datafusion::variant::is_variant_storage_field;
use sail_function::scalar::datetime::spark_date::SparkDate;
use sail_function::scalar::datetime::spark_interval::{
    SparkCalendarInterval, SparkDayTimeInterval, SparkYearMonthInterval, YearMonthIntervalMonths,
};
use sail_function::scalar::datetime::spark_timestamp::SparkTimestamp;
use sail_function::scalar::datetime::timestamp_cast::{
    cast_timestamp_ltz_to_ntz, cast_timestamp_ntz_to_ltz,
};
use sail_function::scalar::spark_ansi_string_cast::SparkAnsiStringCast;
use sail_function::scalar::spark_cast_string_to_int32::SparkCastStringToInt32;
use sail_function::scalar::spark_struct_rename::SparkStructRename;
use sail_function::scalar::spark_to_string::{SparkToLargeUtf8, SparkToUtf8, SparkToUtf8View};
use sail_function::scalar::variant::spark_cast_to_variant::SparkCastToVariant;
use sail_function::scalar::variant::spark_variant_get::SparkVariantGet;
use sail_function::scalar::variant::spark_variant_to_json::SparkVariantToJsonUdf;

use crate::error::{PlanError, PlanResult};
use crate::resolver::PlanResolver;
use crate::resolver::expression::NamedExpr;
use crate::resolver::expression::predicate::spark_interval_metadata_for_expression;
use crate::resolver::state::PlanResolverState;

impl PlanResolver<'_> {
    pub(super) async fn resolve_expression_cast(
        &self,
        expr: spec::Expr,
        cast_to_type: spec::DataType,
        _rename: bool,
        is_try: bool,
        schema: &DFSchemaRef,
        state: &mut PlanResolverState,
    ) -> PlanResult<NamedExpr> {
        if let spec::DataType::UserDefined {
            jvm_class,
            python_class,
            ..
        } = &cast_to_type
        {
            let resolved = self
                .resolve_named_expression(expr.clone(), schema, state)
                .await?;
            let field = resolved.expr.to_field(schema)?.1;
            if let Some(metadata) = field.metadata().get(spec::SAIL_SPARK_UDT_METADATA_KEY) {
                let source: spec::SparkUdtMetadata = serde_json::from_str(metadata)
                    .map_err(|e| PlanError::internal(format!("invalid UDT metadata: {e}")))?;
                let same_type = match (&source.jvm_class, jvm_class) {
                    (Some(source), Some(target)) => source == target,
                    (None, None) => {
                        source.python_class.is_some() && source.python_class == *python_class
                    }
                    _ => false,
                };
                if same_type {
                    return Ok(resolved);
                }
                // Different JVM UDTs can accept each other's user classes through
                // inheritance. Without that hierarchy, leave them unsupported.
                if source.jvm_class.is_none() || jvm_class.is_none() {
                    return Err(PlanError::analysis(
                        "cannot cast between incompatible user-defined types",
                    ));
                }
            }
        }

        // CAST(expr AS VARIANT) → rewrite to SparkCastToVariant UDF
        // Must intercept before resolve_data_type converts Variant to Struct.
        if matches!(cast_to_type, spec::DataType::Variant) {
            let NamedExpr { expr, name, .. } =
                self.resolve_named_expression(expr, schema, state).await?;
            let name = if need_rename_cast(&expr) {
                let prefix = if is_try { "TRY_" } else { "" };
                vec![format!("{}CAST({} AS VARIANT)", prefix, name.one()?)]
            } else {
                name
            };
            let expr = ScalarUDF::new_from_impl(SparkCastToVariant::new()).call(vec![expr]);
            return Ok(NamedExpr::new(name, expr));
        }

        // Extract the DayTimeInterval field unit before resolving to Arrow type,
        // since it determines the multiplier for numeric-to-interval casts.
        // Spark uses the end field (or start field for single-field intervals)
        // to interpret the numeric value: e.g. DayTimeIntervalType(DAY, DAY) treats
        // the value as days, while DayTimeIntervalType(DAY, SECOND) treats it as seconds.
        let day_time_interval_field = match &cast_to_type {
            spec::DataType::Interval {
                interval_unit: spec::IntervalUnit::DayTime,
                start_field,
                end_field,
            } => end_field.or(*start_field),
            _ => None,
        };
        let spark_interval_metadata = match &cast_to_type {
            spec::DataType::Interval {
                interval_unit,
                start_field,
                end_field,
            } => spec::SparkIntervalMetadata::try_new(*interval_unit, *start_field, *end_field)?
                .map(spec::SparkIntervalMetadata::to_json)
                .transpose()?,
            _ => None,
        };
        let spark_time_metadata = match &cast_to_type {
            spec::DataType::Time { precision } => {
                Some(spec::SparkTimeMetadata::try_new(*precision)?)
            }
            _ => None,
        };
        let cast_to_type = self.resolve_data_type(&cast_to_type, state)?;
        let NamedExpr { expr, name, .. } =
            self.resolve_named_expression(expr, schema, state).await?;
        let expr_field = expr.to_field(schema)?.1;
        let expr_type = expr_field.data_type().clone();
        let source_time_precision = if spark_time_metadata.is_some() {
            time_cast_source_precision(expr_field.as_ref())?
        } else {
            None
        };
        let expr_is_variant = is_variant_storage_field(expr_field.as_ref());
        let name = if need_rename_cast(&expr) {
            let service = self.ctx.extension::<PlanService>()?;
            let data_type_string = match spark_time_metadata {
                Some(metadata) => format!("time({})", metadata.precision()),
                None => service
                    .plan_formatter()
                    .data_type_to_simple_string(&cast_to_type)?,
            };
            vec![format!(
                "{}CAST({} AS {})",
                if is_try { "TRY_" } else { "" },
                name.one()?,
                data_type_string.to_ascii_uppercase()
            )]
        } else {
            name
        };
        let override_string_cast = matches!(
            expr_type,
            DataType::Date32
                | DataType::Date64
                | DataType::Time32(_)
                | DataType::Time64(_)
                | DataType::Duration(_)
                | DataType::Interval(_)
                | DataType::Timestamp(_, _)
                | DataType::List(_)
                | DataType::LargeList(_)
                | DataType::FixedSizeList(_, _)
                | DataType::ListView(_)
                | DataType::LargeListView(_)
                | DataType::Struct(_)
                | DataType::Map(_, _)
        );
        // Spark renders TIMESTAMP in the session time zone, whatever zone labels the values.
        let session_timezone = self.config.session_timezone_label();
        let expr = match (expr_type, cast_to_type.clone(), is_try) {
            (DataType::Time32(_) | DataType::Time64(_), _, _)
                if spark_time_metadata.is_some() =>
            {
                let target_precision = spark_time_metadata
                    .ok_or_else(|| PlanError::internal("missing TIME cast precision"))?
                    .precision();
                let nanos = cast(expr, DataType::Time64(TimeUnit::Nanosecond));
                if source_time_precision == Some(target_precision) {
                    // Spark's identity cast retains sub-precision bits. Declared
                    // precision alone does not constrain the stored value.
                    nanos
                } else {
                    let factor = 10_i64.pow(9 - target_precision as u32);
                    let truncated = cast(nanos, DataType::Int64)
                        .div(lit(factor))
                        .mul(lit(factor));
                    cast(truncated, cast_to_type)
                }
            }
            (
                DataType::Timestamp(_, None),
                DataType::Timestamp(TimeUnit::Microsecond, Some(timezone)),
                is_try,
            ) => cast_timestamp_ntz_to_ltz(expr, &timezone, is_try),
            (DataType::Timestamp(_, Some(_)), DataType::Timestamp(unit, None), is_try) => {
                let local = cast_timestamp_ltz_to_ntz(expr, &session_timezone, is_try);
                if unit == TimeUnit::Microsecond {
                    local
                } else {
                    cast(local, cast_to_type)
                }
            }
            // Spark takes the date in the session time zone, whatever zone labels the values. The
            // analyzer converts a cast, and unwraps it in a comparison with a DATE constant, but
            // not a `try_cast`.
            (DataType::Timestamp(unit, Some(_)), DataType::Date32, true) => try_cast(
                cast(
                    expr,
                    DataType::Timestamp(unit, Some(Arc::clone(&session_timezone))),
                ),
                DataType::Date32,
            ),
            (_, DataType::Utf8, _) if expr_is_variant => cast(
                ScalarUDF::new_from_impl(SparkVariantToJsonUdf::new()).call(vec![expr]),
                DataType::Utf8,
            ),
            (_, DataType::LargeUtf8, _) if expr_is_variant => cast(
                ScalarUDF::new_from_impl(SparkVariantToJsonUdf::new()).call(vec![expr]),
                DataType::LargeUtf8,
            ),
            (_, DataType::Utf8View, _) if expr_is_variant => {
                ScalarUDF::new_from_impl(SparkVariantToJsonUdf::new()).call(vec![expr])
            }
            (_, to, is_try) if expr_is_variant => {
                let service = self.ctx.extension::<PlanService>()?;
                let data_type_string = service.plan_formatter().data_type_to_simple_string(&to)?;
                ScalarUDF::new_from_impl(SparkVariantGet::new(is_try)).call(vec![
                    expr,
                    lit("$"),
                    lit(data_type_string),
                ])
            }
            (DataType::Utf8 | DataType::LargeUtf8 | DataType::Utf8View, to, false)
                if self.config.ansi_mode && SparkAnsiStringCast::target_name(&to).is_some() =>
            {
                let sql_target = SparkAnsiStringCast::target_name(&to)
                    .ok_or_else(|| PlanError::internal("missing ANSI cast target name"))?;
                ScalarUDF::new_from_impl(SparkAnsiStringCast::try_new(to, sql_target.into())?)
                    .call(vec![expr])
            }
            (DataType::Utf8 | DataType::LargeUtf8 | DataType::Utf8View, DataType::Int32, false)
                if !self.config.ansi_mode =>
            {
                ScalarUDF::new_from_impl(SparkCastStringToInt32::new()).call(vec![expr])
            }
            (from, DataType::Timestamp(time_unit, _) | DataType::Duration(time_unit), _)
                if from.is_numeric() =>
            {
                let multiplier = match (day_time_interval_field, &cast_to_type) {
                    (Some(field), DataType::Duration(_)) => day_time_field_to_microseconds(field),
                    _ => time_unit_to_multiplier(&time_unit),
                };
                cast(expr.mul(lit(multiplier)), cast_to_type)
            }
            (DataType::Timestamp(time_unit, _) | DataType::Duration(time_unit), to, _)
                if to.is_numeric() =>
            {
                cast(
                    lit(1.0)
                        .div(lit(time_unit_to_multiplier(&time_unit)))
                        .mul(cast(expr, DataType::Int64)),
                    to,
                )
            }
            (DataType::Interval(IntervalUnit::YearMonth), to, is_try) if to.is_integer() => {
                let interval_metadata = expr_field
                    .metadata()
                    .get(spec::SAIL_SPARK_INTERVAL_METADATA_KEY)
                    .map(|value| spec::SparkIntervalMetadata::from_json(value))
                    .transpose()?;
                let months = ScalarUDF::from(YearMonthIntervalMonths::new()).call(vec![expr]);
                let value = if matches!(
                    interval_metadata,
                    Some(spec::SparkIntervalMetadata::YearMonth {
                        end_field: spec::YearMonthIntervalField::Year,
                        ..
                    })
                ) {
                    months / lit(12_i32)
                } else {
                    months
                };
                if is_try {
                    try_cast(value, to)
                } else {
                    cast(value, to)
                }
            }
            (
                DataType::Utf8 | DataType::LargeUtf8 | DataType::Utf8View,
                DataType::Interval(IntervalUnit::YearMonth),
                _,
            ) => ScalarUDF::new_from_impl(SparkYearMonthInterval::new()).call(vec![expr]),
            (
                DataType::Utf8 | DataType::LargeUtf8 | DataType::Utf8View,
                DataType::Duration(TimeUnit::Microsecond),
                _,
            ) => ScalarUDF::new_from_impl(SparkDayTimeInterval::new()).call(vec![expr]),
            (
                DataType::Utf8 | DataType::LargeUtf8 | DataType::Utf8View,
                DataType::Interval(IntervalUnit::MonthDayNano),
                _,
            ) => ScalarUDF::new_from_impl(SparkCalendarInterval::new()).call(vec![expr]),
            (
                DataType::Utf8 | DataType::LargeUtf8 | DataType::Utf8View,
                DataType::Date32,
                is_try,
            ) => ScalarUDF::new_from_impl(SparkDate::new(is_try || !self.config.ansi_mode))
                .call(vec![expr]),
            (
                DataType::Utf8 | DataType::LargeUtf8 | DataType::Utf8View,
                DataType::Timestamp(TimeUnit::Microsecond, tz),
                is_try,
            ) => Arc::new(ScalarUDF::new_from_impl(SparkTimestamp::try_new(
                tz,
                self.config.ansi_mode,
                is_try,
            )?))
            .call(vec![expr]),
            (_, DataType::Utf8, _) if override_string_cast => {
                ScalarUDF::new_from_impl(SparkToUtf8::new().with_timezone(Some(session_timezone)))
                    .call(spark_string_cast_arguments(expr, schema)?)
            }
            (_, DataType::LargeUtf8, _) if override_string_cast => ScalarUDF::new_from_impl(
                SparkToLargeUtf8::new().with_timezone(Some(session_timezone)),
            )
            .call(spark_string_cast_arguments(expr, schema)?),
            (_, DataType::Utf8View, _) if override_string_cast => ScalarUDF::new_from_impl(
                SparkToUtf8View::new().with_timezone(Some(session_timezone)),
            )
            .call(spark_string_cast_arguments(expr, schema)?),
            (DataType::Date32 | DataType::Date64, to, _)
                if to.is_numeric() || matches!(to, DataType::Boolean) =>
            {
                if !is_try && self.config.ansi_mode {
                    return Err(PlanError::invalid(format!("cannot cast date to {to}")));
                }
                lit(ScalarValue::try_from(&to)?)
            }
            (from, to, _) if needs_struct_field_rename(&from, &to) => {
                // Pre-rename the source struct fields positionally so the cast
                // becomes a no-op or a valid name-matched one (see
                // `needs_struct_field_rename`).
                let renamed_target = build_rename_target_type(&from, &to);
                let renamed =
                    ScalarUDF::new_from_impl(SparkStructRename::new(renamed_target.clone()))
                        .call(vec![expr]);
                if renamed_target == to {
                    renamed
                } else if is_try {
                    try_cast(renamed, to)
                } else {
                    cast(renamed, to)
                }
            }
            (
                from,
                DataType::Decimal128(precision, scale) | DataType::Decimal256(precision, scale),
                _,
            ) if from.is_numeric()
                && !self.config.ansi_mode
                && (is_try || decimal_cast_can_overflow(&from, precision, scale)) =>
            {
                try_cast(expr, cast_to_type)
            }
            (
                DataType::Utf8 | DataType::LargeUtf8 | DataType::Utf8View,
                DataType::Decimal128(..) | DataType::Decimal256(..),
                _,
            ) if !self.config.ansi_mode => try_cast(expr, cast_to_type),
            (_, to, true) => try_cast(expr, to),
            (_, to, _) => cast(expr, to),
        };
        let mut target_metadata = vec![];
        if let Some(metadata) = spark_interval_metadata {
            target_metadata.push((spec::SAIL_SPARK_INTERVAL_METADATA_KEY.to_string(), metadata));
        }
        if let Some(metadata) = spark_time_metadata {
            target_metadata.push((
                spec::SAIL_SPARK_TIME_METADATA_KEY.to_string(),
                metadata.to_json()?,
            ));
        }
        if target_metadata.is_empty()
            && !expr_field
                .metadata()
                .contains_key(spec::SAIL_SPARK_TIME_METADATA_KEY)
        {
            return Ok(NamedExpr::new(name, expr));
        }
        let field = expr.to_field(schema)?.1;
        let mut field_metadata = field.metadata().clone();
        // A type-only Arrow cast inherits source metadata. TIME describes the
        // target Spark type, so replacing it also removes it when casting away.
        field_metadata.remove(spec::SAIL_SPARK_TIME_METADATA_KEY);
        field_metadata.extend(target_metadata.iter().cloned());
        let expr = if field_metadata != *field.metadata() || !target_metadata.is_empty() {
            // Nested expressions consume the Expr without its NamedExpr metadata.
            // Keep the target metadata on the cast field as well as the projection.
            let field = Arc::new(field.as_ref().clone().with_metadata(field_metadata));
            match expr {
                expr::Expr::Cast(cast) => {
                    expr::Expr::Cast(expr::Cast::new_from_field(cast.expr, field))
                }
                expr::Expr::TryCast(cast) => {
                    expr::Expr::TryCast(expr::TryCast::new_from_field(cast.expr, field))
                }
                expr => expr::Expr::Cast(expr::Cast::new_from_field(Box::new(expr), field)),
            }
        } else {
            expr
        };
        Ok(NamedExpr::new(name, expr).with_metadata(target_metadata))
    }
}

fn time_cast_source_precision(field: &Field) -> PlanResult<Option<i32>> {
    if let Some(metadata) = field.metadata().get(spec::SAIL_SPARK_TIME_METADATA_KEY) {
        let metadata = spec::SparkTimeMetadata::from_json(metadata)?;
        if field.data_type() != &DataType::Time64(TimeUnit::Nanosecond) {
            return Err(PlanError::invalid(
                "Spark TIME metadata requires Arrow Time64(Nanosecond)",
            ));
        }
        return Ok(Some(metadata.precision()));
    }
    // Keep the existing raw Arrow TIME unit semantics when the input has no
    // Spark annotation. Only the target is converted to the semantic type.
    Ok(match field.data_type() {
        DataType::Time32(TimeUnit::Second) => Some(0),
        DataType::Time32(TimeUnit::Millisecond) => Some(3),
        DataType::Time64(TimeUnit::Microsecond) => Some(6),
        DataType::Time64(TimeUnit::Nanosecond) => Some(9),
        _ => None,
    })
}

fn decimal_cast_can_overflow(from: &DataType, precision: u8, scale: i8) -> bool {
    let integer_digits = i16::from(precision) - i16::from(scale);
    match from {
        DataType::Decimal128(from_precision, from_scale)
        | DataType::Decimal256(from_precision, from_scale) => {
            let source_integer_digits = i16::from(*from_precision) - i16::from(*from_scale);
            integer_digits < source_integer_digits
                || (integer_digits == source_integer_digits && scale < *from_scale)
        }
        DataType::Int8 | DataType::UInt8 => scale < 0 || integer_digits < 3,
        DataType::Int16 | DataType::UInt16 => scale < 0 || integer_digits < 5,
        DataType::Int32 | DataType::UInt32 => scale < 0 || integer_digits < 10,
        DataType::Int64 | DataType::UInt64 => scale < 0 || integer_digits < 20,
        _ => true,
    }
}

fn spark_string_cast_arguments(
    expr: expr::Expr,
    schema: &DFSchemaRef,
) -> PlanResult<Vec<expr::Expr>> {
    let interval = spark_interval_metadata_for_expression(&expr, schema)?;
    let mut arguments = vec![expr];
    if let Some(interval) = interval {
        // Physical expression serialization does not preserve intermediate field metadata.
        arguments.push(lit(interval.to_json()?));
    }
    Ok(arguments)
}

/// Returns true if the cast from `from` to `to` involves a Struct
/// (possibly nested in a List/LargeList/FixedSizeList/Map) whose field names
/// don't share enough overlap for DataFusion's struct cast validator.
fn needs_struct_field_rename(from: &DataType, to: &DataType) -> bool {
    match (from, to) {
        (DataType::Struct(a), DataType::Struct(b)) => {
            a.len() == b.len()
                && a.iter()
                    .zip(b.iter())
                    .any(|(fa, fb)| fa.name() != fb.name())
        }
        (DataType::List(a), DataType::List(b))
        | (DataType::LargeList(a), DataType::LargeList(b)) => {
            needs_struct_field_rename(a.data_type(), b.data_type())
        }
        (DataType::FixedSizeList(a, sa), DataType::FixedSizeList(b, sb)) if sa == sb => {
            needs_struct_field_rename(a.data_type(), b.data_type())
        }
        (DataType::Map(a, _), DataType::Map(b, _)) => {
            needs_struct_field_rename(a.data_type(), b.data_type())
        }
        _ => false,
    }
}

/// Build a target type that has the names from `to` but the data types from
/// `from`. The result is what `SparkStructRename` produces; the subsequent
/// regular CAST then handles any leaf-type conversion.
fn build_rename_target_type(from: &DataType, to: &DataType) -> DataType {
    match (from, to) {
        (DataType::Struct(src_fields), DataType::Struct(tgt_fields))
            if src_fields.len() == tgt_fields.len() =>
        {
            let fields: Fields = src_fields
                .iter()
                .zip(tgt_fields.iter())
                .map(|(src, tgt)| {
                    Arc::new(
                        Field::new(
                            tgt.name(),
                            build_rename_target_type(src.data_type(), tgt.data_type()),
                            src.is_nullable(),
                        )
                        .with_metadata(src.metadata().clone()),
                    )
                })
                .collect();
            DataType::Struct(fields)
        }
        (DataType::List(src), DataType::List(tgt)) => DataType::List(Arc::new(
            Field::new(
                tgt.name(),
                build_rename_target_type(src.data_type(), tgt.data_type()),
                src.is_nullable(),
            )
            .with_metadata(src.metadata().clone()),
        )),
        (DataType::LargeList(src), DataType::LargeList(tgt)) => DataType::LargeList(Arc::new(
            Field::new(
                tgt.name(),
                build_rename_target_type(src.data_type(), tgt.data_type()),
                src.is_nullable(),
            )
            .with_metadata(src.metadata().clone()),
        )),
        (DataType::FixedSizeList(src, sa), DataType::FixedSizeList(tgt, _)) => {
            DataType::FixedSizeList(
                Arc::new(
                    Field::new(
                        tgt.name(),
                        build_rename_target_type(src.data_type(), tgt.data_type()),
                        src.is_nullable(),
                    )
                    .with_metadata(src.metadata().clone()),
                ),
                *sa,
            )
        }
        (DataType::Map(src, sorted), DataType::Map(tgt, _)) => DataType::Map(
            Arc::new(
                Field::new(
                    tgt.name(),
                    build_rename_target_type(src.data_type(), tgt.data_type()),
                    src.is_nullable(),
                )
                .with_metadata(src.metadata().clone()),
            ),
            *sorted,
        ),
        // Leaves: keep the source data type unchanged.
        _ => from.clone(),
    }
}

fn day_time_field_to_microseconds(field: spec::IntervalFieldType) -> i64 {
    match field {
        spec::IntervalFieldType::Day => 86_400_000_000,
        spec::IntervalFieldType::Hour => 3_600_000_000,
        spec::IntervalFieldType::Minute => 60_000_000,
        // Second, or Year/Month (shouldn't appear for DayTime intervals)
        _ => 1_000_000,
    }
}

fn need_rename_cast(expr: &expr::Expr) -> bool {
    match expr {
        expr::Expr::Alias(_) | expr::Expr::Column(_) | expr::Expr::OuterReferenceColumn(..) => {
            false
        }
        expr::Expr::ScalarFunction(function)
            if function.func.inner().is::<SparkAnsiStringCast>() =>
        {
            match function.args.as_slice() {
                [input] => need_rename_cast(input),
                _ => true,
            }
        }
        expr::Expr::Cast(cast) => need_rename_cast(cast.expr.as_ref()),
        expr::Expr::TryCast(try_cast) => need_rename_cast(try_cast.expr.as_ref()),
        _ => true,
    }
}

#[cfg(test)]
mod tests;
