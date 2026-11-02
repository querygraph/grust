use std::sync::Arc;

use datafusion_common::{DFSchema, ScalarValue};

use super::tests::{context, expression};
use super::*;
use crate::config::PlanConfig;
use crate::function::constant_context::ConstantContext;

type TestResult = Result<(), Box<dyn std::error::Error>>;

#[tokio::test]
async fn constant_type_validation_precedes_arithmetic_and_restores_ordinary_policy() -> TestResult {
    let ctx = context()?;
    for ansi_mode in [true, false] {
        let resolver = PlanResolver::new(
            &ctx,
            Arc::new(PlanConfig {
                ansi_mode,
                ..Default::default()
            }),
        );
        let mut state = PlanResolverState::new();
        let schema = Arc::new(DFSchema::empty());
        for sql in ["1 / 0", "1 DIV 0", "1 % 0"] {
            let error = resolver
                .resolve_scalar_identifier_expr(expression(sql)?, &schema, &mut state)
                .await
                .err()
                .ok_or("numeric identifier was accepted")?;
            assert!(
                error
                    .to_string()
                    .contains("NOT_A_CONSTANT_STRING.WRONG_TYPE"),
                "ansi={ansi_mode} {sql}: {error}"
            );
            assert_eq!(state.config().constant_context, ConstantContext::Ordinary);
            assert!(!state.config().require_foldable);
        }
        // The datatype must remain BIGINT even when ANSI mode would evaluate
        // division by zero to NULL. TypeOf does not evaluate its argument.
        assert_eq!(
            resolver
                .resolve_scalar_identifier_expr(
                    expression(
                        "CASE WHEN typeof(1 DIV 0) = 'bigint' THEN 'foo' ELSE 'missing' END"
                    )?,
                    &schema,
                    &mut state
                )
                .await?,
            "foo"
        );
        assert_eq!(state.config().constant_context, ConstantContext::Ordinary);
        let plan = sail_sql_analyzer::statement::from_ast_statement(
            sail_sql_analyzer::parser::parse_one_statement("SELECT 1 DIV 0")?,
        )?;
        // Lowering succeeds; an actually evaluated zero divisor still fails in ANSI.
        let ordinary = resolver.resolve_named_plan(plan).await?;
        let result = async {
            ctx.execute_logical_plan(ordinary.plan)
                .await?
                .collect()
                .await
        }
        .await;
        if ansi_mode {
            let error = result.err().ok_or("ANSI zero division was accepted")?;
            assert!(error.to_string().contains("DIVIDE_BY_ZERO"), "{error}");
        } else {
            let batches = result?;
            assert_eq!(
                batches.iter().map(|batch| batch.num_rows()).sum::<usize>(),
                1
            );
            assert_eq!(
                ScalarValue::try_from_array(batches[0].column(0), 0)?,
                ScalarValue::Int64(None)
            );
        }
    }
    Ok(())
}

#[tokio::test]
async fn ordinary_lowering_preserves_type_only_parents_and_dead_arithmetic() -> TestResult {
    let ctx = context()?;
    for ansi_mode in [true, false] {
        let resolver = PlanResolver::new(
            &ctx,
            Arc::new(PlanConfig {
                ansi_mode,
                ..Default::default()
            }),
        );
        for (sql, expected) in [
            (
                "SELECT typeof(1 DIV 0)",
                ScalarValue::Utf8(Some("bigint".into())),
            ),
            (
                "SELECT typeof(1 / 0)",
                ScalarValue::Utf8(Some("double".into())),
            ),
            (
                "SELECT typeof(1 % 0)",
                ScalarValue::Utf8(Some("int".into())),
            ),
            (
                "SELECT typeof(CAST(1 DIV 0 AS STRING))",
                ScalarValue::Utf8(Some("string".into())),
            ),
            (
                "SELECT CASE WHEN false THEN 1 DIV 0 ELSE 7 END",
                ScalarValue::Int64(Some(7)),
            ),
            ("SELECT coalesce(7, 1 DIV 0)", ScalarValue::Int64(Some(7))),
            (
                "SELECT CAST(NULL AS BIGINT) DIV 0",
                ScalarValue::Int64(None),
            ),
        ] {
            let plan = sail_sql_analyzer::statement::from_ast_statement(
                sail_sql_analyzer::parser::parse_one_statement(sql)?,
            )?;
            let plan = resolver.resolve_named_plan(plan).await?;
            let batches = ctx.execute_logical_plan(plan.plan).await?.collect().await?;
            assert_eq!(
                batches.iter().map(|batch| batch.num_rows()).sum::<usize>(),
                1,
                "ansi={ansi_mode}: {sql}"
            );
            assert_eq!(
                ScalarValue::try_from_array(batches[0].column(0), 0)?,
                expected,
                "ansi={ansi_mode}: {sql}"
            );
        }
    }
    Ok(())
}

