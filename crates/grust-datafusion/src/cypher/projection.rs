//! Shared RETURN planning for node and relationship inputs.
use super::{ExpressionBindings, NodeScanPlan, UnsupportedScan};
use datafusion::{
    common::{Column, Result},
    dataframe::DataFrame,
    logical_expr::Expr,
};
use grust_cypher::{
    CypherParameters,
    ast::{Expr as CypherExpr, Projection},
};

pub(super) fn project(
    projection: &Projection,
    mut frame: DataFrame,
    bindings: &impl ExpressionBindings,
    parameters: &CypherParameters,
) -> Result<NodeScanPlan> {
    if projection.star {
        return Ok(NodeScanPlan::Unsupported(UnsupportedScan::QueryShape));
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
        return Ok(NodeScanPlan::Unsupported(UnsupportedScan::QueryShape));
    }
    let mut ordering = Vec::with_capacity(projection.order_by.len());
    for item in &projection.order_by {
        let alias = match &item.expr {
            CypherExpr::Variable(alias) if names.contains(alias) => alias,
            expression => {
                let Some(index) = projection
                    .items
                    .iter()
                    .position(|item| &item.expr == expression)
                else {
                    return Ok(NodeScanPlan::Unsupported(UnsupportedScan::Ordering));
                };
                &names[index]
            }
        };
        ordering.push(
            Expr::Column(Column::from_name(alias.clone())).sort(!item.descending, item.descending),
        );
    }
    let offset = match bound(projection.skip.as_ref(), parameters) {
        Some(value) => value.unwrap_or(0),
        None => return Ok(NodeScanPlan::Unsupported(UnsupportedScan::Pagination)),
    };
    let limit = match bound(projection.limit.as_ref(), parameters) {
        Some(value) => value,
        None => return Ok(NodeScanPlan::Unsupported(UnsupportedScan::Pagination)),
    };
    let mut expressions = Vec::with_capacity(projection.items.len());
    let mut groups = Vec::new();
    let mut aggregates = Vec::new();
    for item in &projection.items {
        let alias = item
            .alias
            .clone()
            .unwrap_or_else(|| grust_cypher::read::column_name(&item.expr));
        if matches!(&item.expr, CypherExpr::Function { name, .. }
            if ["count", "min", "max", "sum", "avg", "collect"].iter().any(|candidate| name.eq_ignore_ascii_case(candidate)))
        {
            let Ok(expression) =
                super::lower_aggregate_with_bindings(&item.expr, bindings, parameters)
            else {
                return Ok(NodeScanPlan::Unsupported(UnsupportedScan::Expression));
            };
            aggregates.push(expression.alias(&alias));
        } else {
            let Ok(expression) =
                super::lower_expression_with_bindings(&item.expr, bindings, parameters)
            else {
                return Ok(NodeScanPlan::Unsupported(UnsupportedScan::Expression));
            };
            groups.push(expression.alias(&alias));
        }
        expressions.push(Expr::Column(Column::from_name(alias.clone())));
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
    Ok(NodeScanPlan::Supported(frame))
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
