//! Shared request admission before executor selection. A prepared request owns
//! its validated AST and policy, borrows immutable parameters, and retains one
//! absolute deadline. Graph authority and execution accounting are not inferred
//! from successful request preparation.
use super::{
    EncodedResultSize, ReadQueryPolicy, ensure_before_deadline, ensure_graph_bounds,
    ensure_serialized_size, validate_read_query, validate_read_query_with_registry,
};
use crate::{CypherParameters, CypherResultTable, ast::Query, gql_execution};
use grust_core::{Graph, Result, TypedGraphIndex};
use grust_procedures::ProcedureRegistry;
use std::time::Instant;

/// Validated read-only query and parameters with a fixed policy and deadline.
/// Preparing does not authorize a graph, admit input storage, execute a query,
/// or install execution budgets. Executors must check their chosen input and
/// enforce every requested work/intermediate/output limit before using this
/// request. Unsupported policy mappings must decline the route.
pub struct PreparedReadRequest<'a> {
    query: Query,
    parameters: &'a CypherParameters,
    policy: ReadQueryPolicy,
    deadline: Instant,
    registry: Option<ProcedureRegistry>,
}

impl<'a> PreparedReadRequest<'a> {
    /// Validate using the built-in registry. Parameter admission happens before
    /// graph inspection or executor selection, without allocating encoded JSON.
    pub fn new(
        query_text: &str,
        parameters: &'a CypherParameters,
        policy: &ReadQueryPolicy,
    ) -> Result<Self> {
        Self::prepare(query_text, parameters, policy, None)
    }

    /// Validate against and retain an immutable application registry generation.
    pub fn with_registry(
        query_text: &str,
        parameters: &'a CypherParameters,
        policy: &ReadQueryPolicy,
        registry: &ProcedureRegistry,
    ) -> Result<Self> {
        Self::prepare(query_text, parameters, policy, Some(registry))
    }

    pub(super) fn prepare(
        query_text: &str,
        parameters: &'a CypherParameters,
        policy: &ReadQueryPolicy,
        registry: Option<&ProcedureRegistry>,
    ) -> Result<Self> {
        let deadline = Instant::now()
            .checked_add(policy.max_execution_time)
            .ok_or_else(|| gql_execution("read policy execution timeout is too large"))?;
        let query = match registry {
            Some(registry) => validate_read_query_with_registry(query_text, policy, registry)?,
            None => validate_read_query(query_text, policy)?,
        };
        ensure_before_deadline(deadline)?;
        crate::semantics::analyze(&query)?;
        ensure_serialized_size(
            "parameters",
            parameters,
            policy.max_parameter_bytes,
            deadline,
        )?;
        Ok(Self {
            query,
            parameters,
            policy: *policy,
            deadline,
            registry: registry.cloned(),
        })
    }

    /// Parser-prepared and semantically analyzed query; mutation is not exposed.
    pub fn query(&self) -> &Query {
        &self.query
    }
    /// The exact immutable parameter map whose serialized size was admitted.
    pub fn parameters(&self) -> &CypherParameters {
        self.parameters
    }
    /// Policy copied at preparation; later changes to the caller's copy do not apply.
    pub fn policy(&self) -> &ReadQueryPolicy {
        &self.policy
    }
    /// Absolute deadline starting before parsing; route changes must not reset it.
    pub fn deadline(&self) -> Instant {
        self.deadline
    }
    /// Retained application registry, or `None` for built-in registry semantics.
    pub fn registry(&self) -> Option<&ProcedureRegistry> {
        self.registry.as_ref()
    }

    /// Check graph counts and exact serialized size. This does not establish
    /// transaction/principal authority or reserve executor-owned allocations.
    pub fn check_graph(&self, graph: &Graph) -> Result<()> {
        self.check_serializable_graph(graph.nodes.len(), graph.edges.len(), graph)
            .map(|_| ())
    }

    /// Check the index's immutable snapshot using its cached exact byte size,
    /// avoiding graph materialization or repeated serialization.
    pub fn check_index(&self, index: &TypedGraphIndex) -> Result<()> {
        self.check_measured_graph(
            index.node_count(),
            index.edge_count(),
            index.serialized_graph_bytes(),
        )
    }

    /// Check a trusted graph projection's exact counts and borrowed serialization
    /// view. Counts must describe the same immutable projection as `graph`; this
    /// is an adapter contract, not validation of arbitrary serializer behavior.
    /// Returns exact JSON bytes for caching beside that snapshot. Count rejection
    /// happens before serialization; counting allocates no encoded JSON buffer.
    pub fn check_serializable_graph<T: serde::Serialize + ?Sized>(
        &self,
        nodes: usize,
        edges: usize,
        graph: &T,
    ) -> Result<usize> {
        ensure_before_deadline(self.deadline)?;
        ensure_graph_bounds(nodes, edges, &self.policy)?;
        ensure_serialized_size("graph", graph, self.policy.max_graph_bytes, self.deadline)
    }

    /// Check exact measurements retained by a trusted immutable snapshot. The
    /// caller must not substitute estimates or measurements from another graph.
    pub fn check_measured_graph(&self, nodes: usize, edges: usize, bytes: usize) -> Result<()> {
        ensure_before_deadline(self.deadline)?;
        ensure_graph_bounds(nodes, edges, &self.policy)?;
        if bytes > self.policy.max_graph_bytes {
            return Err(gql_execution(format!(
                "bounded read graph exceeds {} serialized bytes",
                self.policy.max_graph_bytes
            )));
        }
        Ok(())
    }

    /// Check the complete result contract. Materializing executors must also
    /// enforce their intermediate budget before allocating this output.
    pub fn check_output(&self, table: &CypherResultTable) -> Result<()> {
        ensure_before_deadline(self.deadline)?;
        if table.rows.len() > self.policy.max_result_rows {
            return Err(gql_execution(format!(
                "query produced more than {} rows",
                self.policy.max_result_rows
            )));
        }
        ensure_serialized_size(
            "query output",
            &EncodedResultSize {
                columns: &table.columns,
                rows: &table.rows,
            },
            self.policy.max_output_bytes,
            self.deadline,
        )
        .map(|_| ())
    }
}

#[cfg(test)]
#[path = "prepared_tests.rs"]
mod tests;
