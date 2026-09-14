//! Pattern property constraints shared by node and relationship planning.
use super::{ExpressionBindings, UnsupportedExpression, lower_expression_with_bindings};
use datafusion::logical_expr::Expr;
use grust_cypher::{
    CypherParameters,
    ast::{BinaryOp, Expr as CypherExpr, MapLiteral},
};

pub(super) fn predicates(
    properties: Option<&MapLiteral>,
    variable: &str,
    bindings: &impl ExpressionBindings,
    parameters: &CypherParameters,
) -> Result<Vec<Expr>, UnsupportedExpression> {
    let Some(properties) = properties else {
        return Ok(Vec::new());
    };
    properties
        .entries
        .iter()
        .map(|(key, value)| {
            // Values are evaluated before introducing the pattern's new bindings.
            // Only context-independent scalar literals and supplied parameters are
            // admitted until correlated pattern expressions have their own planner.
            if !matches!(
                value,
                CypherExpr::Null
                    | CypherExpr::Boolean(_)
                    | CypherExpr::Integer(_)
                    | CypherExpr::String(_)
                    | CypherExpr::Parameter(_)
            ) {
                return Err(UnsupportedExpression::Syntax);
            }
            let comparison = CypherExpr::Binary {
                op: BinaryOp::Eq,
                lhs: Box::new(CypherExpr::Property {
                    base: Box::new(CypherExpr::Variable(variable.into())),
                    key: key.clone(),
                }),
                rhs: Box::new(value.clone()),
            };
            lower_expression_with_bindings(&comparison, bindings, parameters)
        })
        .collect()
}
