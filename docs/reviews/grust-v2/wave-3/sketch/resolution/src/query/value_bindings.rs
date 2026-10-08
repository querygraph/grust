//! Carry declared graph-value provenance through projection and collection.
use super::*;

pub(super) fn projected_bound(
    original: &grust_unresolved_plan::Expr,
    input: &Scope,
    field: &Field,
    resolved: &Expr,
) -> Bound {
    use grust_unresolved_plan::Expr as UExpr;
    if let UExpr::Call(call) = original {
        if let Value::Call { function, .. } = &resolved.kind {
            if let grust_functions::ReturnType::ListArgument(index) = function.signature.result {
                if let Some(UExpr::Binding(binding) | UExpr::GraphValue(binding)) =
                    call.arguments.get(index)
                {
                    if let Some(Bound::Entity(element)) = input.bindings.get(binding) {
                        return Bound::EntityList {
                            raw: Expr::slot(field),
                            element: element.clone(),
                        };
                    }
                }
            }
        }
    }
    if let UExpr::Binding(binding) | UExpr::GraphValue(binding) = original {
        match input.bindings.get(binding) {
            Some(Bound::Entity(entity)) => return entity_bound(entity, field),
            Some(Bound::EntityList { element, .. }) => {
                return Bound::EntityList {
                    raw: Expr::slot(field),
                    element: element.clone(),
                }
            }
            _ => {}
        }
    }
    Bound::Value(Expr::slot(field))
}

pub(super) fn entity_bound(entity: &Entity, field: &Field) -> Bound {
    let object = Expr::slot(field);
    let access = |object: Expr, name: &str, ty: LogicalType, nullable: bool| Expr {
        kind: Value::Property {
            object: Box::new(object),
            name: name.into(),
        },
        ty: Some(ty),
        nullable,
    };
    let identity = access(
        object.clone(),
        "identity",
        LogicalType::Int64,
        field.nullable,
    );
    let group = access(object.clone(), "group", LogicalType::Int64, field.nullable);
    let LogicalType::Struct(shape) = &field.ty else {
        unreachable!()
    };
    let props_ty = shape
        .iter()
        .find(|f| f.name == "properties")
        .unwrap()
        .ty
        .clone();
    let properties_object = access(object, "properties", props_ty, field.nullable);
    let properties = entity
        .properties
        .iter()
        .map(|(name, value)| {
            (
                name.clone(),
                access(
                    properties_object.clone(),
                    name,
                    value.ty.clone().unwrap(),
                    field.nullable || value.nullable,
                ),
            )
        })
        .collect();
    Bound::Entity(Entity {
        graph: entity.graph.clone(),
        identity,
        group,
        properties,
        edge: entity.edge,
    })
}
