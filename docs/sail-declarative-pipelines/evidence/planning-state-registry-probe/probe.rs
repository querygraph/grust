//! Design-only dependency characterization; not offered as a product module.
use std::sync::Arc;

use arrow::datatypes::DataType;
use datafusion::execution::SessionStateBuilder;
use datafusion::logical_expr::{
    ColumnarValue, Execute, LogicalPlan, LogicalPlanBuilder, Prepare, ScalarFunctionArgs,
    ScalarUDF, ScalarUDFImpl, Signature, Statement, Volatility, lit,
};
use datafusion::prelude::SessionContext;
use datafusion_common::config::ConfigOptions;
use datafusion_common::{Result, ScalarValue};

type TestResult = std::result::Result<(), Box<dyn std::error::Error>>;
fn execute() -> LogicalPlan {
    LogicalPlan::Statement(Statement::Execute(Execute {
        name: "retained_plan".into(),
        parameters: vec![],
    }))
}

#[tokio::test]
async fn direct_state_clone_retains_prepared_plan_but_builder_drops_it() -> TestResult {
    let parent = SessionContext::new();
    let plan = LogicalPlanBuilder::empty(true)
        .project(vec![lit(7i32)])?
        .build()?;
    parent
        .execute_logical_plan(LogicalPlan::Statement(Statement::Prepare(Prepare {
            name: "retained_plan".into(),
            fields: vec![],
            input: Arc::new(plan),
        })))
        .await?;
    let snapshot = parent.state();
    let id = snapshot.session_id().to_owned();
    let config = snapshot.config().clone();
    let direct = SessionContext::new_with_state(snapshot.clone());
    let mut rebuilt = SessionStateBuilder::new_from_existing(snapshot)
        .with_session_id(id)
        .build();
    *rebuilt.config_mut() = config;
    let rebuilt = SessionContext::new_with_state(rebuilt);
    for ctx in [&parent, &direct] {
        let batches = ctx.execute_logical_plan(execute()).await?.collect().await?;
        assert_eq!(batches.iter().map(|b| b.num_rows()).sum::<usize>(), 1);
    }
    let error = rebuilt
        .execute_logical_plan(execute())
        .await
        .err()
        .ok_or("rebuilt context unexpectedly retained prepared plan")?;
    assert!(
        error
            .to_string()
            .contains("Prepared statement 'retained_plan' does not exist")
    );
    assert_eq!(parent.session_id(), rebuilt.session_id());
    println!(
        "DESIGN_PROBE prepared: parent=present direct_clone=present builder=missing session_id=preserved"
    );
    Ok(())
}

#[derive(Debug, PartialEq, Eq, Hash)]
struct CatalogFlagUdf {
    signature: Signature,
    flag: bool,
}
impl CatalogFlagUdf {
    fn new(flag: bool) -> Self {
        Self {
            signature: Signature::exact(vec![], Volatility::Immutable),
            flag,
        }
    }
}
impl ScalarUDFImpl for CatalogFlagUdf {
    fn name(&self) -> &str {
        "catalog_flag_probe"
    }
    fn signature(&self) -> &Signature {
        &self.signature
    }
    fn return_type(&self, _: &[DataType]) -> Result<DataType> {
        Ok(DataType::Boolean)
    }
    fn invoke_with_args(&self, _: ScalarFunctionArgs) -> Result<ColumnarValue> {
        Ok(ColumnarValue::Scalar(ScalarValue::Boolean(Some(self.flag))))
    }
    fn with_updated_config(&self, config: &ConfigOptions) -> Option<ScalarUDF> {
        Some(ScalarUDF::from(Self::new(
            config.catalog.create_default_catalog_and_schema,
        )))
    }
}

#[tokio::test]
async fn postbuild_config_restore_leaves_udf_bound_to_temporary_config() -> TestResult {
    let parent = SessionContext::new();
    parent.register_udf(ScalarUDF::from(CatalogFlagUdf::new(true)));
    let snapshot = parent.state();
    let config = snapshot.config().clone();
    let original = snapshot.scalar_functions()["catalog_flag_probe"].clone();
    let direct = snapshot.clone();
    assert!(Arc::ptr_eq(
        &original,
        &direct.scalar_functions()["catalog_flag_probe"]
    ));
    let mut rebuilt = SessionStateBuilder::new_from_existing(snapshot)
        .with_session_id(parent.session_id())
        .build();
    *rebuilt.config_mut() = config;
    let changed = rebuilt.scalar_functions()["catalog_flag_probe"].clone();
    assert!(!Arc::ptr_eq(&original, &changed));
    assert!(rebuilt.config().create_default_catalog_and_schema());
    let child = SessionContext::new_with_state(rebuilt);
    for (ctx, udf, expected) in [(&parent, original, true), (&child, changed, false)] {
        let batches = ctx
            .execute_logical_plan(
                LogicalPlanBuilder::empty(true)
                    .project(vec![udf.call(vec![])])?
                    .build()?,
            )
            .await?
            .collect()
            .await?;
        assert_eq!(
            ScalarValue::try_from_array(batches[0].column(0).as_ref(), 0)?,
            ScalarValue::Boolean(Some(expected))
        );
    }
    println!(
        "DESIGN_PROBE udf: parent=true rebuilt=false restored_config=true direct_clone_arc=preserved builder_arc=replaced"
    );
    Ok(())
}
