//! Conversions from typed-AST pieces to the planner's parsed write shapes:
//! literals, property maps, node and relationship patterns, property
//! references, and `WHERE` leaves.
//!
//! The error variants mirror what the string planner raised for the same
//! input, so callers see the same error class; the messages describe the AST
//! shape rather than quoting a slice of the statement text.

use crate::ast::{BinaryOp, Expr, MapLiteral, NodePattern, RelationshipPattern, UnaryOp};
use crate::*;

/// A literal (or parameter) value, as `SET`, pattern maps and `WHERE`
/// comparisons accept it.
pub(crate) fn literal_value(expr: &Expr, parameters: &CypherParameters) -> Result<Value> {
    match expr {
        Expr::String(value) => Ok(Value::String(value.clone())),
        Expr::Parameter(name) => parameter_value(name, parameters),
        Expr::Boolean(value) => Ok(Value::Bool(*value)),
        Expr::Null => Ok(Value::Null),
        _ => numeric_literal(expr).ok_or_else(|| {
            GrustError::Unsupported(format!(
                "unsupported Cypher literal value: {}",
                describe_expr(expr)
            ))
        }),
    }
}

/// An integer or float literal, optionally signed with one unary `-`/`+`.
fn numeric_literal(expr: &Expr) -> Option<Value> {
    match expr {
        Expr::Integer(value) => Some(Value::Int(*value)),
        Expr::Float(value) => Some(Value::Float(*value)),
        Expr::Unary { op, operand } => match (op, operand.as_ref()) {
            (UnaryOp::Negate, Expr::Integer(value)) => value.checked_neg().map(Value::Int),
            (UnaryOp::Negate, Expr::Float(value)) => Some(Value::Float(-value)),
            (UnaryOp::Plus, Expr::Integer(value)) => Some(Value::Int(*value)),
            (UnaryOp::Plus, Expr::Float(value)) => Some(Value::Float(*value)),
            _ => None,
        },
        _ => None,
    }
}

pub(crate) fn parameter_value(name: &str, parameters: &CypherParameters) -> Result<Value> {
    if !is_cypher_identifier(name) {
        return Err(cypher_syntax(format!(
            "unsupported Cypher parameter reference: ${name}"
        )));
    }
    parameters.get(name).cloned().ok_or_else(|| {
        cypher_unresolved_identity(format!("Cypher parameter '${name}' was not provided"))
    })
}

/// A short rendering of an expression for error messages.
pub(crate) fn describe_expr(expr: &Expr) -> String {
    match expr {
        Expr::Null => "null".to_string(),
        Expr::Boolean(value) => value.to_string(),
        Expr::Integer(value) => value.to_string(),
        Expr::Float(value) => value.to_string(),
        Expr::String(value) => format!("'{value}'"),
        Expr::Parameter(name) => format!("${name}"),
        Expr::Variable(name) => name.clone(),
        Expr::Property { base, key } => format!("{}.{key}", describe_expr(base)),
        Expr::Unary { op, operand } => {
            let op = match op {
                UnaryOp::Not => "NOT ",
                UnaryOp::Negate => "-",
                UnaryOp::Plus => "+",
            };
            format!("{op}{}", describe_expr(operand))
        }
        Expr::List(_) => "a list".to_string(),
        Expr::Map(_) => "a map".to_string(),
        Expr::Function { name, .. } => format!("{name}(...)"),
        Expr::Binary { .. } => "an operator expression".to_string(),
        _ => "an expression".to_string(),
    }
}

/// The properties of a map literal, in source order (a repeated key keeps its
/// last value).
pub(crate) fn props_from_entries(
    entries: &[(String, Expr)],
    parameters: &CypherParameters,
) -> Result<Props> {
    let mut props = Props::new();
    for (key, value) in entries {
        props.insert(key.clone(), literal_value(value, parameters)?);
    }
    Ok(props)
}

fn props_from_map(map: Option<&MapLiteral>, parameters: &CypherParameters) -> Result<Props> {
    match map {
        Some(map) => props_from_entries(&map.entries, parameters),
        None => Ok(Props::new()),
    }
}

