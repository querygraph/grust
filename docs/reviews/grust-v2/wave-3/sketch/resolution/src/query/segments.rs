//! A mixed path joins its segments, tests uniqueness, then selects whole paths.
use super::hydrate::property;
use super::*;
use grust_lpg::Schema;
use grust_unresolved_plan::{
    BinaryOp, Hops, JoinKind, Literal, PathMode, PathPattern, PathSelector,
};
impl State<'_, '_> {
    pub(super) fn segmented_pattern(
        &mut self,
        graph: &str,
        schema: &Schema,
        pattern: &PathPattern,
    ) -> Result<Scope, ResolveError> {
        if pattern.mode != PathMode::Trail {
            return Err(unsupported(
                "segmented path",
                "only TRAIL currently has a whole-path uniqueness lowering",
            ));
        }
        let mut scope = Scope {
            order: vec![],
            visible: None,
            node: Node {
                op: Op::Unit,
                fields: vec![],
            },
            bindings: HashMap::new(),
        };
        let mut edge_lists = Vec::<Expr>::new();
        let mut vertex_lists = Vec::new();
        let mut lengths = Vec::new();
        let occupied = pattern
            .vertices
            .iter()
            .map(|v| v.binding.clone())
            .chain(pattern.edges.iter().map(|e| e.binding.clone()))
            .chain(pattern.binding.clone())
            .collect::<std::collections::HashSet<_>>();
        let mut serial = u64::MAX;
        for (index, edge) in pattern.edges.iter().enumerate() {
            while occupied.contains(&Binding::Anonymous(serial)) {
                serial = serial
                    .checked_sub(1)
                    .ok_or_else(|| unsupported("path", "anonymous binding overflow"))?;
            }
            let key = Binding::Anonymous(serial);
            serial -= 1;
            let ranged = edge.binding_list || edge.hops != Hops::ONE;
            let part = PathPattern {
                binding: ranged.then_some(key.clone()),
                vertices: pattern.vertices[index..=index + 1].to_vec(),
                edges: vec![edge.clone()],
                mode: PathMode::Trail,
                selector: PathSelector::All,
            };
            let resolved = self.pattern(graph, schema, &part)?;
            let (edges, vertices, length) = if ranged {
                let Bound::Path { raw, .. } = &resolved.bindings[&key] else {
                    unreachable!()
                };
                (
                    property(raw.clone(), "edges")?,
                    property(raw.clone(), "vertices")?,
                    property(raw.clone(), "length")?,
                )
            } else {
                (
                    identity_list(vec![entity_identity(&resolved.bindings[&edge.binding])?]),
                    identity_list(
                        part.vertices
                            .iter()
                            .map(|v| entity_identity(&resolved.bindings[&v.binding]))
                            .collect::<Result<_, _>>()?,
                    ),
                    integer(1),
                )
            };
            let mut predicates = Vec::new();
            super::patterns::merge(&mut scope.bindings, &resolved.bindings, &mut predicates)?;
            for previous in &edge_lists {
                predicates.push(Expr {
                    kind: Value::ListDisjoint {
                        left: Box::new(previous.clone()),
                        right: Box::new(edges.clone()),
                    },
                    ty: Some(LogicalType::Boolean),
                    nullable: false,
                });
            }
            scope.node = join(
                scope.node,
                resolved.node,
                JoinKind::Inner,
                conjunction(predicates),
            );
            edge_lists.push(edges);
            lengths.push(length);
            vertex_lists.push(if index == 0 {
                vertices
            } else {
                Expr {
                    ty: vertices.ty.clone(),
                    nullable: vertices.nullable,
                    kind: Value::ListDropFirst(Box::new(vertices)),
                }
            });
            if ranged {
                scope.bindings.remove(&key);
            }
        }
        if pattern.edges.is_empty() {
            let mut fixed = pattern.clone();
            fixed.binding = None;
            fixed.selector = PathSelector::All;
            scope = self.pattern(graph, schema, &fixed)?;
            vertex_lists.push(identity_list(vec![entity_identity(
                &scope.bindings[&pattern.vertices[0].binding],
            )?]));
        }
        let mut predicates = Vec::new();
        for (index, edge) in pattern.edges.iter().enumerate() {
            if !edge.binding_list && edge.hops == Hops::ONE {
                for vertex in &pattern.vertices[index..=index + 1] {
                    for p in &vertex.predicates {
                        predicates.push(self.expression(
                            p,
                            &scope,
                            Some(&vertex.binding),
                            false,
                        )?);
                    }
                }
                for p in &edge.predicates {
                    predicates.push(self.expression(p, &scope, Some(&edge.binding), false)?);
                }
            }
        }
        for p in &predicates {
            super::expressions::boolean(p)?;
        }
        if let Some(predicate) = conjunction(predicates) {
            scope.node = Node {
                fields: scope.node.fields.clone(),
                op: Op::Filter {
                    input: Box::new(scope.node),
                    predicate,
                },
            };
        }
        let edges = concatenate(edge_lists);
        let vertices = concatenate(vertex_lists);
        let length = lengths
            .into_iter()
            .reduce(|left, right| Expr {
                ty: Some(LogicalType::Int64),
                nullable: false,
                kind: Value::Binary {
                    op: BinaryOp::Add,
                    left: Box::new(left),
                    right: Box::new(right),
                },
            })
            .unwrap_or(integer(0));
        let length_field = self.output_field("@length".into(), &length)?;
        let mut fields = scope.node.fields.clone();
        fields.push(length_field.clone());
        let mut items = scope
            .node
            .fields
            .iter()
            .map(|f| (f.slot, Expr::slot(f)))
            .collect::<Vec<_>>();
        items.push((length_field.slot, length));
        scope.node = Node {
            fields,
            op: Op::Project {
                input: Box::new(scope.node),
                items,
                distinct: false,
            },
        };
        if pattern.selector != PathSelector::All {
            let mut partitions = Vec::new();
            for vertex in [&pattern.vertices[0], pattern.vertices.last().unwrap()] {
                let Bound::Entity(entity) = &scope.bindings[&vertex.binding] else {
                    unreachable!()
                };
                partitions.extend([entity.group.clone(), entity.identity.clone()]);
            }
            scope.node = Node {
                fields: scope.node.fields.clone(),
                op: Op::PathSelect {
                    input: Box::new(scope.node),
                    partitions,
                    length: Expr::slot(&length_field),
                    all_ties: pattern.selector == PathSelector::AllShortest,
                },
            };
        }
        if let Some(binding) = &pattern.binding {
            if scope.bindings.contains_key(binding) {
                return Err(unsupported("path", "path binding collides with an entity"));
            }
            let values = vec![
                ("length".into(), Expr::slot(&length_field)),
                ("vertices".into(), vertices),
                ("edges".into(), edges),
            ];
            let value = Expr {
                ty: Some(LogicalType::Struct(
                    values
                        .iter()
                        .map(|(name, e): &(String, Expr)| grust_lpg::Property {
                            name: name.clone(),
                            ty: e.ty.clone().unwrap(),
                            nullable: e.nullable,
                        })
                        .collect(),
                )),
                nullable: false,
                kind: Value::Struct(values),
            };
            let field = self.output_field("@path".into(), &value)?;
            let mut items = scope
                .node
                .fields
                .iter()
                .map(|f| (f.slot, Expr::slot(f)))
                .collect::<Vec<_>>();
            items.push((field.slot, value));
            let mut fields = scope.node.fields.clone();
            fields.push(field.clone());
            scope.node = Node {
                fields,
                op: Op::Project {
                    input: Box::new(scope.node),
                    items,
                    distinct: false,
                },
            };
            scope.bindings.insert(
                binding.clone(),
                Bound::Path {
                    graph: graph.into(),
                    raw: Expr::slot(&field),
                },
            );
        }
        Ok(scope)
    }
}
fn entity_identity(bound: &Bound) -> Result<Expr, ResolveError> {
    let Bound::Entity(entity) = bound else {
        return Err(unsupported("path", "entity identity required"));
    };
    Ok(Expr {
        kind: Value::Struct(vec![
            ("group".into(), entity.group.clone()),
            ("identity".into(), entity.identity.clone()),
        ]),
        ty: Some(super::paths::identity_type()),
        nullable: false,
    })
}
fn identity_list(values: Vec<Expr>) -> Expr {
    Expr {
        kind: Value::List(values),
        ty: Some(LogicalType::List(Box::new(super::paths::identity_type()))),
        nullable: false,
    }
}
fn concatenate(values: Vec<Expr>) -> Expr {
    Expr {
        kind: Value::ListConcat(values),
        ty: Some(LogicalType::List(Box::new(super::paths::identity_type()))),
        nullable: false,
    }
}
fn integer(value: i64) -> Expr {
    Expr {
        kind: Value::Literal(Literal::Integer(value)),
        ty: Some(LogicalType::Int64),
        nullable: false,
    }
}
