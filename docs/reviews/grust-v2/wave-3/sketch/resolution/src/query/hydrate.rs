//! Columnar hydration joins identity lists to typed graph tables, retaining order.
use super::*;
use grust_lpg::{EdgeGroup, Lpg, Property, Schema, VertexGroup};
use grust_unresolved_plan::GraphRef;
impl State<'_, '_> {
    pub(super) fn graph_value(
        &mut self,
        scope: &Scope,
        binding: &Binding,
    ) -> Result<Expr, ResolveError> {
        match scope.bindings.get(binding) {
            Some(Bound::Edges { graph, raw }) => self.entity_list(graph, raw.clone(), true),
            Some(Bound::Path { graph, raw }) => {
                let length = property(raw.clone(), "length")?;
                let nodes = self.entity_list(graph, property(raw.clone(), "vertices")?, false)?;
                let edges = self.entity_list(graph, property(raw.clone(), "edges")?, true)?;
                let value = structure(
                    vec![
                        ("length".into(), length),
                        ("nodes".into(), nodes),
                        ("relationships".into(), edges),
                    ],
                    false,
                );
                if raw.nullable {
                    let condition = Expr {
                        kind: Value::Unary {
                            op: grust_unresolved_plan::UnaryOp::IsNotNull,
                            argument: Box::new(raw.clone()),
                        },
                        ty: Some(LogicalType::Boolean),
                        nullable: false,
                    };
                    let null = Expr {
                        kind: Value::Literal(grust_unresolved_plan::Literal::Null),
                        ty: value.ty.clone(),
                        nullable: true,
                    };
                    Ok(Expr {
                        ty: value.ty.clone(),
                        nullable: true,
                        kind: Value::Case {
                            branches: vec![(condition, value)],
                            otherwise: Box::new(null),
                        },
                    })
                } else {
                    Ok(value)
                }
            }
            _ => self.bound(scope, binding),
        }
    }
    fn graph_schema(&self, graph: &str) -> Result<Schema, ResolveError> {
        if let Ok((name, schema)) = self.context.catalog.graph(&GraphRef::Default) {
            if name == graph {
                return Ok(schema.clone());
            }
        }
        let (name, schema) = self.context.catalog.graph(&GraphRef::Named {
            namespace: vec![],
            name: graph.into(),
        })?;
        if name != graph {
            return Err(unsupported(
                "hydrate",
                "catalog canonical graph identity mismatch",
            ));
        }
        Ok(schema.clone())
    }
    fn entity_list(
        &mut self,
        graph: &str,
        identities: Expr,
        edge: bool,
    ) -> Result<Expr, ResolveError> {
        let schema = self.graph_schema(graph)?;
        let (_, value, _, _) = self.entity_table(graph, &schema, edge)?;
        Ok(Expr {
            ty: Some(LogicalType::List(Box::new(value.ty.unwrap()))),
            nullable: identities.nullable,
            kind: Value::EntityList {
                graph: graph.into(),
                identities: Box::new(identities),
                edge,
            },
        })
    }
    fn entity_table(
        &mut self,
        graph: &str,
        schema: &Schema,
        edge: bool,
    ) -> Result<(Node, Expr, Expr, Expr), ResolveError> {
        let groups = if edge {
            schema.edge_groups().iter().map(EdgeGroup::id).collect()
        } else {
            schema.vertex_groups().iter().map(VertexGroup::id).collect()
        };
        let template = self.template(graph, schema, groups, edge)?;
        let mut branches = Vec::new();
        let mut labels = Vec::new();
        let ids = if edge {
            schema
                .edge_groups()
                .iter()
                .map(|g| (g.id(), g.element_type()))
                .collect::<Vec<_>>()
        } else {
            schema
                .vertex_groups()
                .iter()
                .map(|g| (g.id(), g.element_type()))
                .collect()
        };
        for (id, ty) in ids {
            branches.push(super::patterns::scan(schema, graph, id, &template)?);
            let condition = eq(template.entity.group.clone(), integer(id.0 as i64));
            let names = schema
                .labels(ty)
                .map_err(|e| unsupported("schema", &e.to_string()))?;
            let mut names = names.into_iter().map(str::to_owned).collect::<Vec<_>>();
            names.sort();
            let names = Expr {
                kind: Value::Labels(names),
                ty: Some(LogicalType::List(Box::new(LogicalType::String))),
                nullable: false,
            };
            labels.push((condition, names));
        }
        let labels = Expr {
            kind: Value::Case {
                branches: labels,
                otherwise: Box::new(Expr {
                    kind: Value::Labels(vec![]),
                    ty: Some(LogicalType::List(Box::new(LogicalType::String))),
                    nullable: false,
                }),
            },
            ty: Some(LogicalType::List(Box::new(LogicalType::String))),
            nullable: false,
        };
        let mut values = vec![
            ("identity".into(), template.entity.identity.clone()),
            ("group".into(), template.entity.group.clone()),
            ("graph".into(), text(graph.into())),
            (
                "kind".into(),
                text(if edge { "edge" } else { "vertex" }.into()),
            ),
            ("labels".into(), labels),
            (
                "properties".into(),
                structure(template.entity.properties.clone(), false),
            ),
        ];
        if edge {
            values.push((
                "source".into(),
                Expr::slot(template.source.as_ref().unwrap()),
            ));
            values.push((
                "target".into(),
                Expr::slot(template.target.as_ref().unwrap()),
            ));
        }
        let value = structure(values, false);
        Ok((
            Node {
                fields: template.fields,
                op: Op::Union {
                    inputs: branches,
                    all: true,
                },
            },
            value,
            template.entity.identity,
            template.entity.group,
        ))
    }
    pub(super) fn lift_entities(
        &mut self,
        scope: &mut Scope,
        expression: &mut Expr,
    ) -> Result<(), ResolveError> {
        let output = if matches!(expression.kind, Value::EntityList { .. }) {
            Some(self.output_field("@hydrate_value".into(), expression)?)
        } else {
            None
        };
        match &mut expression.kind {
            Value::EntityList {
                graph,
                identities,
                edge,
            } => {
                self.lift_entities(scope, identities)?;
                let schema = self.graph_schema(graph)?;
                let (entities, value, identity, group) =
                    self.entity_table(graph, &schema, *edge)?;
                let row = self.field("@hydrate_row".into(), LogicalType::Int64, false)?;
                let output = output.unwrap();
                let mut fields = scope.node.fields.clone();
                fields.push(row.clone());
                let original = std::mem::replace(
                    &mut scope.node,
                    Node {
                        op: Op::Unit,
                        fields: vec![],
                    },
                );
                let input = Node {
                    fields: fields.clone(),
                    op: Op::Materialize {
                        id: row.slot.0,
                        input: Box::new(Node {
                            fields,
                            op: Op::RowId {
                                input: Box::new(original),
                                slot: row.slot,
                            },
                        }),
                    },
                };
                let mut fields = input.fields.clone();
                fields.push(output.clone());
                scope.node = Node {
                    fields,
                    op: Op::Hydrate {
                        input: Box::new(input),
                        entities: Box::new(entities),
                        identities: *identities.clone(),
                        identity,
                        group,
                        value: Box::new(value),
                        row: row.slot,
                        output: output.slot,
                    },
                };
                *expression = Expr::slot(&output);
            }
            Value::Property { object, .. }
            | Value::Unary {
                argument: object, ..
            }
            | Value::Cast {
                argument: object, ..
            }
            | Value::ListDropFirst(object)
            | Value::ListLength(object) => self.lift_entities(scope, object)?,
            Value::Binary { left, right, .. } | Value::ListDisjoint { left, right } => {
                self.lift_entities(scope, left)?;
                self.lift_entities(scope, right)?;
            }
            Value::ListConcat(v) | Value::List(v) => {
                for e in v {
                    self.lift_entities(scope, e)?;
                }
            }
            Value::Struct(v) => {
                for (_, e) in v {
                    self.lift_entities(scope, e)?;
                }
            }
            Value::Call {
                arguments, filter, ..
            } => {
                for e in arguments {
                    self.lift_entities(scope, e)?;
                }
                if let Some(e) = filter {
                    self.lift_entities(scope, e)?;
                }
            }
            Value::Case {
                branches,
                otherwise,
            } => {
                for (a, b) in branches {
                    self.lift_entities(scope, a)?;
                    self.lift_entities(scope, b)?;
                }
                self.lift_entities(scope, otherwise)?;
            }
            _ => {}
        }
        Ok(())
    }
}
pub(super) fn property(object: Expr, name: &str) -> Result<Expr, ResolveError> {
    if let Value::Case {
        branches,
        otherwise,
    } = &object.kind
    {
        let values = branches
            .iter()
            .map(|(condition, value)| Ok((condition.clone(), property(value.clone(), name)?)))
            .collect::<Result<Vec<_>, ResolveError>>()?;
        let otherwise = if matches!(
            otherwise.kind,
            Value::Literal(grust_unresolved_plan::Literal::Null)
        ) {
            Expr {
                kind: otherwise.kind.clone(),
                ty: values.first().and_then(|(_, v)| v.ty.clone()),
                nullable: true,
            }
        } else {
            property(*otherwise.clone(), name)?
        };
        return Ok(Expr {
            ty: otherwise.ty.clone(),
            nullable: object.nullable,
            kind: Value::Case {
                branches: values,
                otherwise: Box::new(otherwise),
            },
        });
    }
    if let Value::Struct(values) = &object.kind {
        if let Some((_, value)) = values.iter().find(|(n, _)| n == name) {
            return Ok(value.clone());
        }
    }
    let Some(LogicalType::Struct(fields)) = &object.ty else {
        return Err(unsupported(
            "graph intrinsic",
            "path or entity struct required",
        ));
    };
    let f = fields
        .iter()
        .find(|f| f.name == name)
        .ok_or_else(|| ResolveError::UnknownProperty(name.into()))?;
    Ok(Expr {
        ty: Some(f.ty.clone()),
        nullable: object.nullable || f.nullable,
        kind: Value::Property {
            object: Box::new(object),
            name: name.into(),
        },
    })
}
fn structure(values: Vec<(String, Expr)>, nullable: bool) -> Expr {
    Expr {
        ty: Some(LogicalType::Struct(
            values
                .iter()
                .map(|(n, e)| Property {
                    name: n.clone(),
                    ty: e.ty.clone().unwrap(),
                    nullable: e.nullable,
                })
                .collect(),
        )),
        kind: Value::Struct(values),
        nullable,
    }
}
fn text(value: String) -> Expr {
    Expr {
        kind: Value::Literal(grust_unresolved_plan::Literal::String(value)),
        ty: Some(LogicalType::String),
        nullable: false,
    }
}
fn integer(value: i64) -> Expr {
    Expr {
        kind: Value::Literal(grust_unresolved_plan::Literal::Integer(value)),
        ty: Some(LogicalType::Int64),
        nullable: false,
    }
}
