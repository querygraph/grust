use std::sync::Arc;

use datafusion::arrow::datatypes::{DataType, Schema};
use datafusion::logical_expr::LogicalPlan;
use datafusion::prelude::SessionContext;
use sail_common::spec;
use sail_common_datafusion::catalog::TableColumnStatus;
use sail_common_datafusion::extension::SessionExtensionAccessor;
use sail_plan::resolver::PlanResolver;

use super::graph::{Output, analysis, quoted};
use super::schema_merge::merge_fields;
use crate::error::{SparkError, SparkResult};
use crate::proto::data_type::parse_spark_data_type;
use crate::session::SparkSession;
use crate::spark::connect::data_type::StructField;
use crate::spark::connect::pipeline_command::{DefineOutput, define_output as out};

pub(super) fn declared_schema(output: &DefineOutput) -> SparkResult<Option<spec::Schema>> {
    let Some(out::Details::TableDetails(details)) = &output.details else {
        return Ok(None);
    };
    let Some(schema) = &details.schema else {
        return Ok(None);
    };
    let data_type: spec::DataType = match schema {
        out::table_details::Schema::SchemaDataType(data_type) => data_type.clone().try_into()?,
        out::table_details::Schema::SchemaString(text) => parse_spark_data_type(text)?,
    };
    let spec::DataType::Struct { fields } = data_type else {
        return Err(SparkError::invalid(
            "a pipeline table schema must be a struct",
        ));
    };
    Ok(Some(spec::Schema { fields }))
}

pub(super) fn infer(
    ctx: &SessionContext,
    output: &Output,
    plans: &[LogicalPlan],
) -> SparkResult<Schema> {
    let inferred = plans
        .iter()
        .try_fold(spec::Fields::empty(), |fields, plan| {
            let result = spark_fields(plan.schema().as_arrow())
                .and_then(|next| merge_fields(&fields, &next));
            result.map_err(|error| {
                analysis(
                    "UNABLE_TO_INFER_PIPELINE_TABLE_SCHEMA",
                    format!("{}: {error}", quoted(&output.name)),
                )
            })
        })?;
    let resolver = PlanResolver::new(ctx, ctx.extension::<SparkSession>()?.plan_config()?);
    let Some(schema) = &output.schema else {
        return arrow_schema(&resolver, inferred);
    };
    let declared = arrow_schema(&resolver, schema.fields.clone())?;
    let declared_fields = spark_fields(&declared)?;
    let merged = merge_fields(&declared_fields, &inferred).map_err(|error| {
        analysis(
            "USER_SPECIFIED_AND_INFERRED_SCHEMA_NOT_COMPATIBLE",
            format!(
                "'{}' has a user-specified schema that is incompatible: specified {declared:?}, inferred {inferred:?}: {error}",
                output.name.join(".")
            ),
        )
    })?;
    // Spark validates the merged schema against the declaration after schema
    // inference. A successful merge alone still admits undeclared columns or
    // weaker nullability constraints.
    if merged != declared_fields {
        return Err(analysis(
            "USER_SPECIFIED_AND_INFERRED_SCHEMA_NOT_COMPATIBLE",
            format!(
                "'{}' has a user-specified schema that is incompatible: specified {declared:?}, inferred {inferred:?}",
                output.name.join(".")
            ),
        ));
    }
    Ok(declared)
}

fn spark_fields(schema: &Schema) -> SparkResult<spec::Fields> {
    // Reuse Spark's schema conversion to normalize Arrow representations such
    // as Utf8View and retain semantic types carried by extension metadata.
    schema
        .fields()
        .iter()
        .map(|field| spec::FieldRef::try_from(StructField::try_from(field.as_ref().clone())?))
        .collect()
}

pub(super) fn table_columns(
    output: &Output,
    inferred: &Schema,
) -> SparkResult<Vec<spec::TableColumnDefinition>> {
    columns_from_fields(&output_fields(output, inferred)?)
}

/// Ordinary streaming refresh retains existing fields and their metadata, then
/// appends newly inferred fields using Spark's StructType.merge contract.
pub(super) fn streaming_columns(
    output: &Output,
    inferred: &Schema,
    existing: &[TableColumnStatus],
) -> SparkResult<Vec<spec::TableColumnDefinition>> {
    let existing = existing
        .iter()
        .map(|column| spec::FieldRef::try_from(StructField::try_from(column.field())?))
        .collect::<SparkResult<spec::Fields>>()?;
    columns_from_fields(&merge_fields(&existing, &output_fields(output, inferred)?)?)
}

fn output_fields(output: &Output, inferred: &Schema) -> SparkResult<spec::Fields> {
    match &output.schema {
        Some(schema) => Ok(schema.fields.clone()),
        None => Ok(nullable_fields(&spark_fields(inferred)?)),
    }
}

fn columns_from_fields(fields: &spec::Fields) -> SparkResult<Vec<spec::TableColumnDefinition>> {
    fields
        .iter()
        .map(|field| {
            let metadata = field
                .metadata
                .iter()
                .find(|(key, _)| key == spec::SPARK_METADATA_JSON_KEY)
                .map(|(_, value)| serde_json::from_str::<serde_json::Value>(value))
                .transpose()?;
            let comment = metadata
                .as_ref()
                .and_then(|value| value.get("comment"))
                .and_then(serde_json::Value::as_str)
                .map(str::to_string);
            Ok(spec::TableColumnDefinition {
                name: field.name.clone(),
                data_type: field.data_type.clone(),
                nullable: field.nullable,
                comment,
                default: None,
                generated_always_as: None,
                identity: None,
            })
        })
        .collect()
}

fn nullable_fields(fields: &spec::Fields) -> spec::Fields {
    fields
        .iter()
        .map(|field| {
            let mut field = field.as_ref().clone();
            field.nullable = true;
            field.data_type = nullable_type(&field.data_type);
            Arc::new(field)
        })
        .collect()
}

fn nullable_type(data_type: &spec::DataType) -> spec::DataType {
    let mut data_type = data_type.clone();
    match &mut data_type {
        spec::DataType::Struct { fields } => *fields = nullable_fields(fields),
        spec::DataType::List {
            data_type,
            nullable,
        }
        | spec::DataType::LargeList {
            data_type,
            nullable,
        }
        | spec::DataType::FixedSizeList {
            data_type,
            nullable,
            ..
        } => {
            **data_type = nullable_type(data_type);
            *nullable = true;
        }
        spec::DataType::Map {
            key_type,
            value_type,
            value_type_nullable,
            ..
        } => {
            **key_type = nullable_type(key_type);
            **value_type = nullable_type(value_type);
            *value_type_nullable = true;
        }
        _ => {}
    }
    data_type
}

fn arrow_schema(resolver: &PlanResolver<'_>, fields: spec::Fields) -> SparkResult<Schema> {
    let data_type = resolver.resolve_data_type_for_plan(&spec::DataType::Struct { fields })?;
    let DataType::Struct(fields) = data_type else {
        return Err(SparkError::internal(
            "resolved pipeline schema is not a struct",
        ));
    };
    Ok(Schema::new(fields))
}
