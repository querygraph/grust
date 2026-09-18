//! Automatic route selection for ordinary bounded Cypher reads.
//!
//! [`RoutedGraph`] captures one immutable graph as both a typed index and a
//! DataFusion snapshot, so the two routes can never observe different data.
//! Each read is admitted once through [`PreparedReadRequest`]; whichever route
//! runs keeps that admission, including the original absolute deadline.
//!
//! DataFusion runs only single-node scan plans whose every physical operator is
//! covered by candidate-work and intermediate-byte accounting. The read policy
//! maps onto one [`ExecutionContext`] exactly as the reference executor maps it:
//! `max_candidate_work` bounds scanned rows, `max_intermediate_bytes` bounds
//! cumulative bytes emitted by copying operators plus portable output copies,
//! and the deadline covers planning, execution and output consumption. Output
//! rows/bytes are checked incrementally and again by the shared request.
//! Relationship patterns stay on the reference executor: upstream hash joins
//! build candidate pairs before any hook could charge them.
use super::{GraphSnapshot, PlanKind, QueryPlan, SnapshotStatistics, UnsupportedScan};
use crate::DataFusionEngine;
use datafusion::{
    arrow::{datatypes::SchemaRef, record_batch::RecordBatch},
    common::{DataFusionError, Result as DataFusionResult, tree_node::TreeNodeRecursion},
    execution::{SendableRecordBatchStream, TaskContext, context::SessionContext},
    physical_expr::PhysicalExpr,
    physical_plan::{
        DisplayAs, DisplayFormatType, ExecutionPlan, PlanProperties, displayable, execute_stream,
        execution_plan::replace_children_if_necessary, stream::RecordBatchStreamAdapter,
    },
};
use futures::StreamExt;
use grust_arrow::{ArrowGraph, ArrowGraphTables};
use grust_core::{Graph, TypedGraphIndex, prelude::Result};
use grust_cypher::{
    CypherParameters, CypherResultTable, PreparedReadRequest, ReadQueryPolicy, gql_execution,
};
use grust_procedures::{ExecutionContext, ExecutionLimits, ProcedureError};
use std::{fmt, sync::Arc};

/// Smallest captured node table for which automatic selection prefers the
/// DataFusion route. The `cypher_route` profile (warm representations, three
/// scan shapes) found the typed index faster for a count at 1,000 nodes and
/// DataFusion faster for every shape from 3,000 nodes up. Callers with other
/// workloads or hosts can override it with [`RoutedGraph::with_min_datafusion_nodes`].
pub const DEFAULT_MIN_DATAFUSION_NODES: usize = 3_000;

/// Physical operators whose outputs the accounting wrapper can charge. Any other
/// operator after optimization, including every join, declines the route.
const COVERED_OPERATORS: &[&str] = &[
    "DataSourceExec",
    "FilterExec",
    "ProjectionExec",
    "AggregateExec",
    "SortExec",
    "SortPreservingMergeExec",
    "CoalescePartitionsExec",
    "CoalesceBatchesExec",
    "RepartitionExec",
    "GlobalLimitExec",
    "LocalLimitExec",
    "CooperativeExec",
    "EmptyExec",
    "PlaceholderRowExec",
];

/// Covered operators that emit their input arrays unchanged or as zero-copy
/// slices. Their outputs were already charged where they were produced.
const PASS_THROUGH_OPERATORS: &[&str] = &[
    "CoalescePartitionsExec",
    "GlobalLimitExec",
    "LocalLimitExec",
    "CooperativeExec",
];

/// An executor for one bounded read.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ReadRoute {
    /// The typed-index reference executor, which supports the whole read surface.
    Reference,
    /// The typed DataFusion 55 plan over the captured Arrow snapshot.
    DataFusion,
}

/// How a routed read chooses its executor.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RouteMode {
    /// Select DataFusion only for admitted plans above the size threshold.
    Automatic,
    /// Require one route, for qualification. Forcing DataFusion fails, without
    /// executing anything, when its plan cannot be admitted under the policy.
    Force(ReadRoute),
}

/// Why the DataFusion route was not chosen. Every reason is determined before
/// execution starts; errors after that point propagate and are never rerouted.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum RouteDecline {
    /// The caller forced the reference route.
    ReferenceForced,
    /// The graph could not be captured as native Arrow tables.
    CaptureUnavailable(String),
    /// The typed compiler does not support this query shape.
    Unsupported {
        kind: PlanKind,
        reason: UnsupportedScan,
    },
    /// Relationship patterns need join candidate accounting that upstream
    /// hash joins do not expose.
    RelationshipJoin,
    /// The captured node table is smaller than the automatic threshold.
    BelowThreshold { node_rows: usize, threshold: usize },
    /// Scanning every node would exceed the policy's candidate-work limit.
    CandidateWork { required: usize, limit: usize },
    /// The optimized physical plan contains an operator without accounting.
    UncoveredOperator(String),
}

