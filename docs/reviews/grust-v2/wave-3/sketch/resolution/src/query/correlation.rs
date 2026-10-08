//! Decorrelate a body by a stable materialized input-row identity, preserving bags.
use super::*;
use grust_unresolved_plan::{JoinKind, Relation, UnaryOp};
impl State<'_, '_> {
    pub(super) fn apply(
        &mut self,
        input: &Relation,
        body: &Relation,
    ) -> Result<Scope, ResolveError> {
        let mut outer = self.relation(input)?;
        let key = self.field("@correlation".into(), LogicalType::Int64, false)?;
        let mut fields = outer.node.fields.clone();
        fields.push(key.clone());
        outer.node = Node {
            fields: fields.clone(),
            op: Op::Materialize {
                id: key.slot.0,
                input: Box::new(Node {
                    fields,
                    op: Op::RowId {
                        input: Box::new(outer.node),
                        slot: key.slot,
                    },
                }),
            },
        };
        let previous_argument = self.argument.replace(outer.clone());
        let previous_keys = self.correlation_keys.clone();
        self.correlation_keys.push(key.clone());
        let result = self.relation(body);
        self.argument = previous_argument;
        self.correlation_keys = previous_keys;
        let result = result?;
        let mut bindings = outer.bindings;
        for (name, value) in result.bindings {
            if bindings.insert(name, value).is_some() {
                return Err(unsupported(
                    "apply",
                    "export conflicts with an existing binding",
                ));
            }
        }
        // Remap body slots before joining: the correlation key belongs to both sides.
        let mut remapped = Vec::new();
        let mut items = Vec::new();
        let mut body_key = None;
        let mut slots = HashMap::new();
        for field in &result.node.fields {
            let fresh = self.field(field.name.clone(), field.ty.clone(), field.nullable)?;
            if field.slot == key.slot {
                body_key = Some(Expr::slot(&fresh));
            }
            slots.insert(field.slot, fresh.clone());
            items.push((fresh.slot, Expr::slot(field)));
            remapped.push(fresh);
        }
        let Some(body_key) = body_key else {
            return Err(unsupported("apply", "body lost correlation identity"));
        };
        let right = Node {
            fields: remapped,
            op: Op::Project {
                input: Box::new(result.node),
                items,
                distinct: false,
            },
        };
        let node = join(
            outer.node,
            right,
            JoinKind::Inner,
            Some(eq(Expr::slot(&key), body_key)),
        );
        // Restore all exported expressions to the new slots; imported outer bindings stay unchanged.
        for binding in bindings.values_mut() {
            remap_bound(binding, &slots);
        }
        Ok(Scope {
            order: outer.order,
            visible: None,
            node,
            bindings,
        })
    }
    pub(super) fn carry_keys(
        &self,
        input: &Node,
        fields: &mut Vec<Field>,
        items: &mut Vec<(Slot, Expr)>,
    ) {
        for key in &self.correlation_keys {
            if input.fields.iter().any(|f| f.slot == key.slot)
                && !fields.iter().any(|f| f.slot == key.slot)
            {
                fields.push(key.clone());
                items.push((key.slot, Expr::slot(key)));
            }
        }
    }
    pub(super) fn fill_empty_aggregate(
        &mut self,
        aggregate: Node,
        shape: Vec<Field>,
        items: Vec<(Slot, Expr)>,
    ) -> Result<Node, ResolveError> {
        let domain = self
            .argument
            .as_ref()
            .ok_or_else(|| unsupported("aggregate", "missing correlation domain"))?
            .node
            .clone();
        let mut domain_fields = Vec::new();
        let mut domain_items = Vec::new();
        let mut conditions = Vec::new();
        for key in self.correlation_keys.clone() {
            let field = self.field("@domain".into(), key.ty.clone(), false)?;
            conditions.push(eq(Expr::slot(&field), Expr::slot(&key)));
            domain_items.push((field.slot, Expr::slot(&key)));
            domain_fields.push((key, field));
        }
        let domain = Node {
            fields: domain_fields.iter().map(|(_, f)| f.clone()).collect(),
            op: Op::Project {
                input: Box::new(domain),
                items: domain_items,
                distinct: true,
            },
        };
        let mut empty_fields = Vec::new();
        let mut empty_items = Vec::new();
        let mut replacements = HashMap::new();
        for (slot, expr) in items {
            let field = self.output_field("@empty_aggregate".into(), &expr)?;
            replacements.insert(slot, Expr::slot(&field));
            empty_items.push((field.slot, expr));
            empty_fields.push(field);
        }
        let empty = Node {
            fields: empty_fields,
            op: Op::Aggregate {
                input: Box::new(Node {
                    fields: shape,
                    op: Op::Empty,
                }),
                groups: vec![],
                aggregates: empty_items,
            },
        };
        let output = aggregate.fields.clone();
        let present = Expr {
            kind: Value::Unary {
                op: UnaryOp::IsNotNull,
                argument: Box::new(Expr::slot(self.correlation_keys.last().unwrap())),
            },
            ty: Some(LogicalType::Boolean),
            nullable: false,
        };
        let node = join(
            join(domain, aggregate, JoinKind::Left, conjunction(conditions)),
            empty,
            JoinKind::Cross,
            None,
        );
        let projection = output
            .iter()
            .map(|field| {
                let value = if let Some((_, domain)) =
                    domain_fields.iter().find(|(key, _)| key.slot == field.slot)
                {
                    Expr::slot(domain)
                } else {
                    Expr {
                        kind: Value::Case {
                            branches: vec![(present.clone(), Expr::slot(field))],
                            otherwise: Box::new(replacements[&field.slot].clone()),
                        },
                        ty: Some(field.ty.clone()),
                        nullable: field.nullable,
                    }
                };
                (field.slot, value)
            })
            .collect();
        Ok(Node {
            fields: output,
            op: Op::Project {
                input: Box::new(node),
                items: projection,
                distinct: false,
            },
        })
    }
}
fn remap_bound(bound: &mut Bound, slots: &HashMap<Slot, Field>) {
    fn expression(expr: &mut Expr, slots: &HashMap<Slot, Field>) {
        match &mut expr.kind {
            Value::Slot(slot) => {
                if let Some(field) = slots.get(slot) {
                    *expr = Expr::slot(field)
                }
            }
            Value::Property { object, .. } => expression(object, slots),
            _ => {}
        }
    }
    match bound {
        Bound::Value(e) | Bound::Path { raw: e, .. } | Bound::Edges { raw: e, .. } => {
            expression(e, slots)
        }
        Bound::Entity(e) => {
            expression(&mut e.identity, slots);
            expression(&mut e.group, slots);
            for (_, p) in &mut e.properties {
                expression(p, slots);
            }
        }
    }
}
