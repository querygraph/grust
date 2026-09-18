//! Lexically scoped list bindings, shared by every expression context.
use super::*;

pub(super) fn reduce(
    accumulator: &str,
    seed: &Expr,
    item: &str,
    list: &Expr,
    body: &Expr,
    scope: &ExpressionScope<'_>,
    params: &CypherParameters,
) -> Result<Value> {
    let mut result = eval_scoped(seed, scope, params)?;
    let seed_kind = value_kind(&result);
    let list = eval_scoped(list, scope, params)?;
    if matches!(list, Value::Null) {
        return Ok(Value::Null);
    }
    for value in elements(list, "reduce")? {
        read_budget::charge_candidate_work(1, "evaluating reduce element")?;
        let acc = Bound::Value(result);
        let element = Bound::Value(value);
        let child = scope.bind(accumulator, &acc);
        let child = child.bind(item, &element);
        result = eval_scoped(body, &child, params)?;
        if let (Some(expected), Some(actual)) = (seed_kind, value_kind(&result))
            && expected != actual
        {
            return Err(gql_type(format!(
                "reduce body type {actual} differs from seed type {expected}"
            )));
        }
    }
    Ok(result)
}

fn value_kind(value: &Value) -> Option<&'static str> {
    Some(match value {
        Value::Null => return None,
        Value::Bool(_) => "boolean",
        Value::Int(_) | Value::Float(_) | Value::Decimal(_) => "number",
        Value::String(_) => "string",
        Value::DateTime(_) => "datetime",
        Value::Duration(_) => "duration",
        Value::StringArray(_)
        | Value::IntArray(_)
        | Value::FloatArray(_)
        | Value::Json(serde_json::Value::Array(_)) => "list",
        Value::Json(serde_json::Value::Object(_)) => "map",
        Value::Json(_) => "json",
        Value::Path(_) => "path",
        Value::Graph(_) => "graph",
    })
}

pub(super) fn comprehension(
    item: &str,
    list: &Expr,
    predicate: Option<&Expr>,
    projection: Option<&Expr>,
    scope: &ExpressionScope<'_>,
    params: &CypherParameters,
) -> Result<Value> {
    let list = eval_scoped(list, scope, params)?;
    if matches!(list, Value::Null) {
        return Ok(Value::Null);
    }
    let mut out = Vec::new();
    for value in elements(list, "list comprehension")? {
        read_budget::charge_candidate_work(1, "evaluating list comprehension element")?;
        let element = Bound::Value(value);
        let child = scope.bind(item, &element);
        if let Some(predicate) = predicate
            && as_bool(eval_scoped(predicate, &child, params)?)? != Some(true)
        {
            continue;
        }
        let value = match projection {
            Some(projection) => eval_scoped(projection, &child, params)?,
            None => bound_value(&element)?,
        };
        read_budget::charge_intermediate_bytes(
            read_budget::value_copy_bytes(&value),
            "collecting list comprehension",
        )?;
        out.push(value_into_json(value));
    }
    Ok(Value::Json(serde_json::Value::Array(out)))
}

// Iterate owned lists without collecting a second full vector before charging
// the per-element budget. NULL is handled by each form before this conversion.
fn elements(value: Value, form: &str) -> Result<Box<dyn Iterator<Item = Value>>> {
    Ok(match value {
        Value::StringArray(values) => Box::new(values.into_iter().map(Value::String)),
        Value::IntArray(values) => Box::new(values.into_iter().map(Value::Int)),
        Value::FloatArray(values) => Box::new(values.into_iter().map(Value::Float)),
        Value::Json(serde_json::Value::Array(values)) => {
            Box::new(values.into_iter().map(Value::from_json))
        }
        _ => return Err(gql_type(format!("{form} expects a list"))),
    })
}

pub(super) fn quantifier(
    kind: ListQuantifier,
    item: &str,
    list: &Expr,
    predicate: &Expr,
    scope: &ExpressionScope<'_>,
    params: &CypherParameters,
) -> Result<Value> {
    let legacy_needle = if scope.legacy_quantifier_equality() {
        legacy_equality_operand(item, list, predicate)
            .map(|operand| eval_scoped(operand, scope, params))
            .transpose()?
    } else {
        None
    };
    let list = eval_scoped(list, scope, params)?;
    if matches!(legacy_needle, Some(Value::Null)) {
        return Ok(Value::Null);
    }
    if matches!(list, Value::Null) {
        return Ok(Value::Null);
    }
    let mut matched = 0usize;
    let mut total = 0usize;
    let mut saw_null = false;
    let mut saw_false = false;
    let values = elements(list, "quantifier").map_err(|error| {
        if legacy_needle.is_some() {
            cypher_unsupported_cardinality(
                "writable Cypher RETURN list predicates only support array values",
            )
        } else {
            error
        }
    })?;
    for value in values {
        read_budget::charge_candidate_work(1, "evaluating quantifier element")?;
        let legacy_match = legacy_needle.as_ref().map(|needle| value == *needle);
        let element = Bound::Value(value);
        let child = scope.bind(item, &element);
        total += 1;
        let decision = match legacy_match {
            Some(equal) => Some(equal),
            None => as_bool(eval_scoped(predicate, &child, params)?)?,
        };
        match decision {
            Some(true) => matched += 1,
            Some(false) => saw_false = true,
            None => saw_null = true,
        }
    }
    // Evaluate every element, preserving resource accounting and errors even
    // when a preceding predicate determines the boolean result.
    let known = match kind {
        ListQuantifier::Any if matched > 0 => Some(true),
        ListQuantifier::None if matched > 0 => Some(false),
        ListQuantifier::Single if matched > 1 => Some(false),
        ListQuantifier::All if saw_false => Some(false),
        ListQuantifier::All if !saw_null || matched == total => Some(matched == total),
        _ if saw_null => None,
        ListQuantifier::Any => Some(false),
        ListQuantifier::None => Some(true),
        ListQuantifier::Single => Some(matched == 1),
        ListQuantifier::All => Some(false),
    };
    Ok(to_bool_or_null(known))
}

// The formerly admitted write shape used exact Value equality and returned NULL
// for a NULL needle even on an empty list. Preserve that contract in the shared
// loop; arbitrary predicates retain ordinary three-valued expression semantics.
fn legacy_equality_operand<'a>(item: &str, list: &Expr, predicate: &'a Expr) -> Option<&'a Expr> {
    let Expr::Property { base, .. } = list else {
        return None;
    };
    let Expr::Variable(variable) = base.as_ref() else {
        return None;
    };
    let Expr::Binary {
        op: BinaryOp::Eq,
        lhs,
        rhs,
    } = predicate
    else {
        return None;
    };
    if !matches!(lhs.as_ref(), Expr::Variable(name) if name == item) {
        return None;
    }
    fn references_only(expr: &Expr, allowed: &str) -> bool {
        if let Expr::Variable(name) = expr {
            return name == allowed;
        }
        if matches!(
            expr,
            Expr::Reduce { .. } | Expr::ListComprehension { .. } | Expr::Quantifier { .. }
        ) {
            return false;
        }
        let mut valid = true;
        crate::semantics::visit_children(expr, &mut |child| {
            valid &= references_only(child, allowed)
        });
        valid
    }
    references_only(rhs, variable).then_some(rhs)
}
