use super::*;
use grust_functions::{BackendSupport, NullSemantics, ReturnType, Signature, Volatility};
struct Entries(Vec<FunctionDescriptor>);
impl FunctionRegistry for Entries {
    fn lookup(&self, name: &FunctionName, kind: FunctionKind) -> Vec<&FunctionDescriptor> {
        self.0
            .iter()
            .filter(|f| &f.name == name && f.kind == kind)
            .collect()
    }
}
fn function(kind: FunctionKind) -> FunctionDescriptor {
    FunctionDescriptor {
        name: FunctionName::new("plugin"),
        kind,
        signature: Signature {
            arguments: vec![ArgumentType::Exact(LogicalType::Int64)],
            variadic: None,
            result: ReturnType::Exact(LogicalType::Int64),
        },
        nulls: NullSemantics::Strict,
        backends: BackendSupport::Named(vec!["sail".into()]),
        volatility: Volatility::Volatile,
        provider: "external".into(),
    }
}
#[test]
fn exact_binding_retains_provider_and_semantics() {
    let expected = function(FunctionKind::Aggregate);
    let registry = Entries(vec![expected.clone()]);
    assert_eq!(
        bind_exact(
            &registry,
            &expected.name,
            expected.kind,
            &[LogicalType::Int64]
        ),
        Ok(expected)
    );
}
#[test]
fn no_cast_or_scalar_aggregate_confusion() {
    let f = function(FunctionKind::Aggregate);
    let registry = Entries(vec![f.clone()]);
    assert!(matches!(
        bind_exact(&registry, &f.name, f.kind, &[LogicalType::Int32]),
        Err(ResolveError::NoOverload(_))
    ));
    assert!(matches!(
        bind_exact(
            &registry,
            &f.name,
            FunctionKind::Scalar,
            &[LogicalType::Int64]
        ),
        Err(ResolveError::NoOverload(_))
    ));
}
#[test]
fn ambiguity_is_refused_even_in_replaceable_registry() {
    let f = function(FunctionKind::Scalar);
    let registry = Entries(vec![f.clone(), f.clone()]);
    assert!(matches!(
        bind_exact(&registry, &f.name, f.kind, &[LogicalType::Int64]),
        Err(ResolveError::AmbiguousOverload(_))
    ));
}
#[test]
fn schema_paths_respect_endpoints_direction_and_inherited_labels() {
    use grust_lpg::{Direction, Edge, ElementType, GroupId, Identity, TypeId, Vertex};
    use grust_unresolved_plan::PatternDirection;
    let ty = |id, label: &str, parents| ElementType {
        id: TypeId(id),
        name: label.into(),
        labels: vec![label.into()],
        supertypes: parents,
        properties: vec![],
    };
    let vertex = |id, t| Vertex {
        id: GroupId(id),
        element_type: TypeId(t),
        identity: Identity::Opaque,
        constraints: vec![],
    };
    let schema = Schema::new(
        vec![
            ty(1, "Person", vec![]),
            ty(2, "Employee", vec![TypeId(1)]),
            ty(3, "Company", vec![]),
            ty(4, "WORKS", vec![]),
        ],
        vec![vertex(1, 2), vertex(2, 3)],
        vec![Edge {
            id: GroupId(3),
            element_type: TypeId(4),
            source: GroupId(1),
            target: GroupId(2),
            direction: Direction::Directed,
            identity: Identity::Opaque,
        }],
    )
    .unwrap();
    let forward = paths::one_hop(
        &schema,
        "Person",
        "WORKS",
        "Company",
        PatternDirection::Outgoing,
    )
    .unwrap();
    assert_eq!(forward.len(), 1);
    assert_eq!(forward[0].vertices, vec![GroupId(1), GroupId(2)]);
    assert!(paths::one_hop(
        &schema,
        "Company",
        "WORKS",
        "Person",
        PatternDirection::Outgoing
    )
    .unwrap()
    .is_empty());
    assert_eq!(
        paths::one_hop(
            &schema,
            "Company",
            "WORKS",
            "Person",
            PatternDirection::Incoming
        )
        .unwrap()[0]
            .edges[0]
            .1,
        grust_resolved_plan::Orientation::Reversed
    );
}
