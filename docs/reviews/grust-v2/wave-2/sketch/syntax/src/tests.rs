use super::*;
use grust_unresolved_plan::{Binding, LabelExpr, PathMode, PathSelector, VertexPattern};
struct BrokenParser;
impl Parser for BrokenParser {
    type Syntax = ReadQuery;
    fn parse(&self, _: &str) -> ParseReport<Self::Syntax> {
        ParseReport {
            syntax: Some(ReadQuery {
                graph: GraphRef::Default,
                clauses: vec![],
            }),
            diagnostics: vec![
                Diagnostic {
                    span: Span { start: 0, end: 1 },
                    code: DiagnosticCode::Syntax,
                    message: "first".into(),
                },
                Diagnostic {
                    span: Span { start: 4, end: 5 },
                    code: DiagnosticCode::Syntax,
                    message: "second".into(),
                },
            ],
        }
    }
}
#[test]
fn recovery_diagnostics_are_preserved_and_partial_queries_are_not_planned() {
    let result = parse_and_lower(&BrokenParser, &ReadLowering, "bad bad");
    let errors = result.unwrap_err();
    assert_eq!(errors.len(), 2);
    assert_eq!(errors[1].span, Span { start: 4, end: 5 });
}
struct EmptyParser;
impl Parser for EmptyParser {
    type Syntax = ReadQuery;
    fn parse(&self, _: &str) -> ParseReport<Self::Syntax> {
        ParseReport {
            syntax: None,
            diagnostics: vec![],
        }
    }
}
#[test]
fn no_ast_is_an_error_even_when_parser_diagnostics_are_empty() {
    assert!(parse_and_lower(&EmptyParser, &ReadLowering, "").is_err());
}
#[test]
fn malformed_adapter_paths_are_rejected() {
    let p = PathPattern {
        binding: None,
        vertices: vec![],
        edges: vec![],
        mode: PathMode::Walk,
        selector: PathSelector::All,
    };
    assert!(ReadLowering
        .lower(ReadQuery {
            graph: GraphRef::Default,
            clauses: vec![ReadClause::Match {
                patterns: vec![p],
                optional: false
            }]
        })
        .is_err());
}
#[test]
fn language_ast_adapters_and_programmatic_api_build_the_same_plan() {
    let path = PathPattern {
        binding: None,
        vertices: vec![VertexPattern {
            binding: Binding::Named("person".into()),
            labels: LabelExpr::label("Person"),
            predicates: vec![],
        }],
        edges: vec![],
        mode: PathMode::Walk,
        selector: PathSelector::All,
    };
    let items = vec![NamedExpr {
        name: "name".into(),
        expression: Expr::variable("person").property("name"),
    }];
    let syntax = ReadQuery {
        graph: GraphRef::Default,
        clauses: vec![
            ReadClause::Match {
                patterns: vec![path],
                optional: false,
            },
            ReadClause::Project {
                items: items.clone(),
                distinct: false,
            },
        ],
    };
    let lowered = ReadLowering.lower(syntax).unwrap();
    let built = grust_programmatic::Graph::new(GraphRef::Default)
        .vertices()
        .has_label("Person")
        .as_("person")
        .unwrap()
        .select(items);
    assert_eq!(lowered, grust_programmatic::PlanBuilder::finish(built));
}
