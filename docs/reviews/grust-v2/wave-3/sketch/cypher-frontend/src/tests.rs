use super::*;
use grust_functions::{FunctionDescriptor, FunctionKind, FunctionName, FunctionRegistry};
use grust_syntax::parse_and_lower;
struct Empty;
impl FunctionRegistry for Empty {
    fn lookup(&self, _: &FunctionName, _: FunctionKind) -> Vec<&FunctionDescriptor> {
        vec![]
    }
}
fn lower(source: &str) -> Result<Plan, Vec<Diagnostic>> {
    parse_and_lower(&CypherParser, &CypherLowering { functions: &Empty }, source)
}
#[test]
fn optional_where_stays_inside_match() {
    let plan = lower("OPTIONAL MATCH (n:Person) WHERE n.age > 30 RETURN n.id AS id").unwrap();
    let Relation::Project { input, .. } = plan.root else {
        panic!("project")
    };
    let Relation::Match {
        optional, patterns, ..
    } = *input
    else {
        panic!("match")
    };
    assert!(optional);
    assert_eq!(patterns[0].vertices[0].predicates.len(), 1);
}
#[test]
fn cypher_path_is_trail_and_star_one_is_materialized() {
    let plan = lower("MATCH (a)-[*1]->(b) RETURN b.id AS id").unwrap();
    let Relation::Project { input, .. } = plan.root else {
        panic!("project")
    };
    let Relation::Match { patterns, .. } = *input else {
        panic!("match")
    };
    assert_eq!(patterns[0].mode, grust_unresolved_plan::PathMode::Trail);
    assert!(patterns[0].binding.is_some());
}
#[test]
fn refuse_incomplete_and_unfaithful_queries() {
    for source in [
        "MATCH (n)",
        "CREATE (n) RETURN n",
        "RETURN 1 AS x; RETURN 2 AS y",
        "MATCH (a)-->(b), (c)-->(d) RETURN a",
        "RETURN 2 % 1 AS x",
        "MATCH (n) RETURN n.id AS id ORDER BY n.age",
    ] {
        assert!(lower(source).is_err(), "{source}");
    }
}
#[test]
fn syntax_offsets_are_original_utf8_bytes() {
    let source = "RETURN 'é' AS x; !";
    let errors = lower(source).unwrap_err();
    assert_eq!(errors[0].code, DiagnosticCode::Syntax);
    assert!(errors[0].span.start > "RETURN 'é'".len());
    assert!(source.is_char_boundary(errors[0].span.start));
}
#[test]
fn mixed_unions_remain_left_associative() {
    let plan = lower("RETURN 1 AS x UNION RETURN 1 AS x UNION ALL RETURN 1 AS x").unwrap();
    let Relation::Union { inputs, all } = plan.root else {
        panic!("union")
    };
    assert!(all);
    assert!(matches!(inputs[0], Relation::Union { all: false, .. }));
}
