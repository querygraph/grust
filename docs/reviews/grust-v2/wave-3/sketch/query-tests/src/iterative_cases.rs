use crate::fixtures::*;
use grust_unresolved_plan::{self as u, Expr as E, Relation as R};
use serde_json::json;
pub fn cases() -> Vec<Case> {
    let mut cases = Vec::new();
    for (name, selector, expected) in [
        (
            "unbounded_shortest",
            u::PathSelector::Shortest,
            json!([
                [1, 2, 1],
                [1, 3, 2],
                [1, 1, 3],
                [2, 3, 1],
                [2, 1, 2],
                [2, 2, 3],
                [3, 3, 1],
                [3, 1, 1],
                [3, 2, 2]
            ]),
        ),
        (
            "unbounded_all_shortest",
            u::PathSelector::AllShortest,
            json!([
                [1, 2, 1],
                [1, 2, 1],
                [1, 3, 2],
                [1, 3, 2],
                [1, 1, 3],
                [1, 1, 3],
                [2, 3, 1],
                [2, 1, 2],
                [2, 2, 3],
                [2, 2, 3],
                [3, 3, 1],
                [3, 1, 1],
                [3, 2, 2],
                [3, 2, 2]
            ]),
        ),
    ] {
        let mut p = path("a", "b", u::PatternDirection::Outgoing);
        p.edges[0].hops = u::Hops { min: 1, max: None };
        p.selector = selector;
        p.binding = Some(u::Binding::Named("path".into()));
        cases.push(make(name, p, expected));
    }
    let mut p = path("a", "b", u::PatternDirection::Outgoing);
    p.vertices[0].labels = u::LabelExpr::label("ChainNode");
    p.vertices[1].labels = u::LabelExpr::label("ChainNode");
    p.vertices[0].predicates = vec![p_id("a", 1)];
    p.vertices[1].predicates = vec![p_id("b", 12)];
    p.edges[0].labels = u::LabelExpr::label("CHAIN");
    p.edges[0].hops = u::Hops { min: 1, max: None };
    p.selector = u::PathSelector::AllShortest;
    p.binding = Some(u::Binding::Named("path".into()));
    cases.push(make("unbounded_eleven_hops", p, json!([[1, 12, 11]])));
    let mut p = path("a", "b", u::PatternDirection::Outgoing);
    p.edges[0].hops = u::Hops { min: 1, max: None };
    p.mode = u::PathMode::Acyclic;
    p.binding = Some(u::Binding::Named("path".into()));
    cases.push(make(
        "unbounded_acyclic_all",
        p,
        json!([
            [1, 2, 1],
            [1, 2, 1],
            [2, 3, 1],
            [3, 1, 1],
            [1, 3, 2],
            [1, 3, 2],
            [2, 1, 2],
            [3, 2, 2],
            [3, 2, 2]
        ]),
    ));
    let mut p = path("a", "b", u::PatternDirection::Outgoing);
    p.edges[0].hops = u::Hops { min: 1, max: None };
    p.mode = u::PathMode::Trail;
    p.selector = u::PathSelector::All;
    p.binding = Some(u::Binding::Named("path".into()));
    cases.push(make(
        "unbounded_trail_all",
        p,
        json!([
            [1, 2, 1],
            [1, 3, 2],
            [1, 3, 3],
            [1, 1, 4],
            [1, 2, 5],
            [1, 1, 3],
            [1, 2, 4],
            [1, 2, 1],
            [1, 3, 2],
            [1, 3, 3],
            [1, 1, 4],
            [1, 2, 5],
            [1, 1, 3],
            [1, 2, 4],
            [2, 3, 1],
            [2, 3, 2],
            [2, 1, 3],
            [2, 2, 4],
            [2, 2, 4],
            [2, 1, 2],
            [2, 2, 3],
            [2, 2, 3],
            [3, 3, 1],
            [3, 1, 2],
            [3, 2, 3],
            [3, 3, 4],
            [3, 2, 3],
            [3, 3, 4],
            [3, 1, 1],
            [3, 2, 2],
            [3, 3, 3],
            [3, 3, 4],
            [3, 2, 2],
            [3, 3, 3],
            [3, 3, 4]
        ]),
    ));
    let mut p = path("a", "b", u::PatternDirection::Outgoing);
    p.edges[0].hops = u::Hops { min: 1, max: None };
    p.mode = u::PathMode::Simple;
    p.selector = u::PathSelector::All;
    p.binding = Some(u::Binding::Named("path".into()));
    cases.push(make(
        "unbounded_simple_all",
        p,
        json!([
            [1, 2, 1],
            [1, 3, 2],
            [1, 1, 3],
            [1, 2, 1],
            [1, 3, 2],
            [1, 1, 3],
            [2, 3, 1],
            [2, 1, 2],
            [2, 2, 3],
            [2, 2, 3],
            [3, 3, 1],
            [3, 1, 1],
            [3, 2, 2],
            [3, 3, 3],
            [3, 2, 2],
            [3, 3, 3]
        ]),
    ));
    let mut p = path("a", "b", u::PatternDirection::Outgoing);
    p.edges[0].hops = u::Hops { min: 2, max: None };
    p.mode = u::PathMode::Walk;
    p.selector = u::PathSelector::AllShortest;
    p.binding = Some(u::Binding::Named("path".into()));
    cases.push(make(
        "unbounded_min_two",
        p,
        json!([
            [1, 1, 3],
            [1, 1, 3],
            [1, 2, 4],
            [1, 2, 4],
            [1, 2, 4],
            [1, 2, 4],
            [1, 3, 2],
            [1, 3, 2],
            [2, 1, 2],
            [2, 2, 3],
            [2, 2, 3],
            [2, 3, 2],
            [3, 1, 2],
            [3, 2, 2],
            [3, 2, 2],
            [3, 3, 2]
        ]),
    ));
    let mut p = path("a", "b", u::PatternDirection::Outgoing);
    p.edges[0].hops = u::Hops { min: 0, max: None };
    p.mode = u::PathMode::Walk;
    p.selector = u::PathSelector::AllShortest;
    p.binding = Some(u::Binding::Named("path".into()));
    cases.push(make(
        "unbounded_zero_shortest",
        p,
        json!([
            [1, 1, 0],
            [1, 2, 1],
            [1, 2, 1],
            [1, 3, 2],
            [1, 3, 2],
            [2, 1, 2],
            [2, 2, 0],
            [2, 3, 1],
            [3, 1, 1],
            [3, 2, 2],
            [3, 2, 2],
            [3, 3, 0],
            [4, 4, 0],
            [5, 5, 0]
        ]),
    ));
    let mut p = path("a", "b", u::PatternDirection::Incoming);
    p.edges[0].hops = u::Hops { min: 1, max: None };
    p.mode = u::PathMode::Walk;
    p.selector = u::PathSelector::AllShortest;
    p.binding = Some(u::Binding::Named("path".into()));
    cases.push(make(
        "unbounded_incoming_shortest",
        p,
        json!([
            [1, 1, 3],
            [1, 1, 3],
            [1, 2, 2],
            [1, 3, 1],
            [2, 1, 1],
            [2, 1, 1],
            [2, 2, 3],
            [2, 2, 3],
            [2, 3, 2],
            [2, 3, 2],
            [3, 1, 2],
            [3, 1, 2],
            [3, 2, 1],
            [3, 3, 1]
        ]),
    ));
    let mut p = path("a", "b", u::PatternDirection::Outgoing);
    p.edges[0].hops = u::Hops { min: 1, max: None };
    p.selector = u::PathSelector::AllShortest;
    p.binding = Some(u::Binding::Named("path".into()));
    let mut optional = make(
        "unbounded_optional",
        p,
        json!([
            [1, 2, 1],
            [1, 2, 1],
            [1, 3, 2],
            [1, 3, 2],
            [1, 1, 3],
            [1, 1, 3],
            [2, 3, 1],
            [2, 1, 2],
            [2, 2, 3],
            [2, 2, 3],
            [3, 3, 1],
            [3, 1, 1],
            [3, 2, 2],
            [3, 2, 2],
            [4, null, null],
            [5, null, null]
        ]),
    );
    if let R::Project { input, .. } = &mut optional.plan.root {
        if let R::Match {
            input, optional, ..
        } = input.as_mut()
        {
            **input = scan("a", u::LabelExpr::label("Person"));
            *optional = true;
        }
    }
    cases.push(optional);
    let left = cases[0].plan.root.clone();
    let right = cases[2].plan.root.clone();
    let side = |input, prefix: &str| {
        project(
            input,
            vec![
                item(&format!("{prefix}a"), E::variable("a")),
                item(&format!("{prefix}b"), E::variable("b")),
                item(&format!("{prefix}length"), E::variable("length")),
            ],
        )
    };
    let left = R::Filter {
        input: Box::new(side(left, "l")),
        predicate: E::variable("la")
            .binary(u::BinaryOp::Eq, E::from(1i64))
            .binary(
                u::BinaryOp::And,
                E::variable("lb").binary(u::BinaryOp::Eq, E::from(3i64)),
            ),
    };
    cases.push(Case {
        name: "multiple_iterative_steps",
        plan: u::Plan {
            root: R::Join {
                left: Box::new(left),
                right: Box::new(side(right, "r")),
                kind: u::JoinKind::Cross,
                condition: None,
            },
        },
        expected: json!([[1, 3, 2, 1, 12, 11]]),
        ordered: false,
    });
    cases
}
fn p_id(binding: &str, id: i64) -> E {
    p(binding, "id").binary(u::BinaryOp::Eq, E::from(id))
}
fn make(name: &'static str, p: u::PathPattern, expected: serde_json::Value) -> Case {
    Case {
        name,
        plan: u::Plan {
            root: project(
                R::Match {
                    input: Box::new(R::Unit),
                    graph: u::GraphRef::Default,
                    patterns: vec![p],
                    optional: false,
                },
                vec![
                    item("a", p_id_expr("a")),
                    item("b", p_id_expr("b")),
                    item("length", E::variable("path").property("length")),
                ],
            ),
        },
        expected,
        ordered: false,
    }
}
fn p_id_expr(binding: &str) -> E {
    p(binding, "id")
}
