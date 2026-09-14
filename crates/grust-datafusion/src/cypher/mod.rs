//! Typed Cypher expression lowering. Query routing is not yet implemented.
mod aggregate;
pub use aggregate::lower_aggregate_with_bindings;
mod bindings;
pub use bindings::ExpressionBindings;
mod scan;
pub use scan::{
    NodeScanPlan, UnsupportedScan, lower_node_scan, lower_node_scan_with_parameters, plan_node_scan,
};

use datafusion::{
    arrow::datatypes::{DataType, Schema},
    common::ScalarValue,
    logical_expr::{Expr, lit},
};
use grust_core::Value;
use grust_cypher::CypherParameters;
use grust_cypher::ast::{BinaryOp, Expr as CypherExpr, UnaryOp};

/// A reason an expression must remain with the existing Cypher executor.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum UnsupportedExpression {
    Syntax,
    Binding,
    Type,
    MissingParameter,
}

/// Lower a scalar predicate over one validated native Arrow graph table.
/// The variable identifies its node/edge binding; property columns use the
/// shared `property.<key>` contract. Missing properties become null. Whole
/// elements, arithmetic and mixed-type comparisons are not admitted.
/// This function does not perform query analysis, policy admission or routing.
pub fn lower_expression(
    expression: &CypherExpr,
    variable: &str,
    schema: &Schema,
) -> Result<Expr, UnsupportedExpression> {
    lower_expression_with_parameters(expression, variable, schema, &CypherParameters::new())
}

/// Lower using explicitly supplied scalar parameters. Missing bindings are
/// distinguished from unsupported value types; no parameter value is guessed.
pub fn lower_expression_with_parameters(
    expression: &CypherExpr,
    variable: &str,
    schema: &Schema,
    parameters: &CypherParameters,
) -> Result<Expr, UnsupportedExpression> {
    lower(expression, variable, schema, parameters).map(|(expression, _)| expression)
}

fn lower(
    expression: &CypherExpr,
    variable: &str,
    schema: &Schema,
    parameters: &CypherParameters,
) -> Result<(Expr, DataType), UnsupportedExpression> {
    lower_bound(
        expression,
        &bindings::SingleBinding { variable, schema },
        parameters,
    )
}

/// Lower an expression through caller-supplied typed binding resolution.
/// Resolvers must preserve snapshot identity and report the actual column types.
/// This composes multiple bindings without duplicating scalar semantics.
pub fn lower_expression_with_bindings(
    expression: &CypherExpr,
    bindings: &impl ExpressionBindings,
    parameters: &CypherParameters,
) -> Result<Expr, UnsupportedExpression> {
    lower_bound(expression, bindings, parameters).map(|(expression, _)| expression)
}

fn lower_bound(
    expression: &CypherExpr,
    bindings: &impl ExpressionBindings,
    parameters: &CypherParameters,
) -> Result<(Expr, DataType), UnsupportedExpression> {
    use UnsupportedExpression::{Binding, Syntax, Type};
    let null = || (lit(ScalarValue::Null), DataType::Null);
    Ok(match expression {
        CypherExpr::Parameter(name) => match parameters
            .get(name)
            .ok_or(UnsupportedExpression::MissingParameter)?
        {
            Value::Null => null(),
            Value::Bool(value) => (lit(*value), DataType::Boolean),
            Value::Int(value) => (lit(*value), DataType::Int64),
            Value::String(value) => (lit(value.clone()), DataType::Utf8),
            _ => return Err(Type),
        },
        CypherExpr::Null => null(),
        CypherExpr::Boolean(value) => (lit(*value), DataType::Boolean),
        CypherExpr::Integer(value) => (lit(*value), DataType::Int64),
        CypherExpr::String(value) => (lit(value.clone()), DataType::Utf8),
        CypherExpr::Function {
            name,
            distinct: false,
            star: false,
            args,
        } if name.eq_ignore_ascii_case("id") => {
            let [CypherExpr::Variable(name)] = args.as_slice() else {
                return Err(Binding);
            };
            let (value, kind) = bindings.node_id(name)?;
            if kind != DataType::Utf8 {
                return Err(Type);
            }
            (value, kind)
        }
        CypherExpr::Property { base, key } => {
            let CypherExpr::Variable(name) = base.as_ref() else {
                return Err(Binding);
            };
            let (value, kind) = bindings.property(name, key)?;
            if !matches!(
                kind,
                DataType::Null | DataType::Boolean | DataType::Int64 | DataType::Utf8
            ) {
                return Err(Type);
            }
            (value, kind)
        }
        CypherExpr::IsNull { operand, negated } => {
            let (value, _) = lower_bound(operand, bindings, parameters)?;
            (
                if *negated {
                    value.is_not_null()
                } else {
                    value.is_null()
                },
                DataType::Boolean,
            )
        }
        CypherExpr::Unary {
            op: UnaryOp::Not,
            operand,
        } => {
            let (value, kind) = lower_bound(operand, bindings, parameters)?;
            if !matches!(kind, DataType::Boolean | DataType::Null) {
                return Err(Type);
            }
            (!value, DataType::Boolean)
        }
        CypherExpr::Binary { op, lhs, rhs } => {
            let (left, left_type) = lower_bound(lhs, bindings, parameters)?;
            let (right, right_type) = lower_bound(rhs, bindings, parameters)?;
            if left_type != right_type
                && left_type != DataType::Null
                && right_type != DataType::Null
            {
                return Err(Type);
            }
            let value = match op {
                BinaryOp::Eq => left.eq(right),
                BinaryOp::Ne => left.not_eq(right),
                BinaryOp::Lt => left.lt(right),
                BinaryOp::Le => left.lt_eq(right),
                BinaryOp::Gt => left.gt(right),
                BinaryOp::Ge => left.gt_eq(right),
                BinaryOp::And | BinaryOp::Or | BinaryOp::Xor => {
                    if !matches!(left_type, DataType::Boolean | DataType::Null)
                        || !matches!(right_type, DataType::Boolean | DataType::Null)
                    {
                        return Err(Type);
                    }
                    match op {
                        BinaryOp::And => left.and(right),
                        BinaryOp::Or => left.or(right),
                        _ => left.not_eq(right),
                    }
                }
                _ => return Err(Syntax),
            };
            (value, DataType::Boolean)
        }
        _ => return Err(Syntax),
    })
}

#[cfg(test)]
mod tests;

#[cfg(test)]
mod planning_tests;

#[cfg(test)]
mod binding_tests;
