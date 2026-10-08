//! Presentation order is metadata; hidden sort columns never become result columns.
use super::*;
use grust_resolved_plan::query::SortKey;
use std::collections::BTreeSet;
pub(super) fn result(scope: Scope) -> Node {
    let visible = scope
        .visible
        .unwrap_or_else(|| scope.node.fields.iter().map(|f| f.slot).collect());
    if scope.order.is_empty() && visible.len() == scope.node.fields.len() {
        return scope.node;
    }
    let fields = scope
        .node
        .fields
        .iter()
        .filter(|f| visible.contains(&f.slot))
        .cloned()
        .collect();
    Node {
        fields,
        op: Op::Result {
            input: Box::new(scope.node),
            keys: scope.order,
        },
    }
}
impl State<'_, '_> {
    pub(super) fn carry_order(
        &self,
        input: &Scope,
        fields: &mut Vec<Field>,
        items: &mut Vec<(Slot, Expr)>,
    ) -> Vec<SortKey> {
        let mut needed = BTreeSet::new();
        for key in &input.order {
            references(&key.expression, &mut needed);
        }
        for field in &input.node.fields {
            if needed.contains(&field.slot) && !fields.iter().any(|f| f.slot == field.slot) {
                fields.push(field.clone());
                items.push((field.slot, Expr::slot(field)));
            }
        }
        input.order.clone()
    }
}
fn references(e: &Expr, out: &mut BTreeSet<Slot>) {
    match &e.kind {
        Value::Slot(s) => {
            out.insert(*s);
        }
        Value::Binary { left, right, .. } | Value::ListDisjoint { left, right } => {
            references(left, out);
            references(right, out);
        }
        Value::ListDropFirst(argument)
        | Value::ListLength(argument)
        | Value::EntityList {
            identities: argument,
            ..
        }
        | Value::Cast { argument, .. }
        | Value::Unary { argument, .. } => references(argument, out),
        Value::Call {
            arguments, filter, ..
        } => {
            for e in arguments {
                references(e, out);
            }
            if let Some(e) = filter {
                references(e, out);
            }
        }
        Value::Property { object, .. } => references(object, out),
        Value::List(items) => {
            for e in items {
                references(e, out);
            }
        }
        Value::Struct(items) => {
            for (_, e) in items {
                references(e, out);
            }
        }
        Value::Case {
            branches,
            otherwise,
        } => {
            for (a, b) in branches {
                references(a, out);
                references(b, out);
            }
            references(otherwise, out);
        }
        _ => {}
    }
}

/// UNION aligns language-visible columns, not retained branch ordering keys.
pub(super) fn union_input(mut scope: Scope, keys: &[Field]) -> Scope {
    let visible = scope
        .visible
        .clone()
        .unwrap_or_else(|| scope.node.fields.iter().map(|f| f.slot).collect());
    let fields = scope
        .node
        .fields
        .iter()
        .filter(|f| visible.contains(&f.slot) || keys.iter().any(|k| k.slot == f.slot))
        .cloned()
        .collect::<Vec<_>>();
    if fields.len() != scope.node.fields.len() {
        let items = fields.iter().map(|f| (f.slot, Expr::slot(f))).collect();
        scope.node = Node {
            fields,
            op: Op::Project {
                input: Box::new(scope.node),
                items,
                distinct: false,
            },
        };
    }
    scope.order.clear();
    scope.visible = Some(visible);
    scope
}
