use super::*;
fn ty(id: u64, labels: &[&str], parents: &[u64]) -> ElementType {
    ElementType {
        id: TypeId(id),
        name: format!("type{id}"),
        labels: labels.iter().map(|s| s.to_string()).collect(),
        supertypes: parents.iter().map(|id| TypeId(*id)).collect(),
        properties: Vec::new(),
    }
}
fn vertex(id: u64, ty: u64) -> Vertex {
    Vertex {
        id: GroupId(id),
        element_type: TypeId(ty),
        identity: Identity::Opaque,
        constraints: Vec::new(),
    }
}
#[test]
fn identity_is_not_a_required_property_or_dense_index() {
    let s = Schema::new(
        vec![ty(10, &["Person"], &[])],
        vec![vertex(100_000, 10)],
        vec![],
    )
    .unwrap();
    assert_eq!(s.vertex_groups()[0].identity(), &Identity::Opaque);
    assert_eq!(s.vertex_groups()[0].id(), GroupId(100_000));
}
#[test]
fn inherited_labels_and_multilabel_edges_are_independent_of_ownership() {
    let e = Edge {
        id: GroupId(7),
        element_type: TypeId(3),
        source: GroupId(1),
        target: GroupId(2),
        direction: Direction::Directed,
        identity: Identity::Opaque,
    };
    let s = Schema::new(
        vec![
            ty(1, &["Person"], &[]),
            ty(2, &["Employee"], &[1]),
            ty(3, &["LIKES", "REACTION"], &[]),
        ],
        vec![vertex(1, 2), vertex(2, 1)],
        vec![e],
    )
    .unwrap();
    assert_eq!(
        s.labels(TypeId(2)).unwrap(),
        BTreeSet::from(["Employee", "Person"])
    );
    assert_eq!(s.labels(TypeId(3)).unwrap().len(), 2);
    assert_eq!(s.edge_groups().len(), 1);
}
#[test]
fn unknown_parent_and_cycles_are_catalog_errors() {
    assert!(matches!(
        Schema::new(vec![ty(1, &[], &[2])], vec![], vec![]),
        Err(SchemaError::UnknownType(TypeId(2)))
    ));
    assert!(matches!(
        Schema::new(vec![ty(1, &[], &[2]), ty(2, &[], &[1])], vec![], vec![]),
        Err(SchemaError::InheritanceCycle(_))
    ));
}
#[test]
fn optional_property_keys_are_checked_when_declared() {
    let mut t = ty(1, &[], &[]);
    t.properties
        .push(Property::required("id", LogicalType::String));
    let mut v = vertex(1, 1);
    v.identity = Identity::PropertyKey(vec!["id".into()]);
    assert!(Schema::new(vec![t.clone()], vec![v.clone()], vec![]).is_ok());
    v.identity = Identity::PropertyKey(vec!["missing".into()]);
    assert!(matches!(
        Schema::new(vec![t], vec![v], vec![]),
        Err(SchemaError::UnknownKeyProperty { .. })
    ));
}
#[test]
fn duplicate_ids_and_unknown_endpoints_fail_without_data_reads() {
    assert!(matches!(
        Schema::new(
            vec![ty(1, &[], &[])],
            vec![vertex(1, 1), vertex(1, 1)],
            vec![]
        ),
        Err(SchemaError::DuplicateGroup(GroupId(1)))
    ));
    let e = Edge {
        id: GroupId(2),
        element_type: TypeId(1),
        source: GroupId(1),
        target: GroupId(3),
        direction: Direction::Directed,
        identity: Identity::Opaque,
    };
    assert!(matches!(
        Schema::new(vec![ty(1, &[], &[])], vec![vertex(1, 1)], vec![e]),
        Err(SchemaError::UnknownVertex(GroupId(3)))
    ));
}
#[test]
fn custom_logical_types_are_not_storage_encodings() {
    let p = Property::new(
        "embedding",
        LogicalType::Extension {
            namespace: "tensor".into(),
            name: "vector".into(),
            parameters: vec![("width".into(), "128".into())],
        },
    );
    assert!(matches!(p.ty, LogicalType::Extension { .. }));
}
#[cfg(feature = "serde")]
#[test]
fn schema_round_trip_preserves_identity_and_inheritance() {
    let s = Schema::new(
        vec![ty(1, &["Entity"], &[]), ty(2, &["Person"], &[1])],
        vec![vertex(1, 2)],
        vec![],
    )
    .unwrap();
    let json = serde_json::to_string(&s).unwrap();
    assert_eq!(s, serde_json::from_str::<Schema>(&json).unwrap());
}

#[cfg(feature = "serde")]
#[test]
fn deserialization_cannot_bypass_catalog_checks() {
    let invalid = r#"{"types":[],"vertices":[{"id":1,"element_type":99,"identity":"Opaque","constraints":[]}],"edges":[]}"#;
    assert!(serde_json::from_str::<Schema>(invalid).is_err());
}

#[test]
fn incompatible_inherited_keys_are_not_selected_by_parent_order() {
    let mut a = ty(1, &[], &[]);
    a.properties
        .push(Property::required("id", LogicalType::String));
    let mut b = ty(2, &[], &[]);
    b.properties
        .push(Property::required("id", LogicalType::Int64));
    for parents in [vec![1, 2], vec![2, 1]] {
        let mut v = vertex(1, 3);
        v.identity = Identity::PropertyKey(vec!["id".into()]);
        assert!(matches!(
            Schema::new(
                vec![a.clone(), b.clone(), ty(3, &[], &parents)],
                vec![v],
                vec![]
            ),
            Err(SchemaError::AmbiguousKeyProperty { .. })
        ));
    }
}
