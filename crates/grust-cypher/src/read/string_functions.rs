//! Multi-argument scalar functions shared with the established write surface.
use super::*;

pub(super) fn evaluate(
    name: &str,
    args: &[Expr],
    scope: &ExpressionScope<'_>,
    params: &CypherParameters,
) -> Result<Value> {
    let valid = match name {
        "split" | "left" | "right" => args.len() == 2,
        "replace" => args.len() == 3,
        "substring" => matches!(args.len(), 2 | 3),
        _ => false,
    };
    if !valid {
        return Err(gql_type(format!("invalid argument count for {name}()")));
    }
    let values = args
        .iter()
        .map(|arg| eval_scoped(arg, scope, params))
        .collect::<Result<Vec<_>>>()?;
    if values.iter().any(|v| matches!(v, Value::Null)) {
        return Ok(Value::Null);
    }
    let string = |index: usize| -> Result<String> {
        match &values[index] {
            Value::String(value) => Ok(value.clone()),
            _ => Err(gql_type(format!("{name}() expects a string argument"))),
        }
    };
    let index = |index: usize| -> Result<usize> {
        match values[index] {
            Value::Int(value) if value >= 0 => {
                usize::try_from(value).map_err(|_| gql_type("string index exceeds platform range"))
            }
            _ => Err(gql_type(format!(
                "{name}() expects a non-negative integer argument"
            ))),
        }
    };
    let target = || Box::new(CypherReturnTarget::Literal(Value::Null));
    match name {
        "split" => restricted_string_split_value(
            values[0].clone(),
            &CypherReturnStringSplit {
                variable: None,
                target: target(),
                delimiter: string(1)?,
            },
        ),
        "substring" => restricted_substring_value(
            values[0].clone(),
            &CypherReturnSubstring {
                variable: None,
                target: target(),
                start: index(1)?,
                length: if values.len() == 3 {
                    Some(index(2)?)
                } else {
                    None
                },
            },
        ),
        "left" | "right" => restricted_string_slice_value(
            values[0].clone(),
            &CypherReturnStringSlice {
                variable: None,
                target: target(),
                side: if name == "left" {
                    CypherReturnStringSliceSide::Left
                } else {
                    CypherReturnStringSliceSide::Right
                },
                length: index(1)?,
            },
        ),
        "replace" => restricted_replace_value(
            values[0].clone(),
            &CypherReturnReplace {
                variable: None,
                target: target(),
                search: string(1)?,
                replacement: string(2)?,
            },
        ),
        _ => unreachable!(),
    }
}
