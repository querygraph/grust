//! Initial typed node-scan lowering over a caller-owned immutable provider.
use super::lower_expression;
use datafusion::{
    common::{Column, DataFusionError, Result},
    dataframe::DataFrame,
    functions_aggregate::expr_fn::count,
    logical_expr::{Expr, lit},
};
use grust_cypher::ast::{Clause, Expr as CypherExpr, Query};

/// Lower an analyzed single-node MATCH/WHERE/RETURN into a typed DataFrame.
/// Returns None for unsupported shapes or expression types. Semantic errors
/// remain errors. The provider must expose the validated native node-table
/// schema and one immutable graph snapshot. This does not enforce a Cypher read
/// policy or choose an execution route; callers must admit resources separately.
/// Explicit projection aliases are required in this initial implementation.
pub fn lower_node_scan(query: &Query, input: DataFrame) -> Result<Option<DataFrame>> {
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
        || pattern.start.properties.is_some()
        || projection.star
        || !projection.order_by.is_empty()
        || projection.skip.is_some()
        || projection.limit.is_some()
    {
        return Ok(None);
    }
    let schema = input.schema().as_arrow();
    let mut expressions = Vec::with_capacity(projection.items.len());
    let mut groups = Vec::new();
    let mut aggregates = Vec::new();
    for item in &projection.items {
        let Some(alias) = &item.alias else {
            return Ok(None);
        };
        if let CypherExpr::Function {
            name,
            distinct: false,
            star: true,
            args,
        } = &item.expr
        {
            if !name.eq_ignore_ascii_case("count") || !args.is_empty() {
                return Ok(None);
            }
            aggregates.push(count(lit(1_i64)).alias(alias));
        } else {
            let Ok(expression) = lower_expression(&item.expr, variable, schema) else {
                return Ok(None);
            };
            groups.push(expression.alias(alias));
        }
        expressions.push(Expr::Column(Column::from_name(alias.clone())));
    }
    let predicate = match &matched.where_clause {
        Some(expression) => match lower_expression(expression, variable, schema) {
            Ok(expression) => Some(expression),
            Err(_) => return Ok(None),
        },
        None => None,
    };
    let mut frame = input;
    for label in &pattern.start.labels {
        frame = frame.filter(Expr::Column(Column::from_name("label")).eq(lit(label.clone())))?;
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
    Ok(Some(frame))
}
