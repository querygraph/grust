//! Providers lower extensions to typed, backend-neutral relational operators.
//! Their lowering is resolved again; no provider-created slot or SQL is trusted.
use crate::ResolveError;
use grust_functions::FunctionName;
use grust_unresolved_plan::{Expr, Relation};
pub trait RelationProviders {
    fn lower(
        &self,
        name: &FunctionName,
        inputs: &[Relation],
        arguments: &[Expr],
    ) -> Result<Option<Relation>, ResolveError>;
}
pub struct NoProviders;
impl RelationProviders for NoProviders {
    fn lower(
        &self,
        _: &FunctionName,
        _: &[Relation],
        _: &[Expr],
    ) -> Result<Option<Relation>, ResolveError> {
        Ok(None)
    }
}
/// SQL admission is finite expansion, not an implicit bound on recursive queries.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PathCapability {
    BoundedSql,
    IterativeProviderRequired,
    UnsupportedShape,
}
pub fn path_capability(path: &grust_unresolved_plan::PathPattern) -> PathCapability {
    if path.edges.len() != 1 {
        return PathCapability::UnsupportedShape;
    }
    match path.edges[0].hops.max {
        Some(max) if max <= 8 => PathCapability::BoundedSql,
        _ => PathCapability::IterativeProviderRequired,
    }
}
