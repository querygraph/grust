
#[tokio::test]
async fn operand_evaluation_stages_probe() -> TestResult {
    use std::sync::atomic::{AtomicUsize, Ordering};
    use datafusion_expr::{ColumnarValue, Volatility, create_udf};
    use sail_catalog::manager::CatalogManager;
    use sail_common_datafusion::extension::SessionExtensionAccessor;
    for sql in ["SELECT divisor_probe()", "SELECT abs(divisor_probe())", "SELECT CASE WHEN divisor_probe() = 0.0D THEN NULL ELSE divisor_probe() END", "SELECT 1.0D / divisor_probe()"] {
        let ctx = context()?;
        let calls=Arc::new(AtomicUsize::new(0));let phase=Arc::new(AtomicUsize::new(0));
        let observed=calls.clone();let current=phase.clone();
        ctx.extension::<CatalogManager>()?.register_function(create_udf("divisor_probe",vec![],DataType::Float64,Volatility::Volatile,Arc::new(move |_| {
            let n=observed.fetch_add(1,Ordering::SeqCst)+1;
            eprintln!("CALL n={n} phase={}\n{}",current.load(Ordering::SeqCst),std::backtrace::Backtrace::force_capture());
            Ok(ColumnarValue::Scalar(ScalarValue::Float64(Some(1.0))))
        })))?;
        let resolver=PlanResolver::new(&ctx,Arc::new(PlanConfig{ansi_mode:true,..Default::default()}));
        let statement=sail_sql_analyzer::parser::parse_one_statement(sql)?;
        let plan=resolver.resolve_named_plan(sail_sql_analyzer::statement::from_ast_statement(statement)?).await?;
        eprintln!("LOWER {sql}: {}\n{}",calls.load(Ordering::SeqCst),plan.plan.display_indent());
        phase.store(1,Ordering::SeqCst);
        let frame=ctx.execute_logical_plan(plan.plan).await?;
        eprintln!("FRAME {sql}: {}",calls.load(Ordering::SeqCst));
        phase.store(2,Ordering::SeqCst);
        let result=frame.collect().await;
        eprintln!("COLLECT {sql}: {} result={result:?}",calls.load(Ordering::SeqCst));
    }
    Ok(())
}
