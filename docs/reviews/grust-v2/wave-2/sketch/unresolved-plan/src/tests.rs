use super::*;
use grust_functions::{FunctionKind, FunctionName};
fn path() -> PathPattern {
    PathPattern {
        binding: None,
        vertices: vec![
            VertexPattern {
                binding: Binding::Named("a".into()),
                labels: LabelExpr::Any,
                predicates: vec![],
            },
            VertexPattern {
                binding: Binding::Anonymous(2),
                labels: LabelExpr::Any,
                predicates: vec![],
            },
        ],
        edges: vec![EdgePattern {
            binding: Binding::Anonymous(1),
            labels: LabelExpr::Any,
            direction: PatternDirection::Incoming,
            hops: Hops { min: 0, max: None },
            predicates: vec![],
        }],
        mode: PathMode::Trail,
        selector: PathSelector::AllShortest,
    }
}
#[test]
fn pattern_modes_directions_and_unbounded_hops_survive_ir() {
    let p = path();
    assert!(p.is_well_formed());
    assert_eq!(p.mode, PathMode::Trail);
    assert_eq!(p.edges[0].hops.max, None);
    assert_eq!(p.edges[0].direction, PatternDirection::Incoming);
}
#[test]
fn named_and_anonymous_bindings_cannot_collide() {
    assert_ne!(Binding::Named("0".into()), Binding::Anonymous(0));
}
#[test]
fn malformed_paths_and_invalid_ranges_are_structural() {
    let mut p = path();
    p.vertices.pop();
    assert!(!p.is_well_formed());
    let mut p = path();
    p.edges[0].hops = Hops {
        min: 5,
        max: Some(2),
    };
    assert!(!p.is_well_formed());
}
#[test]
fn functions_remain_unresolved_and_can_be_aggregations() {
    let e = Expr::aggregate(
        FunctionName::qualified(&["plugin"], "median"),
        vec![Expr::variable("a").property("age")],
        true,
    );
    assert!(matches!(
        e,
        Expr::Call(FunctionCall {
            kind: FunctionKind::Aggregate,
            distinct: true,
            ..
        })
    ));
}
#[test]
fn extension_operator_has_no_execution_pointer() {
    let p = Plan {
        root: Relation::Extension {
            name: FunctionName::new("temporal_projection"),
            inputs: vec![Relation::Unit],
            arguments: vec![Expr::Parameter("time".into())],
        },
    };
    assert!(matches!(p.relation(), Relation::Extension { .. }));
}
#[cfg(feature = "serde")]
#[test]
fn plan_json_round_trip_preserves_semantics() {
    let p = Plan {
        root: Relation::Match {
            input: Box::new(Relation::Unit),
            graph: GraphRef::Named {
                namespace: vec!["catalog".into()],
                name: "social".into(),
            },
            patterns: vec![path()],
            optional: true,
        },
    };
    let s = serde_json::to_string(&p).unwrap();
    assert_eq!(p, serde_json::from_str::<Plan>(&s).unwrap());
}

#[cfg(feature = "serde")]
#[test]
fn floating_literals_preserve_nonfinite_values_and_signed_zero() {
    for bits in [
        0x7ff8000000000042,
        f64::INFINITY.to_bits(),
        (-0.0_f64).to_bits(),
    ] {
        let expression = Expr::float(f64::from_bits(bits));
        let json = serde_json::to_string(&expression).unwrap();
        assert_eq!(serde_json::from_str::<Expr>(&json).unwrap(), expression);
    }
}
