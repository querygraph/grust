use super::expressions::{boolean, compatible, grouped};
use super::value_bindings::{entity_bound, projected_bound};
use super::*;
use grust_unresolved_plan::{JoinKind, Relation as U};
impl State<'_, '_> {
    pub(super) fn relation(&mut self, relation: &U) -> Result<Scope, ResolveError> {
        match relation {
            U::Argument => self
                .argument
                .clone()
                .ok_or_else(|| unsupported("argument", "outside correlated apply")),
            U::Apply { input, body } => self.apply(input, body),
            U::Unit => Ok(Scope {
                order: Vec::new(),
                visible: None,
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
                let mut scope = self.relation(input)?;
                let mut predicate = self.expression(predicate, &scope, None, false)?;
                self.lift_entities(&mut scope, &mut predicate)?;
                boolean(&predicate)?;
                Ok(Scope {
                    order: scope.order,
                    visible: scope.visible,
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
                let mut input = self.relation(input)?;
                let mut fields = Vec::new();
                let mut values = Vec::new();
                let mut bindings = HashMap::new();
                for item in items {
                    let mut expr = self.expression(&item.expression, &input, None, false)?;
                    self.lift_entities(&mut input, &mut expr)?;
                    let f = self.output_field(item.name.clone(), &expr)?;
                    if bindings
                        .insert(
                            Binding::Named(item.name.clone()),
                            projected_bound(&item.expression, &input, &f, &expr),
                        )
                        .is_some()
                    {
                        return Err(unsupported("projection", "duplicate output alias"));
                    }
                    values.push((f.slot, expr));
                    fields.push(f);
                }
                let visible = fields.iter().map(|f| f.slot).collect();
                let order = if *distinct {
                    Vec::new()
                } else {
                    self.carry_order(&input, &mut fields, &mut values)
                };
                self.carry_keys(&input.node, &mut fields, &mut values);
                Ok(Scope {
                    order,
                    visible: Some(visible),
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
                            projected_bound(&item.expression, &input, &f, &expr),
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
                self.carry_keys(&input.node, &mut fields, &mut group_items);
                let empty_shape = input.node.fields.clone();
                let empty_items = agg_items.clone();
                let mut node = Node {
                    fields,
                    op: Op::Aggregate {
                        input: Box::new(input.node),
                        groups: group_items,
                        aggregates: agg_items,
                    },
                };
                if groups.is_empty() && !self.correlation_keys.is_empty() {
                    node = self.fill_empty_aggregate(node, empty_shape, empty_items)?;
                }
                Ok(Scope {
                    order: Vec::new(),
                    visible: None,
                    node,
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
                    order: Vec::new(),
                    visible: None,
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
                Ok(Scope {
                    order: Vec::new(),
                    visible: None,
                    node,
                    bindings,
                })
            }
            U::Union { inputs, all } => {
                if inputs.is_empty() {
                    return Err(unsupported("union", "requires inputs"));
                }
                let mut scopes = inputs
                    .iter()
                    .map(|i| {
                        self.relation(i).map(|scope| {
                            super::ordering::union_input(scope, &self.correlation_keys)
                        })
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                let first = scopes.remove(0);
                let mut fields = Vec::new();
                for field in &first.node.fields {
                    fields.push(
                        if self
                            .correlation_keys
                            .iter()
                            .any(|key| key.slot == field.slot)
                        {
                            field.clone()
                        } else {
                            self.field(field.name.clone(), field.ty.clone(), field.nullable)?
                        },
                    );
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
                    .filter(|field| {
                        !self
                            .correlation_keys
                            .iter()
                            .any(|key| key.slot == field.slot)
                    })
                    .map(|f| (Binding::Named(f.name.clone()), Bound::Value(Expr::slot(f))))
                    .collect();
                let mut inputs = vec![first.node];
                inputs.extend(scopes.into_iter().map(|s| s.node));
                Ok(Scope {
                    order: Vec::new(),
                    visible: None,
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
                let entity_element = match list {
                    grust_unresolved_plan::Expr::Binding(binding)
                    | grust_unresolved_plan::Expr::GraphValue(binding) => {
                        match input.bindings.get(binding) {
                            Some(Bound::EntityList { element, .. }) => Some(element.clone()),
                            _ => None,
                        }
                    }
                    _ => None,
                };
                let mut list = self.expression(list, &input, None, false)?;
                self.lift_entities(&mut input, &mut list)?;
                let Some(LogicalType::List(element)) = &list.ty else {
                    return Err(unsupported("unwind", "typed list required"));
                };
                let f = self.field(binding.clone(), *element.clone(), true)?;
                if input
                    .bindings
                    .insert(
                        Binding::Named(binding.clone()),
                        entity_element
                            .as_ref()
                            .map(|entity| entity_bound(entity, &f))
                            .unwrap_or_else(|| Bound::Value(Expr::slot(&f))),
                    )
                    .is_some()
                {
                    return Err(unsupported("unwind", "binding already exists"));
                }
                let mut fields = input.node.fields.clone();
                fields.push(f.clone());
                Ok(Scope {
                    order: input.order,
                    visible: None,
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
                    order: keys.clone(),
                    visible: input.visible,
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
                let mut parse = |e: &grust_unresolved_plan::Expr| -> Result<Expr, ResolveError> {
                    let expr = self.expression(e, &input, None, false)?;
                    if expr.ty != Some(LogicalType::Int64)
                        || expr.nullable
                        || !matches!(expr.kind,Value::Literal(grust_unresolved_plan::Literal::Integer(v)) if v>=0)
                    {
                        return Err(unsupported("slice","nonnegative integer literal required; bind dynamic caps before planning"));
                    }
                    Ok(expr)
                };
                let offset = offset.as_ref().map(&mut parse).transpose()?;
                let limit = limit.as_ref().map(&mut parse).transpose()?;
                if !self.correlation_keys.is_empty() {
                    let (base, keys) = match input.node.op.clone() {
                        Op::Sort { input, keys } => (*input, keys),
                        _ => (input.node.clone(), Vec::new()),
                    };
                    return Ok(Scope {
                        order: input.order.clone(),
                        visible: input.visible.clone(),
                        node: Node {
                            fields: base.fields.clone(),
                            op: Op::PartitionSlice {
                                input: Box::new(base),
                                partitions: self.correlation_keys.iter().map(Expr::slot).collect(),
                                keys,
                                offset,
                                limit,
                            },
                        },
                        bindings: input.bindings,
                    });
                }
                let base = if input.order.is_empty() {
                    input.node
                } else {
                    Node {
                        fields: input.node.fields.clone(),
                        op: Op::Sort {
                            input: Box::new(input.node),
                            keys: input.order.clone(),
                        },
                    }
                };
                Ok(Scope {
                    order: input.order.clone(),
                    visible: input.visible.clone(),
                    node: Node {
                        fields: base.fields.clone(),
                        op: Op::Slice {
                            input: Box::new(base),
                            offset,
                            limit,
                        },
                    },
                    bindings: input.bindings,
                })
            }
            U::Extension { .. } => self.extension_relation(relation),
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
            Bound::Value(e)
            | Bound::Path { raw: e, .. }
            | Bound::Edges { raw: e, .. }
            | Bound::EntityList { raw: e, .. } => update(e, fields),
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
