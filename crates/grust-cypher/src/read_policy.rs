//! Parser-backed policy for exposing bounded, read-only GQL/Cypher surfaces.
//!
//! Applications still own authorization and graph projection. This module owns
//! language-level safety so consumers do not scan query text for keywords.

use crate::ast::{Clause, Expr, PathPattern, Query, SingleQuery};
use crate::parser::parse_query;
use std::io::{self, Write};
use std::time::{Duration, Instant};

use serde::Serialize;

use crate::read::{execute_read_query, execute_read_query_indexed};
use crate::read_budget::{MAX_RANGE_ITEMS, ReadExecutionBudgetLimits, with_budget};
use crate::{CypherParameters, CypherResultTable, gql_execution, gql_syntax};
use grust_core::TypedGraphIndex;
use grust_core::prelude::{Graph, Result};
use grust_procedures::{ProcedureMode, ProcedureRegistry, RegistryBuilder, register_builtins};

mod prepared;
pub use prepared::PreparedReadRequest;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ReadQueryPolicy {
    pub max_query_bytes: usize,
    /// Maximum serialized size of the complete parameter map.
    pub max_parameter_bytes: usize,
    /// Maximum node and edge counts accepted in the projected input graph.
    pub max_graph_nodes: usize,
    pub max_graph_edges: usize,
    /// Maximum serialized size of the projected input graph.
    pub max_graph_bytes: usize,
    /// Cumulative work units spent scanning or producing candidates.
    pub max_candidate_work: usize,
    /// Cumulative bytes copied into executor-owned intermediate rows, graph
    /// bindings, and values. This limits amplification before final `LIMIT`
    /// and output-size checks run.
    pub max_intermediate_bytes: usize,
    pub max_result_rows: usize,
    /// Maximum serialized size of the returned columns and rows.
    pub max_output_bytes: usize,
    /// Maximum number of integers materialized by one `range()` invocation.
    pub max_range_items: usize,
    pub max_union_arms: usize,
    /// Maximum cumulative hop count of every path pattern.
    pub max_path_length: u64,
    /// Cooperative wall-clock deadline for parsing, execution, and encoding.
    pub max_execution_time: Duration,
    pub allow_graph_selection: bool,
    /// Compatibility permission for catalog and graph-free table procedures.
    pub allow_catalog_procedures: bool,
    /// Separate opt-in for registered read-only graph analytics. This never
    /// grants catalog/table access or write procedures.
    pub allow_read_procedures: bool,
    pub require_match: bool,
}

impl Default for ReadQueryPolicy {
    fn default() -> Self {
        Self {
            max_query_bytes: 2_000,
            max_parameter_bytes: 64 * 1024,
            max_graph_nodes: 100_000,
            max_graph_edges: 500_000,
            max_graph_bytes: 64 * 1024 * 1024,
            max_candidate_work: 1_000_000,
            max_intermediate_bytes: 256 * 1024 * 1024,
            max_result_rows: 50,
            max_output_bytes: 1024 * 1024,
            max_range_items: 10_000,
            max_union_arms: 4,
            max_path_length: 4,
            max_execution_time: Duration::from_secs(2),
            allow_graph_selection: false,
            allow_catalog_procedures: false,
            allow_read_procedures: false,
            require_match: true,
        }
    }
}

/// Parse and validate a single bounded read query using Grust's source-of-truth
/// AST. Every query arm must have a positive literal `LIMIT` no larger than the
/// policy's result ceiling.
pub fn validate_read_query(query_text: &str, policy: &ReadQueryPolicy) -> Result<Query> {
    let mut builder = RegistryBuilder::default();
    register_builtins(&mut builder).map_err(|error| gql_syntax(error.to_string()))?;
    validate_read_query_with_registry(query_text, policy, &builder.build())
}

