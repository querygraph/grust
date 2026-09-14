//! Initial typed node-scan lowering over a caller-owned immutable provider.
use super::lower_expression_with_parameters;
use datafusion::{
    common::{Column, DataFusionError, Result},
    dataframe::DataFrame,
    functions_aggregate::expr_fn::{count, count_distinct},
    logical_expr::{Expr, lit},
};
use grust_cypher::CypherParameters;
use grust_cypher::ast::{Clause, Expr as CypherExpr, Query};

/// Lower an analyzed single-node MATCH/WHERE/RETURN into a typed DataFrame.
/// Returns None for unsupported shapes or expression types. Semantic errors
/// remain errors. The provider must expose the validated native node-table
/// schema and one immutable graph snapshot. This does not enforce a Cypher read
/// policy or choose an execution route; callers must admit resources separately.
/// Implicit output names follow the shared Cypher projection contract.
pub fn lower_node_scan(query: &Query, input: DataFrame) -> Result<Option<DataFrame>> {
    lower_node_scan_with_parameters(query, input, &CypherParameters::new())
}

/// Parameter-bound form of [`lower_node_scan`]. Parameter types participate in
/// eligibility; callers must replan when bindings change.
pub fn lower_node_scan_with_parameters(
    query: &Query,
    input: DataFrame,
    parameters: &CypherParameters,
) -> Result<Option<DataFrame>> {
    grust_cypher::semantics::analyze(query)
        .map_err(|error| DataFusionError::Plan(error.to_string()))?;
    let [part] = query.parts.as_slice() else {
        return Ok(None);
    };
    let [Clause::Match(matched), Clause::Return(returned)] = part.query.clauses.as_slice() else {
        return Ok(None);
    };
    let [pattern] = matched.patterns.as_slice() else {
        return Ok(None);
    };
    let Some(variable) = pattern.start.variable.as_deref() else {
        return Ok(None);
    };
    let projection = &returned.projection;
    if part.union.is_some()
        || matched.optional
        || pattern.variable.is_some()
        || pattern.shortest.is_some()
        || !pattern.segments.is_empty()
        || projection.star
    {
        return Ok(None);
    }
    let names = projection
        .items
        .iter()
        .map(|item| {
            item.alias
                .clone()
                .unwrap_or_else(|| grust_cypher::read::column_name(&item.expr))
        })
        .collect::<Vec<_>>();
    if names
        .iter()
        .collect::<std::collections::BTreeSet<_>>()
        .len()
        != names.len()
    {
        // DataFusion requires unique logical field names; the ordinary executor
        // retains Cypher's duplicate-column contract until result remapping exists.
        return Ok(None);
    }
    let mut ordering = Vec::with_capacity(projection.order_by.len());
    for item in &projection.order_by {
        let CypherExpr::Variable(alias) = &item.expr else {
            return Ok(None);
        };
        if !projection
            .items
            .iter()
            .any(|item| item.alias.as_ref() == Some(alias))
        {
            return Ok(None);
        }
        ordering.push(
            Expr::Column(Column::from_name(alias.clone())).sort(!item.descending, item.descending),
        );
    }
    let offset = match bound(projection.skip.as_ref(), parameters) {
        Some(value) => value.unwrap_or(0),
        None => return Ok(None),
    };
    let limit = match bound(projection.limit.as_ref(), parameters) {
        Some(value) => value,
        None => return Ok(None),
    };
    let schema = input.schema().as_arrow();
    let mut expressions = Vec::with_capacity(projection.items.len());
    let mut groups = Vec::new();
    let mut aggregates = Vec::new();
    for item in &projection.items {
        let alias = item
            .alias
            .clone()
            .unwrap_or_else(|| grust_cypher::read::column_name(&item.expr));
        if let CypherExpr::Function {
            name,
            distinct,
            star,
            args,
        } = &item.expr
        {
            if !name.eq_ignore_ascii_case("count") {
                return Ok(None);
            }
            let expression = match (*star, args.as_slice()) {
                (true, []) if !*distinct => lit(1_i64),
                (false, [argument]) => {
                    let Ok(expression) =
                        lower_expression_with_parameters(argument, variable, schema, parameters)
                    else {
                        return Ok(None);
                    };
                    expression
                }
                _ => return Ok(None),
            };
            aggregates.push(
                if *distinct {
                    count_distinct(expression)
                } else {
                    count(expression)
                }
                .alias(&alias),
            );
        } else {
            let Ok(expression) =
                lower_expression_with_parameters(&item.expr, variable, schema, parameters)
            else {
                return Ok(None);
            };
            groups.push(expression.alias(&alias));
        }
        expressions.push(Expr::Column(Column::from_name(alias.clone())));
    }
    let predicate = match &matched.where_clause {
        Some(expression) => {
            match lower_expression_with_parameters(expression, variable, schema, parameters) {
                Ok(expression) => Some(expression),
                Err(_) => return Ok(None),
            }
        }
        None => None,
    };
    let mut inline = Vec::new();
    if let Some(properties) = &pattern.start.properties {
        for (key, value) in &properties.entries {
            // Pattern-map values are evaluated without the new node binding.
            if !matches!(
                value,
                CypherExpr::Null
                    | CypherExpr::Boolean(_)
                    | CypherExpr::Integer(_)
                    | CypherExpr::String(_)
                    | CypherExpr::Parameter(_)
            ) {
                return Ok(None);
            }
            let comparison = CypherExpr::Binary {
                op: grust_cypher::ast::BinaryOp::Eq,
                lhs: Box::new(CypherExpr::Property {
                    base: Box::new(CypherExpr::Variable(variable.into())),
                    key: key.clone(),
                }),
                rhs: Box::new(value.clone()),
            };
            let Ok(predicate) =
                lower_expression_with_parameters(&comparison, variable, schema, parameters)
            else {
                return Ok(None);
            };
            inline.push(predicate);
        }
    }
    let mut frame = input;
    for label in &pattern.start.labels {
        frame = frame.filter(Expr::Column(Column::from_name("label")).eq(lit(label.clone())))?;
    }
    for predicate in inline {
        frame = frame.filter(predicate)?;
    }
    if let Some(predicate) = predicate {
        frame = frame.filter(predicate)?;
    }
    frame = if aggregates.is_empty() {
        frame.select(groups)?
    } else {
        frame.aggregate(groups, aggregates)?.select(expressions)?
    };
    if projection.distinct {
        frame = frame.distinct()?;
    }
    if !ordering.is_empty() {
        frame = frame.sort(ordering)?;
    }
    if offset != 0 || limit.is_some() {
        frame = frame.limit(offset, limit)?;
    }
    Ok(Some(frame))
}

fn bound(expression: Option<&CypherExpr>, parameters: &CypherParameters) -> Option<Option<usize>> {
    let Some(expression) = expression else {
        return Some(None);
    };
    let value = match expression {
        CypherExpr::Integer(value) => *value,
        CypherExpr::Parameter(name) => match parameters.get(name)? {
            grust_core::Value::Int(value) => *value,
            _ => return None,
        },
        _ => return None,
    };
    usize::try_from(value).ok().map(Some)
}
