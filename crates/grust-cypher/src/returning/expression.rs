//! General expression bridge for write RETURN; no binding body is string-parsed.
use super::*;
use crate::ast::Expr;

#[derive(Clone, Debug, PartialEq)]
pub struct CypherReturnExpression {
    pub(crate) expr: Expr,
    pub(crate) parameters: CypherParameters,
    pub(crate) variables: BTreeSet<String>,
}

fn has_binding(expr: &Expr) -> bool {
    if matches!(
        expr,
        Expr::Reduce { .. } | Expr::ListComprehension { .. } | Expr::Quantifier { .. }
    ) {
        return true;
    }
    let mut found = false;
    crate::semantics::visit_children(expr, &mut |child| found |= has_binding(child));
    found
}

fn free_variables(expr: &Expr, local: &BTreeSet<String>, out: &mut BTreeSet<String>) {
    match expr {
        Expr::Variable(name) if !local.contains(name) => {
            out.insert(name.clone());
        }
        Expr::Reduce {
            accumulator,
            seed,
            item,
            list,
            body,
        } => {
            free_variables(seed, local, out);
            free_variables(list, local, out);
            let mut child = local.clone();
            child.extend([accumulator.clone(), item.clone()]);
            free_variables(body, &child, out);
        }
        Expr::ListComprehension {
            item,
            list,
            predicate,
            projection,
        } => {
            free_variables(list, local, out);
            let mut child = local.clone();
            child.insert(item.clone());
            if let Some(p) = predicate {
                free_variables(p, &child, out);
            }
            if let Some(p) = projection {
                free_variables(p, &child, out);
            }
        }
        Expr::Quantifier {
            item,
            list,
            predicate,
            ..
        } => {
            free_variables(list, local, out);
            let mut child = local.clone();
            child.insert(item.clone());
            free_variables(predicate, &child, out);
        }
        _ => crate::semantics::visit_children(expr, &mut |child| free_variables(child, local, out)),
    }
}

pub(super) fn parse_projection(
    text: &str,
    alias: Option<String>,
    scope: &CypherReturnScope<'_>,
    parameters: &CypherParameters,
) -> Result<Option<CypherReturnProjection>> {
    // Existing compatibility adapters still own syntax absent from Expr (such
    // as map projections). Every binding form, including nested uses, comes here.
    let mut expr = match crate::parser::parse_expression(text) {
        Ok(expr) => expr,
        Err(error)
            if error.message.contains("reduce:")
                || error.message.contains("list comprehension:")
                || error.message.contains("quantifier:") =>
        {
            return Err(error.into_grust(text));
        }
        Err(_) => return Ok(None),
    };
    if !has_binding(&expr) {
        return Ok(None);
    }
    crate::semantics::check_return_expression(
        &expr,
        scope
            .node_bindings
            .keys()
            .chain(scope.edge_bindings.keys())
            .chain(scope.row_node_bindings.keys())
            .chain(scope.row_edge_match_bindings.keys())
            .chain(scope.row_edge_bindings.keys())
            .chain(scope.row_path_bindings.keys())
            .cloned(),
    )?;
    let mut aggregate = None;
    let mut distinct = false;
    if let Expr::Function {
        name,
        args,
        distinct: d,
        star: false,
    } = &expr
    {
        aggregate = match name.to_ascii_lowercase().as_str() {
            "count" => Some(CypherReturnAggregate::Count),
            "sum" => Some(CypherReturnAggregate::Sum),
            "avg" => Some(CypherReturnAggregate::Avg),
            "min" => Some(CypherReturnAggregate::Min),
            "max" => Some(CypherReturnAggregate::Max),
            "collect" => Some(CypherReturnAggregate::Collect),
            _ => None,
        };
        if aggregate.is_some() {
            let [arg] = args.as_slice() else {
                return Err(gql_type("aggregate expects one expression"));
            };
            distinct = *d;
            expr = arg.clone();
        }
    }
    if crate::read::expr_has_aggregate(&expr) {
        return Err(gql_type(
            "aggregates are only allowed as top-level RETURN expressions",
        ));
    }
    let mut variables = BTreeSet::new();
    free_variables(&expr, &BTreeSet::new(), &mut variables);
    Ok(Some(CypherReturnProjection {
        variable: String::new(),
        target: CypherReturnTarget::Expression(CypherReturnExpression {
            expr,
            parameters: parameters.clone(),
            variables,
        }),
        column: alias.unwrap_or_else(|| text.to_string()),
        expression: text.to_string(),
        element: if aggregate.is_some() {
            CypherReturnElement::Aggregate
        } else {
            CypherReturnElement::Literal
        },
        aggregate,
        distinct,
    }))
}
