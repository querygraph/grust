use crate::fixtures::*;
use grust_unresolved_plan::{self as u, Expr as E, Relation as R};
use serde_json::json;
pub fn cases() -> Vec<Case> {
    let mut cases = Vec::new();
    for (name, selector, expected) in [
        (
            "bounded_walk_bag",
            u::PathSelector::All,
            json!([
                [1, 2, 1],
                [1, 2, 1],
                [1, 3, 2],
                [1, 3, 2],
                [2, 3, 1],
                [2, 3, 2],
                [2, 1, 2],
                [3, 3, 1],
                [3, 1, 1],
                [3, 3, 2],
                [3, 1, 2],
                [3, 2, 2],
                [3, 2, 2]
            ]),
        ),
        (
            "bounded_all_shortest_ties",
            u::PathSelector::AllShortest,
            json!([
                [1, 2, 1],
                [1, 2, 1],
                [1, 3, 2],
                [1, 3, 2],
                [2, 3, 1],
                [2, 1, 2],
                [3, 3, 1],
                [3, 1, 1],
                [3, 2, 2],
                [3, 2, 2]
            ]),
        ),
        (
            "bounded_shortest_one",
            u::PathSelector::Shortest,
            json!([
                [1, 2, 1],
                [1, 3, 2],
                [2, 3, 1],
                [2, 1, 2],
                [3, 3, 1],
                [3, 1, 1],
                [3, 2, 2]
            ]),
        ),
        (
            "bounded_any_one",
            u::PathSelector::Any,
            json!([
                [1, 2, 1],
                [1, 3, 2],
                [2, 3, 1],
                [2, 1, 2],
                [3, 3, 1],
                [3, 1, 1],
                [3, 2, 2]
            ]),
        ),
    ] {
        let mut pattern = path("a", "b", u::PatternDirection::Outgoing);
        pattern.edges[0].hops = u::Hops {
            min: 1,
            max: Some(2),
        };
        pattern.selector = selector;
        pattern.binding = Some(u::Binding::Named("path".into()));
        let root = project(
            R::Match {
                input: Box::new(R::Unit),
                graph: u::GraphRef::Default,
                patterns: vec![pattern],
                optional: false,
            },
            vec![
                item("a", p("a", "id")),
                item("b", p("b", "id")),
                item("length", E::variable("path").property("length")),
            ],
        );
        cases.push(Case {
            name,
            plan: u::Plan { root },
            expected,
            ordered: false,
        });
    }
    let mut zero = path("a", "b", u::PatternDirection::Outgoing);
    zero.edges[0].hops = u::Hops {
        min: 0,
        max: Some(0),
    };
    zero.binding = Some(u::Binding::Named("path".into()));
    cases.push(Case { name: "zero_hop_vertices_and_empty_edges", plan: u::Plan { root: project(
        R::Match { input: Box::new(R::Unit), graph: u::GraphRef::Default, patterns: vec![zero], optional: false },
        vec![item("a", p("a", "id")), item("b", p("b", "id")), item("edges", E::variable("e")), item("vertices", E::variable("path").property("vertices"))]) },
        expected: json!([[1,1,[],[{"group":1,"identity":1}]],[2,2,[],[{"group":1,"identity":2}]],[3,3,[],[{"group":1,"identity":3}]],[4,4,[],[{"group":1,"identity":4}]],[5,5,[],[{"group":2,"identity":5}]]]), ordered: false });
    let mut optional = path("a", "b", u::PatternDirection::Outgoing);
    optional.edges[0].hops = u::Hops {
        min: 1,
        max: Some(2),
    };
    optional.selector = u::PathSelector::AllShortest;
    optional.binding = Some(u::Binding::Named("path".into()));
    cases.push(Case {
        name: "optional_shortest_path_null",
        plan: u::Plan {
            root: project(
                R::Match {
                    input: Box::new(scan("a", u::LabelExpr::label("Person"))),
                    graph: u::GraphRef::Default,
                    patterns: vec![optional],
                    optional: true,
                },
                vec![
                    item("a", p("a", "id")),
                    item("b", p("b", "id")),
                    item("length", E::variable("path").property("length")),
                ],
            ),
        },
        expected: json!([
            [1, 2, 1],
            [1, 2, 1],
            [1, 3, 2],
            [1, 3, 2],
            [2, 3, 1],
            [2, 1, 2],
            [3, 3, 1],
            [3, 1, 1],
            [3, 2, 2],
            [3, 2, 2],
            [4, null, null],
            [5, null, null]
        ]),
        ordered: false,
    });
    cases.push(Case {
        name: "relation_provider_filtered_input",
        plan: u::Plan {
            root: R::Extension {
                name: grust_functions::FunctionName::new("keep_above"),
                inputs: vec![project(
                    scan("p", u::LabelExpr::label("Person")),
                    vec![item("value", p("p", "age"))],
                )],
                arguments: vec![E::Parameter("minimum".into())],
            },
        },
        expected: json!([[40], [35]]),
        ordered: false,
    });
    let mut trail = path("a", "b", u::PatternDirection::Outgoing);
    trail.edges[0].hops = u::Hops {
        min: 1,
        max: Some(2),
    };
    trail.mode = u::PathMode::Trail;
    trail.binding = Some(u::Binding::Named("path".into()));
    cases.push(Case {
        name: "bounded_trail_excludes_reused_selfloop",
        plan: u::Plan {
            root: project(
                R::Match {
                    input: Box::new(R::Unit),
                    graph: u::GraphRef::Default,
                    patterns: vec![trail],
                    optional: false,
                },
                vec![
                    item("a", p("a", "id")),
                    item("b", p("b", "id")),
                    item("length", E::variable("path").property("length")),
                ],
            ),
        },
        expected: json!([
            [1, 2, 1],
            [1, 2, 1],
            [2, 3, 1],
            [3, 3, 1],
            [3, 1, 1],
            [1, 3, 2],
            [1, 3, 2],
            [2, 3, 2],
            [2, 1, 2],
            [3, 1, 2],
            [3, 2, 2],
            [3, 2, 2]
        ]),
        ordered: false,
    });
    cases
}
