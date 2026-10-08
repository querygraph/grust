//! Backend-neutral unresolved plans. No parsing, catalog resolution or execution.
pub mod expr;
pub mod pattern;
pub mod relation;
pub use expr::{BinaryOp, Expr, FunctionCall, Literal, UnaryOp};
pub use pattern::{
    Binding, EdgePattern, Hops, LabelExpr, PathMode, PathPattern, PathSelector, PatternDirection,
    VertexPattern,
};
pub use relation::{GraphRef, JoinKind, NamedExpr, Plan, Relation, SortKey};

/// An implementation can expose the plan it owns without choosing a resolver.
pub trait UnresolvedPlan {
    fn relation(&self) -> &Relation;
}
impl UnresolvedPlan for Plan {
    fn relation(&self) -> &Relation {
        &self.root
    }
}
#[cfg(test)]
mod tests;
