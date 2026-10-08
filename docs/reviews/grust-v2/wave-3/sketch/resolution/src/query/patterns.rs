use super::catalog::{enumerate, group_properties, label};
use super::*;
use grust_lpg::{Direction, EdgeGroup, GroupId, Lpg, Schema, VertexGroup};
use grust_resolved_plan::query::Column;
use grust_unresolved_plan::{
    BinaryOp, GraphRef, Hops, JoinKind, Literal, PathMode, PathPattern, PathSelector,
    PatternDirection,
};
use std::collections::{BTreeMap, BTreeSet};
#[derive(Clone)]
pub(super) struct Template {
    pub(super) entity: Entity,
    pub(super) fields: Vec<Field>,
    pub(super) source: Option<Field>,
    pub(super) target: Option<Field>,
}
impl State<'_, '_> {
    pub(super) fn matches(
        &mut self,
        input: Scope,
        graph: &GraphRef,
        patterns: &[PathPattern],
        optional: bool,
    ) -> Result<Scope, ResolveError> {
        let (graph, schema) = self.context.catalog.graph(graph)?;
        let graph = graph.to_owned();
        let schema = schema.clone();
        let mut pattern_scope = Scope {
            order: Vec::new(),
            visible: None,
            node: Node {
                op: Op::Unit,
                fields: vec![],
            },
            bindings: HashMap::new(),
        };
        let mut predicates = Vec::new();
        let mut previous_trails = Vec::<Expr>::new();
        for pattern in patterns {
            let part = self.pattern(&graph, &schema, pattern)?;
            if pattern.mode == PathMode::Trail {
                let current = super::uniqueness::edge_sets(pattern, &part.bindings)?;
                for old in &previous_trails {
                    for new in &current {
                        predicates.push(Expr {
                            kind: Value::ListDisjoint {
                                left: Box::new(old.clone()),
                                right: Box::new(new.clone()),
                            },
                            ty: Some(LogicalType::Boolean),
                            nullable: false,
                        });
                    }
                }
                previous_trails.extend(current);
            }
            let mut joins = Vec::new();
            merge(&mut pattern_scope.bindings, &part.bindings, &mut joins)?;
            pattern_scope.node = join(
                pattern_scope.node,
                part.node,
                JoinKind::Inner,
                conjunction(joins),
            );
        }
        let mut bindings = input.bindings.clone();
        merge(&mut bindings, &pattern_scope.bindings, &mut predicates)?;
        let combined = Scope {
            order: Vec::new(),
            visible: None,
            node: Node {
                op: Op::Unit,
                fields: vec![],
            },
            bindings: bindings.clone(),
        };
        for pattern in patterns {
            if pattern.binding.is_some()
                || pattern.selector != PathSelector::All
                || pattern.edges.iter().any(|e| e.hops != Hops::ONE)
            {
                continue;
            }
            for vertex in &pattern.vertices {
                for predicate in &vertex.predicates {
                    let e = self.expression(predicate, &combined, Some(&vertex.binding), false)?;
                    super::expressions::boolean(&e)?;
                    predicates.push(e);
                }
            }
            for edge in &pattern.edges {
                for predicate in &edge.predicates {
                    let e = self.expression(predicate, &combined, Some(&edge.binding), false)?;
                    super::expressions::boolean(&e)?;
                    predicates.push(e);
                }
            }
        }
        let node = join(
            input.node,
            pattern_scope.node,
            if optional {
                JoinKind::Left
            } else {
                JoinKind::Inner
            },
            conjunction(predicates),
        );
        // Only newly introduced entities become nullable under OPTIONAL MATCH.
        if optional {
            for (key, bound) in &mut bindings {
                if pattern_scope.bindings.contains_key(key) && !input.bindings.contains_key(key) {
                    if let Bound::Value(value)
                    | Bound::Path { raw: value, .. }
                    | Bound::Edges { raw: value, .. } = bound
                    {
                        value.nullable = true;
                    }
                    if let Bound::Entity(e) = bound {
                        e.identity.nullable = true;
                        e.group.nullable = true;
                        for (_, p) in &mut e.properties {
                            p.nullable = true;
                        }
                    }
                }
            }
        }
        Ok(Scope {
            order: input.order,
            visible: None,
            node,
            bindings,
        })
    }
    pub(super) fn pattern(
        &mut self,
        graph: &str,
        schema: &Schema,
        pattern: &PathPattern,
    ) -> Result<Scope, ResolveError> {
        if !pattern.is_well_formed() {
            return Err(unsupported("pattern", "malformed path"));
        }
        if pattern.edges.len() != 1
            && (pattern.binding.is_some()
                || pattern.selector != PathSelector::All
                || pattern
                    .edges
                    .iter()
                    .any(|e| e.binding_list || e.hops != Hops::ONE))
            || pattern.edges.len() == 1
                && pattern.binding.is_some()
                && !pattern.edges[0].binding_list
                && pattern.edges[0].hops == Hops::ONE
        {
            return self.segmented_pattern(graph, schema, pattern);
        }
        if pattern.binding.is_some()
            || pattern.selector != PathSelector::All
            || pattern
                .edges
                .iter()
                .any(|e| e.binding_list || e.hops != Hops::ONE)
        {
            return self.ranged_pattern(graph, schema, pattern);
        }
        let paths = enumerate(schema, pattern)?;
        let mut templates = Vec::new();
        for i in 0..pattern.vertices.len() {
            let groups = paths.iter().map(|p| p.0[i]).collect::<BTreeSet<_>>();
            // Infeasible paths still resolve the output shape against label-feasible groups.
            let groups = if groups.is_empty() {
                schema
                    .vertex_groups()
                    .iter()
                    .filter_map(|v| {
                        label(schema, v.element_type(), &pattern.vertices[i].labels)
                            .ok()
                            .filter(|x| *x)
                            .map(|_| v.id())
                    })
                    .collect()
            } else {
                groups
            };
            templates.push(self.template(graph, schema, groups.into_iter().collect(), false)?);
            if i < pattern.edges.len() {
                let groups = paths.iter().map(|p| p.1[i].0).collect::<BTreeSet<_>>();
                let groups = if groups.is_empty() {
                    schema
                        .edge_groups()
                        .iter()
                        .filter_map(|e| {
                            label(schema, e.element_type(), &pattern.edges[i].labels)
                                .ok()
                                .filter(|x| *x)
                                .map(|_| e.id())
                        })
                        .collect()
                } else {
                    groups
                };
                templates.push(self.template(graph, schema, groups.into_iter().collect(), true)?);
            }
        }
        let mut bindings = HashMap::new();
        let mut repeat = Vec::new();
        for (i, template) in templates.iter().enumerate() {
            let binding = if i % 2 == 0 {
                &pattern.vertices[i / 2].binding
            } else {
                &pattern.edges[i / 2].binding
            };
            let mut next = HashMap::new();
            next.insert(binding.clone(), Bound::Entity(template.entity.clone()));
            merge(&mut bindings, &next, &mut repeat)?;
        }
        let fields = templates
            .iter()
            .flat_map(|t| t.fields.clone())
            .collect::<Vec<_>>();
        let mut branches = Vec::new();
        for (vertices, edges) in paths {
            let mut nodes = Vec::new();
            for (i, t) in templates.iter().enumerate() {
                let group = if i % 2 == 0 {
                    vertices[i / 2]
                } else {
                    edges[i / 2].0
                };
                nodes.push(scan(schema, graph, group, t)?);
            }
            let mut predicates = repeat.clone();
            for (i, (edge_group, reversed)) in edges.iter().enumerate() {
                let edge = &templates[2 * i + 1];
                let (src, dst) = if *reversed {
                    (edge.target.as_ref().unwrap(), edge.source.as_ref().unwrap())
                } else {
                    (edge.source.as_ref().unwrap(), edge.target.as_ref().unwrap())
                };
                predicates.push(eq(
                    Expr::slot(src),
                    templates[2 * i].entity.identity.clone(),
                ));
                predicates.push(eq(
                    Expr::slot(dst),
                    templates[2 * i + 2].entity.identity.clone(),
                ));
                let schema_edge = schema
                    .edge_groups()
                    .iter()
                    .find(|e| e.id() == *edge_group)
                    .unwrap();
                if *reversed
                    && (schema_edge.direction() == Direction::Undirected
                        || pattern.edges[i].direction == PatternDirection::Either)
                    && schema_edge.endpoints().0 == schema_edge.endpoints().1
                {
                    predicates.push(binary(
                        BinaryOp::NotEq,
                        Expr::slot(src),
                        Expr::slot(dst),
                        Some(LogicalType::Boolean),
                    ));
                }
            }
            let entities = templates
                .iter()
                .enumerate()
                .filter(|(i, _)| match pattern.mode {
                    PathMode::Walk => false,
                    PathMode::Trail => i % 2 == 1,
                    PathMode::Simple | PathMode::Acyclic => i % 2 == 0,
                })
                .map(|(_, t)| &t.entity)
                .collect::<Vec<_>>();
            // Simple permits a closing cycle; Acyclic forbids any repeated vertex.
            for i in 0..entities.len() {
                for j in i + 1..entities.len() {
                    if pattern.mode == PathMode::Simple && i == 0 && j == entities.len() - 1 {
                        continue;
                    }
                    predicates.push(binary(
                        BinaryOp::Or,
                        binary(
                            BinaryOp::NotEq,
                            entities[i].group.clone(),
                            entities[j].group.clone(),
                            Some(LogicalType::Boolean),
                        ),
                        binary(
                            BinaryOp::NotEq,
                            entities[i].identity.clone(),
                            entities[j].identity.clone(),
                            Some(LogicalType::Boolean),
                        ),
                        Some(LogicalType::Boolean),
                    ));
                }
            }
            if pattern.mode == PathMode::Simple {
                let edges = templates
                    .iter()
                    .enumerate()
                    .filter(|(i, _)| i % 2 == 1)
                    .map(|(_, t)| &t.entity)
                    .collect::<Vec<_>>();
                for i in 0..edges.len() {
                    for j in i + 1..edges.len() {
                        predicates.push(binary(
                            BinaryOp::Or,
                            binary(
                                BinaryOp::NotEq,
                                edges[i].group.clone(),
                                edges[j].group.clone(),
                                Some(LogicalType::Boolean),
                            ),
                            binary(
                                BinaryOp::NotEq,
                                edges[i].identity.clone(),
                                edges[j].identity.clone(),
                                Some(LogicalType::Boolean),
                            ),
                            Some(LogicalType::Boolean),
                        ));
                    }
                }
            }
            let node = nodes
                .into_iter()
                .reduce(|l, r| join(l, r, JoinKind::Inner, None))
                .unwrap();
            let node = if let Some(predicate) = conjunction(predicates) {
                Node {
                    fields: node.fields.clone(),
                    op: Op::Filter {
                        input: Box::new(node),
                        predicate,
                    },
                }
            } else {
                node
            };
            branches.push(node);
        }
        let node = match branches.len() {
            0 => Node {
                op: Op::Empty,
                fields,
            },
            1 => branches.remove(0),
            _ => Node {
                op: Op::Union {
                    inputs: branches,
                    all: true,
                },
                fields,
            },
        };
        Ok(Scope {
            order: Vec::new(),
            visible: None,
            node,
            bindings,
        })
    }
    pub(super) fn template(
        &mut self,
        graph: &str,
        schema: &Schema,
        groups: Vec<GroupId>,
        edge: bool,
    ) -> Result<Template, ResolveError> {
        let identity = self.field("@identity".into(), LogicalType::Int64, false)?;
        let tag = self.field("@group".into(), LogicalType::Int64, false)?;
        let mut properties = BTreeMap::<String, (LogicalType, usize, bool)>::new();
        for group in &groups {
            for (name, (ty, nullable)) in group_properties(schema, *group, edge)? {
                let p = properties
                    .entry(name.clone())
                    .or_insert((ty.clone(), 0, false));
                if p.0 != ty {
                    return Err(ResolveError::AmbiguousProperty(name));
                }
                p.1 += 1;
                p.2 |= nullable;
            }
        }
        let mut fields = vec![identity.clone(), tag.clone()];
        let mut values = Vec::new();
        for (name, (ty, count, nullable)) in properties {
            let f = self.field(name.clone(), ty, nullable || count < groups.len())?;
            values.push((name, Expr::slot(&f)));
            fields.push(f);
        }
        let source = if edge {
            Some(self.field("@source".into(), LogicalType::Int64, false)?)
        } else {
            None
        };
        let target = if edge {
            Some(self.field("@target".into(), LogicalType::Int64, false)?)
        } else {
            None
        };
        fields.extend(source.clone());
        fields.extend(target.clone());
        Ok(Template {
            entity: Entity {
                graph: graph.into(),
                identity: Expr::slot(&identity),
                group: Expr::slot(&tag),
                properties: values,
                edge,
            },
            fields,
            source,
            target,
        })
    }
}
pub(super) fn scan(
    schema: &Schema,
    graph: &str,
    group: GroupId,
    template: &Template,
) -> Result<Node, ResolveError> {
    let properties = group_properties(schema, group, template.entity.edge)?;
    let mut columns = vec![(template.fields[0].slot, Column::Identity)];
    let mut raw = vec![template.fields[0].clone()];
    let mut items = vec![(template.fields[0].slot, Expr::slot(&template.fields[0]))];
    let tag = i64::try_from(group.0)
        .map_err(|_| unsupported("group tag", "group identifier exceeds signed BIGINT"))?;
    items.push((
        template.fields[1].slot,
        Expr {
            kind: Value::Literal(Literal::Integer(tag)),
            ty: Some(LogicalType::Int64),
            nullable: false,
        },
    ));
    for f in template.fields.iter().skip(2) {
        let column = if template.source.as_ref().is_some_and(|s| s.slot == f.slot) {
            Some(Column::Source)
        } else if template.target.as_ref().is_some_and(|s| s.slot == f.slot) {
            Some(Column::Target)
        } else if properties.contains_key(&f.name) {
            Some(Column::Property(f.name.clone()))
        } else {
            None
        };
        let value = if let Some(column) = column {
            columns.push((f.slot, column));
            raw.push(f.clone());
            Expr::slot(f)
        } else {
            Expr {
                kind: Value::Literal(Literal::Null),
                ty: Some(f.ty.clone()),
                nullable: true,
            }
        };
        items.push((f.slot, value));
    }
    let node = Node {
        op: Op::Scan {
            graph: graph.into(),
            group,
            columns,
        },
        fields: raw,
    };
    Ok(Node {
        op: Op::Project {
            input: Box::new(node),
            items,
            distinct: false,
        },
        fields: template.fields.clone(),
    })
}
pub(super) fn merge(
    bindings: &mut HashMap<Binding, Bound>,
    other: &HashMap<Binding, Bound>,
    conditions: &mut Vec<Expr>,
) -> Result<(), ResolveError> {
    let mut ordered = other.iter().collect::<Vec<_>>();
    ordered.sort_by_key(|(binding, _)| format!("{binding:?}"));
    for (binding, value) in ordered {
        if let Some(existing) = bindings.get(binding) {
            match (existing, value) {
                (Bound::Entity(a), Bound::Entity(b)) if a.graph == b.graph && a.edge == b.edge => {
                    conditions.push(eq(a.identity.clone(), b.identity.clone()));
                    conditions.push(eq(a.group.clone(), b.group.clone()));
                }
                (
                    Bound::Edges {
                        graph: a,
                        raw: left,
                    },
                    Bound::Edges {
                        graph: b,
                        raw: right,
                    },
                ) if a == b => conditions.push(eq(left.clone(), right.clone())),
                _ => return Err(unsupported("binding", "incompatible repeated binding")),
            }
        } else {
            bindings.insert(binding.clone(), value.clone());
        }
    }
    Ok(())
}