impl fmt::Display for RouteDecline {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ReferenceForced => write!(f, "reference route forced"),
            Self::CaptureUnavailable(reason) => write!(f, "Arrow capture unavailable: {reason}"),
            Self::Unsupported { kind, reason } => {
                write!(f, "unsupported {kind:?} shape ({reason:?})")
            }
            Self::RelationshipJoin => {
                write!(f, "relationship joins lack candidate-work accounting")
            }
            Self::BelowThreshold {
                node_rows,
                threshold,
            } => write!(
                f,
                "{node_rows} nodes is below the {threshold}-node threshold"
            ),
            Self::CandidateWork { required, limit } => write!(
                f,
                "scanning {required} nodes exceeds the {limit} candidate-work limit"
            ),
            Self::UncoveredOperator(name) => write!(f, "operator {name} has no accounting"),
        }
    }
}

/// The selected route and the evidence behind it, reported without executing.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RouteExplain {
    pub chosen: ReadRoute,
    /// Why DataFusion was not chosen; `None` when it was.
    pub datafusion_declined: Option<RouteDecline>,
    /// Exact capture counts, including the added ordinal payload. Capture
    /// happened once when the [`RoutedGraph`] was built, not per query.
    pub capture: Option<SnapshotStatistics>,
    /// Optimized physical plan, when the typed compiler produced one.
    pub physical_plan: Option<String>,
}

/// A completed routed read.
#[derive(Clone, Debug, PartialEq)]
pub struct RoutedReadResult {
    pub table: CypherResultTable,
    pub explain: RouteExplain,
}

/// One immutable graph captured for both executors.
pub struct RoutedGraph {
    index: TypedGraphIndex,
    snapshot: std::result::Result<GraphSnapshot, String>,
    context: SessionContext,
    min_datafusion_nodes: usize,
}

impl RoutedGraph {
    /// Build the typed index and the Arrow snapshot from the same graph. A graph
    /// whose values have no native Arrow column still gets the reference route;
    /// the capture failure is reported by every explain.
    pub fn capture(engine: &DataFusionEngine, graph: Arc<Graph>) -> Result<Self> {
        let snapshot = ArrowGraph::from_graph(&graph)
            .and_then(|arrow| {
                let (nodes, edges) = arrow.into_tables();
                ArrowGraphTables::try_new(nodes, edges)
            })
            .map_err(|error| error.to_string())
            .and_then(|tables| {
                GraphSnapshot::try_new(engine, tables).map_err(|error| error.to_string())
            });
        Ok(Self {
            index: TypedGraphIndex::new(graph)?,
            snapshot,
            context: engine.context().clone(),
            min_datafusion_nodes: DEFAULT_MIN_DATAFUSION_NODES,
        })
    }

    /// Replace the automatic size threshold. Zero considers every admitted plan.
    pub fn with_min_datafusion_nodes(mut self, nodes: usize) -> Self {
        self.min_datafusion_nodes = nodes;
        self
    }

    /// The reference executor's typed index.
    pub fn index(&self) -> &TypedGraphIndex {
        &self.index
    }

    /// The captured DataFusion snapshot, if capture succeeded.
    pub fn snapshot(&self) -> Option<&GraphSnapshot> {
        self.snapshot.as_ref().ok()
    }

    /// Admit a bounded read and report the route it would take, without executing.
    pub async fn explain(
        &self,
        query_text: &str,
        parameters: &CypherParameters,
        policy: &ReadQueryPolicy,
        mode: RouteMode,
    ) -> Result<RouteExplain> {
        let request = PreparedReadRequest::new(query_text, parameters, policy)?;
        request.check_index(&self.index)?;
        Ok(self.select(&request, mode).await?.1)
    }

    /// Run a bounded read on the selected route under the complete read policy.
    /// The reference route is synchronous and runs on the calling task.
    pub async fn run_bounded_read_query(
        &self,
        query_text: &str,
        parameters: &CypherParameters,
        policy: &ReadQueryPolicy,
        mode: RouteMode,
    ) -> Result<RoutedReadResult> {
        let request = PreparedReadRequest::new(query_text, parameters, policy)?;
        request.check_index(&self.index)?;
        let (plan, explain) = self.select(&request, mode).await?;
        let table = match plan {
            None => grust_cypher::run_prepared_read_query_indexed(&request, &self.index)?,
            Some(plan) => self.execute(&request, plan).await?,
        };
        Ok(RoutedReadResult { table, explain })
    }

