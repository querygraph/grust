//! Read-only Cypher AST adapter. Unsupported semantics fail before resolution.
mod expressions;
mod patterns;
mod projection;
use grust_cypher::{ast as a, lexer};
use grust_functions::FunctionRegistry;
use grust_syntax::{Diagnostic, DiagnosticCode, Lowering, ParseReport, Parser, Span};
use grust_unresolved_plan::{GraphRef, Plan, Relation};

pub struct CypherParser;
impl Parser for CypherParser {
    type Syntax = a::Query;
    fn parse(&self, source: &str) -> ParseReport<a::Query> {
        match grust_cypher::parser::parse_query(source) {
            Ok(query) => ParseReport {
                syntax: Some(query),
                diagnostics: vec![],
            },
            Err(error) => ParseReport {
                syntax: None,
                diagnostics: vec![Diagnostic {
                    span: span(error.span),
                    code: match error.kind {
                        grust_cypher::parser::ParseErrorKind::Syntax => DiagnosticCode::Syntax,
                        _ => DiagnosticCode::UnsupportedFeature,
                    },
                    message: error.message,
                }],
            },
        }
    }
}

pub struct CypherLowering<'a> {
    pub functions: &'a dyn FunctionRegistry,
}
impl Lowering for CypherLowering<'_> {
    type Syntax = a::Query;
    fn lower(&self, query: a::Query) -> Result<Plan, Vec<Diagnostic>> {
        self.query(query)
            .map(|root| Plan { root })
            .map_err(|e| vec![e])
    }
}
impl CypherLowering<'_> {
    fn query(&self, query: a::Query) -> Result<Relation, Diagnostic> {
        self.query_in(query, &[], &GraphRef::Default, &mut 0, false)
            .map(|(root, _)| root)
    }
    fn query_in(
        &self,
        query: a::Query,
        imported: &[String],
        graph: &GraphRef,
        next: &mut u64,
        correlated: bool,
    ) -> Result<(Relation, Vec<String>), Diagnostic> {
        let mut root = None;
        let mut names = None;
        for part in query.parts {
            let (relation, output) = self.single(
                part.query,
                if correlated {
                    Relation::Argument
                } else {
                    Relation::Unit
                },
                graph.clone(),
                imported.to_vec(),
                next,
            )?;
            if names.as_ref().is_some_and(|previous| previous != &output) {
                return Err(refusal(query.span, "UNION output names differ"));
            }
            names = Some(output);
            root = Some(match root {
                None => relation,
                Some(previous) => Relation::Union {
                    inputs: vec![previous, relation],
                    all: part.union == Some(a::UnionKind::All),
                },
            });
        }
        Ok((
            root.ok_or_else(|| refusal(query.span, "empty query"))?,
            names.unwrap_or_default(),
        ))
    }
    fn single(
        &self,
        query: a::SingleQuery,
        mut root: Relation,
        mut graph: GraphRef,
        mut scope: Vec<String>,
        next: &mut u64,
    ) -> Result<(Relation, Vec<String>), Diagnostic> {
        let imported = if matches!(root, Relation::Argument) {
            scope.clone()
        } else {
            Vec::new()
        };
        let mut returned = false;
        for (index, clause) in query.clauses.into_iter().enumerate() {
            let at = clause.span();
            if returned {
                return Err(refusal(at, "clauses after RETURN are not supported"));
            }
            match clause {
                a::Clause::Use(c) => {
                    if index != 0 || c.graph.contains('.') {
                        return Err(refusal(
                            at,
                            "USE requires a leading, single-component graph name",
                        ));
                    }
                    graph = GraphRef::Named {
                        namespace: vec![],
                        name: c.graph,
                    };
                }
                a::Clause::Match(c) => {
                    let mut patterns = c
                        .patterns
                        .iter()
                        .map(|p| self.pattern(p, &mut scope, next))
                        .collect::<Result<Vec<_>, _>>()?;
                    if patterns.is_empty() {
                        return Err(refusal(at, "MATCH needs a pattern"));
                    }
                    if let Some(predicate) = c.where_clause {
                        if patterns.iter().any(|pattern| {
                            pattern.selector != grust_unresolved_plan::PathSelector::All
                                || pattern.binding.is_some()
                                || pattern
                                    .edges
                                    .iter()
                                    .any(|e| e.hops != grust_unresolved_plan::Hops::ONE)
                        }) {
                            return Err(refusal(at, "WHERE on a materialized or ranged path needs correlated path predicate lowering"));
                        }
                        patterns[0].vertices[0]
                            .predicates
                            .push(self.expression(&predicate, at)?);
                    }
                    root = Relation::Match {
                        input: Box::new(root),
                        graph: graph.clone(),
                        patterns,
                        optional: c.optional,
                    };
                }
                a::Clause::Unwind(c) => {
                    if scope.contains(&c.alias) {
                        return Err(refusal(at, "UNWIND cannot replace an existing binding"));
                    }
                    root = Relation::Unwind {
                        input: Box::new(root),
                        list: self.expression(&c.expr, at)?,
                        binding: c.alias.clone(),
                    };
                    scope.push(c.alias);
                }
                a::Clause::With(mut c) => {
                    if !c.projection.star {
                        for name in &imported {
                            let present = c.projection.items.iter().any(|item| {
                                item.alias.as_ref() == Some(name)
                                    || (item.alias.is_none()
                                        && item.expr == a::Expr::Variable(name.clone()))
                            });
                            if !present {
                                c.projection.items.push(a::ReturnItem {
                                    expr: a::Expr::Variable(name.clone()),
                                    alias: None,
                                });
                            }
                        }
                    }
                    root = self.project_filtered(
                        root,
                        &c.projection,
                        &mut scope,
                        at,
                        c.where_clause.as_ref(),
                    )?;
                }
                a::Clause::Call(c) => {
                    if c.yields.is_empty() {
                        return Err(refusal(at,"procedure requires explicit YIELD until provider output metadata is declared"));
                    }
                    let mut parts = c.name.split('.').map(str::to_owned).collect::<Vec<_>>();
                    let name = grust_functions::FunctionName {
                        name: parts.pop().unwrap(),
                        namespace: parts,
                    };
                    let items = c
                        .yields
                        .iter()
                        .map(|(name, alias)| grust_unresolved_plan::NamedExpr {
                            name: alias.clone().unwrap_or_else(|| name.clone()),
                            expression: grust_unresolved_plan::Expr::variable(name),
                        })
                        .collect::<Vec<_>>();
                    for item in &items {
                        if scope.contains(&item.name) {
                            return Err(refusal(
                                at,
                                "YIELD alias conflicts with an existing binding",
                            ));
                        }
                    }
                    let body = Relation::Project {
                        input: Box::new(Relation::Extension {
                            name,
                            inputs: vec![Relation::Argument],
                            arguments: c
                                .args
                                .iter()
                                .map(|e| self.expression(e, at))
                                .collect::<Result<_, _>>()?,
                        }),
                        items: items.clone(),
                        distinct: false,
                    };
                    root = Relation::Apply {
                        input: Box::new(root),
                        body: Box::new(body),
                    };
                    scope.extend(items.into_iter().map(|item| item.name));
                    if let Some(predicate) = c.where_clause {
                        root = Relation::Filter {
                            input: Box::new(root),
                            predicate: self.expression(&predicate, at)?,
                        };
                    }
                }
                a::Clause::Subquery(c) => {
                    let (body, exports) = self.query_in(c.query, &scope, &graph, next, true)?;
                    if exports.iter().any(|name| scope.contains(name)) {
                        return Err(refusal(
                            at,
                            "subquery export conflicts with an existing binding",
                        ));
                    }
                    root = Relation::Apply {
                        input: Box::new(root),
                        body: Box::new(body),
                    };
                    scope.extend(exports);
                }
                a::Clause::Return(c) => {
                    root = self.project(root, &c.projection, &mut scope, at)?;
                    returned = true;
                }
                _ => {
                    return Err(refusal(
                        at,
                        "this read frontend does not lower procedures, subqueries or updates",
                    ))
                }
            }
        }
        if !returned {
            return Err(refusal(
                query.span,
                "a read query must terminate with RETURN",
            ));
        }
        Ok((root, scope))
    }
}
fn span(at: lexer::Span) -> Span {
    Span {
        start: at.start,
        end: at.end,
    }
}
fn refusal(at: lexer::Span, message: impl Into<String>) -> Diagnostic {
    Diagnostic {
        span: span(at),
        code: DiagnosticCode::UnsupportedFeature,
        message: message.into(),
    }
}
#[cfg(test)]
mod tests;
