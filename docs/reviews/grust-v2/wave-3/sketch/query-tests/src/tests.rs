use crate::fixtures::*;
use grust_backend::query::SailSql;
use grust_functions::*;
use grust_lpg::LogicalType;
use grust_resolution::{query::QueryResolver, Context, ResolveError};
use grust_unresolved_plan::{self as u, Expr as E, Relation as R};
fn resolve(plan: u::Plan) -> Result<grust_resolved_plan::query::Plan, Vec<ResolveError>> {
    let catalog = FixtureCatalog::default();
    let registry = registry();
    QueryResolver.resolve(
        &plan,
        &Context {
            catalog: &catalog,
            functions: &registry,
            parameters: &Parameters,
        },
    )
}
#[test]
fn every_result_fixture_resolves_and_emits() {
    let parameters = values();
    for case in cases() {
        let resolved = resolve(case.plan).unwrap_or_else(|e| panic!("{}: {e:?}", case.name));
        assert!(!SailSql {
            storage: &Storage,
            parameters: &parameters
        }
        .emit(&resolved)
        .unwrap()
        .is_empty());
    }
}
#[test]
fn property_scope_and_predicate_types_are_checked() {
    let input = scan("p", u::LabelExpr::label("Person"));
    assert!(
        matches!(resolve(u::Plan{root:project(input.clone(),vec![item("bad",p("p","missing"))])}),Err(e) if matches!(&e[0],ResolveError::UnknownProperty(_)))
    );
    assert!(resolve(u::Plan {
        root: R::Filter {
            input: Box::new(input.clone()),
            predicate: p("p", "age")
        }
    })
    .is_err());
    let projected = project(input, vec![item("name", p("p", "name"))]);
    assert!(resolve(u::Plan {
        root: project(projected, vec![item("age", p("p", "age"))])
    })
    .is_err());
}
#[test]
fn aggregation_scope_and_nesting_are_checked() {
    let input = scan("p", u::LabelExpr::label("Person"));
    assert!(resolve(u::Plan {
        root: R::Aggregate {
            input: Box::new(input.clone()),
            groups: vec![],
            aggregates: vec![item("bad", p("p", "age"))]
        }
    })
    .is_err());
    let nested = E::aggregate(
        FunctionName::new("sum"),
        vec![E::aggregate(
            FunctionName::new("sum"),
            vec![p("p", "age")],
            false,
        )],
        false,
    );
    assert!(resolve(u::Plan {
        root: R::Aggregate {
            input: Box::new(input.clone()),
            groups: vec![],
            aggregates: vec![item("bad", nested)]
        }
    })
    .is_err());
    assert!(resolve(u::Plan {
        root: project(
            input,
            vec![item(
                "bad",
                E::aggregate(FunctionName::new("sum"), vec![p("p", "age")], false)
            )]
        )
    })
    .is_err());
}
#[test]
fn unsupported_paths_unknown_graphs_and_labels_refuse() {
    let mut pat = path("a", "b", u::PatternDirection::Outgoing);
    pat.edges[0].hops = u::Hops { min: 1, max: None };
    assert!(resolve(u::Plan {
        root: R::Match {
            input: Box::new(R::Unit),
            graph: u::GraphRef::Default,
            patterns: vec![pat],
            optional: false
        }
    })
    .is_err());
    assert!(
        matches!(resolve(u::Plan{root:scan("p",u::LabelExpr::label("Unknown"))}),Err(e) if matches!(&e[0],ResolveError::UnknownLabel(_)))
    );
}
#[test]
fn numeric_generic_overloads_are_resolved_without_casts() {
    let catalog = FixtureCatalog::default();
    let mut registry = registry();
    for (argument, provider) in [
        (ArgumentType::Variable(1), "generic"),
        (ArgumentType::Exact(LogicalType::Int64), "exact"),
    ] {
        registry
            .register(FunctionDescriptor {
                name: FunctionName::new("identity"),
                kind: FunctionKind::Scalar,
                signature: Signature {
                    arguments: vec![argument],
                    variadic: None,
                    result: ReturnType::Argument(0),
                },
                nulls: NullSemantics::Strict,
                backends: BackendSupport::Any,
                volatility: Volatility::Immutable,
                provider: provider.into(),
            })
            .unwrap();
    }
    let plan = u::Plan {
        root: project(
            R::Unit,
            vec![item(
                "x",
                E::scalar(FunctionName::new("identity"), vec![E::from(1i64)]),
            )],
        ),
    };
    let resolved = QueryResolver
        .resolve(
            &plan,
            &Context {
                catalog: &catalog,
                functions: &registry,
                parameters: &Parameters,
            },
        )
        .unwrap();
    let grust_resolved_plan::query::Op::Project { items, .. } = resolved.root.op else {
        panic!()
    };
    let grust_resolved_plan::query::Value::Call { function, .. } = &items[0].1.kind else {
        panic!()
    };
    assert_eq!(function.provider, "exact");
}
#[test]
fn parameter_value_mismatch_and_nonfinite_literals_refuse() {
    let plan = resolve(u::Plan {
        root: project(R::Unit, vec![item("x", E::Parameter("minimum".into()))]),
    })
    .unwrap();
    let mut parameters = values();
    parameters.get_mut("minimum").unwrap().ty = Some(LogicalType::String);
    assert!(SailSql {
        storage: &Storage,
        parameters: &parameters
    }
    .emit(&plan)
    .is_err());
    let plan = resolve(u::Plan {
        root: project(R::Unit, vec![item("x", E::float(f64::NAN))]),
    })
    .unwrap();
    assert!(SailSql {
        storage: &Storage,
        parameters: &values()
    }
    .emit(&plan)
    .is_err());
}