    async fn select(
        &self,
        request: &PreparedReadRequest<'_>,
        mode: RouteMode,
    ) -> Result<(Option<Arc<dyn ExecutionPlan>>, RouteExplain)> {
        let mut explain = RouteExplain {
            chosen: ReadRoute::Reference,
            datafusion_declined: None,
            capture: self.snapshot().map(GraphSnapshot::statistics),
            physical_plan: None,
        };
        let decline = |mut explain: RouteExplain, reason: RouteDecline| {
            if mode == RouteMode::Force(ReadRoute::DataFusion) {
                return Err(gql_execution(format!(
                    "DataFusion route unavailable: {reason}"
                )));
            }
            explain.datafusion_declined = Some(reason);
            Ok((None, explain))
        };
        if mode == RouteMode::Force(ReadRoute::Reference) {
            return decline(explain, RouteDecline::ReferenceForced);
        }
        let snapshot = match &self.snapshot {
            Ok(snapshot) => snapshot,
            Err(reason) => {
                return decline(explain, RouteDecline::CaptureUnavailable(reason.clone()));
            }
        };
        let frame = match snapshot
            .plan(request.query(), &self.context, request.parameters())
            .map_err(|error| gql_execution(describe(&error)))?
        {
            QueryPlan::Unsupported { kind, reason } => {
                return decline(explain, RouteDecline::Unsupported { kind, reason });
            }
            QueryPlan::Supported {
                kind: PlanKind::RelationshipScan,
                ..
            } => return decline(explain, RouteDecline::RelationshipJoin),
            QueryPlan::Supported {
                kind: PlanKind::NodeScan,
                frame,
            } => frame,
        };
        let node_rows = snapshot.statistics().node_rows;
        if mode == RouteMode::Automatic && node_rows < self.min_datafusion_nodes {
            return decline(
                explain,
                RouteDecline::BelowThreshold {
                    node_rows,
                    threshold: self.min_datafusion_nodes,
                },
            );
        }
        let limit = request.policy().max_candidate_work;
        if node_rows > limit {
            return decline(
                explain,
                RouteDecline::CandidateWork {
                    required: node_rows,
                    limit,
                },
            );
        }
        let plan = frame
            .create_physical_plan()
            .await
            .map_err(|error| gql_execution(describe(&error)))?;
        explain.physical_plan = Some(displayable(plan.as_ref()).indent(true).to_string());
        if let Some(name) = uncovered_operator(&plan) {
            return decline(explain, RouteDecline::UncoveredOperator(name));
        }
        explain.chosen = ReadRoute::DataFusion;
        Ok((Some(plan), explain))
    }

    async fn execute(
        &self,
        request: &PreparedReadRequest<'_>,
        plan: Arc<dyn ExecutionPlan>,
    ) -> Result<CypherResultTable> {
        let policy = request.policy();
        let execution = ExecutionContext::new(ExecutionLimits {
            memory_bytes: policy.max_intermediate_bytes,
            work_units: policy.max_candidate_work,
            batch_rows: 1024,
            deadline: Some(request.deadline()),
        })
        .map_err(|error| gql_execution(error.to_string()))?;
        let schema: SchemaRef = plan.schema();
        let run = async {
            let plan = instrument(plan, &execution)?;
            super::collect::collect_stream(
                schema,
                std::future::ready(execute_stream(plan, self.context.task_ctx())),
                policy.max_result_rows,
                policy.max_output_bytes,
                Some(&execution),
            )
            .await
        };
        let table = crate::run_cancellable(&execution, run)
            .await
            .map_err(|error| gql_execution(describe(&error)))?;
        request.check_output(&table)?;
        Ok(table)
    }
}

/// Operator name without a variant suffix, e.g. `SortExec(TopK)` -> `SortExec`.
fn operator_kind(plan: &Arc<dyn ExecutionPlan>) -> &str {
    let name = plan.name();
    name.split_once('(').map_or(name, |(kind, _)| kind)
}

fn uncovered_operator(plan: &Arc<dyn ExecutionPlan>) -> Option<String> {
    if !COVERED_OPERATORS.contains(&operator_kind(plan)) {
        return Some(plan.name().to_owned());
    }
    plan.children().into_iter().find_map(uncovered_operator)
}

