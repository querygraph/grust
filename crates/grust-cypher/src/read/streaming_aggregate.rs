//! Constant-space, ungrouped aggregate states with the existing numeric contract.

use super::*;

pub(super) enum AggregateState {
    Count(usize),
    Sum { value: Value, count: usize },
    Average { sum: f64, count: usize },
}

impl AggregateState {
    pub(super) fn supports(expression: &Expr) -> bool {
        matches!(expression, Expr::Function { name, distinct: false, star, args }
            if (name.eq_ignore_ascii_case("count") && (*star || args.len() == 1))
                || (!*star && args.len() == 1 && (name.eq_ignore_ascii_case("sum") || name.eq_ignore_ascii_case("avg"))))
    }

    pub(super) fn new(expression: &Expr) -> Result<Self> {
        let Expr::Function { name, .. } = expression else {
            return Err(gql_type("expected aggregate function"));
        };
        match name.to_ascii_lowercase().as_str() {
            "count" => Ok(Self::Count(0)),
            "sum" => Ok(Self::Sum {
                value: Value::Int(0),
                count: 0,
            }),
            "avg" => Ok(Self::Average { sum: 0.0, count: 0 }),
            _ => Err(gql_type("aggregate has no incremental state")),
        }
    }

    pub(super) fn update(
        &mut self,
        expression: &Expr,
        row: &Row,
        params: &CypherParameters,
    ) -> Result<()> {
        let Expr::Function { star, args, .. } = expression else {
            return Err(gql_type("expected aggregate function"));
        };
        let value = if *star {
            Value::Bool(true)
        } else {
            eval(&args[0], row, params)?
        };
        self.update_value(value)
    }

    pub(super) fn update_value(&mut self, value: Value) -> Result<()> {
        let Some(value) = non_null_return_value(value) else {
            return Ok(());
        };
        match self {
            Self::Count(count) => *count = increment(*count)?,
            Self::Sum { value: sum, count } => {
                *sum = sum_return_values(&[sum.clone(), value])?;
                *count = increment(*count)?;
            }
            Self::Average { sum, count } => {
                *sum += match value {
                    Value::Int(value) => value as f64,
                    Value::Float(value) => value,
                    other => {
                        return Err(gql_type(format!(
                            "RETURN AVG only supports numeric values, got {other:?}"
                        )));
                    }
                };
                *count = increment(*count)?;
            }
        }
        Ok(())
    }

    pub(super) fn finish(self) -> Result<Value> {
        match self {
            Self::Count(count) => count_value(count),
            Self::Sum { value, count } => Ok(if count == 0 { Value::Null } else { value }),
            Self::Average { sum, count } => Ok(if count == 0 {
                Value::Null
            } else {
                Value::Float(sum / count as f64)
            }),
        }
    }
}

fn increment(count: usize) -> Result<usize> {
    count
        .checked_add(1)
        .ok_or_else(|| gql_execution("aggregate count overflow"))
}
