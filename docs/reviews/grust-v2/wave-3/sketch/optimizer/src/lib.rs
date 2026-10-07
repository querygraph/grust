//! Optional optimizer/statistics contracts. No runtime or data access dependency.
use grust_lpg::GroupId;
use grust_optimized_plan::{AccessChoice, Estimate, Plan, Provenance};
use grust_resolved_plan::{Plan as Resolved, Relation};

pub trait Statistics {
    fn revision(&self) -> Option<&str>;
    fn rows(&self, graph: &str, group: GroupId) -> Estimate<u64>;
    fn distinct(&self, graph: &str, group: GroupId, property: &str) -> Estimate<u64>;
    fn degree(&self, graph: &str, group: GroupId) -> Estimate<DegreeSummary>;
}
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct DegreeSummary {
    pub mean: f64,
    pub maximum: u64,
}
pub trait CostModel {
    type Cost;
    fn compare(&self, left: &Self::Cost, right: &Self::Cost) -> std::cmp::Ordering;
    fn scan(&self, group: GroupId, rows: Estimate<u64>) -> Option<Self::Cost>;
}
pub trait Optimizer {
    type Error;
    fn optimize(
        &self,
        plan: Resolved,
        statistics: Option<&dyn Statistics>,
        provenance: Provenance,
    ) -> Result<Plan, Self::Error>;
}
/// Baseline always available: no join reordering or predicate movement.
pub fn preserve(plan: Resolved, provenance: Provenance) -> Plan {
    Plan {
        logical: plan,
        access_order: Vec::new(),
        rewrites: Vec::new(),
        provenance,
    }
}
/// Illustrative ranking of independent candidate scans only; not a join optimizer.
/// Stable unknown estimates follow known candidates; zero is a known empty scan.
pub fn rank_scans(graph: &str, groups: &[GroupId], stats: &dyn Statistics) -> Vec<AccessChoice> {
    let mut choices: Vec<_> = groups
        .iter()
        .map(|&group| AccessChoice {
            group,
            rows: stats.rows(graph, group),
        })
        .collect();
    choices.sort_by_key(|choice| match choice.rows {
        Estimate::Known(rows) => (false, rows),
        Estimate::Unknown => (true, 0),
    });
    choices
}
pub trait Explain {
    fn explain(&self) -> String;
}
impl Explain for Plan {
    fn explain(&self) -> String {
        let mut lines = vec![format!(
            "catalog={} statistics={:?}",
            self.provenance.catalog_revision, self.provenance.statistics_revision
        )];
        show(&self.logical.root, 0, &mut lines);
        for choice in &self.access_order {
            lines.push(format!(
                "candidate group={} rows={:?}",
                choice.group.0, choice.rows
            ));
        }
        for rewrite in &self.rewrites {
            lines.push(format!("rewrite {}: {}", rewrite.rule, rewrite.reason));
        }
        lines.join("\n")
    }
}
fn show(relation: &Relation, depth: usize, lines: &mut Vec<String>) {
    let indent = "  ".repeat(depth);
    match relation {
        Relation::Unit => lines.push(format!("{indent}Unit")),
        Relation::Scan {
            graph,
            group,
            fields,
        } => lines.push(format!(
            "{indent}Scan graph={graph:?} group={} fields={fields:?}",
            group.0
        )),
        Relation::Match {
            input,
            graph,
            alternatives,
            bindings,
            predicates,
            optional,
        } => {
            lines.push(format!("{indent}Match graph={graph:?} optional={optional} bindings={bindings:?} predicates={predicates:?}"));
            for path in alternatives {
                lines.push(format!(
                    "{indent}  LPG path vertices={:?} edges={:?}",
                    path.vertices, path.edges
                ));
            }
            show(input, depth + 1, lines);
        }
        Relation::Filter { input, predicate } => {
            lines.push(format!("{indent}Filter {predicate:?}"));
            show(input, depth + 1, lines);
        }
        Relation::Project {
            input,
            items,
            distinct,
        } => {
            lines.push(format!(
                "{indent}Project distinct={distinct} items={items:?}"
            ));
            show(input, depth + 1, lines);
        }
        Relation::GraphOperator {
            name,
            input,
            arguments,
        } => {
            lines.push(format!("{indent}GraphOperator {name:?} {arguments:?}"));
            show(input, depth + 1, lines);
        }
    }
}
#[cfg(test)]
mod tests;
