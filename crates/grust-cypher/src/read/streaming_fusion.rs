//! Compile array aggregate inputs once per upstream row. The loop consumes every
//! element, without interpreting the AST or cloning arrays/strings per scalar.
//! This optimization is independent of procedure names and graph families.

use super::streaming_aggregate::AggregateState;
use super::*;
use grust_procedures::ExecutionContext;
use std::ops::ControlFlow;

#[derive(Clone, Copy)]
enum Scalar<'a> {
    Borrowed(&'a Value),
    String(&'a str),
    Integer(i64),
    Float(f64),
    Null,
}

impl Scalar<'_> {
    fn null(self) -> bool {
        matches!(
            self,
            Self::Null | Self::Borrowed(Value::Null | Value::Json(serde_json::Value::Null))
        )
    }
    fn owned(self) -> Value {
        match self {
            Self::Borrowed(value) => value.clone(),
            Self::String(value) => Value::String(value.into()),
            Self::Integer(value) => Value::Int(value),
            Self::Float(value) => Value::Float(value),
            Self::Null => Value::Null,
        }
    }
}

enum Input<'a> {
    Item,
    Constant(Scalar<'a>),
    Indexed(&'a Value),
    Integer(Box<Input<'a>>),
    Float(Box<Input<'a>>),
}

impl<'a> Input<'a> {
    fn compile(
        expr: &'a Expr,
        alias: &str,
        row: &'a Row,
        params: &'a CypherParameters,
        depth: usize,
    ) -> Option<Self> {
        if depth > 8 {
            return None;
        }
        match expr {
            Expr::Variable(name) if name == alias => Some(Self::Item),
            Expr::Variable(name) => match row.get(name) {
                Some(Bound::Value(value)) => Some(Self::Constant(Scalar::Borrowed(value))),
                _ => None,
            },
            Expr::Parameter(name) => params
                .get(name)
                .map(|value| Self::Constant(Scalar::Borrowed(value))),
            Expr::Null => Some(Self::Constant(Scalar::Null)),
            Expr::Integer(value) => Some(Self::Constant(Scalar::Integer(*value))),
            Expr::Float(value) => Some(Self::Constant(Scalar::Float(*value))),
            Expr::String(value) => Some(Self::Constant(Scalar::String(value))),
            Expr::Index { base, index } if matches!(index.as_ref(), Expr::Variable(name) if name == alias) => {
                match Self::compile(base, alias, row, params, depth + 1)? {
                    Self::Constant(Scalar::Borrowed(
                        value @ (Value::StringArray(_)
                        | Value::IntArray(_)
                        | Value::FloatArray(_)
                        | Value::Null),
                    )) => Some(Self::Indexed(value)),
                    _ => None,
                }
            }
            Expr::Function {
                name,
                args,
                distinct: false,
                star: false,
            } if args.len() == 1 => {
                if name.eq_ignore_ascii_case("toInteger") {
                    Some(Self::Integer(Box::new(Self::compile(
                        &args[0],
                        alias,
                        row,
                        params,
                        depth + 1,
                    )?)))
                } else if name.eq_ignore_ascii_case("toFloat") {
                    Some(Self::Float(Box::new(Self::compile(
                        &args[0],
                        alias,
                        row,
                        params,
                        depth + 1,
                    )?)))
                } else {
                    None
                }
            }
            _ => None,
        }
    }

    fn evaluate(&self, item: Scalar<'a>) -> Result<Scalar<'a>> {
        match self {
            Self::Item => Ok(item),
            Self::Constant(value) => Ok(*value),
            Self::Indexed(values) => {
                if item.null() || matches!(values, Value::Null) {
                    return Ok(Scalar::Null);
                }
                let index = match item {
                    Scalar::Integer(index) => index,
                    Scalar::Borrowed(Value::Int(index)) => *index,
                    _ => return Err(gql_type("list index must be an integer")),
                };
                let length = match values {
                    Value::StringArray(values) => values.len(),
                    Value::IntArray(values) => values.len(),
                    Value::FloatArray(values) => values.len(),
                    _ => return Err(gql_type("expected typed array")),
                };
                let index = if index < 0 {
                    length as i128 + i128::from(index)
                } else {
                    i128::from(index)
                };
                let Ok(index) = usize::try_from(index) else {
                    return Ok(Scalar::Null);
                };
                Ok(match values {
                    Value::StringArray(values) => {
                        values.get(index).map(|value| Scalar::String(value))
                    }
                    Value::IntArray(values) => {
                        values.get(index).map(|value| Scalar::Integer(*value))
                    }
                    Value::FloatArray(values) => {
                        values.get(index).map(|value| Scalar::Float(*value))
                    }
                    _ => None,
                }
                .unwrap_or(Scalar::Null))
            }
            Self::Integer(input) | Self::Float(input) => {
                let value = input.evaluate(item)?;
                let integer = matches!(self, Self::Integer(_));
                let string = match value {
                    Scalar::String(value) => Some(value),
                    Scalar::Borrowed(Value::String(value)) => Some(value.as_str()),
                    _ => None,
                };
                let converted = if let Some(string) = string {
                    if integer {
                        parse_integer_string_value(string)?
                    } else {
                        parse_float_string_value(string)?
                    }
                } else if integer {
                    restricted_to_integer_value(value.owned())?
                } else {
                    restricted_to_float_value(value.owned())?
                };
                match converted {
                    Value::Null => Ok(Scalar::Null),
                    Value::Int(value) => Ok(Scalar::Integer(value)),
                    Value::Float(value) => Ok(Scalar::Float(value)),
                    _ => Err(gql_execution(
                        "numeric coercion returned a nonnumeric value",
                    )),
                }
            }
        }
    }
}

pub(super) fn try_unwind(
    states: &mut [AggregateState],
    items: &[ReturnItem],
    unwind: &UnwindClause,
    row: &Row,
    params: &CypherParameters,
    context: &ExecutionContext,
) -> Option<Result<ControlFlow<()>>> {
    let typed_source = match &unwind.expr {
        Expr::Variable(name) => match row.get(name) {
            Some(Bound::Value(value)) => typed_array(value),
            _ => false,
        },
        Expr::Parameter(name) => params.get(name).is_some_and(typed_array),
        Expr::Function {
            name,
            distinct: false,
            star: false,
            ..
        } => name.eq_ignore_ascii_case("range"),
        _ => false,
    };
    if !typed_source {
        return None;
    }
    // Bound compilation metadata before constructing inputs and their small
    // expression trees. Deeper/other expressions use the ordinary pipeline.
    let admission = match context.reserve(items.len().saturating_mul(2048)) {
        Ok(value) => value,
        Err(error) => return Some(Err(procedures::translate_error(error))),
    };
    let mut inputs = Vec::new();
    if let Err(error) = inputs.try_reserve_exact(items.len()) {
        return Some(Err(procedures::translate_error(error.into())));
    }
    for item in items {
        let Expr::Function { star, args, .. } = &item.expr else {
            return None;
        };
        inputs.push(if *star {
            Input::Constant(Scalar::Integer(1))
        } else {
            Input::compile(args.first()?, &unwind.alias, row, params, 0)?
        });
    }
    let result = (|| {
        let values = eval(&unwind.expr, row, params)?;
        match &values {
            Value::Null => Ok(ControlFlow::Continue(())),
            Value::StringArray(values) => consume(
                values.iter().map(|value| Scalar::String(value)),
                &inputs,
                states,
                context,
            ),
            Value::IntArray(values) => consume(
                values.iter().map(|value| Scalar::Integer(*value)),
                &inputs,
                states,
                context,
            ),
            Value::FloatArray(values) => consume(
                values.iter().map(|value| Scalar::Float(*value)),
                &inputs,
                states,
                context,
            ),
            _ => Err(gql_type("fused UNWIND requires a typed scalar array")),
        }
    })();
    drop(admission);
    Some(result)
}

fn typed_array(value: &Value) -> bool {
    matches!(
        value,
        Value::Null | Value::StringArray(_) | Value::IntArray(_) | Value::FloatArray(_)
    )
}

fn consume<'a>(
    values: impl ExactSizeIterator<Item = Scalar<'a>>,
    inputs: &[Input<'a>],
    states: &mut [AggregateState],
    context: &ExecutionContext,
) -> Result<ControlFlow<()>> {
    let length = values.len();
    for (index, item) in values.enumerate() {
        if index % 1024 == 0 {
            context
                .charge_work(
                    (length - index)
                        .min(1024)
                        .saturating_mul(inputs.len().saturating_mul(10).saturating_add(1)),
                )
                .map_err(procedures::translate_error)?;
        }
        for (input, state) in inputs.iter().zip(states.iter_mut()) {
            let value = input.evaluate(item)?;
            // COUNT needs nullness, so a borrowed string/array never becomes an
            // allocation just to establish that it exists.
            let value = if matches!(state, AggregateState::Count(_)) {
                if value.null() {
                    Value::Null
                } else {
                    Value::Bool(true)
                }
            } else {
                value.owned()
            };
            state.update_value(value)?;
        }
    }
    Ok(ControlFlow::Continue(()))
}
