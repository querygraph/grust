//! Backend adapters own physical storage mapping and dialect semantics.
use grust_lpg::GroupId;
use grust_optimized_plan::{OptimizedPlan, Plan};
use grust_resolved_plan::Relation;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum EmitError {
    Unsupported { backend: String, operator: String },
    MissingStorage { graph: String, group: GroupId },
    UnsupportedFunction { provider: String, name: String },
}
impl std::fmt::Display for EmitError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}
impl std::error::Error for EmitError {}
pub trait BackendEmitter {
    type Output;
    fn emit(&self, plan: &dyn OptimizedPlan) -> Result<Self::Output, EmitError>;
}
pub trait StorageMapping {
    /// Components, not dotted strings. Identity/endpoints remain adapter metadata.
    fn table(&self, graph: &str, group: GroupId) -> Option<Vec<String>>;
}
/// A bounded Sail SQL example, not the production grust-sail translator.
/// Only a resolved Scan is supported; every other operator refuses explicitly.
pub struct SailScanSql<'a> {
    pub storage: &'a dyn StorageMapping,
}
impl BackendEmitter for SailScanSql<'_> {
    type Output = String;
    fn emit(&self, plan: &dyn OptimizedPlan) -> Result<String, EmitError> {
        let Plan { logical, .. } = plan.plan();
        match &logical.root {
            Relation::Scan {
                graph,
                group,
                fields,
            } if !fields.is_empty() => {
                let table = self
                    .storage
                    .table(graph, *group)
                    .filter(|parts| !parts.is_empty())
                    .ok_or_else(|| EmitError::MissingStorage {
                        graph: graph.clone(),
                        group: *group,
                    })?;
                let columns = fields
                    .iter()
                    .map(|f| quote(&f.name))
                    .collect::<Vec<_>>()
                    .join(", ");
                Ok(format!(
                    "SELECT {columns} FROM {}",
                    table
                        .iter()
                        .map(|part| quote(part))
                        .collect::<Vec<_>>()
                        .join(".")
                ))
            }
            other => Err(EmitError::Unsupported {
                backend: "sail-sql".into(),
                operator: match other {
                    Relation::Unit => "Unit",
                    Relation::Scan { .. } => "zero-column Scan",
                    Relation::Match { .. } => "Match",
                    Relation::Filter { .. } => "Filter",
                    Relation::Project { .. } => "Project",
                    Relation::GraphOperator { .. } => "GraphOperator",
                }
                .into(),
            }),
        }
    }
}
fn quote(value: &str) -> String {
    format!("`{}`", value.replace('`', "``"))
}
#[cfg(test)]
mod tests;
