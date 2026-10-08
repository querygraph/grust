use crate::fixtures::*;
use grust_functions::FunctionName;
use grust_unresolved_plan::{self as u, Expr as E, Relation as R};
use serde_json::json;
pub fn cases() -> Vec<Case> {
    let mut out = Vec::new();
    let mut add = |name, root, expected| {
        out.push(Case {
            name,
            plan: u::Plan { root },
            expected,
            ordered: false,
        })
    };
    let left = || {
        project(
            scan("p", u::LabelExpr::label("Person")),
            vec![item("x", p("p", "id"))],
        )
    };
    let right = || {
        project(
            scan("p", u::LabelExpr::label("Person")),
            vec![item("y", p("p", "id"))],
        )
    };
    let condition = || E::variable("x").binary(u::BinaryOp::Eq, E::variable("y"));
    for (kind, name) in [
        (u::JoinKind::Inner, "explicit_inner_join"),
        (u::JoinKind::Left, "explicit_left_join"),
        (u::JoinKind::Right, "explicit_right_join"),
        (u::JoinKind::Full, "explicit_full_join"),
    ] {
        let r = R::Filter {
            input: Box::new(right()),
            predicate: E::variable("y").binary(u::BinaryOp::Le, E::from(2i64)),
        };
        let l = R::Filter {
            input: Box::new(left()),
            predicate: E::variable("x").binary(u::BinaryOp::Ge, E::from(2i64)),
        };
        let expected = match kind {
            u::JoinKind::Inner => json!([[2, 2]]),
            u::JoinKind::Left => json!([[2, 2], [3, null], [4, null], [5, null]]),
            u::JoinKind::Right => json!([[null, 1], [2, 2]]),
            u::JoinKind::Full => json!([[null, 1], [2, 2], [3, null], [4, null], [5, null]]),
            _ => unreachable!(),
        };
        add(
            name,
            project(
                R::Join {
                    left: Box::new(l),
                    right: Box::new(r),
                    kind,
                    condition: Some(condition()),
                },
                vec![item("x", E::variable("x")), item("y", E::variable("y"))],
            ),
            expected,
        );
    }
    for (kind, name, expected) in [
        (u::JoinKind::Semi, "semi_join", json!([[1], [2]])),
        (u::JoinKind::Anti, "anti_join", json!([[3], [4], [5]])),
    ] {
        let r = R::Filter {
            input: Box::new(right()),
            predicate: E::variable("y").binary(u::BinaryOp::Le, E::from(2i64)),
        };
        add(
            name,
            R::Join {
                left: Box::new(left()),
                right: Box::new(r),
                kind,
                condition: Some(condition()),
            },
            expected,
        );
    }
    let values = project(
        R::Unwind {
            input: Box::new(R::Unit),
            list: E::List(vec![E::from(10i64), E::from(20i64)]),
            binding: "y".into(),
        },
        vec![item("y", E::variable("y"))],
    );
    let l = R::Filter {
        input: Box::new(left()),
        predicate: E::variable("x").binary(u::BinaryOp::Le, E::from(2i64)),
    };
    add(
        "cross_join",
        R::Join {
            left: Box::new(l),
            right: Box::new(values),
            kind: u::JoinKind::Cross,
            condition: None,
        },
        json!([[1, 10], [1, 20], [2, 10], [2, 20]]),
    );
    add(
        "grouped_aggregate",
        R::Aggregate {
            input: Box::new(R::Unwind {
                input: Box::new(R::Unit),
                list: E::List(vec![E::from(1i64), E::from(1i64), E::from(2i64)]),
                binding: "x".into(),
            }),
            groups: vec![item("x", E::variable("x"))],
            aggregates: vec![item(
                "n",
                E::aggregate(FunctionName::new("count"), vec![E::variable("x")], false),
            )],
        },
        json!([[1, 2], [2, 1]]),
    );
    let mut multi = path("a", "b", u::PatternDirection::Outgoing);
    multi
        .vertices
        .push(vertex("c", u::LabelExpr::label("Person")));
    let mut edge = multi.edges[0].clone();
    edge.binding = u::Binding::Named("e2".into());
    multi.edges.push(edge);
    let root = |pattern| R::Match {
        input: Box::new(R::Unit),
        graph: u::GraphRef::Default,
        patterns: vec![pattern],
        optional: false,
    };
    let items = || vec![item("a", p("a", "name")), item("c", p("c", "name"))];
    add(
        "fixed_two_hop_walk",
        project(root(multi.clone()), items()),
        json!([
            ["Alice", "Cara"],
            ["Alice", "Cara"],
            ["Bob", "Cara"],
            ["Bob", "Alice"],
            ["Cara", "Cara"],
            ["Cara", "Alice"],
            ["Cara", "Bob"],
            ["Cara", "Bob"]
        ]),
    );
    multi.mode = u::PathMode::Trail;
    add(
        "fixed_two_hop_trail",
        project(root(multi.clone()), items()),
        json!([
            ["Alice", "Cara"],
            ["Alice", "Cara"],
            ["Bob", "Cara"],
            ["Bob", "Alice"],
            ["Cara", "Alice"],
            ["Cara", "Bob"],
            ["Cara", "Bob"]
        ]),
    );
    multi.mode = u::PathMode::Acyclic;
    add(
        "fixed_two_hop_acyclic",
        project(root(multi), items()),
        json!([
            ["Alice", "Cara"],
            ["Alice", "Cara"],
            ["Bob", "Alice"],
            ["Cara", "Bob"],
            ["Cara", "Bob"]
        ]),
    );
    let mut incoming = path("a", "b", u::PatternDirection::Incoming);
    incoming.vertices[0].labels = u::LabelExpr::And(vec![
        u::LabelExpr::label("Person"),
        u::LabelExpr::Not(Box::new(u::LabelExpr::label("Employee"))),
    ]);
    add(
        "incoming_label_boolean",
        project(
            root(incoming),
            vec![item("a", p("a", "name")), item("b", p("b", "name"))],
        ),
        json!([
            ["Bob", "Alice"],
            ["Bob", "Alice"],
            ["Cara", "Bob"],
            ["Cara", "Cara"],
            ["Alice", "Cara"]
        ]),
    );
    add(
        "untyped_null_comparison",
        project(
            R::Unit,
            vec![item(
                "value",
                E::from(1i64).binary(u::BinaryOp::Eq, E::Literal(u::Literal::Null)),
            )],
        ),
        json!([[null]]),
    );
    add(
        "arithmetic_unary",
        project(
            R::Unit,
            vec![
                item(
                    "value",
                    E::Unary {
                        op: u::UnaryOp::Negate,
                        argument: Box::new(
                            E::from(2i64).binary(u::BinaryOp::Multiply, E::from(3i64)),
                        ),
                    },
                ),
                item(
                    "division",
                    E::from(3i64).binary(u::BinaryOp::Divide, E::from(2i64)),
                ),
            ],
        ),
        json!([[-6, 1.5]]),
    );
    let entities = project(
        scan("p", u::LabelExpr::label("Person")),
        vec![item("q", E::variable("p"))],
    );
    add(
        "entity_projection_property_scope",
        project(entities, vec![item("name", p("q", "name"))]),
        json!([["Alice"], ["Bob"], ["Cara"], ["Dave"], ["Eve"]]),
    );
    let optional = R::Match {
        input: Box::new(scan("a", u::LabelExpr::label("Person"))),
        graph: u::GraphRef::Default,
        patterns: vec![path("a", "b", u::PatternDirection::Outgoing)],
        optional: true,
    };
    let projected = project(
        optional,
        vec![item("a", p("a", "name")), item("q", E::variable("b"))],
    );
    add(
        "nullable_entity_projection",
        project(
            projected,
            vec![item("a", E::variable("a")), item("name", p("q", "name"))],
        ),
        json!([
            ["Alice", "Bob"],
            ["Alice", "Bob"],
            ["Bob", "Cara"],
            ["Cara", "Cara"],
            ["Cara", "Alice"],
            ["Dave", null],
            ["Eve", null]
        ]),
    );
    add(
        "null_only_projection",
        project(R::Unit, vec![item("value", E::Literal(u::Literal::Null))]),
        json!([[null]]),
    );
    add(
        "null_union_type_promotion",
        R::Union {
            inputs: vec![
                project(R::Unit, vec![item("value", E::Literal(u::Literal::Null))]),
                project(R::Unit, vec![item("value", E::from(1i64))]),
            ],
            all: true,
        },
        json!([[null], [1]]),
    );
    add(
        "empty_unwind",
        project(
            R::Unwind {
                input: Box::new(R::Unit),
                list: E::List(vec![]),
                binding: "x".into(),
            },
            vec![item("value", E::variable("x"))],
        ),
        json!([]),
    );
    let mut simple = path("a", "b", u::PatternDirection::Either);
    simple
        .vertices
        .push(vertex("c", u::LabelExpr::label("Person")));
    let mut e = simple.edges[0].clone();
    e.binding = u::Binding::Named("e2".into());
    simple.edges.push(e);
    simple.mode = u::PathMode::Simple;
    add(
        "simple_closed_path_no_edge_reuse",
        project(
            R::Match {
                input: Box::new(R::Unit),
                graph: u::GraphRef::Default,
                patterns: vec![simple],
                optional: false,
            },
            vec![item("a", p("a", "name")), item("c", p("c", "name"))],
        ),
        json!([
            ["Alice", "Cara"],
            ["Alice", "Cara"],
            ["Alice", "Bob"],
            ["Bob", "Cara"],
            ["Bob", "Cara"],
            ["Bob", "Alice"],
            ["Cara", "Bob"],
            ["Cara", "Bob"],
            ["Cara", "Alice"],
            ["Cara", "Alice"],
            ["Alice", "Alice"],
            ["Alice", "Alice"],
            ["Bob", "Bob"],
            ["Bob", "Bob"]
        ]),
    );

    add(
        "entity_materialization",
        project(
            R::Filter {
                input: Box::new(scan("p", u::LabelExpr::label("Person"))),
                predicate: p("p", "id").binary(u::BinaryOp::Eq, E::from(1i64)),
            },
            vec![item("node", E::variable("p"))],
        ),
        json!([[{"identity":1,"group":1,"graph":"fixture","kind":"vertex","properties":{"age":30,"id":1,"name":"Alice","salary":null}}]]),
    );
    use grust_programmatic::{Graph, PlanBuilder};
    let dsl = Graph::new(u::GraphRef::Default)
        .vertices()
        .has_label("Person")
        .as_("a")
        .unwrap()
        .out("KNOWS")
        .as_("b")
        .unwrap()
        .select(vec![item("a", p("a", "name")), item("b", p("b", "name"))])
        .finish();
    add(
        "programmatic_api_to_sail",
        dsl.root,
        json!([
            ["Alice", "Bob"],
            ["Alice", "Bob"],
            ["Bob", "Cara"],
            ["Cara", "Cara"],
            ["Cara", "Alice"]
        ]),
    );
    out
}