/// Validate read-policy admission using the same registry as execution.
/// Unknown providers and denied modes fail before graph preparation.
pub fn validate_read_query_with_registry(
    query_text: &str,
    policy: &ReadQueryPolicy,
    registry: &ProcedureRegistry,
) -> Result<Query> {
    validate_policy(policy)?;
    let text = query_text.trim();
    if text.is_empty() || text.len() > policy.max_query_bytes {
        return Err(gql_syntax(format!(
            "query must contain 1 to {} bytes",
            policy.max_query_bytes
        )));
    }
    let mut query = parse_query(text).map_err(|error| error.into_grust(text))?;
    validate_query(&query, policy, registry)?;
    crate::read::prepare_query_with_registry(&mut query, registry)?;
    Ok(query)
}

/// Execute a parser-validated bounded read query against a projected graph.
pub fn run_bounded_read_query(
    graph: &Graph,
    query_text: &str,
    params: &CypherParameters,
    policy: &ReadQueryPolicy,
) -> Result<CypherResultTable> {
    run_bounded_read_query_with_executor(
        BoundedInput::Graph(graph),
        query_text,
        params,
        policy,
        None,
        |query| execute_read_query(graph, query, params),
    )
}

/// Execute a bounded read against the index's immutable projected graph.
///
/// Applies the same validation, input-size checks, execution budgets and output
/// checks as [`run_bounded_read_query`], including when execution falls back to
/// the reference executor. The exact graph-byte limit uses the size measured
/// when the index acquired its immutable snapshot.
/// `USE` retains the reference entrypoint's behavior: the policy controls whether
/// it is permitted; this wrapper does not resolve a different graph snapshot.
pub fn run_bounded_read_query_indexed(
    index: &TypedGraphIndex,
    query_text: &str,
    params: &CypherParameters,
    policy: &ReadQueryPolicy,
) -> Result<CypherResultTable> {
    run_bounded_read_query_with_executor(
        BoundedInput::Indexed(index),
        query_text,
        params,
        policy,
        None,
        |query| execute_read_query_indexed(index, query, params),
    )
}

/// Execute ordinary Cypher with an application registry under the complete read
/// policy. Catalog/table and graph-analytics permissions are checked separately.
/// The selected local graph is explicit and cannot be changed by a provider.
pub fn run_bounded_read_query_with_registry(
    graph: &Graph,
    graph_name: &str,
    query_text: &str,
    params: &CypherParameters,
    policy: &ReadQueryPolicy,
    registry: &ProcedureRegistry,
) -> Result<CypherResultTable> {
    run_bounded_read_query_with_executor(
        BoundedInput::Graph(graph),
        query_text,
        params,
        policy,
        Some(registry),
        |query| {
            crate::ensure_query_uses_graph(query, graph_name)?;
            crate::read::execute_read_query_with_registry(
                graph, graph_name, query, params, registry,
            )
        },
    )
}

/// Execute on an explicitly authorized snapshot, preserving graph/revision/
/// principal identity while applying the complete bounded read policy.
pub fn run_bounded_read_query_on_snapshot(
    snapshot: grust_procedures::LocalSnapshot<'_>,
    query_text: &str,
    params: &CypherParameters,
    policy: &ReadQueryPolicy,
    registry: &ProcedureRegistry,
) -> Result<CypherResultTable> {
    run_bounded_read_query_with_executor(
        BoundedInput::Graph(snapshot.graph()),
        query_text,
        params,
        policy,
        Some(registry),
        |query| crate::read::execute_read_query_on_snapshot(snapshot, query, params, registry),
    )
}

