use crate::fixtures::*;
use grust_functions::{FunctionKind, FunctionName};
use grust_unresolved_plan::{self as u, Expr as E, Relation as R};
pub fn cases() -> Vec<Case> {
    use serde_json::json;
    let mut cases = Vec::new();
    let mut add = |name, root, expected, ordered| {
        cases.push(Case {
            name,
            plan: u::Plan { root },
            expected,
            ordered,
        })
    };
    let people = || scan("p", u::LabelExpr::label("Person"));
    let knows = |direction, source, target| R::Match {
        input: Box::new(R::Unit),
        graph: u::GraphRef::Default,
        patterns: vec![path(source, target, direction)],
        optional: false,
    };
    add(
        "property_filter_parameter",
        project(
            R::Filter {
                input: Box::new(people()),
                predicate: p("p", "age").binary(u::BinaryOp::Ge, E::Parameter("minimum".into())),
            },
            vec![item("name", p("p", "name"))],
        ),
        json!([["Alice"], ["Dave"], ["Eve"]]),
        false,
    );
    let two = || vec![item("a", p("a", "name")), item("b", p("b", "name"))];
    add(
        "outgoing_parallel_edges",
        project(knows(u::PatternDirection::Outgoing, "a", "b"), two()),
        json!([
            ["Alice", "Bob"],
            ["Alice", "Bob"],
            ["Bob", "Cara"],
            ["Cara", "Cara"],
            ["Cara", "Alice"]
        ]),
        false,
    );
    add(
        "either_direction_selfloop_once",
        project(knows(u::PatternDirection::Either, "a", "b"), two()),
        json!([
            ["Alice", "Bob"],
            ["Alice", "Bob"],
            ["Bob", "Alice"],
            ["Bob", "Alice"],
            ["Bob", "Cara"],
            ["Cara", "Bob"],
            ["Cara", "Cara"],
            ["Cara", "Alice"],
            ["Alice", "Cara"]
        ]),
        false,
    );
    add(
        "repeated_binding",
        project(
            knows(u::PatternDirection::Outgoing, "a", "a"),
            vec![item("name", p("a", "name"))],
        ),
        json!([["Cara"]]),
        false,
    );
    let optional = |predicate: Option<E>| {
        let mut pat = path("a", "b", u::PatternDirection::Outgoing);
        if let Some(p) = predicate {
            pat.vertices[1].predicates.push(p);
        }
        R::Match {
            input: Box::new(scan("a", u::LabelExpr::label("Person"))),
            graph: u::GraphRef::Default,
            patterns: vec![pat],
            optional: true,
        }
    };
    add(
        "optional_match",
        project(optional(None), two()),
        json!([
            ["Alice", "Bob"],
            ["Alice", "Bob"],
            ["Bob", "Cara"],
            ["Cara", "Cara"],
            ["Cara", "Alice"],
            ["Dave", null],
            ["Eve", null]
        ]),
        false,
    );
    add(
        "optional_predicate_in_on",
        project(
            optional(Some(
                E::CurrentElement
                    .property("age")
                    .binary(u::BinaryOp::Ge, E::from(30i64)),
            )),
            two(),
        ),
        json!([
            ["Alice", null],
            ["Bob", null],
            ["Cara", "Alice"],
            ["Dave", null],
            ["Eve", null]
        ]),
        false,
    );
    add(
        "polymorphic_missing_property",
        project(
            scan("v", u::LabelExpr::Any),
            vec![item("name", p("v", "name")), item("age", p("v", "age"))],
        ),
        json!([
            ["Alice", 30],
            ["Bob", 20],
            ["Cara", null],
            ["Dave", 40],
            ["Eve", 35],
            ["Acme", null]
        ]),
        false,
    );
    add(
        "aggregate_distinct_filter",
        R::Aggregate {
            input: Box::new(people()),
            groups: vec![],
            aggregates: vec![
                item(
                    "count",
                    E::aggregate(FunctionName::new("count"), vec![p("p", "age")], true),
                ),
                item(
                    "sum",
                    E::Call(u::FunctionCall {
                        name: FunctionName::new("sum"),
                        kind: FunctionKind::Aggregate,
                        arguments: vec![p("p", "age")],
                        distinct: false,
                        filter: Some(Box::new(
                            p("p", "age").binary(u::BinaryOp::Gt, E::from(30i64)),
                        )),
                    }),
                ),
            ],
        },
        json!([[4, 75]]),
        false,
    );
    let filtered = project(
        R::Filter {
            input: Box::new(people()),
            predicate: p("p", "age").binary(u::BinaryOp::Ge, E::from(30i64)),
        },
        vec![item("name", p("p", "name"))],
    );
    add(
        "union_all",
        R::Union {
            inputs: vec![filtered.clone(), filtered.clone()],
            all: true,
        },
        json!([["Alice"], ["Dave"], ["Eve"], ["Alice"], ["Dave"], ["Eve"]]),
        false,
    );
    add(
        "union_distinct",
        R::Union {
            inputs: vec![filtered.clone(), filtered],
            all: false,
        },
        json!([["Alice"], ["Dave"], ["Eve"]]),
        false,
    );
    add(
        "unwind_null_element",
        project(
            R::Unwind {
                input: Box::new(R::Unit),
                list: E::List(vec![
                    E::from(1i64),
                    E::Literal(u::Literal::Null),
                    E::from(2i64),
                ]),
                binding: "x".into(),
            },
            vec![item("x", E::variable("x"))],
        ),
        json!([[1], [null], [2]]),
        false,
    );
    add(
        "sort_offset_limit",
        R::Slice {
            input: Box::new(R::Sort {
                input: Box::new(project(people(), vec![item("name", p("p", "name"))])),
                keys: vec![u::SortKey {
                    expression: E::variable("name"),
                    descending: true,
                    nulls_first: false,
                }],
            }),
            offset: Some(E::from(1i64)),
            limit: Some(E::from(2i64)),
        },
        json!([["Dave"], ["Cara"]]),
        true,
    );
    add(
        "plugin_scalar_case",
        project(
            people(),
            vec![item(
                "value",
                E::Case {
                    branches: vec![(
                        p("p", "age").binary(u::BinaryOp::Ge, E::from(30i64)),
                        E::scalar(FunctionName::new("upper"), vec![p("p", "name")]),
                    )],
                    otherwise: Box::new(E::from("young or unknown")),
                },
            )],
        ),
        json!([
            ["ALICE"],
            ["young or unknown"],
            ["young or unknown"],
            ["DAVE"],
            ["EVE"]
        ]),
        false,
    );
    add(
        "in_list",
        project(
            R::Filter {
                input: Box::new(people()),
                predicate: p("p", "name").binary(
                    u::BinaryOp::In,
                    E::List(vec![E::from("Alice"), E::from("Dave")]),
                ),
            },
            vec![item("name", p("p", "name"))],
        ),
        json!([["Alice"], ["Dave"]]),
        false,
    );
    let map = E::Map(vec![("text".into(), E::from("a'b\\c; SELECT ☃"))]);
    add(
        "struct_literal_escaping",
        project(R::Unit, vec![item("text", map.property("text"))]),
        json!([["a'b\\c; SELECT ☃"]]),
        false,
    );
    add(
        "known_infeasible_pattern",
        project(
            R::Match {
                input: Box::new(R::Unit),
                graph: u::GraphRef::Default,
                patterns: vec![u::PathPattern {
                    vertices: vec![
                        vertex("a", u::LabelExpr::label("Company")),
                        vertex("b", u::LabelExpr::label("Person")),
                    ],
                    ..path("a", "b", u::PatternDirection::Outgoing)
                }],
                optional: false,
            },
            vec![item("name", p("a", "name"))],
        ),
        json!([]),
        false,
    );
    cases.extend(crate::more_cases::cases());
    cases
}
