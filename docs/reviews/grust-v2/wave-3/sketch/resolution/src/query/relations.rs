use super::expressions::{boolean, compatible, grouped};
use super::*;
use grust_unresolved_plan::{JoinKind, Relation as U};
impl State<'_, '_> {
    pub(super) fn relation(&mut self, relation: &U) -> Result<Scope, ResolveError> {
        match relation {
            U::Unit => Ok(Scope {
                node: Node {
                    op: Op::Unit,
                    fields: vec![],
                },
                bindings: HashMap::new(),
            }),
            U::Match {
                input,
                graph,
                patterns,
                optional,
            } => {
                let input = self.relation(input)?;
                self.matches(input, graph, patterns, *optional)
            }
            U::Filter { input, predicate } => {
                let scope = self.relation(input)?;
                let predicate = self.expression(predicate, &scope, None, false)?;
                boolean(&predicate)?;
                Ok(Scope {
                    node: Node {
                        fields: scope.node.fields.clone(),
                        op: Op::Filter {
                            input: Box::new(scope.node),
                            predicate,
                        },
                    },
                    bindings: scope.bindings,
                })
            }
            U::Project {
                input,
                items,
                distinct,
            } => {
                let input = self.relation(input)?;
                let mut fields = Vec::new();
                let mut values = Vec::new();
                let mut bindings = HashMap::new();
                for item in items {
                    let expr = self.expression(&item.expression, &input, None, false)?;
                    let f = self.output_field(item.name.clone(), &expr)?;
                    if bindings
                        .insert(
                            Binding::Named(item.name.clone()),
                            projected_bound(&item.expression, &input, &f),
                        )
                        .is_some()
                    {
                        return Err(unsupported("projection", "duplicate output alias"));
                    }
                    values.push((f.slot, expr));
                    fields.push(f);
                }
                Ok(Scope {
                    node: Node {
                        fields,
                        op: Op::Project {
                            input: Box::new(input.node),
                            items: values,
                            distinct: *distinct,
                        },
                    },
                    bindings,
                })
            }
            U::Aggregate {
                input,
                groups,
                aggregates,
            } => {
                let input = self.relation(input)?;
                let grouping = groups
                    .iter()
                    .map(|g| self.expression(&g.expression, &input, None, false))
                    .collect::<Result<Vec<_>, _>>()?;
                let mut fields = Vec::new();
                let mut bindings = HashMap::new();
                let mut group_items = Vec::new();
                let mut agg_items = Vec::new();
                for (is_group, item) in groups
                    .iter()
                    .map(|g| (true, g))
                    .chain(aggregates.iter().map(|a| (false, a)))
                {
                    let expr = self.expression(&item.expression, &input, None, !is_group)?;
                    if !is_group && !grouped(&expr, &grouping) {
                        return Err(unsupported(
                            "aggregate",
                            "ungrouped expression outside aggregate",
                        ));
                    }
                    let f = self.output_field(item.name.clone(), &expr)?;
                    if bindings
                        .insert(
                            Binding::Named(item.name.clone()),
                            Bound::Value(Expr::slot(&f)),
                        )
                        .is_some()
                    {
                        return Err(unsupported("aggregate", "duplicate output alias"));
                    }
                    if is_group {
                        group_items.push((f.slot, expr));
                    } else {
                        agg_items.push((f.slot, expr));
                    }
                    fields.push(f);
                }
                Ok(Scope {
                    node: Node {
                        fields,
                        op: Op::Aggregate {
                            input: Box::new(input.node),
                            groups: group_items,
                            aggregates: agg_items,
                        },
                    },
                    bindings,
                })
            }
            U::Join {
                left,
                right,
                kind,
                condition,
            } => {
                let left = self.relation(left)?;
                let right = self.relation(right)?;
                let mut bindings = left.bindings.clone();
                for (key, value) in &right.bindings {
                    if bindings.insert(key.clone(), value.clone()).is_some() {
                        return Err(unsupported(
                            "join",
                            "overlapping bindings require explicit aliases",
                        ));
                    }
                }
                if *kind == JoinKind::Cross && condition.is_some() {
                    return Err(unsupported("cross join", "condition is not allowed"));
                }
                let combined = Scope {
                    node: Node {
                        op: Op::Unit,
                        fields: vec![],
                    },
                    bindings: bindings.clone(),
                };
                let condition = condition
                    .as_ref()
                    .map(|c| {
                        self.expression(c, &combined, None, false).and_then(|c| {
                            boolean(&c)?;
                            Ok(c)
                        })
                    })
                    .transpose()?;
                let node = join(left.node, right.node, *kind, condition);
                if matches!(kind, JoinKind::Semi | JoinKind::Anti) {
                    bindings = left.bindings;
                }
                null_scope(&mut bindings, &node.fields);
                Ok(Scope { node, bindings })
            }
            U::Union { inputs, all } => {
                if inputs.is_empty() {
                    return Err(unsupported("union", "requires inputs"));
                }
                let mut scopes = inputs
                    .iter()
                    .map(|i| self.relation(i))
                    .collect::<Result<Vec<_>, _>>()?;
                let first = scopes.remove(0);
                let mut fields = Vec::new();
                for field in &first.node.fields {
                    fields.push(self.field(
                        field.name.clone(),
                        field.ty.clone(),
                        field.nullable,
                    )?);
                }
                for input in &scopes {
                    if input.node.fields.len() != fields.len() {
                        return Err(unsupported("union", "column count mismatch"));
                    }
                    for (expected, actual) in fields.iter_mut().zip(&input.node.fields) {
                        compatible(Some(&expected.ty), Some(&actual.ty))?;
                        if grust_resolved_plan::query::is_null_type(&expected.ty) {
                            expected.ty = actual.ty.clone();
                        }
                        expected.nullable |= actual.nullable;
                    }
                }
                let bindings = fields
                    .iter()
                    .map(|f| (Binding::Named(f.name.clone()), Bound::Value(Expr::slot(f))))
                    .collect();
                let mut inputs = vec![first.node];
                inputs.extend(scopes.into_iter().map(|s| s.node));
                Ok(Scope {
                    node: Node {
                        fields,
                        op: Op::Union { inputs, all: *all },
                    },
                    bindings,
                })
            }
            U::Unwind {
                input,
                list,
                binding,
            } => {
                let mut input = self.relation(input)?;
                let list = self.expression(list, &input, None, false)?;
                let Some(LogicalType::List(element)) = &list.ty else {
                    return Err(unsupported("unwind", "typed list required"));
                };
                let f = self.field(binding.clone(), *element.clone(), true)?;
                if input
                    .bindings
                    .insert(
                        Binding::Named(binding.clone()),
                        Bound::Value(Expr::slot(&f)),
                    )
                    .is_some()
                {
                    return Err(unsupported("unwind", "binding already exists"));
                }
                let mut fields = input.node.fields.clone();
                fields.push(f.clone());
                Ok(Scope {
                    node: Node {
                        fields,
                        op: Op::Unwind {
                            input: Box::new(input.node),
                            list,
                            slot: f.slot,
                        },
                    },
                    bindings: input.bindings,
                })
            }
            U::Sort { input, keys } => {
                let input = self.relation(input)?;
                let keys = keys
                    .iter()
                    .map(|k| {
                        Ok(grust_resolved_plan::query::SortKey {
                            expression: self.expression(&k.expression, &input, None, false)?,
                            descending: k.descending,
                            nulls_first: k.nulls_first,
                        })
                    })
                    .collect::<Result<Vec<_>, ResolveError>>()?;
                Ok(Scope {
                    node: Node {
                        fields: input.node.fields.clone(),
                        op: Op::Sort {
                            input: Box::new(input.node),
                            keys,
                        },
                    },
                    bindings: input.bindings,
                })
            }
            U::Slice {
                input,
                offset,
                limit,
            } => {
                let input = self.relation(input)?;
                let parse = |e: &grust_unresolved_plan::Expr| -> Result<Expr, ResolveError> {
                    let expr = self.expression(e, &input, None, false)?;
                    if expr.ty != Some(LogicalType::Int64)
                        || expr.nullable
                        || !matches!(expr.kind,Value::Literal(grust_unresolved_plan::Literal::Integer(v)) if v>=0)
                    {
                        return Err(unsupported("slice","nonnegative integer literal required; bind dynamic caps before planning"));
                    }
                    Ok(expr)
                };
                let offset = offset.as_ref().map(parse).transpose()?;
                let limit = limit.as_ref().map(parse).transpose()?;
                Ok(Scope {
                    node: Node {
                        fields: input.node.fields.clone(),
                        op: Op::Slice {
                            input: Box::new(input.node),
                            offset,
                            limit,
                        },
                    },
                    bindings: input.bindings,
                })
            }
            U::Extension { name, .. } => Err(unsupported(
                "extension",
                &format!("no relation provider registered for {name:?}"),
            )),
        }
    }
}
fn null_scope(bindings: &mut HashMap<Binding, Bound>, fields: &[Field]) {
    fn affected(e: &Expr, fields: &[Field]) -> bool {
        match &e.kind {
            Value::Slot(s) => fields.iter().any(|f| f.slot == *s && f.nullable),
            Value::Property { object, .. } => affected(object, fields),
            _ => false,
        }
    }
    fn update(e: &mut Expr, fields: &[Field]) {
        if affected(e, fields) {
            e.nullable = true;
        }
    }
    for bound in bindings.values_mut() {
        match bound {
            Bound::Value(e) => update(e, fields),
            Bound::Entity(e) => {
                update(&mut e.identity, fields);
                update(&mut e.group, fields);
                for (_, p) in &mut e.properties {
                    update(p, fields);
                }
            }
        }
    }
}

fn projected_bound(original: &grust_unresolved_plan::Expr, input: &Scope, field: &Field) -> Bound {
    if let grust_unresolved_plan::Expr::Binding(binding) = original {
        if let Some(Bound::Entity(entity)) = input.bindings.get(binding) {
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
            return Bound::Entity(Entity {
                graph: entity.graph.clone(),
                identity,
                group,
                properties,
                edge: entity.edge,
            });
        }
    }
    Bound::Value(Expr::slot(field))
}
