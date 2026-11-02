//! Admission of a resolved, bound plan to the stateless bounded subset
//! (BOUNDED-PLAN-ADMISSION-DESIGN §4 as narrowed in §10 after CF-0136).
//!
//! The visitor classifies every operator of the resolved `LogicalPlan` and
//! returns evidence, not only a verdict: which operators were admitted or
//! rejected and why, which bound sources and static sides were scanned,
//! whether every scan was bound, and whether the plan is replayable in
//! content. One join rule applies everywhere, including through
//! projections, aliases, unions, nested joins and subquery expressions:
//! exactly one range-bearing side and one proven static side.

use std::collections::BTreeSet;

use datafusion::common::tree_node::{TreeNode, TreeNodeRecursion};
use datafusion::logical_expr::{Expr, LogicalPlan};
use serde::{Deserialize, Serialize};

use super::binding::ReadSet;
use crate::pipelines::graph::Name;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Decision {
    Admit,
    Reject,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct OperatorEvidence {
    pub operator: String,
    pub decision: Decision,
    pub reason: String,
}

/// Serialisable admission evidence, recorded next to the intent.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct AdmissionEvidence {
    pub admitted: bool,
    pub operators: Vec<OperatorEvidence>,
    /// Bound streaming sources the plan scans.
    pub sources_read: BTreeSet<Name>,
    /// Local outputs and static bindings the plan scans.
    pub static_read: BTreeSet<Name>,
    /// Scans that match no binding, rendered as the resolver named them.
    pub unbound_scans: Vec<String>,
    /// `false` once a volatile expression was met: the same plan can yield
    /// different rows on re-evaluation, so the batch is non-replayable in
    /// content and must be materialised once.
    pub replayable: bool,
}

/// What a subtree carries, for the join rule.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct Side {
    range_bearing: bool,
}

/// Classifies `plan` against the reads the binding step accepted.
pub fn admit(plan: &LogicalPlan, reads: &ReadSet) -> AdmissionEvidence {
    let mut visitor = Visitor {
        reads,
        evidence: AdmissionEvidence {
            admitted: true,
            replayable: true,
            ..Default::default()
        },
    };
    visitor.visit(plan);
    visitor.evidence
}

struct Visitor<'a> {
    reads: &'a ReadSet,
    evidence: AdmissionEvidence,
}