/// The projected input graph whose size a bounded read checks.
#[derive(Clone, Copy)]
enum BoundedInput<'a> {
    Graph(&'a Graph),
    /// A typed index: its counts, and the serialized size it measures once
    /// per snapshot, without materializing an owned graph.
    Indexed(&'a TypedGraphIndex),
}

fn run_bounded_read_query_with_executor(
    input: BoundedInput<'_>,
    query_text: &str,
    params: &CypherParameters,
    policy: &ReadQueryPolicy,
    registry: Option<&ProcedureRegistry>,
    execute: impl FnOnce(&Query) -> Result<CypherResultTable>,
) -> Result<CypherResultTable> {
    let request = PreparedReadRequest::prepare(query_text, params, policy, registry)?;
    match input {
        BoundedInput::Graph(graph) => request.check_graph(graph)?,
        BoundedInput::Indexed(index) => request.check_index(index)?,
    }
    let limits = ReadExecutionBudgetLimits {
        max_candidate_work: policy.max_candidate_work,
        max_intermediate_bytes: policy.max_intermediate_bytes,
        max_range_items: policy.max_range_items,
        deadline: request.deadline(),
    };
    with_budget(limits, || {
        let table = execute(request.query())?;
        request.check_output(&table)?;
        Ok(table)
    })
}

#[cfg(test)]
#[path = "read_policy/indexed_tests.rs"]
mod indexed_tests;

fn validate_policy(policy: &ReadQueryPolicy) -> Result<()> {
    let positive = [
        ("max_query_bytes", policy.max_query_bytes),
        ("max_parameter_bytes", policy.max_parameter_bytes),
        ("max_graph_nodes", policy.max_graph_nodes),
        ("max_graph_edges", policy.max_graph_edges),
        ("max_graph_bytes", policy.max_graph_bytes),
        ("max_candidate_work", policy.max_candidate_work),
        ("max_intermediate_bytes", policy.max_intermediate_bytes),
        ("max_result_rows", policy.max_result_rows),
        ("max_output_bytes", policy.max_output_bytes),
        ("max_range_items", policy.max_range_items),
        ("max_union_arms", policy.max_union_arms),
    ];
    if let Some((name, _)) = positive.into_iter().find(|(_, value)| *value == 0) {
        return Err(gql_syntax(format!("read policy {name} must be positive")));
    }
    if policy.max_path_length == 0 {
        return Err(gql_syntax("read policy max_path_length must be positive"));
    }
    if policy.max_execution_time.is_zero() {
        return Err(gql_syntax(
            "read policy max_execution_time must be positive",
        ));
    }
    if policy.max_range_items > MAX_RANGE_ITEMS {
        return Err(gql_syntax(format!(
            "read policy max_range_items cannot exceed the executor maximum of {MAX_RANGE_ITEMS}"
        )));
    }
    Ok(())
}

fn ensure_graph_bounds(nodes: usize, edges: usize, policy: &ReadQueryPolicy) -> Result<()> {
    if nodes > policy.max_graph_nodes {
        return Err(gql_execution(format!(
            "bounded read graph contains {} nodes; policy maximum is {}",
            nodes, policy.max_graph_nodes
        )));
    }
    if edges > policy.max_graph_edges {
        return Err(gql_execution(format!(
            "bounded read graph contains {} edges; policy maximum is {}",
            edges, policy.max_graph_edges
        )));
    }
    Ok(())
}

fn ensure_before_deadline(deadline: Instant) -> Result<()> {
    if Instant::now() >= deadline {
        Err(gql_execution("bounded read execution timed out"))
    } else {
        Ok(())
    }
}

#[derive(Serialize)]
struct EncodedResultSize<'a> {
    columns: &'a [String],
    rows: &'a [Vec<grust_core::Value>],
}

struct LimitWriter {
    written: usize,
    maximum: usize,
    deadline: Instant,
    exceeded: bool,
    timed_out: bool,
}

