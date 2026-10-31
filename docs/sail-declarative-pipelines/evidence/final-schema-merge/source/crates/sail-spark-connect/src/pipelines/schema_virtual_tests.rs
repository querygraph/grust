use std::collections::HashMap;
use std::sync::Arc;

use datafusion::arrow::datatypes::{DataType, Field, Schema};

use super::*;
use crate::pipelines::graph::PipelineGraph;
use crate::pipelines::sql;
use crate::spark::connect::pipeline_command as pc;

type TestResult<T = ()> = Result<T, Box<dyn std::error::Error>>;

async fn output(schema: &str) -> TestResult<Output> {
    let mut graph = PipelineGraph::new("test_catalog".into(), "test_db".into(), HashMap::new());
    sql::prepare(
        pc::DefineSqlGraphElements {
            sql_text: Some(format!("CREATE STREAMING TABLE target {schema}")),
            ..Default::default()
        },
        |_| async { Err(SparkError::internal("fixture has no catalog expression")) },
    )
    .await?
    .commit(&mut graph)?;
    graph
        .definition
        .outputs
        .pop()
        .ok_or_else(|| "fixture output missing".into())
}
fn incoming(data_type: DataType, nullable: bool) -> SchemaRef {
    Arc::new(Schema::new(vec![Field::new("id", data_type, nullable)]))
}

#[tokio::test]
async fn declared_load_does_not_merge_incompatible_producers() -> TestResult {
    let ctx = sql::tests::resolution_context()?;
    let output = output("(id INT NOT NULL COMMENT 'declared')").await?;
    let descriptor = VirtualTableSchema::new(
        &output,
        vec![
            incoming(DataType::Int32, false),
            incoming(DataType::Utf8, false),
        ],
    );
    let loaded = descriptor.load(&ctx)?;
    assert_eq!(loaded.field(0).data_type(), &DataType::Int32);
    assert!(!loaded.field(0).is_nullable());
    let metadata = loaded
        .field(0)
        .metadata()
        .get(spec::SPARK_METADATA_JSON_KEY)
        .ok_or("declared Spark metadata envelope missing")?;
    assert_eq!(
        serde_json::from_str::<serde_json::Value>(metadata)?,
        serde_json::json!({"comment":"declared"})
    );
    let error = descriptor
        .validate(&ctx)
        .err()
        .ok_or("incompatible producers validated")?;
    assert!(
        error
            .to_string()
            .contains("UNABLE_TO_INFER_PIPELINE_TABLE_SCHEMA")
    );
    assert_eq!(
        descriptor.load(&ctx)?,
        loaded,
        "failed compatibility validation mutated load semantics"
    );
    Ok(())
}

#[tokio::test]
async fn undeclared_load_reports_inference_error_without_fallback() -> TestResult {
    let ctx = sql::tests::resolution_context()?;
    let descriptor = VirtualTableSchema::new(
        &output("").await?,
        vec![
            incoming(DataType::Int32, false),
            incoming(DataType::Utf8, false),
        ],
    );
    assert!(
        descriptor
            .load(&ctx)
            .err()
            .ok_or("incompatible load supplied a fallback schema")?
            .to_string()
            .contains("UNABLE_TO_INFER_PIPELINE_TABLE_SCHEMA")
    );
    Ok(())
}

#[tokio::test]
async fn declaration_load_and_final_nullability_validation_are_distinct() -> TestResult {
    let ctx = sql::tests::resolution_context()?;
    let output = output("(id INT NOT NULL COMMENT 'declared')").await?;
    let valid = VirtualTableSchema::new(&output, vec![incoming(DataType::Int32, false)]);
    assert_eq!(valid.load(&ctx)?, valid.validate(&ctx)?);
    let nullable = VirtualTableSchema::new(&output, vec![incoming(DataType::Int32, true)]);
    assert!(!nullable.load(&ctx)?.field(0).is_nullable());
    assert!(
        nullable
            .validate(&ctx)
            .err()
            .ok_or("nullable producer accepted by NOT NULL declaration")?
            .to_string()
            .contains("USER_SPECIFIED_AND_INFERRED_SCHEMA_NOT_COMPATIBLE")
    );
    let undeclared = VirtualTableSchema::new(
        &self::output("").await?,
        vec![incoming(DataType::Int32, false)],
    );
    assert!(!undeclared.load(&ctx)?.field(0).is_nullable());
    Ok(())
}

#[tokio::test]
async fn final_forcing_exposes_merge_error_while_load_keeps_table_context() -> TestResult {
    let ctx = sql::tests::resolution_context()?;
    for declared in ["", "(id INT)"] {
        let descriptor = VirtualTableSchema::new(
            &output(declared).await?,
            vec![
                incoming(DataType::Int32, false),
                incoming(DataType::Utf8, false),
            ],
        );
        let SparkError::Structured(error) = descriptor
            .final_schema(&ctx)
            .err()
            .ok_or("final merge succeeded")?
        else {
            return Err("final forcing did not preserve structured merge error".into());
        };
        assert_eq!(error.condition, "CANNOT_MERGE_INCOMPATIBLE_DATA_TYPE");
        assert_eq!(error.sql_state, "42825");
        assert_eq!(error.class, "org.apache.spark.SparkException");
        assert!(error.to_string().ends_with("SQLSTATE: 42825"));
        assert_eq!(error.parameters["left"], "\"INT\"");
        assert_eq!(error.parameters["right"], "\"STRING\"");
        if declared.is_empty() {
            assert!(
                descriptor
                    .load(&ctx)
                    .err()
                    .ok_or("incompatible read succeeded")?
                    .to_string()
                    .contains("UNABLE_TO_INFER_PIPELINE_TABLE_SCHEMA")
            );
        } else {
            assert_eq!(
                descriptor.load(&ctx)?.field(0).data_type(),
                &DataType::Int32
            );
        }
    }
    Ok(())
}

#[tokio::test]
async fn final_schema_is_inferred_while_publication_keeps_declared_nullability() -> TestResult {
    let ctx = sql::tests::resolution_context()?;
    let output = output("(id INT)").await?;
    let descriptor = VirtualTableSchema::new(&output, vec![incoming(DataType::Int32, false)]);
    assert!(descriptor.load(&ctx)?.field(0).is_nullable());
    let inferred = descriptor.final_schema(&ctx)?;
    assert!(!inferred.field(0).is_nullable());
    assert!(table_columns(&output, &inferred)?[0].nullable);
    Ok(())
}