impl Visitor<'_> {
    fn record(&mut self, operator: &str, decision: Decision, reason: impl Into<String>) {
        if decision == Decision::Reject {
            self.evidence.admitted = false;
        }
        self.evidence.operators.push(OperatorEvidence {
            operator: operator.to_string(),
            decision,
            reason: reason.into(),
        });
    }

    fn admit(&mut self, operator: &str, reason: &str) {
        self.record(operator, Decision::Admit, reason);
    }

    fn reject(&mut self, operator: &str, reason: &str) {
        self.record(operator, Decision::Reject, reason);
    }

    /// Volatile expressions make the batch non-replayable; subquery
    /// expressions are visited as plan children and join the join rule.
    fn expressions(&mut self, operator: &str, plan: &LogicalPlan) -> Side {
        let mut side = Side::default();
        for expr in plan.expressions() {
            if expr.is_volatile() {
                self.evidence.replayable = false;
                self.record(
                    operator,
                    Decision::Admit,
                    "volatile expression: evaluated once, not replayable in content",
                );
            }
            let mut subqueries = vec![];
            let _ = expr.apply(|node| {
                match node {
                    Expr::ScalarSubquery(subquery) => subqueries.push(subquery.subquery.clone()),
                    Expr::InSubquery(in_subquery) => {
                        subqueries.push(in_subquery.subquery.subquery.clone())
                    }
                    Expr::Exists(exists) => subqueries.push(exists.subquery.subquery.clone()),
                    _ => {}
                }
                Ok(TreeNodeRecursion::Continue)
            });
            for subquery in subqueries {
                let inner = self.visit(&subquery);
                side.range_bearing |= inner.range_bearing;
            }
        }
        side
    }

    /// The join rule over any set of sides: more than one range-bearing side
    /// needs cross-batch state and is rejected.
    fn combine(&mut self, operator: &str, sides: &[Side]) -> Side {
        let range_bearing = sides.iter().filter(|side| side.range_bearing).count();
        match range_bearing {
            0 => {
                self.admit(operator, "static sides only");
                Side {
                    range_bearing: false,
                }
            }
            1 => {
                self.admit(operator, "one range-bearing side and static sides");
                Side {
                    range_bearing: true,
                }
            }
            _ => {
                self.reject(
                    operator,
                    "more than one range-bearing side needs cross-batch state",
                );
                Side {
                    range_bearing: true,
                }
            }
        }
    }

    fn visit(&mut self, plan: &LogicalPlan) -> Side {
        match plan {
            LogicalPlan::TableScan(scan) => {
                let name: Name = [
                    scan.table_name.catalog(),
                    scan.table_name.schema(),
                    Some(scan.table_name.table()),
                ]
                .into_iter()
                .flatten()
                .map(str::to_string)
                .collect();
                if self.reads.streaming.contains(&name) {
                    self.evidence.sources_read.insert(name);
                    self.admit("TableScan", "bound range of a recorded source");
                    Side {
                        range_bearing: true,
                    }
                } else if self.reads.local.contains(&name) || self.reads.statics.contains(&name) {
                    self.evidence.static_read.insert(name);
                    self.admit("TableScan", "local output or pinned static binding");
                    Side::default()
                } else {
                    self.evidence
                        .unbound_scans
                        .push(scan.table_name.to_string());
                    self.reject("TableScan", "scan outside the binding set");
                    Side::default()
                }
            }
            // A schema-only placeholder of a local output during analysis.
            LogicalPlan::EmptyRelation(_) => {
                self.admit("EmptyRelation", "schema-only relation");
                Side::default()
            }
            LogicalPlan::Values(_) => {
                self.admit("Values", "literal rows");
                Side::default()
            }
            LogicalPlan::Projection(_)
            | LogicalPlan::Filter(_)
            | LogicalPlan::SubqueryAlias(_)
            | LogicalPlan::Repartition(_)
            | LogicalPlan::Unnest(_) => {
                let operator = operator_name(plan);
                let mut sides = vec![self.expressions(operator, plan)];
                for input in plan.inputs() {
                    sides.push(self.visit(input));
                }
                // A subquery expression over a range-bearing input is a join.
                self.combine(operator, &sides)
            }
            LogicalPlan::Union(union) => {
                let sides: Vec<Side> = union.inputs.iter().map(|input| self.visit(input)).collect();
                let range_bearing = sides.iter().any(|side| side.range_bearing);
                self.admit("Union", "row-local union of its inputs");
                Side { range_bearing }
            }
            LogicalPlan::Join(join) => {
                let expression_side = self.expressions("Join", plan);
                let left = self.visit(&join.left);
                let right = self.visit(&join.right);
                self.combine("Join", &[expression_side, left, right])
            }
            LogicalPlan::Subquery(subquery) => self.visit(&subquery.subquery),
            LogicalPlan::Aggregate(_)
            | LogicalPlan::Window(_)
            | LogicalPlan::Sort(_)
            | LogicalPlan::Limit(_)
            | LogicalPlan::Distinct(_)
            | LogicalPlan::RecursiveQuery(_) => {
                let operator = operator_name(plan);
                self.reject(
                    operator,
                    "needs durable cross-batch state under AvailableNow semantics",
                );
                let mut side = Side::default();
                for input in plan.inputs() {
                    side.range_bearing |= self.visit(input).range_bearing;
                }
                side
            }
            LogicalPlan::Extension(extension) => {
                self.reject(
                    &format!("Extension({})", extension.node.name()),
                    "extension node without qualified semantics",
                );
                let mut side = Side::default();
                for input in plan.inputs() {
                    side.range_bearing |= self.visit(input).range_bearing;
                }
                side
            }
            LogicalPlan::Statement(_)
            | LogicalPlan::Explain(_)
            | LogicalPlan::Analyze(_)
            | LogicalPlan::Dml(_)
            | LogicalPlan::Ddl(_)
            | LogicalPlan::Copy(_)
            | LogicalPlan::DescribeTable(_) => {
                self.reject(operator_name(plan), "not a query over bound inputs");
                Side::default()
            }
        }
    }
}

