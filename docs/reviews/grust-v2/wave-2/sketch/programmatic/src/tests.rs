use super::*;
use grust_functions::FunctionName;
#[test]
fn fluent_traversal_constructs_named_pattern_and_projection() {
    let p = Graph::new(GraphRef::Default)
        .vertices()
        .has_label("Person")
        .as_("a")
        .unwrap()
        .out("LIKES")
        .as_("b")
        .unwrap()
        .select(vec![NamedExpr {
            name: "content".into(),
            expression: Expr::variable("b").property("content"),
        }])
        .limit(10)
        .finish();
    let Relation::Slice { input, limit, .. } = p.root else {
        panic!("slice")
    };
    assert_eq!(limit, Some(10i64.into()));
    let Relation::Project { input, items, .. } = *input else {
        panic!("project")
    };
    assert_eq!(items[0].name, "content");
    let Relation::Match { patterns, .. } = *input else {
        panic!("match")
    };
    assert_eq!(patterns[0].vertices[0].binding, Binding::Named("a".into()));
    assert_eq!(patterns[0].edges[0].direction, PatternDirection::Outgoing);
}
#[test]
fn binding_after_has_does_not_leave_a_dangling_anonymous_reference() {
    let p = Graph::new(GraphRef::Default)
        .vertices()
        .has("age", BinaryOp::Gt, 18i64.into())
        .as_("person")
        .unwrap()
        .finish();
    let Relation::Match { patterns, .. } = p.root else {
        panic!()
    };
    assert!(
        matches!(&patterns[0].vertices[0].predicates[0],Expr::Binary{left,..} if matches!(left.as_ref(),Expr::Property{object,..} if object.as_ref()==&Expr::CurrentElement))
    );
}
#[test]
fn direction_path_mode_selector_and_optional_are_explicit() {
    let p = Graph::new(GraphRef::Default)
        .vertices()
        .incoming("KNOWS")
        .hops(Hops { min: 1, max: None })
        .unwrap()
        .mode(PathMode::Acyclic)
        .selector(PathSelector::Any)
        .optional()
        .finish();
    let Relation::Match {
        patterns, optional, ..
    } = p.root
    else {
        panic!()
    };
    assert!(optional);
    assert_eq!(patterns[0].edges[0].direction, PatternDirection::Incoming);
    assert_eq!(patterns[0].mode, PathMode::Acyclic);
    assert_eq!(patterns[0].selector, PathSelector::Any);
}
#[test]
fn invalid_bindings_and_hop_ranges_return_typed_errors() {
    assert!(matches!(
        Graph::new(GraphRef::Default).vertices().as_(""),
        Err(BuildError::EmptyBinding)
    ));
    assert!(matches!(
        Graph::new(GraphRef::Default)
            .vertices()
            .as_("a")
            .unwrap()
            .as_("b"),
        Err(BuildError::AlreadyBound)
    ));
    assert!(matches!(
        Graph::new(GraphRef::Default)
            .vertices()
            .out("X")
            .hops(Hops {
                min: 3,
                max: Some(1)
            }),
        Err(BuildError::InvalidHopRange)
    ));
}
#[test]
fn aggregate_and_parameterized_slice_use_the_same_ir() {
    let q = Graph::new(GraphRef::Default)
        .vertices()
        .as_("a")
        .unwrap()
        .query()
        .aggregate(
            vec![],
            vec![NamedExpr {
                name: "median".into(),
                expression: Expr::aggregate(
                    FunctionName::qualified(&["plugin"], "median"),
                    vec![Expr::variable("a").property("age")],
                    false,
                ),
            }],
        )
        .slice(None, Some(Expr::Parameter("n".into())))
        .finish();
    assert!(matches!(
        q.root,
        Relation::Slice {
            limit: Some(Expr::Parameter(_)),
            ..
        }
    ));
}
#[test]
fn join_and_union_do_not_choose_a_backend() {
    let query = || Graph::new(GraphRef::Default).vertices().query();
    assert!(matches!(
        query().join(query(), JoinKind::Cross, None).finish().root,
        Relation::Join {
            kind: JoinKind::Cross,
            ..
        }
    ));
    assert!(matches!(
        query().union(query(), true).finish().root,
        Relation::Union { all: true, .. }
    ));
}
