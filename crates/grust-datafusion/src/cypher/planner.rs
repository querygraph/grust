//! Common typed-plan selection over one validated immutable snapshot.
use super::{GraphSnapshot, NodeScanPlan, UnsupportedScan};
use datafusion::{common::Result, dataframe::DataFrame, execution::context::SessionContext};
use grust_cypher::{
    CypherParameters,
    ast::{Clause, Query},
};

/// The relational shape selected by the typed compiler, not a cost estimate.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PlanKind {
    NodeScan,
    RelationshipScan,
}

/// Explicit compilation outcome for ordinary parsed Cypher input.
/// Unsupported queries have not executed. Planning/execution errors are never
/// permission to retry on a different snapshot or through another executor.
pub enum QueryPlan {
    Supported {
        kind: PlanKind,
        frame: DataFrame,
    },
    Unsupported {
        kind: PlanKind,
        reason: UnsupportedScan,
    },
}

impl GraphSnapshot {
    /// Select and compile the supported node/relationship shape from a parsed
    /// query against this captured provider pair. Semantic analysis still rejects
    /// invalid queries before returning an unsupported outcome. No graph buffers
    /// are materialized, SQL generated, or queries executed by this method.
    ///
    /// This selects a typed compiler, not the lowest-cost executor. Applications
    /// must still enforce resource/authorization policy before executing a frame;
    /// ordinary Grust Cypher entrypoints do not yet route here automatically.
    pub fn plan(
        &self,
        query: &Query,
        context: &SessionContext,
        parameters: &CypherParameters,
    ) -> Result<QueryPlan> {
        let kind = if query.parts.iter().any(|part| part.query.clauses.iter().any(|clause| {
            matches!(clause, Clause::Match(matched) if matched.patterns.iter().any(|pattern| !pattern.segments.is_empty()))
        })) { PlanKind::RelationshipScan } else { PlanKind::NodeScan };
        let plan = match kind {
            PlanKind::NodeScan => super::plan_node_scan(query, self.nodes(context)?, parameters)?,
            PlanKind::RelationshipScan => {
                super::plan_relationship_scan(query, self, context, parameters)?
            }
        };
        Ok(match plan {
            NodeScanPlan::Supported(frame) => QueryPlan::Supported { kind, frame },
            NodeScanPlan::Unsupported(reason) => QueryPlan::Unsupported { kind, reason },
        })
    }
}