/// A variable name as the planner binds it: a plain identifier.
pub(crate) fn checked_variable(name: &str) -> Result<String> {
    if is_cypher_identifier(name) {
        Ok(name.to_string())
    } else {
        Err(GrustError::Unsupported(format!(
            "unsupported Cypher variable name: {name}"
        )))
    }
}

fn optional_variable(name: Option<&String>) -> Result<Option<String>> {
    name.map(|name| checked_variable(name)).transpose()
}

/// A node pattern as the write planner consumes it: at most one label.
pub(crate) fn node_from_pattern(
    node: &NodePattern,
    parameters: &CypherParameters,
) -> Result<ParsedCypherNode> {
    let props = props_from_map(node.properties.as_ref(), parameters)?;
    let variable = optional_variable(node.variable.as_ref())?;
    let label = match node.labels.as_slice() {
        [] => None,
        [label] => Some(Label::new(label.clone())),
        _ => {
            return Err(GrustError::Unsupported(format!(
                "writable Cypher node patterns support one label, found :{}",
                node.labels.join(":")
            )));
        }
    };
    Ok(ParsedCypherNode {
        variable,
        label,
        props,
        predicates: Vec::new(),
    })
}

/// A relationship pattern as the write planner consumes it: exactly one type,
/// fixed length.
pub(crate) fn relationship_from_pattern(
    relationship: &RelationshipPattern,
    parameters: &CypherParameters,
) -> Result<ParsedCypherRelationship> {
    let props = props_from_map(relationship.properties.as_ref(), parameters)?;
    let label = match relationship.types.as_slice() {
        [] => {
            return Err(GrustError::Unsupported(
                "edge CREATE/MERGE/DELETE requires a relationship type".into(),
            ));
        }
        [label] => Label::new(label.clone()),
        _ => {
            return Err(GrustError::Unsupported(format!(
                "writable Cypher relationship patterns support one type, found :{}",
                relationship.types.join("|")
            )));
        }
    };
    if relationship.length.is_some() {
        return Err(GrustError::Unsupported(
            "writable Cypher does not support variable-length relationship patterns".into(),
        ));
    }
    Ok(ParsedCypherRelationship {
        variable: optional_variable(relationship.variable.as_ref())?,
        label,
        props,
        predicates: Vec::new(),
    })
}

/// True when the expression, as written, contains an unquoted `.`; the string
/// planner reported a non-property target with a dot as an unsupported
/// variable name and one without as a syntax error.
fn expr_text_has_dot(expr: &Expr) -> bool {
    match expr {
        Expr::Float(_) | Expr::Property { .. } => true,
        Expr::Null
        | Expr::Boolean(_)
        | Expr::Integer(_)
        | Expr::String(_)
        | Expr::Parameter(_)
        | Expr::Variable(_) => false,
        Expr::Unary { operand, .. } | Expr::IsNull { operand, .. } => expr_text_has_dot(operand),
        Expr::Binary { lhs, rhs, .. } => expr_text_has_dot(lhs) || expr_text_has_dot(rhs),
        Expr::List(items) => items.iter().any(expr_text_has_dot),
        Expr::Map(entries) => entries.iter().any(|(_, value)| expr_text_has_dot(value)),
        Expr::Function { args, .. } => args.iter().any(expr_text_has_dot),
        Expr::Index { base, index } => expr_text_has_dot(base) || expr_text_has_dot(index),
        _ => false,
    }
}

/// `variable.key`, as `SET`, `REMOVE` and `WHERE` targets require.
pub(crate) fn property_ref(expr: &Expr, context: &str) -> Result<(String, String)> {
    match expr {
        Expr::Property { base, key } => match base.as_ref() {
            Expr::Variable(variable) => Ok((checked_variable(variable)?, key.clone())),
            base => Err(GrustError::Unsupported(format!(
                "{context} requires property syntax target.key, found {}.{key}",
                describe_expr(base)
            ))),
        },
        expr if expr_text_has_dot(expr) => Err(GrustError::Unsupported(format!(
            "{context} requires property syntax target.key, found {}",
            describe_expr(expr)
        ))),
        _ => Err(cypher_syntax(format!(
            "{context} requires property syntax target.key"
        ))),
    }
}

