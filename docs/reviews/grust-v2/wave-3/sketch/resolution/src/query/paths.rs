//! Finite-range provider: explicit expansion, path bags, then endpoint selection.
use super::catalog::label;
use super::patterns::Template;
use super::providers::{path_capability, PathCapability};
use super::*;
use grust_lpg::{Lpg, Schema, VertexGroup};
use grust_unresolved_plan::{Hops, LabelExpr, Literal, PathPattern, PathSelector};
impl State<'_, '_> {
    pub(super) fn ranged_pattern(
        &mut self,
        graph: &str,
        schema: &Schema,
        pattern: &PathPattern,
    ) -> Result<Scope, ResolveError> {
        if path_capability(pattern) != PathCapability::BoundedSql {
            if self.iterative {
                return self.iterative_pattern(graph, schema, pattern);
            }
            return Err(unsupported("path", "finite single-segment SQL provider admits at most 8 hops; unbounded traversal requires a separate iterative execution adapter"));
        }
        let edge = &pattern.edges[0];
        if pattern.vertices[0].binding == edge.binding
            || pattern.vertices[1].binding == edge.binding
            || pattern.binding.as_ref().is_some_and(|b| {
                pattern.vertices.iter().any(|v| &v.binding == b) || &edge.binding == b
            })
        {
            return Err(unsupported(
                "path",
                "incompatible vertex, edge-list or path binding",
            ));
        }
        let mut endpoints = Vec::new();
        for vertex in &pattern.vertices {
            let groups = schema
                .vertex_groups()
                .iter()
                .map(|v| {
                    label(schema, v.element_type(), &vertex.labels).map(|yes| yes.then_some(v.id()))
                })
                .collect::<Result<Vec<_>, _>>()?
                .into_iter()
                .flatten()
                .collect();
            endpoints.push(self.template(graph, schema, groups, false)?);
        }
        let edge_list = self.field(
            "@edges".into(),
            LogicalType::List(Box::new(identity_type())),
            false,
        )?;
        let vertex_list = self.field(
            "@vertices".into(),
            LogicalType::List(Box::new(identity_type())),
            false,
        )?;
        let length = self.field("@length".into(), LogicalType::Int64, false)?;
        let mut fields = endpoints
            .iter()
            .flat_map(|t| t.fields.clone())
            .collect::<Vec<_>>();
        fields.extend([edge_list.clone(), vertex_list.clone(), length.clone()]);
        let mut branches = Vec::new();
        for hops in edge.hops.min..=edge.hops.max.unwrap() {
            let mut fixed = pattern.clone();
            fixed.binding = None;
            fixed.selector = PathSelector::All;
            fixed.edges.clear();
            fixed.vertices.clear();
            let mut occupied = pattern
                .vertices
                .iter()
                .map(|v| v.binding.clone())
                .chain(pattern.edges.iter().map(|e| e.binding.clone()))
                .chain(pattern.binding.clone())
                .collect::<std::collections::HashSet<_>>();
            let mut serial = u64::MAX;
            let mut fresh = || loop {
                let b = Binding::Anonymous(serial);
                serial -= 1;
                if occupied.insert(b.clone()) {
                    break b;
                }
            };
            fixed.vertices.push(pattern.vertices[0].clone());
            if hops == 0 {
                fixed.vertices[0].labels =
                    LabelExpr::And(pattern.vertices.iter().map(|v| v.labels.clone()).collect());
            } else {
                for i in 0..hops {
                    let mut e = edge.clone();
                    e.hops = Hops::ONE;
                    e.binding_list = false;
                    e.binding = fresh();
                    fixed.edges.push(e);
                    let mut v = pattern.vertices[1].clone();
                    if i + 1 != hops {
                        v.binding = fresh();
                        v.labels = LabelExpr::Any;
                        v.predicates.clear();
                    }
                    fixed.vertices.push(v);
                }
            }
            let mut scope = self.pattern(graph, schema, &fixed)?;
            if hops == 0 {
                scope.bindings.insert(
                    pattern.vertices[1].binding.clone(),
                    scope.bindings[&pattern.vertices[0].binding].clone(),
                );
            }
            // Predicates are evaluated before shortest selection, including each edge.
            let mut predicates = Vec::new();
            for v in &pattern.vertices {
                for p in &v.predicates {
                    predicates.push(self.expression(p, &scope, Some(&v.binding), false)?);
                }
            }
            for e in &fixed.edges {
                // The repeated edge predicate resolves its original name to this edge.
                let mut local = scope.clone();
                local
                    .bindings
                    .insert(edge.binding.clone(), scope.bindings[&e.binding].clone());
                for p in &edge.predicates {
                    predicates.push(self.expression(p, &local, Some(&edge.binding), false)?);
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
            let mut items = Vec::new();
            for (index, endpoint) in endpoints.iter().enumerate() {
                let Bound::Entity(actual) = &scope.bindings[&pattern.vertices[index].binding]
                else {
                    unreachable!()
                };
                project_entity(endpoint, actual, &mut items);
            }
            let edges = fixed
                .edges
                .iter()
                .map(|e| identity(&scope.bindings[&e.binding]))
                .collect();
            let vertices = fixed
                .vertices
                .iter()
                .map(|v| identity(&scope.bindings[&v.binding]))
                .collect();
            items.extend([
                (edge_list.slot, list(edges)),
                (vertex_list.slot, list(vertices)),
                (
                    length.slot,
                    Expr {
                        kind: Value::Literal(Literal::Integer(hops as i64)),
                        ty: Some(LogicalType::Int64),
                        nullable: false,
                    },
                ),
            ]);
            branches.push(Node {
                fields: fields.clone(),
                op: Op::Project {
                    input: Box::new(scope.node),
                    items,
                    distinct: false,
                },
            });
        }
        let node = Node {
            fields: fields.clone(),
            op: Op::Union {
                inputs: branches,
                all: true,
            },
        };
        self.finish_path_scope(pattern, endpoints, node, edge_list, vertex_list, length)
    }
    pub(super) fn finish_path_scope(
        &mut self,
        pattern: &PathPattern,
        endpoints: Vec<Template>,
        mut node: Node,
        edge_list: Field,
        vertex_list: Field,
        length: Field,
    ) -> Result<Scope, ResolveError> {
        if pattern.selector != PathSelector::All {
            let partitions = endpoints
                .iter()
                .flat_map(|t| [t.entity.group.clone(), t.entity.identity.clone()])
                .collect();
            node = Node {
                fields: node.fields.clone(),
                op: Op::PathSelect {
                    input: Box::new(node),
                    partitions,
                    length: Expr::slot(&length),
                    all_ties: pattern.selector == PathSelector::AllShortest,
                },
            };
        }
        let mut bindings = HashMap::new();
        for (v, endpoint) in pattern.vertices.iter().zip(endpoints) {
            if let Some(Bound::Entity(existing)) = bindings.get(&v.binding) {
                let conditions = vec![
                    eq(existing.identity.clone(), endpoint.entity.identity.clone()),
                    eq(existing.group.clone(), endpoint.entity.group.clone()),
                ];
                node = Node {
                    fields: node.fields.clone(),
                    op: Op::Filter {
                        input: Box::new(node),
                        predicate: conjunction(conditions).unwrap(),
                    },
                };
            } else {
                bindings.insert(v.binding.clone(), Bound::Entity(endpoint.entity));
            }
        }
        bindings.insert(
            pattern.edges[0].binding.clone(),
            Bound::Edges {
                graph: endpoints_graph(&bindings)?,
                raw: Expr::slot(&edge_list),
            },
        );
        if let Some(binding) = &pattern.binding {
            let values = vec![
                ("length".into(), Expr::slot(&length)),
                ("vertices".into(), Expr::slot(&vertex_list)),
                ("edges".into(), Expr::slot(&edge_list)),
            ];
            let value = structure(values);
            let field = self.output_field("@path".into(), &value)?;
            let mut items = node
                .fields
                .iter()
                .map(|f| (f.slot, Expr::slot(f)))
                .collect::<Vec<_>>();
            items.push((field.slot, value));
            let mut fields = node.fields.clone();
            fields.push(field.clone());
            node = Node {
                fields,
                op: Op::Project {
                    input: Box::new(node),
                    items,
                    distinct: false,
                },
            };
            bindings.insert(
                binding.clone(),
                Bound::Path {
                    graph: endpoints_graph(&bindings)?,
                    raw: Expr::slot(&field),
                },
            );
        }
        Ok(Scope {
            order: Vec::new(),
            visible: None,
            node,
            bindings,
        })
    }
}
pub(super) fn identity_type() -> LogicalType {
    LogicalType::Struct(vec![
        grust_lpg::Property::required("group", LogicalType::Int64),
        grust_lpg::Property::required("identity", LogicalType::Int64),
    ])
}
fn structure(values: Vec<(String, Expr)>) -> Expr {
    let ty = LogicalType::Struct(
        values
            .iter()
            .map(|(name, e)| grust_lpg::Property {
                name: name.clone(),
                ty: e.ty.clone().unwrap(),
                nullable: e.nullable,
            })
            .collect(),
    );
    Expr {
        kind: Value::Struct(values),
        ty: Some(ty),
        nullable: false,
    }
}
fn identity(bound: &Bound) -> Expr {
    let Bound::Entity(e) = bound else {
        unreachable!()
    };
    structure(vec![
        ("group".into(), e.group.clone()),
        ("identity".into(), e.identity.clone()),
    ])
}
fn list(values: Vec<Expr>) -> Expr {
    Expr {
        kind: Value::List(values),
        ty: Some(LogicalType::List(Box::new(identity_type()))),
        nullable: false,
    }
}
pub(super) fn project_entity(template: &Template, actual: &Entity, items: &mut Vec<(Slot, Expr)>) {
    items.push((template.fields[0].slot, actual.identity.clone()));
    items.push((template.fields[1].slot, actual.group.clone()));
    for f in template.fields.iter().skip(2) {
        let value = actual
            .properties
            .iter()
            .find(|(name, _)| name == &f.name)
            .map(|(_, e)| e.clone())
            .unwrap_or(Expr {
                kind: Value::Literal(Literal::Null),
                ty: Some(f.ty.clone()),
                nullable: true,
            });
        items.push((f.slot, value));
    }
}

fn endpoints_graph(bindings: &HashMap<Binding, Bound>) -> Result<String, ResolveError> {
    bindings
        .values()
        .find_map(|b| {
            if let Bound::Entity(e) = b {
                Some(e.graph.clone())
            } else {
                None
            }
        })
        .ok_or_else(|| unsupported("path", "missing graph identity"))
}
