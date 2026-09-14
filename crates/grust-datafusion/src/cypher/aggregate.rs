//! Aggregate lowering with explicit scalar-domain eligibility.
use super::{UnsupportedExpression, lower};
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
        (false, [argument]) => lower(argument, variable, schema, parameters)?,
        _ => return Err(UnsupportedExpression::Syntax),
    };
    if name.eq_ignore_ascii_case("count") {
        return Ok(if *distinct {
            count_distinct(value)
        } else {
            count(value)
        });
    }
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
