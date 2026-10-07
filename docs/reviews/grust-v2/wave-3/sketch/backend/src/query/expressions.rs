use super::*;
use grust_unresolved_plan::{BinaryOp, Literal, UnaryOp};
impl Emitter<'_, '_> {
    pub(super) fn expression(
        &self,
        expr: &Expr,
        env: &BTreeMap<Slot, String>,
    ) -> Result<String, EmitError> {
        match &expr.kind {
            Value::Slot(slot) => env
                .get(slot)
                .cloned()
                .ok_or_else(|| refusal("out-of-scope resolved slot")),
            Value::Parameter(name) => {
                let value = self
                    .adapter
                    .parameters
                    .get(name)
                    .ok_or_else(|| refusal("missing parameter value"))?;
                let ty = expr
                    .ty
                    .as_ref()
                    .ok_or_else(|| refusal("untyped parameter"))?;
                if !parameter_value(value, ty, expr.nullable) {
                    return Err(refusal("parameter type/nullability/value mismatch"));
                }
                Ok(format!(
                    "CAST({} AS {})",
                    self.expression(value, &BTreeMap::new())?,
                    data_type(ty)?
                ))
            }
            Value::Literal(literal) => Ok(match literal {
                Literal::Null => {
                    if let Some(ty) = &expr.ty {
                        format!("CAST(NULL AS {})", data_type(ty)?)
                    } else {
                        "NULL".into()
                    }
                }
                Literal::Boolean(v) => if *v { "TRUE" } else { "FALSE" }.into(),
                Literal::Integer(v) => format!("CAST('{v}' AS BIGINT)"),
                Literal::FloatBits(bits) => {
                    let v = f64::from_bits(*bits);
                    if !v.is_finite() {
                        return Err(refusal("nonfinite floating literal"));
                    }
                    format!("CAST('{}' AS DOUBLE)", v)
                }
                Literal::String(v) => string(v)?,
                Literal::Binary(v) => format!(
                    "X'{}'",
                    v.iter().map(|b| format!("{b:02x}")).collect::<String>()
                ),
            }),
            Value::Binary { op, left, right } => {
                let l = self.expression(left, env)?;
                let r = self.expression(right, env)?;
                if *op == BinaryOp::In {
                    return Ok(format!("array_contains({r}, {l})"));
                }
                Ok(format!(
                    "({l} {} {r})",
                    match op {
                        BinaryOp::Eq => "=",
                        BinaryOp::NotEq => "<>",
                        BinaryOp::Lt => "<",
                        BinaryOp::Le => "<=",
                        BinaryOp::Gt => ">",
                        BinaryOp::Ge => ">=",
                        BinaryOp::Add => "+",
                        BinaryOp::Subtract => "-",
                        BinaryOp::Multiply => "*",
                        BinaryOp::Divide => "/",
                        BinaryOp::And => "AND",
                        BinaryOp::Or => "OR",
                        BinaryOp::In => unreachable!(),
                    }
                ))
            }
            Value::Unary { op, argument } => {
                let a = self.expression(argument, env)?;
                Ok(match op {
                    UnaryOp::Not => format!("(NOT {a})"),
                    UnaryOp::Negate => format!("(-{a})"),
                    UnaryOp::IsNull => format!("({a} IS NULL)"),
                    UnaryOp::IsNotNull => format!("({a} IS NOT NULL)"),
                })
            }
            Value::Call {
                function,
                arguments,
                distinct,
                filter,
            } => {
                if let BackendSupport::Named(names) = &function.backends {
                    if !names.iter().any(|n| n == "sail" || n == "sail-sql") {
                        return Err(EmitError::UnsupportedFunction {
                            provider: function.provider.clone(),
                            name: function.name.name.clone(),
                        });
                    }
                }
                let name = self
                    .adapter
                    .storage
                    .function(function)
                    .filter(|parts| !parts.is_empty())
                    .ok_or_else(|| EmitError::UnsupportedFunction {
                        provider: function.provider.clone(),
                        name: function.name.name.clone(),
                    })?;
                let args = arguments
                    .iter()
                    .map(|e| self.expression(e, env))
                    .collect::<Result<Vec<_>, _>>()?;
                let mut sql = format!(
                    "{}({}{})",
                    name.iter().map(|n| quote(n)).collect::<Vec<_>>().join("."),
                    if *distinct { "DISTINCT " } else { "" },
                    args.join(", ")
                );
                if let Some(filter) = filter {
                    sql.push_str(&format!(
                        " FILTER (WHERE {})",
                        self.expression(filter, env)?
                    ));
                }
                Ok(sql)
            }
            Value::List(values) if values.is_empty() => {
                let ty = expr
                    .ty
                    .as_ref()
                    .ok_or_else(|| refusal("empty list without type"))?;
                Ok(format!("CAST(array() AS {})", data_type(ty)?))
            }
            Value::List(values) => Ok(format!(
                "array({})",
                values
                    .iter()
                    .map(|v| self.expression(v, env))
                    .collect::<Result<Vec<_>, _>>()?
                    .join(", ")
            )),
            Value::Struct(values) => {
                let mut parts = Vec::new();
                for (name, value) in values {
                    if name.is_empty()
                        || !name.chars().all(|c| c.is_ascii_alphanumeric() || c == '_')
                    {
                        return Err(refusal(
                            "struct field name outside qualified literal subset",
                        ));
                    }
                    parts.push(format!("'{name}'"));
                    parts.push(self.expression(value, env)?);
                }
                Ok(format!("named_struct({})", parts.join(", ")))
            }
            Value::Property { object, name } => Ok(format!(
                "({}).{}",
                self.expression(object, env)?,
                quote(name)
            )),
            Value::Case {
                branches,
                otherwise,
            } => {
                let mut sql = "CASE".to_string();
                for (condition, value) in branches {
                    sql.push_str(&format!(
                        " WHEN {} THEN {}",
                        self.expression(condition, env)?,
                        self.expression(value, env)?
                    ));
                }
                sql.push_str(&format!(" ELSE {} END", self.expression(otherwise, env)?));
                Ok(sql)
            }
        }
    }
}
fn string(value: &str) -> Result<String, EmitError> {
    // Hex UTF-8 decoding avoids parser-dependent apostrophe/backslash escape modes.
    let hex = value
        .as_bytes()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<String>();
    Ok(format!("decode(X'{hex}', 'UTF-8')"))
}

