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
        self.project_filtered(input, p, scope, at, None)
    }
    pub(crate) fn project_filtered(
        &self,
        input: Relation,
        p: &a::Projection,
        scope: &mut Vec<String>,
        at: Span,
        predicate: Option<&a::Expr>,
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
        let public = items.iter().map(|i| i.name.clone()).collect::<Vec<_>>();
        let aggregate = items.iter().any(|i| has_aggregate(&i.expression));
        let mut keys = Vec::new();
        for order in &p.order_by {
            let expression = self.expression(&order.expr, at)?;
            let expression = if let Some(item) = items.iter().find(|i| i.expression == expression) {
                Expr::variable(&item.name)
            } else if bindings_visible(&expression, &public) {
                expression
            } else {
                if p.distinct || aggregate {
                    return Err(refusal(
                        at,
                        "DISTINCT and aggregate ORDER BY require projected bindings",
                    ));
                }
                let mut name = format!("@sort_{}", keys.len());
                while items.iter().any(|i| i.name == name) || scope.contains(&name) {
                    name.push('_');
                }
                items.push(NamedExpr {
                    name: name.clone(),
                    expression,
                });
                Expr::variable(name)
            };
            keys.push(SortKey {
                expression,
                descending: order.descending,
                nulls_first: order.descending,
            });
        }
        let mut root = if aggregate {
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
        *scope = public.clone();
        if let Some(predicate) = predicate {
            root = Relation::Filter {
                input: Box::new(root),
                predicate: self.expression(predicate, at)?,
            };
        }
        if !keys.is_empty() {
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
        if items.len() != public.len() {
            root = Relation::Project {
                input: Box::new(root),
                items: public
                    .iter()
                    .map(|name| NamedExpr {
                        name: name.clone(),
                        expression: Expr::variable(name),
                    })
                    .collect(),
                distinct: false,
            };
        }
        Ok(root)
    }
}

fn bindings_visible(e: &Expr, names: &[String]) -> bool {
    match e {
        Expr::Binding(grust_unresolved_plan::Binding::Named(n))
        | Expr::GraphValue(grust_unresolved_plan::Binding::Named(n)) => names.contains(n),
        Expr::Binding(_) | Expr::GraphValue(_) | Expr::CurrentElement => false,
        Expr::Property { object, .. } => bindings_visible(object, names),
        Expr::GraphIntrinsic { argument, .. } => bindings_visible(argument, names),
        Expr::Binary { left, right, .. } => {
            bindings_visible(left, names) && bindings_visible(right, names)
        }
        Expr::Unary { argument, .. } => bindings_visible(argument, names),
        Expr::Call(c) => c.arguments.iter().all(|e| bindings_visible(e, names)),
        Expr::List(v) => v.iter().all(|e| bindings_visible(e, names)),
        Expr::Map(v) => v.iter().all(|(_, e)| bindings_visible(e, names)),
        Expr::Case {
            branches,
            otherwise,
        } => {
            branches
                .iter()
                .all(|(a, b)| bindings_visible(a, names) && bindings_visible(b, names))
                && bindings_visible(otherwise, names)
        }
        Expr::Literal(_) | Expr::Parameter(_) => true,
    }
}
