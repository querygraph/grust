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
        let mut root = None;
        for part in query.parts {
            let next = self.single(part.query)?;
            root = Some(match root {
                None => next,
                Some(previous) => Relation::Union {
                    inputs: vec![previous, next],
                    all: part.union == Some(a::UnionKind::All),
                },
            });
        }
        root.ok_or_else(|| refusal(query.span, "empty query"))
    }
    fn single(&self, query: a::SingleQuery) -> Result<Relation, Diagnostic> {
        let mut root = Relation::Unit;
        let mut graph = GraphRef::Default;
        let mut scope = Vec::<String>::new();
        let mut returned = false;
        let mut next = 0;
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
                    // Cross-pattern relationship uniqueness requires a separate MATCH-wide constraint.
                    if c.patterns.len() != 1 {
                        return Err(refusal(at, "comma-separated MATCH patterns need MATCH-wide relationship uniqueness"));
                    }
                    let mut pattern = self.pattern(&c.patterns[0], &mut scope, &mut next)?;
                    if let Some(predicate) = c.where_clause {
                        if pattern.selector != grust_unresolved_plan::PathSelector::All
                            || pattern.binding.is_some()
                            || pattern
                                .edges
                                .iter()
                                .any(|e| e.hops != grust_unresolved_plan::Hops::ONE)
                        {
                            return Err(refusal(at, "WHERE on a materialized or ranged path needs correlated path predicate lowering"));
                        }
                        pattern.vertices[0]
                            .predicates
                            .push(self.expression(&predicate, at)?);
                    }
                    root = Relation::Match {
                        input: Box::new(root),
                        graph: graph.clone(),
                        patterns: vec![pattern],
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
                a::Clause::With(c) => {
                    if !c.projection.order_by.is_empty() {
                        return Err(refusal(
                            at,
                            "WITH ordering needs ordering propagation through subsequent clauses",
                        ));
                    }
                    if c.where_clause.is_some()
                        && (!c.projection.order_by.is_empty()
                            || c.projection.skip.is_some()
                            || c.projection.limit.is_some())
                    {
                        return Err(refusal(at, "WITH WHERE combined with ordering or pagination requires explicit clause-order lowering"));
                    }
                    root = self.project(root, &c.projection, &mut scope, at)?;
                    if let Some(predicate) = c.where_clause {
                        root = Relation::Filter {
                            input: Box::new(root),
                            predicate: self.expression(&predicate, at)?,
                        };
                    }
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
        Ok(root)
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