fn parameter_value(value: &Expr, ty: &LogicalType, nullable: bool) -> bool {
    if value.ty.as_ref().is_some_and(|t| t != ty) {
        return false;
    }
    match (&value.kind, ty) {
        (Value::Literal(Literal::Null), _) => nullable,
        (Value::Literal(Literal::Boolean(_)), LogicalType::Boolean) => true,
        (Value::Literal(Literal::Integer(v)), LogicalType::Int32) => i32::try_from(*v).is_ok(),
        (Value::Literal(Literal::Integer(_)), LogicalType::Int64) => true,
        (Value::Literal(Literal::FloatBits(v)), LogicalType::Float32 | LogicalType::Float64) => {
            f64::from_bits(*v).is_finite()
        }
        (Value::Literal(Literal::String(_)), LogicalType::String) => true,
        (Value::Literal(Literal::Binary(_)), LogicalType::Binary) => true,
        (Value::List(items), LogicalType::List(element)) => {
            items.iter().all(|v| parameter_value(v, element, true))
        }
        (Value::Struct(items), LogicalType::Struct(fields)) => {
            items.len() == fields.len()
                && items.iter().zip(fields).all(|((name, value), field)| {
                    name == &field.name && parameter_value(value, &field.ty, field.nullable)
                })
        }
        _ => false,
    }
}