#[tokio::test]
async fn floating_signed_zero_divisors_preserve_ansi_policy_and_result_types() -> TestResult {
    let ctx = context()?;
    for ansi_mode in [true, false] {
        let resolver = PlanResolver::new(
            &ctx,
            Arc::new(PlanConfig {
                ansi_mode,
                ..Default::default()
            }),
        );
        for data_type in ["FLOAT", "DOUBLE"] {
            for zero in ["0.0D", "-0.0D"] {
                for (operation, expected) in [
                    ("/", ScalarValue::Float64(None)),
                    ("DIV", ScalarValue::Int64(None)),
                    (
                        "%",
                        if data_type == "FLOAT" {
                            ScalarValue::Float32(None)
                        } else {
                            ScalarValue::Float64(None)
                        },
                    ),
                ] {
                    let sql = format!(
                        "SELECT CAST(1 AS {data_type}) {operation} CAST({zero} AS {data_type})"
                    );
                    let plan = sail_sql_analyzer::statement::from_ast_statement(
                        sail_sql_analyzer::parser::parse_one_statement(&sql)?,
                    )?;
                    let plan = resolver.resolve_named_plan(plan).await?;
                    let result =
                        async { ctx.execute_logical_plan(plan.plan).await?.collect().await }.await;
                    if ansi_mode {
                        let error = result
                            .err()
                            .ok_or("signed-zero ANSI arithmetic was accepted")?;
                        let condition = if operation == "%" {
                            "REMAINDER_BY_ZERO"
                        } else {
                            "DIVIDE_BY_ZERO"
                        };
                        assert!(error.to_string().contains(condition), "{sql}: {error}");
                    } else {
                        let batches = result?;
                        assert_eq!(batches.iter().map(|b| b.num_rows()).sum::<usize>(), 1);
                        assert_eq!(
                            ScalarValue::try_from_array(batches[0].column(0), 0)?,
                            expected,
                            "{sql}"
                        );
                    }
                }
            }
        }
    }
    Ok(())
}

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
            let bt = std::backtrace::Backtrace::force_capture().to_string();
            let frames: Vec<String> = bt.lines().filter(|l| l.contains("datafusion") || l.contains("sail_")).filter(|l| !l.contains("at /") ).map(|l| l.trim().to_string()).take(14).collect();
            println!("CALL {draw}\n    {}", frames.join("\n    "));
            Ok(ColumnarValue::Scalar(ScalarValue::Float64(Some(if draw==0 { 1.0 } else { 0.0 }))))
        }),
    ))?;
    let resolver = PlanResolver::new(&ctx, Arc::new(PlanConfig { ansi_mode: true, ..Default::default() }));
    let statement = sail_sql_analyzer::parser::parse_one_statement("SELECT 1.0D / divisor_probe()")?;
    let plan = resolver.resolve_named_plan(sail_sql_analyzer::statement::from_ast_statement(statement)?).await?;
    assert_eq!(calls.load(Ordering::SeqCst), 0, "lowering evaluated the operand");
    let state = ctx.state();
    let optimized = state.optimize(&plan.plan)?;
    println!("PHASE after-optimize calls={} occurrences={}", calls.load(Ordering::SeqCst), format!("{optimized}").matches("divisor_probe").count());
    println!("OPTIMIZED {optimized}");
    let physical = state.create_physical_plan(&plan.plan).await?;
    let text = datafusion::physical_plan::displayable(physical.as_ref()).indent(true).to_string();
    println!("PHASE after-physical-plan calls={} occurrences={}", calls.load(Ordering::SeqCst), text.matches("divisor_probe").count());
    println!("PHYSICAL {text}");
    let result = datafusion::physical_plan::collect(physical, state.task_ctx()).await;
    println!("PHASE after-collect calls={} result={result:?}", calls.load(Ordering::SeqCst));
    let result = async { ctx.execute_logical_plan(plan.plan).await?.collect().await }.await;
    println!("PHASE after-execute_logical_plan calls={} result={result:?}", calls.load(Ordering::SeqCst));
    let _ = result;
    Ok(())
}
