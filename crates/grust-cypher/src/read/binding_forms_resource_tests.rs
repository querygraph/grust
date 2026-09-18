//! Binding forms are unbounded user work: a fold must observe cancellation and
//! deadline expiry between elements, not only when its enclosing row finishes.
use super::*;
use grust_procedures::{ExecutionContext, ExecutionLimits};
use std::time::{Duration, Instant};

// 4096 * 4096 inner elements: far more work than either signal allows.
const WIDTH: usize = 4096;

fn long_nested_forms() -> Vec<Expr> {
    [
        "reduce(s = 0, x IN $xs | s + reduce(t = 0, y IN $xs | t + y))",
        "[x IN $xs | size([y IN $xs WHERE y > x | y])]",
        "all(x IN $xs WHERE none(y IN $xs WHERE y < 0))",
    ]
    .into_iter()
    .map(|text| crate::parser::parse_expression(text).unwrap())
    .collect()
}

fn context(deadline: Option<Instant>) -> ExecutionContext {
    ExecutionContext::new(ExecutionLimits {
        memory_bytes: usize::MAX,
        work_units: usize::MAX,
        batch_rows: 1,
        deadline,
    })
    .unwrap()
}

fn evaluate(context: &ExecutionContext, expr: &Expr) -> Result<Value> {
    let params = CypherParameters::from([("xs".into(), Value::IntArray(vec![1; WIDTH]))]);
    let row = Row::new();
    read_budget::with_live_intermediates(context, || {
        eval_scoped(expr, &ExpressionScope::row(&row), &params)
    })
}

#[test]
fn cancellation_is_observed_inside_every_binding_form() {
    for expr in long_nested_forms() {
        let context = context(None);
        let canceller = context.clone();
        let handle = std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(20));
            canceller.cancel().unwrap();
        });
        let error = evaluate(&context, &expr).expect_err("cancelled form must not complete");
        handle.join().unwrap();
        assert!(error.to_string().contains("cancelled"), "{error}");
        let usage = context.usage().unwrap().work_units;
        assert!(
            usage > 0 && usage < WIDTH * WIDTH,
            "stopped mid-form: {usage}"
        );
    }
}

#[test]
fn deadline_is_observed_inside_every_binding_form() {
    for expr in long_nested_forms() {
        let context = context(Some(Instant::now() + Duration::from_millis(20)));
        let error = evaluate(&context, &expr).expect_err("expired form must not complete");
        assert!(error.to_string().contains("timed out"), "{error}");
        let usage = context.usage().unwrap().work_units;
        assert!(
            usage > 0 && usage < WIDTH * WIDTH,
            "stopped mid-form: {usage}"
        );
    }
}

#[test]
fn bounded_read_deadline_is_observed_inside_every_binding_form() {
    // The thread-local bounded budget reads the clock on every charge.
    let params = CypherParameters::from([("xs".into(), Value::IntArray(vec![1; WIDTH]))]);
    let row = Row::new();
    for expr in long_nested_forms() {
        let limits = read_budget::ReadExecutionBudgetLimits {
            max_candidate_work: usize::MAX,
            max_intermediate_bytes: usize::MAX,
            max_range_items: 0,
            deadline: Instant::now() + Duration::from_millis(20),
        };
        let error = read_budget::with_budget(limits, || {
            eval_scoped(&expr, &ExpressionScope::row(&row), &params)
        })
        .expect_err("expired form must not complete");
        assert!(error.to_string().contains("timed out"), "{error}");
    }
}
