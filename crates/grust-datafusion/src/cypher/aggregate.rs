//! Aggregate lowering with explicit scalar-domain eligibility.
use super::{ExpressionBindings, UnsupportedExpression, lower_bound};
use datafusion::{
    arrow::datatypes::{DataType, Schema},
    functions_aggregate::expr_fn::{count, count_distinct, max, min},
    logical_expr::{Expr, lit},
};
use grust_cypher::{CypherParameters, ast::Expr as CypherExpr};

pub(super) fn aggregate(
    expression: &CypherExpr,
    variable: &str,
    schema: &Schema,
    parameters: &CypherParameters,
) -> Result<Expr, UnsupportedExpression> {
    lower_aggregate_with_bindings(
        expression,
        &super::bindings::SingleBinding { variable, schema },
        parameters,
    )
}

/// Lower count and integer/string extrema over caller-resolved graph bindings.
/// Scalar domains, missing values and unknown variables follow the same contract
/// as [`super::lower_expression_with_bindings`]. This does not admit resource
/// usage or select an execution route. Unsupported aggregates remain explicit.
pub fn lower_aggregate_with_bindings(
    expression: &CypherExpr,
    bindings: &impl ExpressionBindings,
    parameters: &CypherParameters,
) -> Result<Expr, UnsupportedExpression> {
    let CypherExpr::Function {
        name,
        distinct,
        star,
        args,
    } = expression
    else {
        return Err(UnsupportedExpression::Syntax);
    };
    let (value, kind) = match (*star, args.as_slice()) {
        (true, []) if !*distinct && name.eq_ignore_ascii_case("count") => {
            (lit(1_i64), DataType::Int64)
        }
        (false, [argument]) => lower_bound(argument, bindings, parameters)?,
        _ => return Err(UnsupportedExpression::Syntax),
    };
    if name.eq_ignore_ascii_case("count") {
        return Ok(if *distinct {
            count_distinct(value)
        } else {
            count(value)
        });
    }
    let (value, kind) = if kind == DataType::Null {
        // A typed null permits upstream aggregation on absent/null-only columns.
        (
            lit(datafusion::common::ScalarValue::Int64(None)),
            DataType::Int64,
        )
    } else {
        (value, kind)
    };
    if !matches!(kind, DataType::Int64 | DataType::Utf8) {
        return Err(UnsupportedExpression::Type);
    }
    // DISTINCT cannot change the extremum in these totally ordered domains.
    if name.eq_ignore_ascii_case("min") {
        Ok(min(value))
    } else if name.eq_ignore_ascii_case("max") {
        Ok(max(value))
    } else {
        Err(UnsupportedExpression::Syntax)
    }
}
