//! Full relational resolver entry point; unsupported path/extension semantics refuse.
mod catalog;
mod expressions;
mod patterns;
mod relations;
use crate::{Context, ResolveError};
use grust_lpg::LogicalType;
use grust_resolved_plan::query::{Expr, Node, Op, Plan, Value};
use grust_resolved_plan::{Field, Slot};
use grust_unresolved_plan::{Binding, UnresolvedPlan};
use std::collections::HashMap;
#[derive(Clone)]
enum Bound {
    Value(Expr),
    Entity(Entity),
}
#[derive(Clone)]
struct Entity {
    graph: String,
    identity: Expr,
    group: Expr,
    properties: Vec<(String, Expr)>,
    edge: bool,
}
#[derive(Clone)]
struct Scope {
    node: Node,
    bindings: HashMap<Binding, Bound>,
}
pub struct QueryResolver;
impl QueryResolver {
    pub fn resolve(
        &self,
        plan: &dyn UnresolvedPlan,
        context: &Context<'_>,
    ) -> Result<Plan, Vec<ResolveError>> {
        let mut state = State { context, next: 0 };
        state
            .relation(plan.relation())
            .map(|scope| Plan { root: scope.node })
            .map_err(|e| vec![e])
    }
}
struct State<'a, 'b> {
    context: &'a Context<'b>,
    next: u32,
}
impl State<'_, '_> {
    fn field(
        &mut self,
        name: String,
        ty: LogicalType,
        nullable: bool,
    ) -> Result<Field, ResolveError> {
        let slot = Slot(self.next);
        self.next = self
            .next
            .checked_add(1)
            .ok_or_else(|| unsupported("slots", "query too large"))?;
        Ok(Field {
            slot,
            name,
            ty,
            nullable,
        })
    }
    fn output_field(&mut self, name: String, expr: &Expr) -> Result<Field, ResolveError> {
        self.field(
            name,
            expr.ty
                .clone()
                .unwrap_or_else(grust_resolved_plan::query::null_type),
            expr.nullable,
        )
    }
}
fn unsupported(operator: &str, reason: &str) -> ResolveError {
    ResolveError::Unsupported {
        operator: operator.into(),
        reason: reason.into(),
    }
}
fn eq(left: Expr, right: Expr) -> Expr {
    binary(
        grust_unresolved_plan::BinaryOp::Eq,
        left,
        right,
        Some(LogicalType::Boolean),
    )
}
fn binary(
    op: grust_unresolved_plan::BinaryOp,
    left: Expr,
    right: Expr,
    ty: Option<LogicalType>,
) -> Expr {
    let nullable = left.nullable || right.nullable;
    Expr {
        kind: Value::Binary {
            op,
            left: Box::new(left),
            right: Box::new(right),
        },
        ty,
        nullable,
    }
}
fn conjunction(values: Vec<Expr>) -> Option<Expr> {
    values.into_iter().reduce(|l, r| {
        binary(
            grust_unresolved_plan::BinaryOp::And,
            l,
            r,
            Some(LogicalType::Boolean),
        )
    })
}
fn join(
    left: Node,
    right: Node,
    kind: grust_unresolved_plan::JoinKind,
    condition: Option<Expr>,
) -> Node {
    use grust_unresolved_plan::JoinKind;
    let mut fields = left.fields.clone();
    if !matches!(kind, JoinKind::Semi | JoinKind::Anti) {
        fields.extend(right.fields.clone());
    }
    if matches!(kind, JoinKind::Right | JoinKind::Full) {
        for f in &mut fields[..left.fields.len()] {
            f.nullable = true;
        }
    }
    if matches!(kind, JoinKind::Left | JoinKind::Full) {
        for f in &mut fields[left.fields.len()..] {
            f.nullable = true;
        }
    }
    Node {
        op: Op::Join {
            left: Box::new(left),
            right: Box::new(right),
            kind,
            condition,
        },
        fields,
    }
}

/// Replaceable implementation entry point for the executable query IR.
pub trait QueryResolution {
    fn resolve_query(
        &self,
        plan: &dyn UnresolvedPlan,
        context: &Context<'_>,
    ) -> Result<Plan, Vec<ResolveError>>;
}
impl QueryResolution for QueryResolver {
    fn resolve_query(
        &self,
        plan: &dyn UnresolvedPlan,
        context: &Context<'_>,
    ) -> Result<Plan, Vec<ResolveError>> {
        self.resolve(plan, context)
    }
}
