use crate::{refusal, CypherLowering};
use grust_cypher::{ast as a, lexer::Span};
use grust_functions::{FunctionKind, FunctionName};
use grust_syntax::Diagnostic;
use grust_unresolved_plan::{BinaryOp as B, Expr as E, FunctionCall, Literal, UnaryOp as U};
impl CypherLowering<'_> {
    pub(crate) fn expression(&self, expression: &a::Expr, at: Span) -> Result<E, Diagnostic> {
        Ok(match expression {
            a::Expr::Null => E::Literal(Literal::Null),
            a::Expr::Boolean(v) => (*v).into(),
            a::Expr::Integer(v) => (*v).into(),
            a::Expr::Float(v) => E::float(*v),
            a::Expr::String(v) => E::from(v.as_str()),
            a::Expr::Variable(v) => E::GraphValue(grust_unresolved_plan::Binding::Named(v.clone())),
            a::Expr::Parameter(v) => E::Parameter(v.clone()),
            a::Expr::Property { base, key } => self.expression(base, at)?.property(key),
            a::Expr::List(values) => E::List(
                values
                    .iter()
                    .map(|v| self.expression(v, at))
                    .collect::<Result<_, _>>()?,
            ),
            a::Expr::Map(map) => E::Map(
                map.iter()
                    .map(|(k, v)| Ok((k.clone(), self.expression(v, at)?)))
                    .collect::<Result<_, Diagnostic>>()?,
            ),
            a::Expr::Unary { op, operand } => match op {
                a::UnaryOp::Plus => self.expression(operand, at)?,
                a::UnaryOp::Not | a::UnaryOp::Negate => E::Unary {
                    op: if *op == a::UnaryOp::Not {
                        U::Not
                    } else {
                        U::Negate
                    },
                    argument: Box::new(self.expression(operand, at)?),
                },
            },
            a::Expr::IsNull { operand, negated } => E::Unary {
                op: if *negated { U::IsNotNull } else { U::IsNull },
                argument: Box::new(self.expression(operand, at)?),
            },
            a::Expr::Binary { op, lhs, rhs } => {
                let op = match op {
                    a::BinaryOp::Add => B::Add,
                    a::BinaryOp::Subtract => B::Subtract,
                    a::BinaryOp::Multiply => B::Multiply,
                    a::BinaryOp::Divide => B::TruncatingDivide,
                    a::BinaryOp::Modulo => B::Modulo,
                    a::BinaryOp::Eq => B::Eq,
                    a::BinaryOp::Ne => B::NotEq,
                    a::BinaryOp::Lt => B::Lt,
                    a::BinaryOp::Le => B::Le,
                    a::BinaryOp::Gt => B::Gt,
                    a::BinaryOp::Ge => B::Ge,
                    a::BinaryOp::And => B::And,
                    a::BinaryOp::Or => B::Or,
                    a::BinaryOp::In => B::In,
                    _ => {
                        return Err(refusal(
                            at,
                            "operator has no faithful unresolved-plan representation",
                        ))
                    }
                };
                self.expression(lhs, at)?
                    .binary(op, self.expression(rhs, at)?)
            }
            a::Expr::Function {
                name,
                distinct,
                star,
                args,
            } => {
                if ["length", "nodes", "relationships"].contains(&name.to_lowercase().as_str()) {
                    if *distinct || *star || args.len() != 1 {
                        return Err(refusal(at, "graph intrinsic requires one argument"));
                    }
                    return Ok(E::GraphIntrinsic {
                        name: name.to_lowercase(),
                        argument: Box::new(self.expression(&args[0], at)?),
                    });
                }
                let mut function = FunctionName::new(name);
                let mut scalar = !self
                    .functions
                    .lookup(&function, FunctionKind::Scalar)
                    .is_empty();
                let mut aggregate = !self
                    .functions
                    .lookup(&function, FunctionKind::Aggregate)
                    .is_empty();
                if !scalar && !aggregate {
                    function = FunctionName::new(name.to_lowercase());
                    scalar = !self
                        .functions
                        .lookup(&function, FunctionKind::Scalar)
                        .is_empty();
                    aggregate = !self
                        .functions
                        .lookup(&function, FunctionKind::Aggregate)
                        .is_empty();
                }
                if scalar && aggregate {
                    return Err(refusal(
                        at,
                        "function name is ambiguous between scalar and aggregate contracts",
                    ));
                }
                if *star && (function.name != "count" || !aggregate || *distinct) {
                    return Err(refusal(at, "only count(*) has a star lowering"));
                }
                if *distinct && !aggregate {
                    return Err(refusal(at, "DISTINCT requires a registered aggregate"));
                }
                E::Call(FunctionCall {
                    name: function,
                    kind: if aggregate {
                        FunctionKind::Aggregate
                    } else {
                        FunctionKind::Scalar
                    },
                    arguments: if *star {
                        vec![1i64.into()]
                    } else {
                        args.iter()
                            .map(|a| self.expression(a, at))
                            .collect::<Result<_, _>>()?
                    },
                    distinct: *distinct,
                    filter: None,
                })
            }
            a::Expr::Case {
                operand,
                branches,
                default,
            } => E::Case {
                branches: branches
                    .iter()
                    .map(|branch| {
                        let condition = self.expression(&branch.when, at)?;
                        Ok((
                            if let Some(subject) = operand {
                                self.expression(subject, at)?.binary(B::Eq, condition)
                            } else {
                                condition
                            },
                            self.expression(&branch.then, at)?,
                        ))
                    })
                    .collect::<Result<_, Diagnostic>>()?,
                otherwise: Box::new(
                    default
                        .as_ref()
                        .map(|v| self.expression(v, at))
                        .transpose()?
                        .unwrap_or(E::Literal(Literal::Null)),
                ),
            },
            _ => {
                return Err(refusal(
                    at,
                    "comprehension, indexing or quantifier needs an explicit expression lowering",
                ))
            }
        })
    }
}
pub(crate) fn has_aggregate(e: &E) -> bool {
    match e {
        E::Call(c) => c.kind == FunctionKind::Aggregate || c.arguments.iter().any(has_aggregate),
        E::Binary { left, right, .. } => has_aggregate(left) || has_aggregate(right),
        E::Unary { argument, .. } => has_aggregate(argument),
        E::Property { object, .. } => has_aggregate(object),
        E::GraphIntrinsic { argument, .. } => has_aggregate(argument),
        E::List(v) => v.iter().any(has_aggregate),
        E::Map(v) => v.iter().any(|(_, e)| has_aggregate(e)),
        E::Case {
            branches,
            otherwise,
        } => {
            branches
                .iter()
                .any(|(a, b)| has_aggregate(a) || has_aggregate(b))
                || has_aggregate(otherwise)
        }
        _ => false,
    }
}
