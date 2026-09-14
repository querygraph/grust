//! Typed Cypher expression lowering. Query routing is not yet implemented.
mod scan;
pub use scan::{lower_node_scan, lower_node_scan_with_parameters};

use datafusion::{
    arrow::datatypes::{DataType, Schema},
    common::{Column, ScalarValue},
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
        CypherExpr::Property { base, key } => {
            if !matches!(base.as_ref(), CypherExpr::Variable(name) if name == variable) {
                return Err(Binding);
            }
            let name = format!("property.{key}");
            match schema.field_with_name(&name) {
                Err(_) => null(),
                Ok(field) => {
                    let kind = field.data_type();
                    if !matches!(
                        kind,
                        DataType::Null | DataType::Boolean | DataType::Int64 | DataType::Utf8
                    ) {
                        return Err(Type);
                    }
                    // Do not parse dots in property keys as relation qualifiers.
                    (Expr::Column(Column::from_name(name)), kind.clone())
                }
            }
        }
        CypherExpr::IsNull { operand, negated } => {
            let (value, _) = lower(operand, variable, schema, parameters)?;
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
            let (value, kind) = lower(operand, variable, schema, parameters)?;
            if !matches!(kind, DataType::Boolean | DataType::Null) {
                return Err(Type);
            }
            (!value, DataType::Boolean)
        }
        CypherExpr::Binary { op, lhs, rhs } => {
            let (left, left_type) = lower(lhs, variable, schema, parameters)?;
            let (right, right_type) = lower(rhs, variable, schema, parameters)?;
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
                BinaryOp::And | BinaryOp::Or => {
                    if !matches!(left_type, DataType::Boolean | DataType::Null)
                        || !matches!(right_type, DataType::Boolean | DataType::Null)
                    {
                        return Err(Type);
                    }
                    if *op == BinaryOp::And {
                        left.and(right)
                    } else {
                        left.or(right)
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
