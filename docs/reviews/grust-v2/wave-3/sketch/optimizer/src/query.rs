//! Costed, bounded dynamic programming over pure inner-join regions.
use crate::Statistics;
mod estimates;
pub use estimates::references;
use estimates::{estimate, origins, pure, pure_node, selectivity};
use grust_optimized_plan::query::Plan as Optimized;
use grust_resolved_plan::query::{Expr, Node, Op, Plan, Value};
use grust_resolved_plan::Slot;
use grust_unresolved_plan::{BinaryOp, JoinKind};
use std::collections::{BTreeMap, BTreeSet};
pub trait JoinCostModel {
    fn scan(&self, rows: f64) -> f64;
    /// Additional join work; caller includes both child costs separately.
    fn join(&self, left_rows: f64, right_rows: f64, output_rows: f64) -> f64;
}
pub struct HashJoinCost;
impl JoinCostModel for HashJoinCost {
    fn scan(&self, rows: f64) -> f64 {
        rows
    }
    fn join(&self, left: f64, right: f64, output: f64) -> f64 {
        left + 2.0 * right + output
    }
}
pub struct JoinOptimizer<'a> {
    pub statistics: Option<&'a dyn Statistics>,
    pub cost: &'a dyn JoinCostModel,
    pub max_relations: usize,
}
impl JoinOptimizer<'_> {
    pub fn optimize(&self, plan: Plan) -> Optimized {
        let mut trace = Vec::new();
        let Some(stats) = self.statistics else {
            return Optimized {
                logical: plan,
                trace: vec!["unchanged: no statistics".into()],
                estimated_cost: None,
                statistics_revision: None,
            };
        };
        let root = self.rewrite(plan.root, stats, &mut trace);
        let estimate = estimate(&root, stats, self.cost);
        Optimized {
            logical: Plan { root },
            trace,
            estimated_cost: estimate.map(|e| e.cost),
            statistics_revision: stats.revision().map(str::to_string),
        }
    }
    fn rewrite(&self, mut node: Node, stats: &dyn Statistics, trace: &mut Vec<String>) -> Node {
        // Transform maximal regions first; boundaries are never flattened.
        if matches!(
            node.op,
            Op::Join {
                kind: JoinKind::Inner,
                ..
            } | Op::Filter { .. }
        ) {
            if let Some(reordered) = self.region(&node, stats, trace) {
                return reordered;
            }
        }
        match &mut node.op {
            Op::Filter { input, .. }
            | Op::Project { input, .. }
            | Op::Aggregate { input, .. }
            | Op::Unwind { input, .. }
            | Op::Sort { input, .. }
            | Op::PathSelect { input, .. }
            | Op::Slice { input, .. } => **input = self.rewrite(*input.clone(), stats, trace),
            Op::Join { left, right, .. } => {
                **left = self.rewrite(*left.clone(), stats, trace);
                **right = self.rewrite(*right.clone(), stats, trace);
            }
            Op::Traverse {
                seed, adjacency, ..
            } => {
                **seed = self.rewrite(*seed.clone(), stats, trace);
                **adjacency = self.rewrite(*adjacency.clone(), stats, trace);
            }
            Op::Union { inputs, .. } => {
                for input in inputs {
                    *input = self.rewrite(input.clone(), stats, trace);
                }
            }
            _ => {}
        }
        node
    }
    fn region(&self, node: &Node, stats: &dyn Statistics, trace: &mut Vec<String>) -> Option<Node> {
        let mut leaves = Vec::new();
        let mut predicates = Vec::new();
        flatten(node, &mut leaves, &mut predicates);
        if leaves.len() < 2 {
            return None;
        }
        if leaves.len() > self.max_relations.min(10)
            || leaves.iter().any(|n| !pure_node(n))
            || predicates.iter().any(|e| !pure(e))
        {
            trace.push("unchanged inner region: relation cap or non-immutable expression".into());
            return None;
        }
        let slots = leaves
            .iter()
            .map(|n| n.fields.iter().map(|f| f.slot).collect::<BTreeSet<_>>())
            .collect::<Vec<_>>();
        let refs = predicates.iter().map(references).collect::<Vec<_>>();
        let mut dp = BTreeMap::<usize, Candidate>::new();
        for (i, leaf) in leaves.iter().enumerate() {
            let mut leaf = leaf.clone();
            let local = predicates
                .iter()
                .zip(&refs)
                .filter(|(_, r)| !r.is_empty() && r.is_subset(&slots[i]))
                .map(|(e, _)| e.clone())
                .collect::<Vec<_>>();
            if let Some(predicate) = conjoin(local) {
                leaf = Node {
                    fields: leaf.fields.clone(),
                    op: Op::Filter {
                        input: Box::new(leaf),
                        predicate,
                    },
                };
            }
            let Some(e) = estimate(&leaf, stats, self.cost) else {
                trace.push("unchanged inner region: unknown cardinality".into());
                return None;
            };
            dp.insert(
                1 << i,
                Candidate {
                    node: leaf,
                    rows: e.rows,
                    cost: e.cost,
                },
            );
        }
        let full = (1 << leaves.len()) - 1;
        let subset_slots = |mask: usize| -> BTreeSet<Slot> {
            slots
                .iter()
                .enumerate()
                .filter(|(i, _)| mask & (1 << i) != 0)
                .flat_map(|(_, s)| s.iter().copied())
                .collect()
        };
        for size in 2..=leaves.len() {
            for mask in 1usize..=full {
                if mask.count_ones() as usize != size {
                    continue;
                }
                let available = subset_slots(mask);
                let mut left = (mask - 1) & mask;
                while left > 0 {
                    let right = mask ^ left;
                    if right > 0 {
                        if let (Some(l), Some(r)) = (dp.get(&left), dp.get(&right)) {
                            let ls = subset_slots(left);
                            let rs = subset_slots(right);
                            let crossing = predicates
                                .iter()
                                .zip(&refs)
                                .filter(|(_, s)| {
                                    !s.is_empty()
                                        && s.is_subset(&available)
                                        && !s.is_subset(&ls)
                                        && !s.is_subset(&rs)
                                })
                                .map(|(e, _)| e.clone())
                                .collect::<Vec<_>>();
                            let condition = conjoin(crossing);
                            let mut fields = l.node.fields.clone();
                            fields.extend(r.node.fields.clone());
                            let candidate = Node {
                                fields,
                                op: Op::Join {
                                    left: Box::new(l.node.clone()),
                                    right: Box::new(r.node.clone()),
                                    kind: JoinKind::Inner,
                                    condition,
                                },
                            };
                            let selectivity = if let Op::Join {
                                condition: Some(e), ..
                            } = &candidate.op
                            {
                                selectivity(e, &origins(&candidate), stats)
                            } else {
                                1.0
                            };
                            let rows = (l.rows * r.rows * selectivity).max(0.0);
                            let cost = l.cost + r.cost + self.cost.join(l.rows, r.rows, rows);
                            if cost.is_finite()
                                && cost >= 0.0
                                && rows.is_finite()
                                && dp.get(&mask).is_none_or(|previous| cost < previous.cost)
                            {
                                dp.insert(
                                    mask,
                                    Candidate {
                                        node: candidate,
                                        rows,
                                        cost,
                                    },
                                );
                            }
                        }
                    }
                    left = (left - 1) & mask;
                }
            }
        }
        let mut result = dp.remove(&full)?;
        let constant = predicates
            .iter()
            .zip(refs)
            .filter(|(_, r)| r.is_empty())
            .map(|(e, _)| e.clone())
            .collect::<Vec<_>>();
        if let Some(predicate) = conjoin(constant) {
            result.node = Node {
                fields: result.node.fields.clone(),
                op: Op::Filter {
                    input: Box::new(result.node),
                    predicate,
                },
            };
        }
        let before = estimate(node, stats, self.cost).map(|e| e.cost);
        result.node.fields = node.fields.clone();
        if before.is_some_and(|b| result.cost >= b) {
            return None;
        }
        trace.push(format!("costed inner region: {} relations, before={before:?}, after={}, NDV equality estimates; absent selectivity uses 1",leaves.len(),result.cost));
        Some(result.node)
    }
}
#[derive(Clone)]
struct Candidate {
    node: Node,
    rows: f64,
    cost: f64,
}
fn flatten(node: &Node, leaves: &mut Vec<Node>, conditions: &mut Vec<Expr>) {
    match &node.op {
        Op::Join {
            left,
            right,
            kind: JoinKind::Inner,
            condition,
        } => {
            flatten(left, leaves, conditions);
            flatten(right, leaves, conditions);
            if let Some(e) = condition {
                split(e, conditions);
            }
        }
        Op::Filter { input, predicate }
            if matches!(
                input.op,
                Op::Join {
                    kind: JoinKind::Inner,
                    ..
                } | Op::Filter { .. }
            ) =>
        {
            flatten(input, leaves, conditions);
            split(predicate, conditions);
        }
        _ => leaves.push(node.clone()),
    }
}
fn split(e: &Expr, out: &mut Vec<Expr>) {
    if let Value::Binary {
        op: BinaryOp::And,
        left,
        right,
    } = &e.kind
    {
        split(left, out);
        split(right, out);
    } else {
        out.push(e.clone());
    }
}
fn conjoin(values: Vec<Expr>) -> Option<Expr> {
    values.into_iter().reduce(|left, right| Expr {
        nullable: left.nullable || right.nullable,
        ty: Some(grust_lpg::LogicalType::Boolean),
        kind: Value::Binary {
            op: BinaryOp::And,
            left: Box::new(left),
            right: Box::new(right),
        },
    })
}
/// Explain names the actual rewritten operators, groups and slots, followed by costs.
pub fn explain(plan: &Optimized) -> String {
    format!(
        "statistics={:?} estimated_cost={:?}\n{:#?}\n{}",
        plan.statistics_revision,
        plan.estimated_cost,
        plan.logical.root,
        plan.trace.join("\n")
    )
}
#[cfg(test)]
mod tests;

pub trait QueryOptimization {
    fn optimize_query(&self, plan: Plan) -> Optimized;
}
impl QueryOptimization for JoinOptimizer<'_> {
    fn optimize_query(&self, plan: Plan) -> Optimized {
        self.optimize(plan)
    }
}