#[test]
fn parameter_literal_cannot_lie_about_its_type_or_nullability() {
    use grust_resolved_plan::query::Value;
    let plan = resolve(u::Plan {
        root: project(R::Unit, vec![item("x", E::Parameter("minimum".into()))]),
    })
    .unwrap();
    let mut parameters = values();
    parameters.get_mut("minimum").unwrap().kind =
        Value::Literal(u::Literal::String("not an integer".into()));
    assert!(SailSql {
        storage: &Storage,
        parameters: &parameters
    }
    .emit(&plan)
    .is_err());
    parameters.get_mut("minimum").unwrap().kind = Value::Literal(u::Literal::Null);
    assert!(SailSql {
        storage: &Storage,
        parameters: &parameters
    }
    .emit(&plan)
    .is_err());
}
#[test]
fn ambiguous_generic_overloads_refuse() {
    let catalog = FixtureCatalog::default();
    let mut registry = registry();
    for variable in [1, 2] {
        registry
            .register(FunctionDescriptor {
                name: FunctionName::new("identity"),
                kind: FunctionKind::Scalar,
                signature: Signature {
                    arguments: vec![ArgumentType::Variable(variable)],
                    variadic: None,
                    result: ReturnType::Variable(variable),
                },
                nulls: NullSemantics::Strict,
                backends: BackendSupport::Any,
                volatility: Volatility::Immutable,
                provider: format!("p{variable}"),
            })
            .unwrap();
    }
    let plan = u::Plan {
        root: project(
            R::Unit,
            vec![item(
                "x",
                E::scalar(FunctionName::new("identity"), vec![E::from(1i64)]),
            )],
        ),
    };
    let e = QueryResolver
        .resolve(
            &plan,
            &Context {
                catalog: &catalog,
                functions: &registry,
                parameters: &Parameters,
            },
        )
        .unwrap_err();
    assert!(matches!(&e[0], ResolveError::AmbiguousOverload(_)));
}
#[test]
fn inherited_property_conflicts_refuse() {
    use grust_lpg::{ElementType, GroupId, Identity, Property, Schema, TypeId, Vertex};
    let catalog = FixtureCatalog {
        schema: Schema::new(
            vec![
                ElementType {
                    id: TypeId(1),
                    name: "base".into(),
                    labels: vec!["Base".into()],
                    supertypes: vec![],
                    properties: vec![Property::required("value", LogicalType::Int64)],
                },
                ElementType {
                    id: TypeId(2),
                    name: "derived".into(),
                    labels: vec!["Derived".into()],
                    supertypes: vec![TypeId(1)],
                    properties: vec![Property::required("value", LogicalType::String)],
                },
            ],
            vec![Vertex {
                id: GroupId(1),
                element_type: TypeId(2),
                identity: Identity::Opaque,
                constraints: vec![],
            }],
            vec![],
        )
        .unwrap(),
    };
    let plan = u::Plan {
        root: project(
            scan("p", u::LabelExpr::label("Derived")),
            vec![item("x", p("p", "value"))],
        ),
    };
    let e = QueryResolver
        .resolve(
            &plan,
            &Context {
                catalog: &catalog,
                functions: &registry(),
                parameters: &Parameters,
            },
        )
        .unwrap_err();
    assert!(matches!(&e[0], ResolveError::AmbiguousProperty(_)));
}
#[test]
fn union_types_aliases_and_cap_domains_refuse() {
    let int = project(R::Unit, vec![item("x", E::from(1i64))]);
    let text = project(R::Unit, vec![item("x", E::from("text"))]);
    assert!(resolve(u::Plan {
        root: R::Union {
            inputs: vec![int.clone(), text],
            all: true
        }
    })
    .is_err());
    assert!(resolve(u::Plan {
        root: project(
            R::Unit,
            vec![item("x", E::from(1i64)), item("x", E::from(2i64))]
        )
    })
    .is_err());
    assert!(resolve(u::Plan {
        root: R::Slice {
            input: Box::new(int),
            offset: None,
            limit: Some(E::from(-1i64))
        }
    })
    .is_err());
}
#[test]
fn unsupported_plugin_does_not_execute_under_another_provider() {
    let catalog = FixtureCatalog::default();
    let mut registry = registry();
    registry
        .register(FunctionDescriptor {
            name: FunctionName::new("external"),
            kind: FunctionKind::Scalar,
            signature: Signature {
                arguments: vec![ArgumentType::Exact(LogicalType::Int64)],
                variadic: None,
                result: ReturnType::Exact(LogicalType::Int64),
            },
            nulls: NullSemantics::Strict,
            backends: BackendSupport::Named(vec!["other".into()]),
            volatility: Volatility::Immutable,
            provider: "not-installed".into(),
        })
        .unwrap();
    let plan = u::Plan {
        root: project(
            R::Unit,
            vec![item(
                "x",
                E::scalar(FunctionName::new("external"), vec![E::from(1i64)]),
            )],
        ),
    };
    let resolved = QueryResolver
        .resolve(
            &plan,
            &Context {
                catalog: &catalog,
                functions: &registry,
                parameters: &Parameters,
            },
        )
        .unwrap();
    assert!(matches!(
        SailSql {
            storage: &Storage,
            parameters: &values()
        }
        .emit(&resolved),
        Err(grust_backend::EmitError::UnsupportedFunction { .. })
    ));
}
