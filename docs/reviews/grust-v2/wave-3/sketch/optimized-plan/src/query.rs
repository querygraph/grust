//! Actual optimized relational plan, independent of any optimizer.
/// Physical choices and diagnostic trace accompany the actual rewritten plan.
#[derive(Clone, Debug, PartialEq)]
pub struct Plan {
    pub logical: grust_resolved_plan::query::Plan,
    pub trace: Vec<String>,
    pub estimated_cost: Option<f64>,
    pub statistics_revision: Option<String>,
}