/// Build the boolean tree of a `WHERE` expression: `OR`/`AND` chains are
/// flattened, `NOT` is kept, and every other expression is a leaf.
pub(crate) fn where_boolean_from_expr(expr: &Expr) -> CypherWhereBoolean<'_> {
    fn flatten<'e>(expr: &'e Expr, op: BinaryOp, out: &mut Vec<&'e Expr>) {
        match expr {
            Expr::Binary {
                op: found,
                lhs,
                rhs,
            } if *found == op => {
                flatten(lhs, op, out);
                flatten(rhs, op, out);
            }
            _ => out.push(expr),
        }
    }
    match expr {
        Expr::Binary {
            op: op @ (BinaryOp::Or | BinaryOp::And),
            ..
        } => {
            let mut terms = Vec::new();
            flatten(expr, *op, &mut terms);
            let terms = terms.into_iter().map(where_boolean_from_expr).collect();
            if *op == BinaryOp::Or {
                CypherWhereBoolean::Or(terms)
            } else {
                CypherWhereBoolean::And(terms)
            }
        }
        Expr::Unary {
            op: UnaryOp::Not,
            operand,
        } => CypherWhereBoolean::Not(Box::new(where_boolean_from_expr(operand))),
        leaf => CypherWhereBoolean::Predicate(CypherWhereLeaf::Expr(leaf)),
    }
}

/// Lower one `WHERE` leaf to a property predicate.
pub(crate) fn where_predicate_from_expr(
    expr: &Expr,
    negated: bool,
    parameters: &CypherParameters,
) -> Result<ParsedWherePredicate> {
    let maybe_invert = |op| {
        if negated {
            inverted_graph_predicate_op(op)
        } else {
            op
        }
    };
    let (lhs, op, rhs) = match expr {
        Expr::IsNull {
            operand,
            negated: is_not,
        } => {
            let op = if *is_not {
                GraphPredicateOp::IsNotNull
            } else {
                GraphPredicateOp::IsNull
            };
            let (target, key) = property_ref(operand, "MATCH WHERE predicate")?;
            return Ok(ParsedWherePredicate {
                target,
                predicate: GraphPropertyPredicate {
                    key,
                    op: maybe_invert(op),
                    value: Value::Null,
                },
            });
        }
        // The string planner cut `a.x = 1 XOR ...` at the `=` and failed on
        // the value `1 XOR ...`.
        Expr::Binary {
            op: BinaryOp::Xor, ..
        } => {
            return Err(GrustError::Unsupported(
                "MATCH WHERE does not support XOR".to_string(),
            ));
        }
        Expr::Binary { op, lhs, rhs } => (lhs.as_ref(), *op, rhs.as_ref()),
        _ => {
            return Err(cypher_syntax(
                "MATCH WHERE only supports property comparisons against literals or parameters",
            ));
        }
    };
    let string_op = match op {
        BinaryOp::StartsWith => Some(GraphPredicateOp::StartsWith),
        BinaryOp::EndsWith => Some(GraphPredicateOp::EndsWith),
        BinaryOp::Contains => Some(GraphPredicateOp::Contains),
        _ => None,
    };
    if let Some(string_op) = string_op {
        let (target, key) = property_ref(lhs, "MATCH WHERE string predicate")?;
        let value = literal_value(rhs, parameters)?;
        if !matches!(value, Value::String(_)) {
            return Err(cypher_syntax(
                "MATCH WHERE string predicates require string literals or parameters",
            ));
        }
        return Ok(ParsedWherePredicate {
            target,
            predicate: GraphPropertyPredicate {
                key,
                op: maybe_invert(string_op),
                value,
            },
        });
    }
    if op == BinaryOp::In {
        let (target, key) = property_ref(lhs, "MATCH WHERE IN predicate")?;
        let value = in_values(rhs, parameters)?;
        let op = if negated {
            GraphPredicateOp::NotIn
        } else {
            GraphPredicateOp::In
        };
        return Ok(ParsedWherePredicate {
            target,
            predicate: GraphPropertyPredicate { key, op, value },
        });
    }
    let comparison = match op {
        BinaryOp::Ge => GraphPredicateOp::GreaterThanOrEqual,
        BinaryOp::Le => GraphPredicateOp::LessThanOrEqual,
        BinaryOp::Ne => GraphPredicateOp::NotEqual,
        BinaryOp::Eq => GraphPredicateOp::Equal,
        BinaryOp::Gt => GraphPredicateOp::GreaterThan,
        BinaryOp::Lt => GraphPredicateOp::LessThan,
        _ => {
            return Err(cypher_syntax(
                "MATCH WHERE only supports property comparisons against literals or parameters",
            ));
        }
    };
    let (target, key) = property_ref(lhs, "MATCH WHERE predicate")?;
    let value = literal_value(rhs, parameters)?;
    let op = maybe_invert(comparison);
    if matches!(
        op,
        GraphPredicateOp::GreaterThan
            | GraphPredicateOp::GreaterThanOrEqual
            | GraphPredicateOp::LessThan
            | GraphPredicateOp::LessThanOrEqual
    ) && !matches!(value, Value::Int(_) | Value::Float(_) | Value::String(_))
    {
        return Err(cypher_syntax(
            "MATCH WHERE ordered comparisons require integer, float, or string literals",
        ));
    }
    Ok(ParsedWherePredicate {
        target,
        predicate: GraphPropertyPredicate { key, op, value },
    })
}

