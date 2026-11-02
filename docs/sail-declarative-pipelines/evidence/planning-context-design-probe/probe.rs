//! Design-only characterization; this module is not offered for product import.
use std::sync::Arc;

use arrow::array::{Int32Array, RecordBatch};
use arrow::datatypes::{DataType, Field, Schema};
use datafusion::execution::SessionStateBuilder;
use datafusion::logical_expr::{
    ColumnarValue, LogicalPlan, SetVariable, Statement, Volatility, create_udf,
};
use datafusion::prelude::{SessionConfig, SessionContext};
use datafusion_common::ScalarValue;

type TestResult = Result<(), Box<dyn std::error::Error>>;
fn batch() -> Result<RecordBatch, arrow::error::ArrowError> {
    RecordBatch::try_new(
        Arc::new(Schema::new(vec![Field::new("id", DataType::Int32, false)])),
        vec![Arc::new(Int32Array::from(vec![1]))],
    )
}
fn udf(name: &str) -> datafusion::logical_expr::ScalarUDF {
    create_udf(
        name,
        vec![],
        DataType::Int32,
        Volatility::Immutable,
        Arc::new(|_| Ok(ColumnarValue::Scalar(ScalarValue::Int32(Some(7))))),
    )
}

#[tokio::test]
async fn snapshot_catalog_sharing_does_not_make_session_mutations_authoritative() -> TestResult {
    let parent = SessionContext::new_with_config(SessionConfig::new().with_target_partitions(7));
    parent.register_batch("anchor", batch()?)?;
    let child = SessionContext::new_with_state(
        SessionStateBuilder::new_from_existing(parent.state()).build(),
    );
    assert_ne!(parent.session_id(), child.session_id());
    assert!(!child.state().config().create_default_catalog_and_schema());
    assert!(Arc::ptr_eq(
        parent.state().catalog_list(),
        child.state().catalog_list()
    ));
    child.register_batch("child_table", batch()?)?;
    assert!(parent.table_exist("child_table")?);
    child
        .execute_logical_plan(LogicalPlan::Statement(Statement::SetVariable(
            SetVariable {
                variable: "datafusion.execution.target_partitions".into(),
                value: "9".into(),
            },
        )))
        .await?
        .collect()
        .await?;
    assert_eq!(child.state().config().target_partitions(), 9);
    assert_eq!(parent.state().config().target_partitions(), 7);
    child.register_udf(udf("child_only"));
    assert!(child.state().scalar_functions().contains_key("child_only"));
    assert!(!parent.state().scalar_functions().contains_key("child_only"));
    println!(
        "DESIGN_PROBE {}",
        serde_json::json!({"case":"snapshot_mutations", "catalog_shared":true,"child_table_visible_in_parent":true,"child_set":9,"parent_set":7,"child_udf_visible_in_parent":false,"session_id_preserved_by_default":false})
    );
    Ok(())
}

#[tokio::test]
async fn restoring_create_default_before_build_replaces_the_shared_catalog() -> TestResult {
    let parent = SessionContext::new();
    parent.register_batch("anchor", batch()?)?;
    let snapshot = parent.state();
    let config = snapshot.config().clone();
    let name = config.options().catalog.default_catalog.clone();
    let before = snapshot
        .catalog_list()
        .catalog(&name)
        .ok_or("default catalog missing")?;
    assert!(parent.table_exist("anchor")?);
    let _child = SessionContext::new_with_state(
        SessionStateBuilder::new_from_existing(snapshot)
            .with_config(config)
            .build(),
    );
    let after = parent
        .state()
        .catalog_list()
        .catalog(&name)
        .ok_or("catalog removed")?;
    assert!(!Arc::ptr_eq(&before, &after));
    assert!(!parent.table_exist("anchor")?);
    println!(
        "DESIGN_PROBE {}",
        serde_json::json!({"case":"prebuild_config_restore","shared_default_catalog_replaced":true,"parent_anchor_retained":false})
    );
    Ok(())
}

#[tokio::test]
async fn postbuild_config_restore_preserves_catalog_but_still_has_separate_state() -> TestResult {
    let parent = SessionContext::new_with_config(SessionConfig::new().with_target_partitions(7));
    parent.register_batch("anchor", batch()?)?;
    parent.register_udf(udf("parent_udf"));
    let snapshot = parent.state();
    let config = snapshot.config().clone();
    let id = snapshot.session_id().to_string();
    let mut state = SessionStateBuilder::new_from_existing(snapshot)
        .with_session_id(id)
        .build();
    *state.config_mut() = config;
    let child = SessionContext::new_with_state(state);
    assert_eq!(child.session_id(), parent.session_id());
    assert!(child.state().config().create_default_catalog_and_schema());
    assert_eq!(child.state().config().target_partitions(), 7);
    assert!(parent.table_exist("anchor")?);
    assert!(child.table_exist("anchor")?);
    assert!(!Arc::ptr_eq(&parent.state_ref(), &child.state_ref()));
    assert!(Arc::ptr_eq(
        parent.state().runtime_env(),
        child.state().runtime_env()
    ));
    assert!(Arc::ptr_eq(
        parent
            .state()
            .scalar_functions()
            .get("parent_udf")
            .ok_or("parent udf")?,
        child
            .state()
            .scalar_functions()
            .get("parent_udf")
            .ok_or("child udf")?
    ));
    child
        .execute_logical_plan(LogicalPlan::Statement(Statement::SetVariable(
            SetVariable {
                variable: "datafusion.execution.target_partitions".into(),
                value: "9".into(),
            },
        )))
        .await?
        .collect()
        .await?;
    assert_eq!(parent.state().config().target_partitions(), 7);
    println!(
        "DESIGN_PROBE {}",
        serde_json::json!({"case":"postbuild_config_restore","catalog_retained":true,"session_id_retained":true,"runtime_shared":true,"udf_arc_shared":true,"state_arc_shared":false,"parent_set_after_child_set":7})
    );
    Ok(())
}
