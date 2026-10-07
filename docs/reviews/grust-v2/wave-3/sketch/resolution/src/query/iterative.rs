//! Compile one unbounded segment to seed/adjacency plus ordinary endpoint joins.
use super::catalog::label;
use super::paths::{identity_type, project_entity};
use super::*;
use grust_lpg::{Lpg, Schema, VertexGroup};
use grust_unresolved_plan::{Hops, LabelExpr, PathMode, PathPattern, PathSelector, VertexPattern};
impl State<'_, '_> {
    pub(super) fn iterative_pattern(
        &mut self,
        graph: &str,
        schema: &Schema,
        p: &PathPattern,
    ) -> Result<Scope, ResolveError> {
        if p.edges.len() != 1 {
            return Err(unsupported("iterative path", "one ranged segment required"));
        }
        if p.mode == PathMode::Walk
            && p.selector == PathSelector::All
            && p.edges[0].hops.max.is_none()
        {
            return Err(unsupported(
                "iterative path",
                "unbounded ALL WALK can have infinitely many results",
            ));
        }
        let edge = &p.edges[0];
        if p.vertices[0].binding == edge.binding
            || p.vertices[1].binding == edge.binding
            || p.binding
                .as_ref()
                .is_some_and(|b| p.vertices.iter().any(|v| &v.binding == b) || &edge.binding == b)
        {
            return Err(unsupported("iterative path", "incompatible bindings"));
        }
        // Edge predicates may use the edge or parameters; endpoint-dependent predicates
        // require a correlated adjacency provider rather than substituting intermediate nodes.
        for predicate in &edge.predicates {
            if endpoint_reference(predicate, &p.vertices) {
                return Err(unsupported(
                    "iterative edge predicate",
                    "endpoint correlations require a correlated provider",
                ));
            }
        }
        let mut endpoints = Vec::new();
        for vertex in &p.vertices {
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
        let vertex_scope = |state: &mut Self, vertex: VertexPattern| {
            state.pattern(
                graph,
                schema,
                &PathPattern {
                    binding: None,
                    vertices: vec![vertex],
                    edges: vec![],
                    mode: PathMode::Walk,
                    selector: PathSelector::All,
                },
            )
        };
        let seed_scope = vertex_scope(self, p.vertices[0].clone())?;
        let Bound::Entity(source) = &seed_scope.bindings[&p.vertices[0].binding] else {
            unreachable!()
        };
        let seed = self.identity_projection(
            seed_scope.node.clone(),
            &[source.group.clone(), source.identity.clone()],
        )?;
        let mut adjacent = p.clone();
        adjacent.binding = None;
        adjacent.selector = PathSelector::All;
        adjacent.mode = PathMode::Walk;
        adjacent.edges[0].hops = Hops::ONE;
        // Capture internal entities before introducing the caller edge alias.
        adjacent.vertices[0].binding = Binding::Anonymous(0);
        adjacent.vertices[1].binding = Binding::Anonymous(1);
        adjacent.edges[0].binding = Binding::Anonymous(2);
        for vertex in &mut adjacent.vertices {
            vertex.labels = LabelExpr::Any;
            vertex.predicates.clear();
        }
        let mut adjacency_scope = self.pattern(graph, schema, &adjacent)?;
        let entity = |key| match &adjacency_scope.bindings[&Binding::Anonymous(key)] {
            Bound::Entity(e) => e.clone(),
            _ => unreachable!(),
        };
        let a = entity(0);
        let b = entity(1);
        let actual_edge = adjacency_scope.bindings[&Binding::Anonymous(2)].clone();
        adjacency_scope
            .bindings
            .insert(edge.binding.clone(), actual_edge.clone());
        let mut conditions = Vec::new();
        for predicate in &edge.predicates {
            let e = self.expression(predicate, &adjacency_scope, Some(&edge.binding), false)?;
            super::expressions::boolean(&e)?;
            if !immutable(&e) {
                return Err(unsupported(
                    "iterative predicate",
                    "non-immutable predicates require correlated execution",
                ));
            }
            conditions.push(e);
        }
        if let Some(predicate) = conjunction(conditions) {
            adjacency_scope.node = Node {
                fields: adjacency_scope.node.fields.clone(),
                op: Op::Filter {
                    input: Box::new(adjacency_scope.node),
                    predicate,
                },
            };
        }
        let Bound::Entity(e) = actual_edge else {
            unreachable!()
        };
        let adjacency = self.identity_projection(
            adjacency_scope.node.clone(),
            &[
                a.group, a.identity, b.group, b.identity, e.group, e.identity,
            ],
        )?;
        let mut raw = Vec::new();
        for name in ["@src_group", "@src_id", "@dst_group", "@dst_id"] {
            raw.push(self.field(name.into(), LogicalType::Int64, false)?);
        }
        let edges = self.field(
            "@edges".into(),
            LogicalType::List(Box::new(identity_type())),
            false,
        )?;
        let vertices = self.field(
            "@vertices".into(),
            LogicalType::List(Box::new(identity_type())),
            false,
        )?;
        let length = self.field("@length".into(), LogicalType::Int64, false)?;
        raw.extend([edges.clone(), vertices.clone(), length.clone()]);
        let mut node = Node {
            fields: raw.clone(),
            op: Op::Traverse {
                seed: Box::new(seed),
                adjacency: Box::new(adjacency),
                hops: edge.hops,
                mode: p.mode,
                shortest_walk: p.mode == PathMode::Walk && p.selector != PathSelector::All,
            },
        };
        let mut items = Vec::new();
        let mut scope = Scope {
            node: node.clone(),
            bindings: HashMap::new(),
        };
        for (index, endpoint) in endpoints.iter().enumerate() {
            let mut v = p.vertices[index].clone();
            v.binding = Binding::Anonymous(10 + index as u64);
            let part = vertex_scope(self, v.clone())?;
            let Bound::Entity(actual) = &part.bindings[&v.binding] else {
                unreachable!()
            };
            let condition = conjunction(vec![
                eq(Expr::slot(&raw[index * 2]), actual.group.clone()),
                eq(Expr::slot(&raw[index * 2 + 1]), actual.identity.clone()),
            ]);
            node = join(
                node,
                part.node.clone(),
                grust_unresolved_plan::JoinKind::Inner,
                condition,
            );
            project_entity(endpoint, actual, &mut items);
            scope.bindings.insert(
                p.vertices[index].binding.clone(),
                Bound::Entity(actual.clone()),
            );
        }
        scope.node = node;
        let mut conditions = Vec::new();
        for v in &p.vertices {
            for predicate in &v.predicates {
                let e = self.expression(predicate, &scope, Some(&v.binding), false)?;
                super::expressions::boolean(&e)?;
                if !immutable(&e) {
                    return Err(unsupported(
                        "iterative predicate",
                        "non-immutable predicates require correlated execution",
                    ));
                }
                conditions.push(e);
            }
        }
        if let Some(predicate) = conjunction(conditions) {
            scope.node = Node {
                fields: scope.node.fields.clone(),
                op: Op::Filter {
                    input: Box::new(scope.node),
                    predicate,
                },
            };
        }
        items.extend(
            [edges.clone(), vertices.clone(), length.clone()]
                .iter()
                .map(|f| (f.slot, Expr::slot(f))),
        );
        let mut fields = endpoints
            .iter()
            .flat_map(|t| t.fields.clone())
            .collect::<Vec<_>>();
        fields.extend([edges.clone(), vertices.clone(), length.clone()]);
        let node = Node {
            fields,
            op: Op::Project {
                input: Box::new(scope.node),
                items,
                distinct: false,
            },
        };
        self.finish_path_scope(p, endpoints, node, edges, vertices, length)
    }
    fn identity_projection(&mut self, input: Node, values: &[Expr]) -> Result<Node, ResolveError> {
        let fields = values
            .iter()
            .enumerate()
            .map(|(i, e)| self.output_field(format!("@identity{i}"), e))
            .collect::<Result<Vec<_>, _>>()?;
        let items = fields
            .iter()
            .zip(values)
            .map(|(f, e)| (f.slot, e.clone()))
            .collect();
        Ok(Node {
            fields,
            op: Op::Project {
                input: Box::new(input),
                items,
                distinct: false,
            },
        })
    }
}
fn endpoint_reference(e: &grust_unresolved_plan::Expr, vertices: &[VertexPattern]) -> bool {
    use grust_unresolved_plan::Expr as E;
    match e {
        E::Binding(b) => vertices.iter().any(|v| &v.binding == b),
        E::Property { object, .. } => endpoint_reference(object, vertices),
        E::Binary { left, right, .. } => {
            endpoint_reference(left, vertices) || endpoint_reference(right, vertices)
        }
        E::Unary { argument, .. } => endpoint_reference(argument, vertices),
        // Reject complex forms conservatively; simple edge predicates stay useful.
        E::Literal(_) | E::Parameter(_) | E::CurrentElement => false,
        _ => true,
    }
}

fn immutable(e: &Expr) -> bool {
    match &e.kind {
        Value::Call {
            function,
            arguments,
            filter,
            ..
        } => {
            function.volatility == grust_functions::Volatility::Immutable
                && arguments.iter().all(immutable)
                && filter.as_ref().is_none_or(|e| immutable(e))
        }
        Value::Binary { left, right, .. } => immutable(left) && immutable(right),
        Value::Unary { argument, .. } => immutable(argument),
        Value::List(items) => items.iter().all(immutable),
        Value::Struct(items) => items.iter().all(|(_, e)| immutable(e)),
        Value::Property { object, .. } => immutable(object),
        Value::Case {
            branches,
            otherwise,
        } => branches.iter().all(|(a, b)| immutable(a) && immutable(b)) && immutable(otherwise),
        _ => true,
    }
}
