//! Optimized IR remains independent of the optimizer and backend adapters.
use grust_lpg::GroupId;
use grust_resolved_plan::Plan as Resolved;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Estimate<T> {
    Unknown,
    Known(T),
}
#[derive(Clone, Debug, PartialEq)]
pub struct Provenance {
    pub catalog_revision: String,
    pub statistics_revision: Option<String>,
}
#[derive(Clone, Debug, PartialEq)]
pub struct AccessChoice {
    pub group: GroupId,
    pub rows: Estimate<u64>,
}
#[derive(Clone, Debug, PartialEq)]
pub struct Rewrite {
    pub rule: String,
    pub reason: String,
}
/// An optimized plan owns its resolved semantics. Ordering choices never modify output slots.
#[derive(Clone, Debug, PartialEq)]
pub struct Plan {
    pub logical: Resolved,
    pub access_order: Vec<AccessChoice>,
    pub rewrites: Vec<Rewrite>,
    pub provenance: Provenance,
}
pub trait OptimizedPlan {
    fn plan(&self) -> &Plan;
}
impl OptimizedPlan for Plan {
    fn plan(&self) -> &Plan {
        self
    }
}

pub mod query;
