//! Write statements the string-scanning planner planned wrongly or rejected,
//! which the AST planner reads as the parser does, and the error classes it
//! keeps for clauses no write form supports.

use super::*;

fn plan(cypher: &str) -> Result<GraphMutationPlan> {
    cypher_mutation_plan(cypher)
}

#[test]
fn several_labels_types_or_lengths_are_rejected_not_joined_into_one_name() {
    // The string planner stored or matched `A:B`, `R|S` and `R*2` as one name.
    for cypher in [
        "CREATE (n:A:B {id: 'a'})",
        "MATCH (n:A:B) DELETE n",
        "MATCH (n:A:B {id: 'a'}) SET n.x = 1",
        "CREATE (a {id: 'a'})-[:R|S]->(b {id: 'b'})",
        "CREATE (a {id: 'a'})-[:R*2]->(b {id: 'b'})",
    ] {
        assert!(
            matches!(plan(cypher), Err(GrustError::Unsupported(_))),
            "{cypher}: {:?}",
            plan(cypher)
        );
    }
}

#[test]
fn an_operator_expression_is_not_stored_as_the_text_between_its_quotes() {
    // The string planner stored the string `x' + 'y`.
    assert!(matches!(
        plan("CREATE (n:X {id: 'a', v: 'x' + 'y'})"),
        Err(GrustError::Unsupported(_))
    ));
}

#[test]
fn literals_are_read_as_the_parser_reads_them() {
    let planned =
        plan("CREATE (n:X {id: 'a', s: - 5, e: 1e3, t: True, z: Null, u: 'a\\u0041', w: 'b\\u{41}', o: 'c\\0'})")
            .unwrap();
    match &planned.operations[..] {
        [GraphMutationPlanOp::UpsertNode { node, .. }] => {
            assert_eq!(node.props.get("s"), Some(&Value::Int(-5)));
            assert_eq!(node.props.get("e"), Some(&Value::Float(1000.0)));
            assert_eq!(node.props.get("t"), Some(&Value::Bool(true)));
            assert_eq!(node.props.get("z"), Some(&Value::Null));
            assert_eq!(node.props.get("u"), Some(&Value::from("aA")));
            assert_eq!(node.props.get("w"), Some(&Value::from("bA")));
            assert_eq!(node.props.get("o"), Some(&Value::from("c\0")));
        }
        other => panic!("{other:?}"),
    }
}

#[test]
fn keywords_need_no_surrounding_spaces() {
    let spaced = plan("CREATE (n:X {id: 'a'})").unwrap();
    assert_eq!(plan("CREATE(n:X {id: 'a'})").unwrap(), spaced);
    assert_eq!(
        plan("MATCH(n:X {id: 'a'}) DELETE n").unwrap(),
        plan("MATCH (n:X {id: 'a'}) DELETE n").unwrap()
    );
    let returning = cypher_mutation_plan_with_return_options(
        "CREATE (n:X {id: 'a'})RETURN n",
        CypherMutationOptions::default(),
    )
    .unwrap();
    assert_eq!(returning.plan, spaced);
    assert_eq!(
        plan("MATCH (n:X) WHERE n.name STARTS  WITH 'a' SET n.y = 1").unwrap(),
        plan("MATCH (n:X) WHERE n.name STARTS WITH 'a' SET n.y = 1").unwrap()
    );
    assert_eq!(
        plan("MATCH (n:X) WHERE n.x=1 AND(n.y=2) SET n.z = 3").unwrap(),
        plan("MATCH (n:X) WHERE n.x = 1 AND n.y = 2 SET n.z = 3").unwrap()
    );
}

#[test]
fn a_backtick_quoted_variable_is_the_name_it_quotes() {
    assert_eq!(
        plan("CREATE (`n`:X {id: 'a'})").unwrap(),
        plan("CREATE (n:X {id: 'a'})").unwrap()
    );
    // A quoted name that is not an identifier is still not a variable.
    assert!(matches!(
        plan("CREATE (`my n`:X {id: 'a'})"),
        Err(GrustError::Unsupported(_))
    ));
}

#[test]
fn a_hyphenated_word_after_delete_is_a_negated_target() {
    // `delete-a` parses as `DELETE -a`, whose target is not a node pattern.
    assert!(matches!(plan("delete-a"), Err(GrustError::Unsupported(_))));
}

#[test]
fn map_keys_and_property_names_that_are_keywords_stay_names() {
    let returning = cypher_mutation_plan_with_return_options(
        "CREATE (n:X {id: 'a', return: 1}) RETURN n",
        CypherMutationOptions::default(),
    )
    .unwrap();
    match &returning.plan.operations[..] {
        [GraphMutationPlanOp::UpsertNode { node, .. }] => {
            assert_eq!(node.props.get("return"), Some(&Value::Int(1)));
        }
        other => panic!("{other:?}"),
    }
}

fn error_class(error: &GrustError) -> &'static str {
    match error {
        GrustError::CypherSyntax(_) => "syntax",
        GrustError::Unsupported(_) => "unsupported",
        GrustError::CypherUnresolvedIdentity(_) => "unresolved",
        GrustError::CypherUnsupportedCardinality(_) => "cardinality",
        _ => "other",
    }
}

#[test]
fn unsupported_clauses_keep_their_error_classes() {
    for (cypher, expected) in [
        ("MATCH (n:X) DETACH DELETE n", "syntax"),
        ("MATCH (n:X) WHERE n.v = 1 DETACH DELETE n", "unsupported"),
        ("MATCH (n:X) DELETE n RETURN n", "unsupported"),
        ("MATCH (n:X) SET n.v = 1 RETURN n", "unsupported"),
        ("MATCH (n:X) SET n.v = $p RETURN n", "syntax"),
        ("CREATE (n:X {id: 'a'}) RETURN n", "syntax"),
        ("MATCH (n:X) WITH n SET n.v = 1", "syntax"),
        ("MERGE (n:X {id: 'a'}) ON CREATE SET n.v = 1", "syntax"),
        ("MATCH (n:X) RETURN n", "syntax"),
        ("CREATE (n:X {id: 'a'}); DELETE n", "unsupported"),
    ] {
        let error = plan(cypher).expect_err(cypher);
        assert_eq!(error_class(&error), expected, "{cypher}: {error:?}");
    }
}
