
#[tokio::test]
async fn volatile_divisor_is_evaluated_once_regression_probe() -> TestResult {
    use std::sync::atomic::{AtomicUsize, Ordering};
    use datafusion_expr::{ColumnarValue, Volatility, create_udf};
    use sail_catalog::manager::CatalogManager;
    use sail_common_datafusion::extension::SessionExtensionAccessor;

    let ctx = context()?;
    let calls = Arc::new(AtomicUsize::new(0));
    let observed = calls.clone();
    ctx.extension::<CatalogManager>()?.register_function(create_udf(
        "divisor_probe", vec![], DataType::Float64, Volatility::Volatile,
        Arc::new(move |_| {
            let draw = observed.fetch_add(1, Ordering::SeqCst);
            Ok(ColumnarValue::Scalar(ScalarValue::Float64(Some(if draw==0 { 1.0 } else { 0.0 }))))
        }),
    ))?;
    let resolver = PlanResolver::new(&ctx, Arc::new(PlanConfig { ansi_mode: true, ..Default::default() }));
    let statement = sail_sql_analyzer::parser::parse_one_statement("SELECT 1.0D / divisor_probe()")?;
    let plan = resolver.resolve_named_plan(sail_sql_analyzer::statement::from_ast_statement(statement)?).await?;
    assert_eq!(calls.load(Ordering::SeqCst), 0, "lowering evaluated the operand");
    let result = ctx.execute_logical_plan(plan.plan).await?.collect().await?;
    assert_eq!(calls.load(Ordering::SeqCst), 1, "a divisor must be evaluated once");
    assert_eq!(ScalarValue::try_from_array(result[0].column(0), 0)?, ScalarValue::Float64(Some(1.0)));
    Ok(())
}
