use super::*;
fn descriptor(kind: FunctionKind) -> FunctionDescriptor {
    FunctionDescriptor {
        name: FunctionName::qualified(&["plugin"], "score"),
        kind,
        signature: Signature {
            arguments: vec![ArgumentType::Exact(LogicalType::String)],
            variadic: None,
            result: ReturnType::Exact(LogicalType::Float64),
        },
        nulls: NullSemantics::Strict,
        backends: BackendSupport::Any,
        volatility: Volatility::Immutable,
        provider: "separate-plugin".into(),
    }
}
#[test]
fn arbitrary_scalar_and_aggregate_names_share_one_registry() {
    let mut r = Registry::default();
    for kind in [FunctionKind::Scalar, FunctionKind::Aggregate] {
        r.register(descriptor(kind)).unwrap();
    }
    assert_eq!(
        r.lookup(&descriptor(FunctionKind::Scalar).name, FunctionKind::Scalar)
            .len(),
        1
    );
    assert_eq!(
        r.lookup(
            &descriptor(FunctionKind::Scalar).name,
            FunctionKind::Aggregate
        )
        .len(),
        1
    );
}
#[test]
fn overloads_are_retained_and_duplicate_arguments_are_refused() {
    let mut r = Registry::default();
    let d = descriptor(FunctionKind::Scalar);
    r.register(d.clone()).unwrap();
    assert!(matches!(
        r.register(d.clone()),
        Err(RegistryError::DuplicateSignature(_))
    ));
    let mut other = d;
    other.signature.arguments = vec![ArgumentType::Numeric];
    r.register(other).unwrap();
    assert_eq!(
        r.lookup(
            &FunctionName::qualified(&["plugin"], "score"),
            FunctionKind::Scalar
        )
        .len(),
        2
    );
}
#[test]
fn signature_return_variables_are_bound() {
    let mut r = Registry::default();
    let mut d = descriptor(FunctionKind::Scalar);
    d.signature.result = ReturnType::Variable(2);
    assert_eq!(
        r.register(d.clone()),
        Err(RegistryError::UnknownTypeVariable(2))
    );
    d.signature.arguments = vec![ArgumentType::Variable(2)];
    assert!(r.register(d).is_ok());
}
#[test]
fn invalid_return_argument_and_empty_backend_set_fail() {
    let mut r = Registry::default();
    let mut d = descriptor(FunctionKind::Scalar);
    d.signature.result = ReturnType::Argument(1);
    assert_eq!(r.register(d), Err(RegistryError::InvalidReturnArgument(1)));
    let mut d = descriptor(FunctionKind::Scalar);
    d.backends = BackendSupport::Named(vec![]);
    assert_eq!(r.register(d), Err(RegistryError::EmptyBackendSet));
}
#[test]
fn provider_null_and_backend_contracts_survive_lookup() {
    let mut r = Registry::default();
    let mut d = descriptor(FunctionKind::Scalar);
    d.nulls = NullSemantics::ProviderDefined;
    d.backends = BackendSupport::Named(vec!["any-future-engine".into()]);
    r.register(d.clone()).unwrap();
    assert_eq!(r.lookup(&d.name, d.kind)[0], &d);
}