impl Write for LimitWriter {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if Instant::now() >= self.deadline {
            self.timed_out = true;
            return Err(io::Error::new(io::ErrorKind::TimedOut, "deadline elapsed"));
        }
        let Some(next) = self.written.checked_add(bytes.len()) else {
            self.exceeded = true;
            return Err(io::Error::other("serialized-size counter overflowed"));
        };
        if next > self.maximum {
            self.exceeded = true;
            return Err(io::Error::other("serialized-size limit exceeded"));
        }
        self.written = next;
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

fn ensure_serialized_size<T: Serialize + ?Sized>(
    what: &str,
    value: &T,
    maximum: usize,
    deadline: Instant,
) -> Result<usize> {
    let mut writer = LimitWriter {
        written: 0,
        maximum,
        deadline,
        exceeded: false,
        timed_out: false,
    };
    let encoded = serde_json::to_writer(&mut writer, value);
    if writer.timed_out {
        return Err(gql_execution("bounded read execution timed out"));
    }
    if writer.exceeded {
        return Err(gql_execution(format!(
            "bounded read {what} exceeds {maximum} serialized bytes"
        )));
    }
    encoded.map_err(|error| {
        gql_execution(format!("could not measure bounded read {what}: {error}"))
    })?;
    Ok(writer.written)
}

fn validate_query(
    query: &Query,
    policy: &ReadQueryPolicy,
    registry: &ProcedureRegistry,
) -> Result<()> {
    if query.parts.is_empty() || query.parts.len() > policy.max_union_arms {
        return Err(gql_syntax(format!(
            "query must contain 1 to {} UNION arms",
            policy.max_union_arms
        )));
    }
    for part in &query.parts {
        validate_single(&part.query, policy, registry)?;
    }
    Ok(())
}

fn validate_single(
    query: &SingleQuery,
    policy: &ReadQueryPolicy,
    registry: &ProcedureRegistry,
) -> Result<()> {
    if policy.require_match
        && !query
            .clauses
            .iter()
            .any(|clause| matches!(clause, Clause::Match(_)))
    {
        return Err(gql_syntax("bounded read query requires MATCH"));
    }
    for clause in &query.clauses {
        if clause.is_updating() {
            return Err(gql_syntax("updating clauses are forbidden by read policy"));
        }
        match clause {
            Clause::Use(_) if !policy.allow_graph_selection => {
                return Err(gql_syntax("graph selection is forbidden by read policy"));
            }
            Clause::Call(call) => {
                let procedure = registry
                    .resolve(&call.name)
                    .map_err(|error| gql_syntax(error.to_string()))?;
                let allowed = match procedure.definition().mode {
                    ProcedureMode::Catalog | ProcedureMode::Table => {
                        policy.allow_catalog_procedures
                    }
                    ProcedureMode::Read => policy.allow_read_procedures,
                    ProcedureMode::Write => false,
                };
                if !allowed {
                    return Err(gql_syntax(
                        "procedure calls are forbidden by read policy for this provider mode",
                    ));
                }
            }
            Clause::Subquery(subquery) => validate_query(&subquery.query, policy, registry)?,
            Clause::Match(clause) => {
                for pattern in &clause.patterns {
                    validate_pattern(pattern, policy)?;
                }
            }
            _ => {}
        }
    }
    let Some(Clause::Return(return_clause)) = query.clauses.last() else {
        return Err(gql_syntax("bounded read query must end with RETURN"));
    };
    match return_clause.projection.limit {
        Some(Expr::Integer(limit))
            if limit > 0
                && usize::try_from(limit).is_ok_and(|limit| limit <= policy.max_result_rows) =>
        {
            Ok(())
        }
        _ => Err(gql_syntax(format!(
            "RETURN requires a positive literal LIMIT no larger than {}",
            policy.max_result_rows
        ))),
    }
}

fn validate_pattern(pattern: &PathPattern, policy: &ReadQueryPolicy) -> Result<()> {
    let mut total_hops = 0_u64;
    for segment in &pattern.segments {
        let segment_hops = if let Some(length) = segment.relationship.length {
            let Some(maximum) = length.max else {
                return Err(gql_syntax("unbounded variable-length paths are forbidden"));
            };
            maximum
        } else {
            1
        };
        total_hops = total_hops
            .checked_add(segment_hops)
            .ok_or_else(|| gql_syntax("path length overflowed the read policy bound"))?;
        if total_hops > policy.max_path_length {
            return Err(gql_syntax(format!(
                "path can traverse {total_hops} hops; read policy maximum is {}",
                policy.max_path_length
            )));
        }
    }
    Ok(())
}

#[cfg(test)]
#[path = "read_policy_tests.rs"]
mod tests;