fn operator_name(plan: &LogicalPlan) -> &'static str {
    match plan {
        LogicalPlan::Projection(_) => "Projection",
        LogicalPlan::Filter(_) => "Filter",
        LogicalPlan::Window(_) => "Window",
        LogicalPlan::Aggregate(_) => "Aggregate",
        LogicalPlan::Sort(_) => "Sort",
        LogicalPlan::Join(_) => "Join",
        LogicalPlan::Repartition(_) => "Repartition",
        LogicalPlan::Union(_) => "Union",
        LogicalPlan::TableScan(_) => "TableScan",
        LogicalPlan::EmptyRelation(_) => "EmptyRelation",
        LogicalPlan::Subquery(_) => "Subquery",
        LogicalPlan::SubqueryAlias(_) => "SubqueryAlias",
        LogicalPlan::Limit(_) => "Limit",
        LogicalPlan::Statement(_) => "Statement",
        LogicalPlan::Values(_) => "Values",
        LogicalPlan::Explain(_) => "Explain",
        LogicalPlan::Analyze(_) => "Analyze",
        LogicalPlan::Extension(_) => "Extension",
        LogicalPlan::Distinct(_) => "Distinct",
        LogicalPlan::Dml(_) => "Dml",
        LogicalPlan::Ddl(_) => "Ddl",
        LogicalPlan::Copy(_) => "Copy",
        LogicalPlan::DescribeTable(_) => "DescribeTable",
        LogicalPlan::Unnest(_) => "Unnest",
        LogicalPlan::RecursiveQuery(_) => "RecursiveQuery",
    }
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use datafusion::arrow::datatypes::{DataType, Field, Schema};
    use datafusion::common::{Result as DFResult, TableReference};
    use datafusion::datasource::{MemTable, provider_as_source};
    use datafusion::logical_expr::{
        ColumnarValue, Expr, JoinType, LogicalPlanBuilder, ScalarFunctionArgs, ScalarUDF,
        ScalarUDFImpl, Signature, Volatility, col, lit,
    };

    use super::*;

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    fn name(parts: &[&str]) -> Name {
        parts.iter().map(|part| part.to_string()).collect()
    }

    fn scan(parts: &[&str]) -> DFResult<LogicalPlanBuilder> {
        let schema = Arc::new(Schema::new(vec![
            Field::new("id", DataType::Int64, false),
            Field::new("v", DataType::Int64, true),
        ]));
        let provider = Arc::new(MemTable::try_new(schema, vec![vec![]])?);
        let reference = TableReference::full(parts[0], parts[1], parts[2]);
        LogicalPlanBuilder::scan(reference, provider_as_source(provider), None)
    }

    fn reads() -> ReadSet {
        ReadSet {
            streaming: BTreeSet::from([name(&["c", "d", "clicks"]), name(&["c", "d", "views"])]),
            local: BTreeSet::from([name(&["c", "d", "events"])]),
            statics: BTreeSet::from([name(&["c", "d", "dim"])]),
        }
    }

    #[derive(Debug, PartialEq, Eq, Hash)]
    struct Volatile {
        signature: Signature,
    }

    impl ScalarUDFImpl for Volatile {
        fn name(&self) -> &str {
            "volatile_test"
        }
        fn signature(&self) -> &Signature {
            &self.signature
        }
        fn return_type(&self, _: &[DataType]) -> DFResult<DataType> {
            Ok(DataType::Int64)
        }
        fn invoke_with_args(&self, _: ScalarFunctionArgs) -> DFResult<ColumnarValue> {
            Ok(ColumnarValue::Scalar(
                datafusion::common::ScalarValue::Int64(Some(4)),
            ))
        }
    }

    fn volatile() -> Expr {
        let udf = ScalarUDF::from(Volatile {
            signature: Signature::nullary(Volatility::Volatile),
        });
        udf.call(vec![])
    }

    #[test]
    fn a_filtered_projection_over_one_bound_range_is_admitted_and_replayable() -> TestResult {
        let plan = scan(&["c", "d", "clicks"])?
            .filter(col("v").gt(lit(1)))?
            .project(vec![col("id")])?
            .build()?;
        let evidence = admit(&plan, &reads());
        assert!(evidence.admitted, "{evidence:?}");
        assert!(evidence.replayable);
        assert_eq!(
            evidence.sources_read,
            BTreeSet::from([name(&["c", "d", "clicks"])])
        );
        assert!(evidence.unbound_scans.is_empty());
        assert!(
            evidence
                .operators
                .iter()
                .all(|op| op.decision == Decision::Admit)
        );
        Ok(())
    }

    #[test]
    fn a_join_needs_exactly_one_range_bearing_side() -> TestResult {
        let stream_static = scan(&["c", "d", "clicks"])?
            .join(
                scan(&["c", "d", "dim"])?.build()?,
                JoinType::Inner,
                (vec!["id"], vec!["id"]),
                None,
            )?
            .build()?;
        let evidence = admit(&stream_static, &reads());
        assert!(evidence.admitted, "{evidence:?}");
        assert_eq!(
            evidence.static_read,
            BTreeSet::from([name(&["c", "d", "dim"])])
        );

        let stream_stream = scan(&["c", "d", "clicks"])?
            .join(
                scan(&["c", "d", "views"])?.build()?,
                JoinType::Inner,
                (vec!["id"], vec!["id"]),
                None,
            )?
            .build()?;
        let evidence = admit(&stream_stream, &reads());
        assert!(!evidence.admitted);
        assert!(evidence.operators.iter().any(|op| op.operator == "Join"
            && op.decision == Decision::Reject
            && op.reason.contains("cross-batch")));

        // Through an alias and a projection, nested under another join with a
        // static side: still two range-bearing sides.
        let nested = scan(&["c", "d", "clicks"])?
            .alias("a")?
            .project(vec![col("a.id")])?
            .join(
                scan(&["c", "d", "views"])?.alias("b")?.build()?,
                JoinType::Inner,
                (vec!["a.id"], vec!["b.id"]),
                None,
            )?
            .join(
                scan(&["c", "d", "events"])?.build()?,
                JoinType::Inner,
                (vec!["a.id"], vec!["id"]),
                None,
            )?
            .build()?;
        assert!(!admit(&nested, &reads()).admitted);
        Ok(())
    }

    #[test]
    fn stateful_operators_and_unbound_scans_are_rejected_with_evidence() -> TestResult {
        let aggregate = scan(&["c", "d", "clicks"])?
            .aggregate(vec![col("id")], Vec::<Expr>::new())?
            .build()?;
        let evidence = admit(&aggregate, &reads());
        assert!(!evidence.admitted);
        assert!(
            evidence
                .operators
                .iter()
                .any(|op| op.operator == "Aggregate" && op.decision == Decision::Reject)
        );

        let limited = scan(&["c", "d", "clicks"])?.limit(0, Some(5))?.build()?;
        assert!(!admit(&limited, &reads()).admitted);
        let sorted = scan(&["c", "d", "clicks"])?
            .sort(vec![col("id").sort(true, true)])?
            .build()?;
        assert!(!admit(&sorted, &reads()).admitted);
        let distinct = scan(&["c", "d", "clicks"])?.distinct()?.build()?;
        assert!(!admit(&distinct, &reads()).admitted);

        let unbound = scan(&["c", "d", "elsewhere"])?.build()?;
        let evidence = admit(&unbound, &reads());
        assert!(!evidence.admitted);
        assert_eq!(evidence.unbound_scans, vec!["c.d.elsewhere".to_string()]);
        Ok(())
    }

    #[test]
    fn a_volatile_expression_is_admitted_but_not_replayable() -> TestResult {
        let plan = scan(&["c", "d", "clicks"])?
            .project(vec![col("id"), volatile().alias("r")])?
            .build()?;
        let evidence = admit(&plan, &reads());
        assert!(evidence.admitted, "{evidence:?}");
        assert!(!evidence.replayable);
        assert!(
            evidence
                .operators
                .iter()
                .any(|op| op.reason.contains("volatile"))
        );
        Ok(())
    }

    #[test]
    fn a_union_of_ranges_is_row_local_and_a_static_subquery_is_a_join_side() -> TestResult {
        let union = scan(&["c", "d", "clicks"])?
            .union(scan(&["c", "d", "views"])?.build()?)?
            .build()?;
        let evidence = admit(&union, &reads());
        assert!(evidence.admitted, "{evidence:?}");
        assert_eq!(evidence.sources_read.len(), 2);

        // EXISTS over a range-bearing subquery under a range-bearing outer
        // input is two range-bearing sides.
        let inner = scan(&["c", "d", "views"])?.build()?;
        let exists = scan(&["c", "d", "clicks"])?
            .filter(datafusion::logical_expr::exists(Arc::new(inner)))?
            .build()?;
        let evidence = admit(&exists, &reads());
        assert!(!evidence.admitted, "{evidence:?}");

        let static_inner = scan(&["c", "d", "dim"])?.build()?;
        let exists_static = scan(&["c", "d", "clicks"])?
            .filter(datafusion::logical_expr::exists(Arc::new(static_inner)))?
            .build()?;
        assert!(admit(&exists_static, &reads()).admitted);
        Ok(())
    }

    #[test]
    fn evidence_round_trips_through_serde() -> TestResult {
        let plan = scan(&["c", "d", "clicks"])?.build()?;
        let evidence = admit(&plan, &reads());
        let json = serde_json::to_string(&evidence)?;
        let decoded: AdmissionEvidence = serde_json::from_str(&json)?;
        assert_eq!(decoded, evidence);
        Ok(())
    }
}
