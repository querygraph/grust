//! Recoverable parser and lowering contracts. No parser dependency is required.
//! Cypher and GQL implement Parser independently and can use different grammars.
use grust_unresolved_plan::{Expr, GraphRef, NamedExpr, PathPattern, Plan, Relation, SortKey};
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
/// Half-open UTF-8 byte offsets into the original source. Parser adapters
/// supply valid boundaries; this metadata does not slice the source itself.
pub struct Span {
    pub start: usize,
    pub end: usize,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DiagnosticCode {
    Syntax,
    InvalidLiteral,
    UnsupportedFeature,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Diagnostic {
    pub span: Span,
    pub code: DiagnosticCode,
    pub message: String,
}
#[derive(Clone, Debug, PartialEq)]
pub struct ParseReport<T> {
    pub syntax: Option<T>,
    pub diagnostics: Vec<Diagnostic>,
}
impl<T> ParseReport<T> {
    pub fn is_clean(&self) -> bool {
        self.syntax.is_some() && self.diagnostics.is_empty()
    }
}
pub trait Parser {
    type Syntax;
    fn parse(&self, source: &str) -> ParseReport<Self::Syntax>;
}
pub trait Lowering {
    type Syntax;
    fn lower(&self, syntax: Self::Syntax) -> Result<Plan, Vec<Diagnostic>>;
}
/// Only a complete, clean parse is exposed as input to the logical planner. Recovery may
/// retain partial syntax for editors without silently planning a partial query.
pub fn parse_and_lower<P, L>(
    parser: &P,
    lowering: &L,
    source: &str,
) -> Result<Plan, Vec<Diagnostic>>
where
    P: Parser,
    L: Lowering<Syntax = P::Syntax>,
{
    let report = parser.parse(source);
    if !report.diagnostics.is_empty() {
        return Err(report.diagnostics);
    }
    match report.syntax {
        Some(syntax) => lowering.lower(syntax),
        None => Err(vec![Diagnostic {
            span: Span {
                start: 0,
                end: source.len(),
            },
            code: DiagnosticCode::Syntax,
            message: "parser produced no query".into(),
        }]),
    }
}
/// A small shared read-query lowering surface; language AST adapters produce it.
/// It is not a Cypher or GQL parser or a full grammar AST.
#[derive(Clone, Debug, PartialEq)]
pub struct ReadQuery {
    pub graph: GraphRef,
    pub clauses: Vec<ReadClause>,
}
#[derive(Clone, Debug, PartialEq)]
pub enum ReadClause {
    Match {
        patterns: Vec<PathPattern>,
        optional: bool,
    },
    Filter(Expr),
    Project {
        items: Vec<NamedExpr>,
        distinct: bool,
    },
    Aggregate {
        groups: Vec<NamedExpr>,
        aggregates: Vec<NamedExpr>,
    },
    Sort(Vec<SortKey>),
    Slice {
        offset: Option<Expr>,
        limit: Option<Expr>,
    },
}
#[derive(Clone, Copy, Debug)]
pub struct ReadLowering;
impl Lowering for ReadLowering {
    type Syntax = ReadQuery;
    fn lower(&self, query: ReadQuery) -> Result<Plan, Vec<Diagnostic>> {
        let mut root = Relation::Unit;
        for clause in query.clauses {
            root = match clause {
                ReadClause::Match { patterns, optional } => {
                    if patterns.is_empty() || patterns.iter().any(|p| !p.is_well_formed()) {
                        return Err(vec![Diagnostic {
                            span: Span { start: 0, end: 0 },
                            code: DiagnosticCode::UnsupportedFeature,
                            message: "malformed graph path supplied by AST adapter".into(),
                        }]);
                    }
                    Relation::Match {
                        input: Box::new(root),
                        graph: query.graph.clone(),
                        patterns,
                        optional,
                    }
                }
                ReadClause::Filter(predicate) => Relation::Filter {
                    input: Box::new(root),
                    predicate,
                },
                ReadClause::Project { items, distinct } => Relation::Project {
                    input: Box::new(root),
                    items,
                    distinct,
                },
                ReadClause::Aggregate { groups, aggregates } => Relation::Aggregate {
                    input: Box::new(root),
                    groups,
                    aggregates,
                },
                ReadClause::Sort(keys) => Relation::Sort {
                    input: Box::new(root),
                    keys,
                },
                ReadClause::Slice { offset, limit } => Relation::Slice {
                    input: Box::new(root),
                    offset,
                    limit,
                },
            }
        }
        Ok(Plan { root })
    }
}
#[cfg(test)]
mod tests;
