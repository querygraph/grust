//! Entity equality depends on graph, kind, group and identity, never its properties.
use super::*;
use grust_lpg::Property;
use grust_unresolved_plan::{Literal, UnaryOp};

pub(super) fn key(entity: &Entity) -> Expr {
    let text = |value: &str| Expr {
        kind: Value::Literal(Literal::String(value.into())),
        ty: Some(LogicalType::String),
        nullable: false,
    };
    let items = vec![
        ("identity".into(), entity.identity.clone()),
        ("group".into(), entity.group.clone()),
        ("graph".into(), text(&entity.graph)),
        (
            "kind".into(),
            text(if entity.edge { "edge" } else { "vertex" }),
        ),
    ];
    let ty = LogicalType::Struct(
        items
            .iter()
            .map(|(name, value): &(String, Expr)| Property {
                name: name.clone(),
                ty: value.ty.clone().expect("typed identity"),
                nullable: false,
            })
            .collect(),
    );
    let object = Expr {
        kind: Value::Struct(items),
        ty: Some(ty.clone()),
        nullable: false,
    };
    if !entity.identity.nullable {
        return object;
    }
    Expr {
        kind: Value::Case {
            branches: vec![(
                Expr {
                    kind: Value::Unary {
                        op: UnaryOp::IsNotNull,
                        argument: Box::new(entity.identity.clone()),
                    },
                    ty: Some(LogicalType::Boolean),
                    nullable: false,
                },
                object,
            )],
            otherwise: Box::new(Expr {
                kind: Value::Literal(Literal::Null),
                ty: Some(ty.clone()),
                nullable: true,
            }),
        },
        ty: Some(ty),
        nullable: true,
    }
}
