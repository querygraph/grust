//! Until a dialect implements binding forms, decline the entire read plan,
//! including bindings hidden inside projections, subqueries or procedure args.
use crate::ast::*;

fn expression(expr: &Expr) -> bool {
    if matches!(
        expr,
        Expr::Reduce { .. } | Expr::ListComprehension { .. } | Expr::Quantifier { .. }
    ) {
        return true;
    }
    let mut found = false;
    crate::semantics::visit_children(expr, &mut |child| found |= expression(child));
    found
}

fn projection(p: &Projection) -> bool {
    p.items.iter().any(|i| expression(&i.expr))
        || p.order_by.iter().any(|i| expression(&i.expr))
        || p.skip.as_ref().is_some_and(expression)
        || p.limit.as_ref().is_some_and(expression)
}

fn pattern(p: &PathPattern) -> bool {
    let map = |m: &MapLiteral| m.entries.iter().any(|(_, e)| expression(e));
    p.start.properties.as_ref().is_some_and(map)
        || p.segments.iter().any(|s| {
            s.node.properties.as_ref().is_some_and(map)
                || s.relationship.properties.as_ref().is_some_and(map)
        })
}

pub(super) fn query_has_bindings(query: &Query) -> bool {
    query.parts.iter().any(|part| {
        part.query.clauses.iter().any(|clause| match clause {
            Clause::Match(c) => {
                c.patterns.iter().any(pattern) || c.where_clause.as_ref().is_some_and(expression)
            }
            Clause::With(c) => {
                projection(&c.projection) || c.where_clause.as_ref().is_some_and(expression)
            }
            Clause::Return(c) => projection(&c.projection),
            Clause::Unwind(c) => expression(&c.expr),
            Clause::Call(c) => {
                c.args.iter().any(expression) || c.where_clause.as_ref().is_some_and(expression)
            }
            Clause::Subquery(c) => query_has_bindings(&c.query),
            Clause::Use(_) => false,
            // Updating queries cannot be read pushdowns either.
            Clause::Create(_)
            | Clause::Merge(_)
            | Clause::Delete(_)
            | Clause::Set(_)
            | Clause::Remove(_) => true,
        })
    })
}
