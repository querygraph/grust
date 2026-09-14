//! End-to-end explicit Cypher execution on one captured Arrow graph.
use super::{GraphSnapshot, PlanKind, QueryPlan, UnsupportedScan, collect_result};
use datafusion::{
    common::{DataFusionError, Result},
    execution::context::SessionContext,
};
use grust_cypher::{CypherParameters, CypherResultTable};

/// Cumulative limits on the returned portable table, not a complete read policy.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct OutputLimits {
    pub max_rows: usize,
    pub max_serialized_bytes: usize,
}

/// A completed typed execution or an unsupported query that never executed.
/// Errors are returned separately and are never converted into fallback advice.
pub enum CypherExecution {
    Completed {
        kind: PlanKind,
        table: CypherResultTable,
    },
    Unsupported {
        kind: PlanKind,
        reason: UnsupportedScan,
    },
}

impl GraphSnapshot {
    /// Parse, select a typed compiler and execute Cypher on this snapshot, with
    /// cumulative portable output limits. No SQL text or intermediate graph is
    /// generated. Unsupported syntax shapes return without execution; parse,
    /// semantic, planning, execution and output-limit errors propagate directly.
    ///
    /// This explicitly chooses DataFusion. Callers still own query/parameter/input
    /// admission, candidate-work/intermediate-memory policy and deadlines. The
    /// runtime controls its tracked working memory separately. Ordinary Grust
    /// entrypoints do not yet perform automatic cost-based routing to this API.
    pub async fn execute(
        &self,
        query_text: &str,
        context: &SessionContext,
        parameters: &CypherParameters,
        output: OutputLimits,
    ) -> Result<CypherExecution> {
        let query = grust_cypher::parser::parse_query(query_text)
            .map_err(|error| DataFusionError::Plan(error.into_grust(query_text).to_string()))?;
        match self.plan(&query, context, parameters)? {
            QueryPlan::Supported { kind, frame } => Ok(CypherExecution::Completed {
                kind,
                table: collect_result(frame, output.max_rows, output.max_serialized_bytes).await?,
            }),
            QueryPlan::Unsupported { kind, reason } => {
                Ok(CypherExecution::Unsupported { kind, reason })
            }
        }
    }
}
