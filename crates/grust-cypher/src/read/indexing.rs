//! Borrowed list indexing avoids copying a complete array for each element read.

use super::*;

pub(super) fn evaluate(
    base: &Expr,
    index: &Expr,
    row: &Row,
    params: &CypherParameters,
) -> Result<Value> {
    let borrowed = match base {
        Expr::Variable(name) => match row.get(name) {
            Some(Bound::Value(value)) => Some(value),
            _ => None,
        },
        Expr::Parameter(name) => params.get(name),
        _ => None,
    };
    if let Some(base) = borrowed {
        return element(base, eval(index, row, params)?);
    }
    // Preserve left-to-right evaluation for computed and volatile expressions.
    let base = eval(base, row, params)?;
    element(&base, eval(index, row, params)?)
}

fn element(base: &Value, index: Value) -> Result<Value> {
    match (base, index) {
        (Value::Null, _) | (_, Value::Null) => Ok(Value::Null),
        (Value::Json(serde_json::Value::Object(map)), Value::String(key)) => {
            json_element(map.get(&key))
        }
        (Value::StringArray(values), Value::Int(index)) => {
            match offset(values.len(), index).and_then(|index| values.get(index)) {
                Some(value) => {
                    read_budget::charge_intermediate_bytes(value.len(), "indexing a string array")?;
                    Ok(Value::String(value.clone()))
                }
                None => Ok(Value::Null),
            }
        }
        (Value::IntArray(values), Value::Int(index)) => Ok(offset(values.len(), index)
            .and_then(|index| values.get(index))
            .copied()
            .map(Value::Int)
            .unwrap_or(Value::Null)),
        (Value::FloatArray(values), Value::Int(index)) => Ok(offset(values.len(), index)
            .and_then(|index| values.get(index))
            .copied()
            .map(Value::Float)
            .unwrap_or(Value::Null)),
        (Value::Json(serde_json::Value::Array(values)), Value::Int(index)) => {
            json_element(offset(values.len(), index).and_then(|index| values.get(index)))
        }
        (base, index) => Err(gql_type(format!(
            "indexing expects list[integer] or map[string], got {base:?}[{index:?}]"
        ))),
    }
}

fn offset(length: usize, index: i64) -> Option<usize> {
    let index = if index < 0 {
        (length as i128) + i128::from(index)
    } else {
        i128::from(index)
    };
    usize::try_from(index).ok().filter(|index| *index < length)
}

fn json_element(value: Option<&serde_json::Value>) -> Result<Value> {
    match value {
        None => Ok(Value::Null),
        Some(value) => {
            read_budget::charge_intermediate_bytes(
                read_budget::json_copy_bytes(value),
                "indexing a JSON value",
            )?;
            Ok(Value::from_json(value.clone()))
        }
    }
}
