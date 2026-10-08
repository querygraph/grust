use crate::fixtures::*;
use grust_functions::FunctionName;
use grust_resolution::{
    query::{providers::*, QueryResolver},
    Context, ResolveError,
};
use grust_unresolved_plan::{self as u, Expr, Relation};
struct Echo;
impl RelationProviders for Echo {
    fn lower(
        &self,
        name: &FunctionName,
        inputs: &[Relation],
        arguments: &[Expr],
    ) -> Result<Option<Relation>, ResolveError> {
        if name.name != "echo" {
            return Ok(None);
        }
        if !inputs.is_empty() || arguments.len() != 1 {
            return Err(ResolveError::Unsupported {
                operator: "echo".into(),
                reason: "one scalar argument required".into(),
            });
        }
        Ok(Some(project(
            Relation::Unit,
            vec![item("value", arguments[0].clone())],
        )))
    }
}
#[test]
fn registered_relation_lowering_is_resolved_again() {
    let catalog = FixtureCatalog::default();
    let functions = registry();
    let context = Context {
        catalog: &catalog,
        functions: &functions,
        parameters: &Parameters,
    };
    let plan = u::Plan {
        root: Relation::Extension {
            name: FunctionName::new("echo"),
            inputs: vec![],
            arguments: vec![Expr::from(42i64)],
        },
    };
    assert!(QueryResolver.resolve(&plan, &context).is_err());
    let resolved = QueryResolver
        .resolve_with_providers(&plan, &context, &Echo)
        .unwrap();
    assert_eq!(resolved.output()[0].name, "value");
    let bad = u::Plan {
        root: Relation::Extension {
            name: FunctionName::new("echo"),
            inputs: vec![],
            arguments: vec![Expr::variable("missing")],
        },
    };
    assert!(QueryResolver
        .resolve_with_providers(&bad, &context, &Echo)
        .is_err());
}
struct Cycle;
impl RelationProviders for Cycle {
    fn lower(
        &self,
        name: &FunctionName,
        inputs: &[Relation],
        arguments: &[Expr],
    ) -> Result<Option<Relation>, ResolveError> {
        Ok(Some(Relation::Extension {
            name: name.clone(),
            inputs: inputs.to_vec(),
            arguments: arguments.to_vec(),
        }))
    }
}
#[test]
fn provider_cycles_and_path_capabilities_are_explicit() {
    let catalog = FixtureCatalog::default();
    let functions = registry();
    let context = Context {
        catalog: &catalog,
        functions: &functions,
        parameters: &Parameters,
    };
    let plan = u::Plan {
        root: Relation::Extension {
            name: FunctionName::new("cycle"),
            inputs: vec![],
            arguments: vec![],
        },
    };
    assert!(QueryResolver
        .resolve_with_providers(&plan, &context, &Cycle)
        .is_err());
    let mut pattern = path("a", "b", u::PatternDirection::Outgoing);
    assert_eq!(path_capability(&pattern), PathCapability::BoundedSql);
    pattern.edges[0].hops.max = None;
    assert_eq!(
        path_capability(&pattern),
        PathCapability::IterativeProviderRequired
    );
}
#[test]
fn bound_and_binding_admission_controls() {
    let catalog = FixtureCatalog::default();
    let functions = registry();
    let context = Context {
        catalog: &catalog,
        functions: &functions,
        parameters: &Parameters,
    };
    for (min, max) in [(2, Some(1)), (0, Some(9)), (1, None)] {
        let mut p = path("a", "b", u::PatternDirection::Outgoing);
        p.edges[0].hops = u::Hops { min, max };
        let plan = u::Plan {
            root: Relation::Match {
                input: Box::new(Relation::Unit),
                graph: u::GraphRef::Default,
                patterns: vec![p],
                optional: false,
            },
        };
        assert!(QueryResolver.resolve(&plan, &context).is_err());
    }
    let mut p = path("a", "b", u::PatternDirection::Outgoing);
    p.binding = Some(u::Binding::Named("a".into()));
    let plan = u::Plan {
        root: Relation::Match {
            input: Box::new(Relation::Unit),
            graph: u::GraphRef::Default,
            patterns: vec![p],
            optional: false,
        },
    };
    assert!(QueryResolver.resolve(&plan, &context).is_err());
}
#[test]
fn iterative_plans_require_the_program_adapter() {
    let catalog = FixtureCatalog::default();
    let functions = registry();
    let context = Context {
        catalog: &catalog,
        functions: &functions,
        parameters: &Parameters,
    };
    for case in crate::iterative_cases::cases() {
        let plan = QueryResolver
            .resolve_iterative(&case.plan, &context, &NoProviders)
            .unwrap();
        let values = values();
        let adapter = grust_backend::query::SailSql {
            storage: &Storage,
            parameters: &values,
        };
        assert!(adapter.emit(&plan).is_err());
        assert_eq!(
            adapter.emit_program(&plan).unwrap().traversals.len(),
            if case.name == "multiple_iterative_steps" {
                2
            } else {
                1
            }
        );
    }
    let mut p = path("a", "b", u::PatternDirection::Outgoing);
    p.edges[0].hops = u::Hops { min: 0, max: None };
    let plan = u::Plan {
        root: Relation::Match {
            input: Box::new(Relation::Unit),
            graph: u::GraphRef::Default,
            patterns: vec![p],
            optional: false,
        },
    };
    assert!(QueryResolver
        .resolve_iterative(&plan, &context, &NoProviders)
        .is_err());
}
#[test]
fn iterative_correlations_and_volatile_predicates_refuse() {
    use grust_functions::*;
    let catalog = FixtureCatalog::default();
    let mut functions = registry();
    functions
        .register(FunctionDescriptor {
            name: FunctionName::new("coin"),
            kind: FunctionKind::Scalar,
            signature: Signature {
                arguments: vec![],
                variadic: None,
                result: ReturnType::Exact(grust_lpg::LogicalType::Boolean),
            },
            nulls: NullSemantics::NonNull,
            backends: BackendSupport::Any,
            volatility: Volatility::Volatile,
            provider: "control".into(),
        })
        .unwrap();
    let context = Context {
        catalog: &catalog,
        functions: &functions,
        parameters: &Parameters,
    };
    let mut p = path("a", "b", u::PatternDirection::Outgoing);
    p.edges[0].hops = u::Hops { min: 1, max: None };
    p.selector = u::PathSelector::Shortest;
    p.vertices[0].predicates = vec![Expr::scalar(FunctionName::new("coin"), vec![])];
    let plan = |p| u::Plan {
        root: Relation::Match {
            input: Box::new(Relation::Unit),
            graph: u::GraphRef::Default,
            patterns: vec![p],
            optional: false,
        },
    };
    assert!(QueryResolver
        .resolve_iterative(&plan(p.clone()), &context, &NoProviders)
        .is_err());
    p.vertices[0].predicates.clear();
    p.edges[0].predicates =
        vec![crate::fixtures::p("a", "id").binary(u::BinaryOp::Eq, Expr::from(1i64))];
    assert!(QueryResolver
        .resolve_iterative(&plan(p), &context, &NoProviders)
        .is_err());
}
