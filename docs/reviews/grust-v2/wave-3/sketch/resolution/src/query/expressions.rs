use super::*;
use crate::functions::{bind, numeric};
use grust_functions::FunctionKind;
use grust_lpg::Property;
use grust_unresolved_plan::{BinaryOp, Expr as U, Literal, UnaryOp};
impl State<'_, '_> {
    pub(super) fn expression(
        &self,
        expr: &U,
        scope: &Scope,
        current: Option<&Binding>,
        aggregate: bool,
    ) -> Result<Expr, ResolveError> {
        match expr {
            U::CurrentElement => self.bound(
                scope,
                current
                    .ok_or_else(|| unsupported("CurrentElement", "outside pattern predicate"))?,
            ),
            U::Binding(binding) => self.bound(scope, binding),
            U::Literal(literal) => Ok(Expr {
                kind: Value::Literal(literal.clone()),
                nullable: matches!(literal, Literal::Null),
                ty: match literal {
                    Literal::Null => None,
                    Literal::Boolean(_) => Some(LogicalType::Boolean),
                    Literal::Integer(_) => Some(LogicalType::Int64),
                    Literal::FloatBits(_) => Some(LogicalType::Float64),
                    Literal::String(_) => Some(LogicalType::String),
                    Literal::Binary(_) => Some(LogicalType::Binary),
                },
            }),
            U::Parameter(name) => {
                let (ty, nullable) = self.context.parameters.parameter(name).ok_or_else(|| {
                    unsupported("parameter", &format!("missing declared type for {name}"))
                })?;
                Ok(Expr {
                    kind: Value::Parameter(name.clone()),
                    ty: Some(ty),
                    nullable,
                })
            }
            U::Property { object, name } => {
                let binding = match object.as_ref() {
                    U::Binding(b) => Some(b),
                    U::CurrentElement => current,
                    _ => None,
                };
                if let Some(Bound::Entity(entity)) = binding.and_then(|b| scope.bindings.get(b)) {
                    return entity
                        .properties
                        .iter()
                        .find(|(n, _)| n == name)
                        .map(|(_, e)| e.clone())
                        .ok_or_else(|| ResolveError::UnknownProperty(name.clone()));
                }
                let object = self.expression(object, scope, current, aggregate)?;
                let Some(LogicalType::Struct(fields)) = &object.ty else {
                    return Err(unsupported(
                        "property",
                        "subject is not an entity or struct",
                    ));
                };
                let f = fields
                    .iter()
                    .find(|f| &f.name == name)
                    .ok_or_else(|| ResolveError::UnknownProperty(name.clone()))?;
                let ty = f.ty.clone();
                let nullable = object.nullable || f.nullable;
                Ok(Expr {
                    kind: Value::Property {
                        object: Box::new(object),
                        name: name.clone(),
                    },
                    ty: Some(ty),
                    nullable,
                })
            }
            U::Binary { op, left, right } => {
                let left = self.expression(left, scope, current, aggregate)?;
                let right = self.expression(right, scope, current, aggregate)?;
                let ty = match op {
                    BinaryOp::And | BinaryOp::Or => {
                        boolean(&left)?;
                        boolean(&right)?;
                        LogicalType::Boolean
                    }
                    BinaryOp::In => {
                        if let Some(LogicalType::List(element)) = &right.ty {
                            compatible(left.ty.as_ref(), Some(element))?;
                        } else if right.ty.is_some() {
                            return Err(unsupported("IN", "right operand must be a list"));
                        }
                        LogicalType::Boolean
                    }
                    BinaryOp::Eq
                    | BinaryOp::NotEq
                    | BinaryOp::Lt
                    | BinaryOp::Le
                    | BinaryOp::Gt
                    | BinaryOp::Ge => {
                        compatible(left.ty.as_ref(), right.ty.as_ref())?;
                        LogicalType::Boolean
                    }
                    _ => {
                        compatible(left.ty.as_ref(), right.ty.as_ref())?;
                        let ty = left
                            .ty
                            .as_ref()
                            .or(right.ty.as_ref())
                            .ok_or_else(|| unsupported("arithmetic", "untyped operands"))?;
                        if !numeric(ty) {
                            return Err(unsupported("arithmetic", "non-numeric operands"));
                        }
                        if *op == BinaryOp::Divide {
                            LogicalType::Float64
                        } else {
                            ty.clone()
                        }
                    }
                };
                let mut value = binary(*op, left, right, Some(ty));
                if matches!(op, BinaryOp::In | BinaryOp::Divide) {
                    value.nullable = true;
                }
                Ok(value)
            }
            U::Unary { op, argument } => {
                let argument = self.expression(argument, scope, current, aggregate)?;
                let (ty, nullable) = match op {
                    UnaryOp::Not => {
                        boolean(&argument)?;
                        (Some(LogicalType::Boolean), argument.nullable)
                    }
                    UnaryOp::IsNull | UnaryOp::IsNotNull => (Some(LogicalType::Boolean), false),
                    UnaryOp::Negate => {
                        if !argument.ty.as_ref().is_some_and(numeric) {
                            return Err(unsupported("negate", "numeric operand required"));
                        }
                        (argument.ty.clone(), argument.nullable)
                    }
                };
                Ok(Expr {
                    kind: Value::Unary {
                        op: *op,
                        argument: Box::new(argument),
                    },
                    ty,
                    nullable,
                })
            }
            U::Call(call) => {
                if call.kind == FunctionKind::Aggregate && !aggregate {
                    return Err(unsupported(
                        "aggregate",
                        "outside aggregation or nested aggregate",
                    ));
                }
                if call.kind == FunctionKind::Scalar && (call.distinct || call.filter.is_some()) {
                    return Err(unsupported(
                        "scalar",
                        "DISTINCT/FILTER require an aggregate",
                    ));
                }
                let arguments = call
                    .arguments
                    .iter()
                    .map(|a| {
                        self.expression(
                            a,
                            scope,
                            current,
                            aggregate && call.kind != FunctionKind::Aggregate,
                        )
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                let filter = call
                    .filter
                    .as_ref()
                    .map(|f| {
                        self.expression(f, scope, current, false).and_then(|f| {
                            boolean(&f)?;
                            Ok(Box::new(f))
                        })
                    })
                    .transpose()?;
                let (function, ty, nullable) =
                    bind(self.context.functions, &call.name, call.kind, &arguments)?;
                Ok(Expr {
                    kind: Value::Call {
                        function: Box::new(function),
                        arguments,
                        distinct: call.distinct,
                        filter,
                    },
                    ty: Some(ty),
                    nullable,
                })
            }
            U::List(items) => {
                let items = items
                    .iter()
                    .map(|a| self.expression(a, scope, current, aggregate))
                    .collect::<Result<Vec<_>, _>>()?;
                let ty = items.iter().find_map(|e| e.ty.clone());
                for item in &items {
                    compatible(ty.as_ref(), item.ty.as_ref())?;
                }
                Ok(Expr {
                    kind: Value::List(items),
                    ty: Some(LogicalType::List(Box::new(
                        ty.unwrap_or_else(grust_resolved_plan::query::null_type),
                    ))),
                    nullable: false,
                })
            }
            U::Map(items) => {
                let mut seen = std::collections::HashSet::new();
                let mut values = Vec::new();
                let mut fields = Vec::new();
                for (name, value) in items {
                    if !seen.insert(name) {
                        return Err(unsupported("struct", "duplicate field"));
                    }
                    let value = self.expression(value, scope, current, aggregate)?;
                    let ty = value
                        .ty
                        .clone()
                        .unwrap_or_else(grust_resolved_plan::query::null_type);
                    fields.push(Property {
                        name: name.clone(),
                        ty,
                        nullable: value.nullable,
                    });
                    values.push((name.clone(), value));
                }
                Ok(Expr {
                    kind: Value::Struct(values),
                    ty: Some(LogicalType::Struct(fields)),
                    nullable: false,
                })
            }
            U::Case {
                branches,
                otherwise,
            } => {
                let otherwise = self.expression(otherwise, scope, current, aggregate)?;
                let mut ty = otherwise.ty.clone();
                let mut nullable = otherwise.nullable;
                let mut values = Vec::new();
                for (condition, value) in branches {
                    let condition = self.expression(condition, scope, current, aggregate)?;
                    boolean(&condition)?;
                    let value = self.expression(value, scope, current, aggregate)?;
                    compatible(ty.as_ref(), value.ty.as_ref())?;
                    if ty.is_none() {
                        ty = value.ty.clone();
                    }
                    nullable |= value.nullable;
                    values.push((condition, value));
                }
                Ok(Expr {
                    kind: Value::Case {
                        branches: values,
                        otherwise: Box::new(otherwise),
                    },
                    ty,
                    nullable,
                })
            }
        }
    }
    fn bound(&self, scope: &Scope, binding: &Binding) -> Result<Expr, ResolveError> {
        match scope.bindings.get(binding) {
            Some(Bound::Value(value)) => Ok(value.clone()),
            Some(Bound::Entity(e)) => {
                use grust_lpg::Property;
                let properties = Expr {
                    kind: Value::Struct(e.properties.clone()),
                    ty: Some(LogicalType::Struct(
                        e.properties
                            .iter()
                            .map(|(name, expr)| Property {
                                name: name.clone(),
                                ty: expr.ty.clone().expect("resolved property"),
                                nullable: expr.nullable,
                            })
                            .collect(),
                    )),
                    nullable: false,
                };
                let text = |value: &str| Expr {
                    kind: Value::Literal(Literal::String(value.into())),
                    ty: Some(LogicalType::String),
                    nullable: false,
                };
                let values = vec![
                    ("identity".into(), e.identity.clone()),
                    ("group".into(), e.group.clone()),
                    ("graph".into(), text(&e.graph)),
                    ("kind".into(), text(if e.edge { "edge" } else { "vertex" })),
                    ("properties".into(), properties),
                ];
                let ty = LogicalType::Struct(
                    values
                        .iter()
                        .map(|(name, expr): &(String, Expr)| Property {
                            name: name.clone(),
                            ty: expr.ty.clone().expect("entity shape"),
                            nullable: expr.nullable,
                        })
                        .collect(),
                );
                let object = Expr {
                    kind: Value::Struct(values),
                    ty: Some(ty.clone()),
                    nullable: false,
                };
                if e.identity.nullable {
                    let condition = Expr {
                        kind: Value::Unary {
                            op: UnaryOp::IsNotNull,
                            argument: Box::new(e.identity.clone()),
                        },
                        ty: Some(LogicalType::Boolean),
                        nullable: false,
                    };
                    Ok(Expr {
                        kind: Value::Case {
                            branches: vec![(condition, object)],
                            otherwise: Box::new(Expr {
                                kind: Value::Literal(Literal::Null),
                                ty: Some(ty.clone()),
                                nullable: true,
                            }),
                        },
                        ty: Some(ty),
                        nullable: true,
                    })
                } else {
                    Ok(object)
                }
            }
            None => Err(ResolveError::UnknownBinding(format!("{binding:?}"))),
        }
    }
}
pub(super) fn compatible(
    left: Option<&LogicalType>,
    right: Option<&LogicalType>,
) -> Result<(), ResolveError> {
    if let (Some(l), Some(r)) = (left, right) {
        if l != r
            && !grust_resolved_plan::query::is_null_type(l)
            && !grust_resolved_plan::query::is_null_type(r)
        {
            return Err(ResolveError::TypeMismatch {
                expected: Box::new(l.clone()),
                actual: Box::new(r.clone()),
            });
        }
    }
    Ok(())
}
pub(super) fn boolean(expr: &Expr) -> Result<(), ResolveError> {
    compatible(expr.ty.as_ref(), Some(&LogicalType::Boolean))
}
pub(super) fn grouped(expr: &Expr, groups: &[Expr]) -> bool {
    if groups.contains(expr) {
        return true;
    }
    match &expr.kind {
        Value::Slot(_) => false,
        Value::Call { function, .. } if function.kind == FunctionKind::Aggregate => true,
        Value::Call {
            arguments, filter, ..
        } => {
            arguments.iter().all(|e| grouped(e, groups))
                && filter.as_ref().is_none_or(|e| grouped(e, groups))
        }
        Value::Binary { left, right, .. } => grouped(left, groups) && grouped(right, groups),
        Value::Unary { argument, .. } => grouped(argument, groups),
        Value::List(values) => values.iter().all(|e| grouped(e, groups)),
        Value::Struct(values) => values.iter().all(|(_, e)| grouped(e, groups)),
        Value::Property { object, .. } => grouped(object, groups),
        Value::Case {
            branches,
            otherwise,
        } => {
            branches
                .iter()
                .all(|(a, b)| grouped(a, groups) && grouped(b, groups))
                && grouped(otherwise, groups)
        }
        Value::Literal(_) | Value::Parameter(_) => true,
    }
}
