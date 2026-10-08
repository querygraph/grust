use crate::{expressions::has_aggregate, refusal, CypherLowering};
use grust_cypher::{ast as a, lexer::Span};
use grust_syntax::Diagnostic;
use grust_unresolved_plan::{Expr, NamedExpr, Relation, SortKey};
impl CypherLowering<'_> {
    pub(crate) fn project(
        &self,
        input: Relation,
        p: &a::Projection,
        scope: &mut Vec<String>,
        at: Span,
    ) -> Result<Relation, Diagnostic> {
        let mut items = if p.star {
            scope
                .iter()
                .map(|name| NamedExpr {
                    name: name.clone(),
                    expression: Expr::variable(name),
                })
                .collect::<Vec<_>>()
        } else {
            vec![]
        };
        if p.star && scope.is_empty() {
            return Err(refusal(at, "star projection requires a visible binding"));
        }
        for item in &p.items {
            let name = match &item.alias {
                Some(alias) => alias.clone(),
                None => match &item.expr {
                    a::Expr::Variable(v) => v.clone(),
                    a::Expr::Property { base, key } => match base.as_ref() {
                        a::Expr::Variable(v) => format!("{v}.{key}"),
                        _ => return Err(refusal(at, "complex result expressions require AS")),
                    },
                    _ => return Err(refusal(at, "complex result expressions require AS")),
                },
            };
            if items.iter().any(|i| i.name == name) {
                return Err(refusal(at, "duplicate projection names"));
            }
            items.push(NamedExpr {
                name,
                expression: self.expression(&item.expr, at)?,
            });
        }
        let mut root = if items.iter().any(|i| has_aggregate(&i.expression)) {
            if p.star {
                return Err(refusal(
                    at,
                    "star expansion combined with aggregate is not supported",
                ));
            }
            let (aggregates, groups) = items
                .iter()
                .cloned()
                .partition(|i| has_aggregate(&i.expression));
            Relation::Project {
                input: Box::new(Relation::Aggregate {
                    input: Box::new(input),
                    groups,
                    aggregates,
                }),
                items: items
                    .iter()
                    .map(|i| NamedExpr {
                        name: i.name.clone(),
                        expression: Expr::variable(&i.name),
                    })
                    .collect(),
                distinct: p.distinct,
            }
        } else {
            Relation::Project {
                input: Box::new(input),
                items: items.clone(),
                distinct: p.distinct,
            }
        };
        *scope = items.iter().map(|i| i.name.clone()).collect();
        if !p.order_by.is_empty() {
            let keys=p.order_by.iter().map(|order| {
                let expression=self.expression(&order.expr,at)?;
                let name=if let a::Expr::Variable(name)=&order.expr {
                    if scope.contains(name) {Some(name.clone())} else {None}
                } else {None}.or_else(||items.iter().find(|i|i.expression==expression).map(|i|i.name.clone()));
                Ok(SortKey{expression:Expr::variable(name.ok_or_else(||refusal(at,"ORDER BY must reference a projected name or exact projected expression"))?),descending:order.descending,nulls_first:order.descending})
            }).collect::<Result<_,Diagnostic>>()?;
            root = Relation::Sort {
                input: Box::new(root),
                keys,
            };
        }
        if p.skip.is_some() || p.limit.is_some() {
            root = Relation::Slice {
                input: Box::new(root),
                offset: p
                    .skip
                    .as_ref()
                    .map(|e| self.expression(e, at))
                    .transpose()?,
                limit: p
                    .limit
                    .as_ref()
                    .map(|e| self.expression(e, at))
                    .transpose()?,
            };
        }
        Ok(root)
    }
}