/// Wrap every leaf in candidate-row charging and every copying operator in
/// cumulative byte charging. Operators are only wrapped, never replaced, so
/// the optimized plan and its upstream kernels run unchanged.
fn instrument(
    plan: Arc<dyn ExecutionPlan>,
    execution: &ExecutionContext,
) -> DataFusionResult<Arc<dyn ExecutionPlan>> {
    let children = plan
        .children()
        .into_iter()
        .map(|child| instrument(Arc::clone(child), execution))
        .collect::<DataFusionResult<Vec<_>>>()?;
    let charge = if children.is_empty() {
        Some(Charge::CandidateRows)
    } else if PASS_THROUGH_OPERATORS.contains(&operator_kind(&plan)) {
        None
    } else {
        Some(Charge::CopiedBytes)
    };
    let plan = if children.is_empty() {
        plan
    } else {
        replace_children_if_necessary(plan, children)?
    };
    Ok(match charge {
        None => plan,
        Some(charge) => Arc::new(AccountedExec {
            input: plan,
            charge,
            execution: execution.clone(),
        }),
    })
}

#[derive(Clone, Copy, Debug)]
enum Charge {
    /// Rows produced by a scan are candidate work.
    CandidateRows,
    /// Arrays produced by an operator are cumulative intermediate copies,
    /// measured by their sliced contents rather than shared parent buffers.
    CopiedBytes,
}

impl Charge {
    fn apply(self, execution: &ExecutionContext, batch: &RecordBatch) -> DataFusionResult<()> {
        let charged = match self {
            Self::CandidateRows => execution.charge_work(batch.num_rows()),
            Self::CopiedBytes => execution.charge_cumulative_memory(slice_bytes(batch)?),
        };
        charged.map_err(|error| DataFusionError::External(Box::new(error)))
    }
}

fn slice_bytes(batch: &RecordBatch) -> DataFusionResult<usize> {
    batch.columns().iter().try_fold(0_usize, |total, column| {
        let bytes = column.to_data().get_slice_memory_size()?;
        total
            .checked_add(bytes)
            .ok_or_else(|| DataFusionError::Execution("intermediate byte count overflow".into()))
    })
}

/// Charges each emitted batch against the query's shared execution context
/// before passing it on. Shared across partitions through one context.
#[derive(Debug)]
struct AccountedExec {
    input: Arc<dyn ExecutionPlan>,
    charge: Charge,
    execution: ExecutionContext,
}

impl DisplayAs for AccountedExec {
    fn fmt_as(&self, _format: DisplayFormatType, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "AccountedExec: {:?}", self.charge)
    }
}

impl ExecutionPlan for AccountedExec {
    fn name(&self) -> &str {
        "AccountedExec"
    }

    fn properties(&self) -> &Arc<PlanProperties> {
        self.input.properties()
    }

    fn children(&self) -> Vec<&Arc<dyn ExecutionPlan>> {
        vec![&self.input]
    }

    fn apply_expressions(
        &self,
        _f: &mut dyn FnMut(&Arc<dyn PhysicalExpr>) -> DataFusionResult<TreeNodeRecursion>,
    ) -> DataFusionResult<TreeNodeRecursion> {
        Ok(TreeNodeRecursion::Continue)
    }

    fn with_new_children(
        self: Arc<Self>,
        children: Vec<Arc<dyn ExecutionPlan>>,
    ) -> DataFusionResult<Arc<dyn ExecutionPlan>> {
        let [input] = <[_; 1]>::try_from(children).map_err(|_| {
            DataFusionError::Internal("AccountedExec requires exactly one child".into())
        })?;
        Ok(Arc::new(Self {
            input,
            charge: self.charge,
            execution: self.execution.clone(),
        }))
    }

    fn execute(
        &self,
        partition: usize,
        context: Arc<TaskContext>,
    ) -> DataFusionResult<SendableRecordBatchStream> {
        let stream = self.input.execute(partition, context)?;
        let schema = stream.schema();
        let (charge, execution) = (self.charge, self.execution.clone());
        Ok(Box::pin(RecordBatchStreamAdapter::new(
            schema,
            stream.map(move |batch| {
                let batch = batch?;
                charge.apply(&execution, &batch)?;
                Ok(batch)
            }),
        )))
    }
}

/// Translate a DataFusion failure into the reference executor's messages for
/// the same policy outcomes, so callers see one bounded-read contract.
fn describe(error: &DataFusionError) -> String {
    if let DataFusionError::External(inner) = error.find_root()
        && let Some(error) = inner.downcast_ref::<ProcedureError>()
    {
        return match error {
            ProcedureError::DeadlineExceeded => "bounded read execution timed out".into(),
            ProcedureError::BudgetExceeded {
                resource: "work", ..
            } => format!(
                "bounded read candidate-work units ({error}) while executing DataFusion scan"
            ),
            ProcedureError::BudgetExceeded { .. } => format!(
                "bounded read cumulative intermediate bytes ({error}) while executing DataFusion scan"
            ),
            error => format!("bounded read DataFusion execution failed: {error}"),
        };
    }
    format!("bounded read DataFusion execution failed: {error}")
}