/// The right-hand side of `x IN ...`: a list literal of scalars, or a list
/// parameter.
fn in_values(expr: &Expr, parameters: &CypherParameters) -> Result<Value> {
    match expr {
        Expr::Parameter(name) => {
            let value = parameter_value(name, parameters)?;
            validate_cypher_in_values(&value)?;
            Ok(value)
        }
        Expr::List(items) => {
            let mut values = Vec::with_capacity(items.len());
            for item in items {
                let item = literal_value(item, parameters)?;
                validate_cypher_in_item(&item)?;
                values.push(item.to_json());
            }
            Ok(Value::Json(serde_json::Value::Array(values)))
        }
        _ => Err(cypher_syntax(
            "MATCH WHERE IN predicates require a list literal or list parameter",
        )),
    }
}

/// Mark the last leaf of a `WHERE` tree as followed by unsupported text.
pub(crate) fn mark_last_leaf_followed_by_text(tree: &mut CypherWhereBoolean<'_>) {
    match tree {
        CypherWhereBoolean::Predicate(leaf) => {
            if let CypherWhereLeaf::Expr(expr) = *leaf {
                *leaf = CypherWhereLeaf::FollowedByText(expr);
            }
        }
        CypherWhereBoolean::Not(inner) => mark_last_leaf_followed_by_text(inner),
        CypherWhereBoolean::And(terms) | CypherWhereBoolean::Or(terms) => {
            if let Some(last) = terms.last_mut() {
                mark_last_leaf_followed_by_text(last);
            }
        }
    }
}

/// The error the string planner raised for the last `WHERE` comparison when
/// text that is not part of the `WHERE` (a later clause, or `DETACH`)
/// followed it: the stray text was read as part of the comparison's value.
pub(crate) fn leaf_followed_by_text_error(leaf: &Expr) -> GrustError {
    let message = "MATCH WHERE is followed by an unsupported clause";
    match leaf {
        Expr::Binary {
            op: BinaryOp::Xor, ..
        } => GrustError::Unsupported(message.to_string()),
        Expr::Binary { op, lhs, rhs } => {
            let comparison = matches!(
                op,
                BinaryOp::Eq
                    | BinaryOp::Ne
                    | BinaryOp::Lt
                    | BinaryOp::Le
                    | BinaryOp::Gt
                    | BinaryOp::Ge
                    | BinaryOp::In
                    | BinaryOp::StartsWith
                    | BinaryOp::EndsWith
                    | BinaryOp::Contains
            );
            if comparison && let Err(error) = property_ref(lhs, "MATCH WHERE predicate") {
                return error;
            }
            if *op == BinaryOp::In || matches!(rhs.as_ref(), Expr::Parameter(_)) {
                cypher_syntax(message)
            } else {
                GrustError::Unsupported(message.to_string())
            }
        }
        _ => cypher_syntax(message),
    }
}
