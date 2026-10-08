//! Relationship uniqueness is local to one MATCH, including comma-separated paths.
use super::*;
use grust_unresolved_plan::PathPattern;
pub(super) fn edge_sets(
    pattern: &PathPattern,
    bindings: &HashMap<Binding, Bound>,
) -> Result<Vec<Expr>, ResolveError> {
    pattern
        .edges
        .iter()
        .map(|edge| match bindings.get(&edge.binding) {
            Some(Bound::Value(value)) | Some(Bound::Edges { raw: value, .. })
                if matches!(value.ty, Some(LogicalType::List(_))) =>
            {
                Ok(value.clone())
            }
            Some(Bound::Entity(entity)) if entity.edge => {
                let ty = super::paths::identity_type();
                let value = Expr {
                    kind: Value::Struct(vec![
                        ("group".into(), entity.group.clone()),
                        ("identity".into(), entity.identity.clone()),
                    ]),
                    ty: Some(ty.clone()),
                    nullable: false,
                };
                Ok(Expr {
                    kind: Value::List(vec![value]),
                    ty: Some(LogicalType::List(Box::new(ty))),
                    nullable: false,
                })
            }
            _ => Err(unsupported(
                "relationship uniqueness",
                "edge binding has no identity set",
            )),
        })
        .collect()
}
