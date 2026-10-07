//! Replaceable catalog and resolution interfaces plus an exact-overload example.
pub mod paths;
use grust_functions::{
    ArgumentType, FunctionDescriptor, FunctionKind, FunctionName, FunctionRegistry,
};
use grust_lpg::{LogicalType, Schema};
use grust_resolved_plan::Plan;
use grust_unresolved_plan::{GraphRef, UnresolvedPlan};

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ResolveError {
    UnknownGraph(GraphRef),
    UnknownBinding(String),
    UnknownProperty(String),
    AmbiguousProperty(String),
    UnknownLabel(String),
    InfeasiblePattern,
    NoOverload(FunctionName),
    AmbiguousOverload(FunctionName),
    TypeMismatch {
        expected: Box<LogicalType>,
        actual: Box<LogicalType>,
    },
    Unsupported {
        operator: String,
        reason: String,
    },
}
impl std::fmt::Display for ResolveError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}
impl std::error::Error for ResolveError {}
pub trait Catalog {
    /// The returned canonical name survives resolution; GraphRef is not a storage path.
    fn graph(&self, graph: &GraphRef) -> Result<(&str, &Schema), ResolveError>;
}
pub trait ParameterTypes {
    fn parameter(&self, name: &str) -> Option<(LogicalType, bool)>;
}
pub struct Context<'a> {
    pub catalog: &'a dyn Catalog,
    pub functions: &'a dyn FunctionRegistry,
    pub parameters: &'a dyn ParameterTypes,
}
pub trait Resolver {
    /// All catalog/property/function failures are planning diagnostics, never data scans.
    fn resolve(
        &self,
        plan: &dyn UnresolvedPlan,
        context: &Context<'_>,
    ) -> Result<Plan, Vec<ResolveError>>;
}
/// Deliberately bounded overload binder: no implicit casts, generics or variadics.
/// A production resolver may replace this policy, but must record its chosen signature.
pub fn bind_exact(
    registry: &dyn FunctionRegistry,
    name: &FunctionName,
    kind: FunctionKind,
    arguments: &[LogicalType],
) -> Result<FunctionDescriptor, ResolveError> {
    let matches: Vec<_> = registry
        .lookup(name, kind)
        .into_iter()
        .filter(|f| {
            f.signature.variadic.is_none() && f.signature.arguments.len() == arguments.len()
        && f.signature.arguments.iter().zip(arguments).all(|(pattern, actual)| {
            matches!(pattern, ArgumentType::Exact(expected) if expected == actual)
        })
        })
        .collect();
    match matches.as_slice() {
        [only] => Ok((*only).clone()),
        [] => Err(ResolveError::NoOverload(name.clone())),
        _ => Err(ResolveError::AmbiguousOverload(name.clone())),
    }
}
#[cfg(test)]
mod tests;
