//! Memory reference executor for bounded read-only `MATCH … RETURN`
//! (Unit 6 of `docs/GQL_GOAL.md`).
//!
//! This is the first executable use of the new lexer → parser → semantics
//! pipeline. It runs a bounded read-query subset against an in-memory
//! [`Graph`] snapshot (the deterministic reference; persistent backends will
//! push the same plans down later). It does **not** touch the existing write
//! planner — reads are a new, additive capability.
//!
//! Supported subset:
//! - one or more `MATCH` clauses (node patterns and fixed-length relationship
//!   segments with direction, types, and inline property-equality maps),
//! - an optional `WHERE` per `MATCH` (comparison, boolean with three-valued
//!   NULL logic, `IN`, `IS [NOT] NULL`, `STARTS/ENDS WITH`, `CONTAINS`,
//!   arithmetic),
//! - a final `RETURN` with item aliases, `*`, `DISTINCT`, `ORDER BY`, `SKIP`,
//!   and `LIMIT`.
//!
//! Everything else (OPTIONAL MATCH, WITH, UNION, UNWIND, variable-length and
//! quantified paths, path variables, aggregates, functions, CASE) fails with a
//! feature-tagged [`unsupported_gql_feature`] error rather than a silent wrong
//! answer. Aggregation and the general expression/function registry arrive in
//! Units 7–9.

use std::borrow::Cow;
use std::collections::{BTreeMap, HashMap};
use std::sync::Arc;

use grust_core::TypedGraphIndex;

use crate::ast;
use crate::ast::*;
use crate::parser::parse_query;
use crate::read_budget;
use crate::session::ensure_query_uses_graph;
use crate::*;

mod binding_key;
mod count_cycle;
mod count_predicate;
mod count_scan;
mod count_support;
mod count_tags;
mod count_tree;
mod count_triangle;
mod count_wedge;
mod indexed;
mod match_scope;
mod prepared_procedures;
mod procedure_plan;
pub use procedure_plan::{
    ProcedureCallPlan, ProcedureExecutionTarget, ProcedureQueryPlan, ProcedureRowExecution,
};
mod indexing;
mod procedures;
mod streaming;
mod streaming_aggregate;
mod streaming_fusion;
pub use prepared_procedures::PreparedProcedureQuery;
mod property_equality;
pub use indexed::{
    IndexedReadPlan, classify_indexed_read_query, execute_read_query_indexed,
    run_read_query_indexed,
};
use match_scope::{EdgeTrail, MatchRow};
use procedures::ProcedureExecution;
pub(crate) use procedures::execute_read_query_on_snapshot;
pub(crate) use procedures::execute_read_query_with_registry;
pub(crate) use procedures::prepare_query_with_registry;
pub use procedures::run_read_query_with_registry;

/// A value bound to a variable in a candidate row. Pattern matching binds
/// immutable shared `Node`/`Edge`; `WITH`/`UNWIND` bind computed `Value`s.
/// Candidate copies share graph elements; projection still produces owned values.
#[derive(Debug)]
enum Bound {
    Node(Arc<Node>),
    // Graph-free pushed bindings have no slot; graph MATCH bindings do.
    Edge(Arc<Edge>, Option<usize>),
    Value(Value),
}

/// One candidate solution: pattern variable -> bound graph element.
type Row = BTreeMap<String, Bound>;

/// The graph a read executes over: an owned [`Graph`], or a typed index whose
/// source may build nodes and edges on demand instead of holding a copy of
/// each. Rows share immutable copies of bound elements, so only elements a
/// query actually examines are ever built.
#[derive(Clone, Copy)]
pub(crate) enum GraphRef<'g> {
    Owned(&'g Graph),
    Indexed(&'g TypedGraphIndex),
}

impl<'g> GraphRef<'g> {
    fn node_count(self) -> usize {
        match self {
            Self::Owned(graph) => graph.nodes.len(),
            Self::Indexed(index) => index.node_count(),
        }
    }

    fn edge_count(self) -> usize {
        match self {
            Self::Owned(graph) => graph.edges.len(),
            Self::Indexed(index) => index.edge_count(),
        }
    }

    fn node_id(self, slot: usize) -> &'g NodeId {
        match self {
            Self::Owned(graph) => &graph.nodes[slot].id,
            Self::Indexed(index) => index.node_id(slot as u32),
        }
    }

    /// The whole graph, for procedures that read a local snapshot. Over an
    /// index whose source is not an owned graph this materializes, once per
    /// index, a full copy; only `CALL` needs it.
    pub(crate) fn local_graph(self) -> &'g Graph {
        match self {
            Self::Owned(graph) => graph,
            Self::Indexed(index) => index.graph(),
        }
    }
}

fn charge_intermediate_copy(context: &str, measure: impl FnOnce() -> usize) -> Result<()> {
    if read_budget::intermediate_accounting_active() {
        read_budget::charge_intermediate_bytes(measure(), context)?;
    }
    Ok(())
}

// Keep logical full-element charges when sharing bindings. The budget remains
// conservative; physical sharing must not waive property-copy admission.
fn bound_copy_bytes(bound: &Bound) -> usize {
    let nested = match bound {
        Bound::Node(node) => read_budget::node_copy_bytes(node),
        Bound::Edge(edge, _) => read_budget::edge_copy_bytes(edge),
        Bound::Value(value) => read_budget::value_copy_bytes(value),
    };
    std::mem::size_of::<Bound>().saturating_add(nested)
}

fn row_copy_bytes(row: &Row) -> usize {
    row.iter()
        .fold(std::mem::size_of::<Row>(), |bytes, (name, bound)| {
            bytes
                .saturating_add(std::mem::size_of::<(String, Bound)>())
                .saturating_add(name.len())
                .saturating_add(bound_copy_bytes(bound))
        })
}

fn clone_bound_unaccounted(bound: &Bound) -> Bound {
    match bound {
        Bound::Node(node) => Bound::Node(node.clone()),
        Bound::Edge(edge, slot) => Bound::Edge(edge.clone(), *slot),
        Bound::Value(value) => Bound::Value(value.clone()),
    }
}

fn clone_bound(bound: &Bound, context: &str) -> Result<Bound> {
    charge_intermediate_copy(context, || bound_copy_bytes(bound))?;
    Ok(clone_bound_unaccounted(bound))
}

fn clone_row(row: &Row, context: &str) -> Result<Row> {
    charge_intermediate_copy(context, || row_copy_bytes(row))?;
    Ok(row
        .iter()
        .map(|(name, bound)| (name.clone(), clone_bound_unaccounted(bound)))
        .collect())
}

fn clone_value(value: &Value, context: &str) -> Result<Value> {
    charge_intermediate_copy(context, || read_budget::value_copy_bytes(value))?;
    Ok(value.clone())
}

fn materialize_node_value(node: &Node, context: &str) -> Result<Value> {
    charge_intermediate_copy(context, || read_budget::node_copy_bytes(node))?;
    graph_node_value(node)
}

fn materialize_edge_value(edge: &Edge, context: &str) -> Result<Value> {
    charge_intermediate_copy(context, || read_budget::edge_copy_bytes(edge))?;
    graph_edge_value(edge)
}

fn materialize_edge_json(edge: &Edge, context: &str) -> Result<serde_json::Value> {
    Ok(value_into_json(materialize_edge_value(edge, context)?))
}

fn clone_json_value(value: &serde_json::Value, context: &str) -> Result<Value> {
    charge_intermediate_copy(context, || read_budget::json_copy_bytes(value))?;
    Ok(Value::from_json(value.clone()))
}

fn clone_node(node: &Node, context: &str) -> Result<Node> {
    charge_intermediate_copy(context, || read_budget::node_copy_bytes(node))?;
    Ok(node.clone())
}

fn clone_edge(edge: &Edge, context: &str) -> Result<Edge> {
    charge_intermediate_copy(context, || read_budget::edge_copy_bytes(edge))?;
    Ok(edge.clone())
}

fn clone_nodes(nodes: &[Node], context: &str) -> Result<Vec<Node>> {
    charge_intermediate_copy(context, || {
        nodes.iter().fold(
            nodes.len().saturating_mul(std::mem::size_of::<Node>()),
            |bytes, node| bytes.saturating_add(read_budget::node_copy_bytes(node)),
        )
    })?;
    Ok(nodes.to_vec())
}

fn clone_edges(edges: &[Edge], context: &str) -> Result<Vec<Edge>> {
    charge_intermediate_copy(context, || {
        edges.iter().fold(
            edges.len().saturating_mul(std::mem::size_of::<Edge>()),
            |bytes, edge| bytes.saturating_add(read_budget::edge_copy_bytes(edge)),
        )
    })?;
    Ok(edges.to_vec())
}

/// Parse, analyze, and execute a read-only query against an in-memory graph.
///
/// Backends that can materialize a [`Graph`] (e.g. `MemoryGraphStore::graph()`)
/// use this directly as the portable reference; it returns the same
/// [`CypherResultTable`] shape as the writable returning path.
pub fn run_read_query(
    graph: &Graph,
    cypher: &str,
    params: &CypherParameters,
) -> Result<CypherResultTable> {
    let mut query = parse_query(cypher).map_err(|e| e.into_grust(cypher))?;
    ensure_query_uses_graph(&query, "default")?;
    let procedures = ProcedureExecution::builtins()?;
    procedures.prepare(&mut query)?;
    execute_read_query_with_procedures(GraphRef::Owned(graph), &query, params, &procedures)
}

pub fn run_read_query_on_named_graph(
    graph: &Graph,
    graph_name: &str,
    cypher: &str,
    params: &CypherParameters,
) -> Result<CypherResultTable> {
    let mut query = parse_query(cypher).map_err(|e| e.into_grust(cypher))?;
    ensure_query_uses_graph(&query, graph_name)?;
    let procedures = ProcedureExecution::builtins()?.with_graph_name(graph_name)?;
    procedures.prepare(&mut query)?;
    execute_read_query_with_procedures(GraphRef::Owned(graph), &query, params, &procedures)
}

/// Execute an already-parsed read-only query against an in-memory graph.
pub fn execute_read_query(
    graph: &Graph,
    query: &Query,
    params: &CypherParameters,
) -> Result<CypherResultTable> {
    execute_read_query_on(GraphRef::Owned(graph), query, params)
}

/// [`execute_read_query`] over either an owned graph or a typed index.
pub(crate) fn execute_read_query_on(
    graph: GraphRef<'_>,
    query: &Query,
    params: &CypherParameters,
) -> Result<CypherResultTable> {
    execute_read_query_with_procedures(graph, query, params, &ProcedureExecution::builtins()?)
}

fn execute_read_query_with_procedures(
    graph: GraphRef<'_>,
    query: &Query,
    params: &CypherParameters,
    procedures: &ProcedureExecution,
) -> Result<CypherResultTable> {
    read_budget::checkpoint()?;
    procedures.preflight(query, Some(params))?;
    let mut combined: Option<CypherResultTable> = None;
    // `UNION` (without ALL) deduplicates the whole result; `UNION ALL` keeps
    // duplicates. A mixed chain dedups if any boundary is a distinct UNION.
    let mut distinct = false;

    for part in &query.parts {
        if part.union == Some(UnionKind::Distinct) {
            distinct = true;
        }
        let table = execute_single(graph, &part.query, params, procedures)?;
        match combined.as_mut() {
            None => combined = Some(table),
            Some(acc) => {
                if acc.columns != table.columns {
                    return Err(gql_name(
                        "all UNION arms must return the same column names in the same order",
                    ));
                }
                acc.rows.extend(table.rows);
            }
        }
    }

    let mut table = combined.ok_or_else(|| gql_execution("query has no parts"))?;
    if distinct {
        let mut seen = std::collections::HashSet::new();
        let mut deduped = Vec::with_capacity(table.rows.len());
        for values in std::mem::take(&mut table.rows) {
            let key = return_row_key(&values, "UNION")?;
            if seen.insert(key) {
                deduped.push(values);
            }
        }
        table.rows = deduped;
    }
    Ok(table)
}

fn execute_single(
    graph: GraphRef<'_>,
    query: &SingleQuery,
    params: &CypherParameters,
    procedures: &ProcedureExecution,
) -> Result<CypherResultTable> {
    if let Some(result) = streaming::try_execute(graph, query, params, procedures) {
        return result;
    }
    let requirements = query_adjacency_requirements(query);
    read_budget::charge_candidate_work(graph.node_count(), "building the node index")?;
    if requirements.outgoing || requirements.incoming {
        read_budget::charge_candidate_work(graph.edge_count(), "building adjacency indexes")?;
    }
    let index = NodeIndex::build(graph, requirements)?;
    read_budget::checkpoint()?;
    let mut rows: Vec<Row> = vec![Row::new()];
    // Columns produced by a trailing CALL with no RETURN (standalone `CALL …`),
    // so the procedure's YIELD shape becomes the result table.
    let mut call_output: Option<Vec<String>> = None;

    // A clause pipeline: each clause transforms the binding-row stream; RETURN is
    // terminal and produces the result table.
    for clause in &query.clauses {
        if let Clause::Return(r) = clause {
            // Terminal: project the current bindings to the result table.
            return project(graph, &rows, &r.projection, params);
        }
        let (next, call_cols) = advance_rows(graph, &index, clause, rows, params, procedures)?;
        rows = next;
        if call_cols.is_some() {
            call_output = call_cols;
        }
    }

    // A standalone `CALL …` (no RETURN) returns the procedure's YIELD columns.
    if let Some(columns) = call_output {
        let mut out_rows = Vec::with_capacity(rows.len());
        for row in &rows {
            let mut vals = Vec::with_capacity(columns.len());
            for col in &columns {
                match row.get(col) {
                    Some(Bound::Value(value)) => {
                        vals.push(clone_value(value, "shaping standalone procedure output")?)
                    }
                    _ => vals.push(Value::Null),
                }
            }
            out_rows.push(vals);
        }
        return Ok(CypherResultTable {
            columns,
            rows: out_rows,
        });
    }

    Err(gql_execution("read query has no RETURN clause"))
}

/// Apply one non-`RETURN` clause to the binding-row stream. Returns the new
/// rows plus, for a `CALL <proc>`, the procedure's output columns (so a
/// standalone trailing `CALL` can shape the result table).
fn advance_rows(
    graph: GraphRef<'_>,
    index: &NodeIndex,
    clause: &Clause,
    rows: Vec<Row>,
    params: &CypherParameters,
    procedures: &ProcedureExecution,
) -> Result<(Vec<Row>, Option<Vec<String>>)> {
    match clause {
        Clause::Use(_) => Ok((rows, None)),
        Clause::Match(m) if !m.optional => {
            let mut rows = match_scope::begin(rows)?;
            for pattern in &m.patterns {
                rows = expand_pattern(graph, index, pattern, rows, params)?;
            }
            let mut rows = match_scope::finish(rows)?;
            if let Some(where_expr) = &m.where_clause {
                rows = filter_rows(rows, where_expr, params)?;
            }
            Ok((rows, None))
        }
        Clause::Match(m) => {
            // OPTIONAL MATCH: each incoming row produces its matches, or a
            // single row with this match's new variables NULL-padded.
            let new_vars = pattern_variables(&m.patterns);
            let mut out = Vec::new();
            for row in rows {
                let mut matched = match_scope::begin(vec![clone_row(
                    &row,
                    "starting OPTIONAL MATCH expansion",
                )?])?;
                for pattern in &m.patterns {
                    matched = expand_pattern(graph, index, pattern, matched, params)?;
                }
                let mut matched = match_scope::finish(matched)?;
                if let Some(where_expr) = &m.where_clause {
                    matched = filter_rows(matched, where_expr, params)?;
                }
                if matched.is_empty() {
                    let mut padded = row;
                    for var in &new_vars {
                        padded
                            .entry(var.clone())
                            .or_insert(Bound::Value(Value::Null));
                    }
                    read_budget::charge_candidate_work(1, "producing OPTIONAL MATCH rows")?;
                    out.push(padded);
                } else {
                    out.extend(matched);
                }
            }
            Ok((out, None))
        }
        Clause::With(w) => {
            let mut rows = project_to_bindings(&w.projection, rows, params)?;
            if let Some(where_expr) = &w.where_clause {
                rows = filter_rows(rows, where_expr, params)?;
            }
            Ok((rows, None))
        }
        Clause::Unwind(u) => Ok((unwind_rows(rows, u, params)?, None)),
        Clause::Call(c) => procedures.advance(graph, c, rows, params),
        Clause::Subquery(s) => Ok((
            execute_subquery_clause(graph, s, rows, params, procedures)?,
            None,
        )),
        Clause::Return(_) => unreachable!("RETURN is handled by the caller"),
        Clause::Create(_)
        | Clause::Merge(_)
        | Clause::Delete(_)
        | Clause::Set(_)
        | Clause::Remove(_) => Err(gql_execution(
            "the read reference executor only runs read-only MATCH/WITH/UNWIND/RETURN queries",
        )),
    }
}

/// `CALL { … }`: execute the inline subquery once per incoming row (the outer
/// bindings are visible inside), joining its returned columns onto the row.
/// A row whose subquery returns no rows is dropped.
fn execute_subquery_clause(
    graph: GraphRef<'_>,
    subquery: &SubqueryClause,
    rows: Vec<Row>,
    params: &CypherParameters,
    procedures: &ProcedureExecution,
) -> Result<Vec<Row>> {
    let mut out = Vec::new();
    for row in rows {
        let (columns, inner_rows) = run_subquery(graph, &subquery.query, &row, params, procedures)?;
        for col in &columns {
            if row.contains_key(col) {
                return Err(gql_name(format!(
                    "CALL {{ … }} returns `{col}`, which is already bound in the outer scope"
                )));
            }
        }
        for inner in inner_rows {
            let mut next = clone_row(&row, "joining subquery rows")?;
            for col in &columns {
                let bound = match inner.get(col) {
                    Some(bound) => clone_bound(bound, "joining subquery bindings")?,
                    None => Bound::Value(Value::Null),
                };
                next.insert(col.clone(), bound);
            }
            read_budget::charge_candidate_work(1, "joining subquery rows")?;
            out.push(next);
        }
    }
    Ok(out)
}

/// Run a subquery (possibly `UNION`-composed) seeded with the outer row's
/// bindings. Returns the output column names and one binding row per result.
fn run_subquery(
    graph: GraphRef<'_>,
    query: &Query,
    seed: &Row,
    params: &CypherParameters,
    procedures: &ProcedureExecution,
) -> Result<(Vec<String>, Vec<Row>)> {
    let mut columns: Option<Vec<String>> = None;
    let mut all: Vec<Row> = Vec::new();
    let mut distinct = false;
    for part in &query.parts {
        if part.union == Some(UnionKind::Distinct) {
            distinct = true;
        }
        let (cols, rows) = run_subquery_single(graph, &part.query, seed, params, procedures)?;
        match &columns {
            None => columns = Some(cols),
            Some(existing) if existing != &cols => {
                return Err(gql_name(
                    "all UNION arms inside CALL { … } must return the same column names in the same order",
                ));
            }
            Some(_) => {}
        }
        all.extend(rows);
    }
    let columns = columns.ok_or_else(|| gql_execution("CALL { … } subquery has no parts"))?;
    if distinct {
        let mut seen = std::collections::HashSet::new();
        let mut deduped = Vec::with_capacity(all.len());
        for row in all {
            let mut values = Vec::with_capacity(columns.len());
            for col in &columns {
                values.push(match row.get(col) {
                    Some(bound) => bound_value(bound)?,
                    None => Value::Null,
                });
            }
            if seen.insert(return_row_key(&values, "CALL { … } UNION")?) {
                deduped.push(row);
            }
        }
        all = deduped;
    }
    Ok((columns, all))
}

fn run_subquery_single(
    graph: GraphRef<'_>,
    query: &SingleQuery,
    seed: &Row,
    params: &CypherParameters,
    procedures: &ProcedureExecution,
) -> Result<(Vec<String>, Vec<Row>)> {
    let requirements = query_adjacency_requirements(query);
    read_budget::charge_candidate_work(graph.node_count(), "building a subquery node index")?;
    if requirements.outgoing || requirements.incoming {
        read_budget::charge_candidate_work(
            graph.edge_count(),
            "building subquery adjacency indexes",
        )?;
    }
    let index = NodeIndex::build(graph, requirements)?;
    read_budget::checkpoint()?;
    let mut rows = vec![clone_row(seed, "seeding a correlated subquery")?];
    for clause in &query.clauses {
        if let Clause::Return(r) = clause {
            return project_subquery_return(&r.projection, rows, params);
        }
        let (next, _) = advance_rows(graph, &index, clause, rows, params, procedures)?;
        rows = next;
    }
    Err(gql_execution("CALL { … } subquery must end in RETURN"))
}

/// Project a subquery's terminal `RETURN` to named binding rows (WITH-style:
/// bare variables keep their node/edge binding; computed items bind values
/// under their alias or derived column name).
fn project_subquery_return(
    projection: &Projection,
    rows: Vec<Row>,
    params: &CypherParameters,
) -> Result<(Vec<String>, Vec<Row>)> {
    if projection.star {
        return Err(unsupported_gql_feature(
            GqlFeature::Subquery,
            GqlConformanceProfile::PortableGql,
            "RETURN * inside CALL { … } is not supported (it would re-project the imported outer scope)",
        ));
    }
    let items: Vec<ReturnItem> = projection
        .items
        .iter()
        .map(|item| ReturnItem {
            expr: item.expr.clone(),
            alias: Some(item.alias.clone().unwrap_or_else(|| match &item.expr {
                Expr::Variable(v) => v.clone(),
                other => column_name(other),
            })),
        })
        .collect();
    let columns: Vec<String> = items
        .iter()
        .map(|item| item.alias.clone().expect("alias was just filled in"))
        .collect();
    let mut unique = std::collections::HashSet::new();
    for col in &columns {
        if !unique.insert(col.as_str()) {
            return Err(gql_name(format!(
                "CALL {{ … }} returns the column `{col}` more than once; alias the items uniquely"
            )));
        }
    }
    let named = Projection {
        distinct: projection.distinct,
        star: false,
        items,
        order_by: projection.order_by.clone(),
        skip: projection.skip.clone(),
        limit: projection.limit.clone(),
    };
    let out = project_to_bindings(&named, rows, params)?;
    Ok((columns, out))
}

/// Resolve a `YIELD` list against the procedure's full columns: the projected
/// output names plus, for each, the index into the full row.
fn yield_projection(
    name: &str,
    full_cols: &[String],
    yields: &[(String, Option<String>)],
) -> Result<(Vec<String>, Vec<usize>)> {
    if yields.is_empty() {
        return Ok((full_cols.to_vec(), (0..full_cols.len()).collect()));
    }
    let mut out_cols = Vec::with_capacity(yields.len());
    let mut indices = Vec::with_capacity(yields.len());
    for (col, alias) in yields {
        let idx = full_cols.iter().position(|c| c == col).ok_or_else(|| {
            gql_name(format!(
                "procedure `{name}` does not yield a column named `{col}`"
            ))
        })?;
        out_cols.push(alias.clone().unwrap_or_else(|| col.clone()));
        indices.push(idx);
    }
    Ok((out_cols, indices))
}

/// Keep rows whose `where_expr` evaluates to TRUE (NULL/FALSE drop), surfacing
/// evaluation errors instead of silently dropping rows.
fn filter_rows(rows: Vec<Row>, where_expr: &Expr, params: &CypherParameters) -> Result<Vec<Row>> {
    let mut kept = Vec::with_capacity(rows.len());
    for row in rows {
        read_budget::charge_candidate_work(1, "filtering candidate rows")?;
        if matches!(eval(where_expr, &row, params)?, Value::Bool(true)) {
            kept.push(row);
        }
    }
    Ok(kept)
}

/// `UNWIND list AS x`: expand each row into one row per list element. A NULL or
/// empty list yields no rows for that input row.
fn unwind_rows(
    rows: Vec<Row>,
    unwind: &UnwindClause,
    params: &CypherParameters,
) -> Result<Vec<Row>> {
    let mut out = Vec::new();
    for row in rows {
        // A list literal is evaluated element-wise (round-tripping a list
        // through JSON would be lossy); other expressions evaluate to a value.
        let elements: Vec<Value> = if let Expr::List(items) = &unwind.expr {
            items
                .iter()
                .map(|e| eval(e, &row, params))
                .collect::<Result<_>>()?
        } else {
            match eval(&unwind.expr, &row, params)? {
                Value::Null => continue,
                Value::StringArray(xs) => xs.into_iter().map(Value::String).collect(),
                Value::IntArray(xs) => xs.into_iter().map(Value::Int).collect(),
                Value::FloatArray(xs) => xs.into_iter().map(Value::Float).collect(),
                Value::Json(serde_json::Value::Array(arr)) => {
                    arr.into_iter().map(Value::from_json).collect()
                }
                other => return Err(gql_type(format!("UNWIND expects a list, got {other:?}"))),
            }
        };
        for element in elements {
            read_budget::charge_candidate_work(1, "expanding UNWIND rows")?;
            let mut next = clone_row(&row, "expanding UNWIND rows")?;
            next.insert(unwind.alias.clone(), Bound::Value(element));
            out.push(next);
        }
    }
    Ok(out)
}

/// `WITH` horizon: project the binding-row stream into a new binding-row stream
/// (bare variables keep their node/edge/value binding; computed items bind a
/// value), then apply DISTINCT / ORDER BY / SKIP / LIMIT.
fn project_to_bindings(
    projection: &Projection,
    rows: Vec<Row>,
    params: &CypherParameters,
) -> Result<Vec<Row>> {
    let has_aggregate = projection.items.iter().any(|i| expr_has_aggregate(&i.expr));

    let mut out: Vec<Row> = if has_aggregate {
        // `WITH *` + aggregates: the star expands to the bound variables
        // (sorted), which become grouping keys alongside the explicit items.
        let expanded: Vec<ReturnItem>;
        let items: &[ReturnItem] = if projection.star {
            let mut vars: BTreeMap<String, ()> = BTreeMap::new();
            for row in &rows {
                for var in row.keys() {
                    vars.insert(var.clone(), ());
                }
            }
            expanded = vars
                .keys()
                .map(|v| ReturnItem {
                    expr: Expr::Variable(v.clone()),
                    alias: None,
                })
                .chain(projection.items.iter().cloned())
                .collect();
            &expanded
        } else {
            &projection.items
        };
        grouped_bindings(items, &rows, params)?
    } else {
        let mut produced = Vec::with_capacity(rows.len());
        for row in &rows {
            read_budget::charge_candidate_work(1, "projecting WITH rows")?;
            let mut next = if projection.star {
                clone_row(row, "projecting WITH star rows")?
            } else {
                Row::new()
            };
            for item in &projection.items {
                let (name, bound) = binding_for_item(item, row, params)?;
                next.insert(name, bound);
            }
            produced.push(next);
        }
        produced
    };

    if projection.distinct {
        out = dedup_bindings(out)?;
    }
    order_bindings(&mut out, &projection.order_by, params)?;
    skip_limit_bindings(&mut out, projection, params)?;
    Ok(out)
}

/// The (name, binding) a `WITH`/`RETURN` item contributes. A bare variable keeps
/// its existing binding (so a node stays a node downstream); anything else binds
/// a computed value under its alias.
fn binding_for_item(
    item: &ReturnItem,
    row: &Row,
    params: &CypherParameters,
) -> Result<(String, Bound)> {
    match &item.expr {
        Expr::Variable(v) => {
            let bound = match row.get(v) {
                Some(bound) => clone_bound(bound, "projecting WITH variable bindings")?,
                None => Bound::Value(Value::Null),
            };
            Ok((item.alias.clone().unwrap_or_else(|| v.clone()), bound))
        }
        other => {
            let name = item.alias.clone().ok_or_else(|| {
                gql_name("WITH requires an alias (AS ...) for non-variable expressions")
            })?;
            Ok((name, Bound::Value(eval(other, row, params)?)))
        }
    }
}

fn grouped_bindings(
    items: &[ReturnItem],
    rows: &[Row],
    params: &CypherParameters,
) -> Result<Vec<Row>> {
    // Group by the non-aggregate items; carry bare-variable keys as their
    // original binding, computed keys/aggregates as values.
    let key_items: Vec<&ReturnItem> = items
        .iter()
        .filter(|i| !expr_has_aggregate(&i.expr))
        .collect();

    let mut order: Vec<binding_key::Key> = Vec::new();
    let mut groups: HashMap<binding_key::Key, (Row, Vec<usize>)> = HashMap::new();
    for (idx, row) in rows.iter().enumerate() {
        let key = binding_key::grouping(&key_items, row, params)?;
        match groups.entry(key) {
            std::collections::hash_map::Entry::Occupied(mut entry) => {
                entry.get_mut().1.push(idx);
            }
            std::collections::hash_map::Entry::Vacant(entry) => {
                order.push(entry.key().copy("recording WITH grouping order")?);
                entry.insert((
                    clone_row(row, "retaining WITH group representatives")?,
                    vec![idx],
                ));
            }
        }
    }
    if key_items.is_empty() && rows.is_empty() {
        order.push(binding_key::Key::default());
        groups.insert(binding_key::Key::default(), (Row::new(), Vec::new()));
    }

    let mut out = Vec::with_capacity(order.len());
    for key in &order {
        let (representative, group_idxs) = &groups[key];
        let group_rows: Vec<&Row> = group_idxs.iter().map(|&i| &rows[i]).collect();
        let mut next = Row::new();
        for item in items {
            if expr_has_aggregate(&item.expr) {
                let name = item.alias.clone().ok_or_else(|| {
                    gql_name("WITH requires an alias (AS ...) for aggregate expressions")
                })?;
                next.insert(
                    name,
                    Bound::Value(eval_aggregate(&item.expr, &group_rows, params)?),
                );
            } else {
                let (name, bound) = binding_for_item(item, representative, params)?;
                next.insert(name, bound);
            }
        }
        read_budget::charge_candidate_work(1, "producing grouped WITH rows")?;
        out.push(next);
    }
    Ok(out)
}

/// Deduplicate a `WITH DISTINCT` (or subquery `RETURN DISTINCT`) row stream by
/// the **produced** rows' bindings. Bare relationships retain physical identity.
/// The projection has already run, so the
/// items' source expressions may reference variables the new rows no longer
/// bind (e.g. `WITH DISTINCT p.name AS n` drops `p`); the produced bindings
/// are exactly the projected bindings, so they are the dedup key.
fn dedup_bindings(rows: Vec<Row>) -> Result<Vec<Row>> {
    let mut seen = std::collections::HashSet::new();
    let mut out = Vec::with_capacity(rows.len());
    for row in rows {
        if seen.insert(binding_key::bindings(&row)?) {
            read_budget::charge_candidate_work(1, "deduplicating WITH rows")?;
            out.push(row);
        }
    }
    Ok(out)
}

fn order_bindings(
    rows: &mut Vec<Row>,
    order_by: &[OrderItem],
    params: &CypherParameters,
) -> Result<()> {
    if order_by.is_empty() {
        return Ok(());
    }
    let mut keyed: Vec<Vec<Value>> = Vec::with_capacity(rows.len());
    for row in rows.iter() {
        let mut keys = Vec::with_capacity(order_by.len());
        for item in order_by {
            keys.push(eval(&item.expr, row, params)?);
        }
        keyed.push(keys);
    }
    let mut order: Vec<usize> = (0..rows.len()).collect();
    order.sort_by(|&a, &b| {
        for (k, item) in order_by.iter().enumerate() {
            let ord = compare_return_values(&keyed[a][k], &keyed[b][k]);
            let ord = if item.descending { ord.reverse() } else { ord };
            if ord != std::cmp::Ordering::Equal {
                return ord;
            }
        }
        std::cmp::Ordering::Equal
    });
    read_budget::charge_intermediate_bytes(
        rows.len().saturating_mul(std::mem::size_of::<Row>()),
        "reordering WITH rows",
    )?;
    let mut original = std::mem::take(rows)
        .into_iter()
        .map(Some)
        .collect::<Vec<_>>();
    *rows = order
        .into_iter()
        .map(|index| original[index].take().expect("ORDER BY index is unique"))
        .collect();
    Ok(())
}

fn skip_limit_bindings(
    rows: &mut Vec<Row>,
    projection: &Projection,
    params: &CypherParameters,
) -> Result<()> {
    if let Some(skip) = &projection.skip {
        let n = eval_usize(skip, params, "SKIP")?;
        rows.drain(0..n.min(rows.len()));
    }
    if let Some(limit) = &projection.limit {
        let n = eval_usize(limit, params, "LIMIT")?;
        rows.truncate(n);
    }
    Ok(())
}

fn bound_value(bound: &Bound) -> Result<Value> {
    match bound {
        Bound::Node(node) => materialize_node_value(node, "materializing bound nodes"),
        Bound::Edge(edge, _) => materialize_edge_value(edge, "materializing bound relationships"),
        Bound::Value(value) => clone_value(value, "materializing bound values"),
    }
}

/// A graph element a backend's pushdown query reconstructed for one binding.
#[derive(Clone, Debug)]
pub enum PushedBinding {
    Node(Node),
    Edge(Edge),
    /// An `OPTIONAL MATCH` variable with no match — bound to `null`, matching the
    /// reference's null-padding (`b.key` then evaluates to `null`).
    Null,
}

/// Reconstructed backend bindings for one pushed row.
pub(crate) type PushedBindingRow = Vec<(String, PushedBinding)>;
/// One outer binding row and the inner nodes joined to it.
pub(crate) type PushedNodeGroup = (PushedBindingRow, Vec<Node>);
/// One outer binding row and the procedure values joined to it.
pub(crate) type PushedValueRow = (PushedBindingRow, Vec<Value>);

/// Deduplicate result rows by value identity, preserving first-seen order — the
/// shared `UNION` (distinct) dedup, reused by backend pushdown's union combine.
pub(crate) fn dedup_return_rows(rows: Vec<Vec<Value>>, context: &str) -> Result<Vec<Vec<Value>>> {
    let mut seen = std::collections::HashSet::new();
    let mut deduped = Vec::with_capacity(rows.len());
    for values in rows {
        let key = return_row_key(&values, context)?;
        if seen.insert(key) {
            deduped.push(values);
        }
    }
    Ok(deduped)
}

/// Project a set of already-matched nodes through a `RETURN`/`WITH` projection.
///
/// This is the shared tail used by single-node backend **read pushdown**
/// (Unit 15): a persistent backend lowers the `MATCH`/`WHERE` filter into its own
/// SQL, fetches the surviving nodes, and hands them here so the `RETURN`
/// projection (aliases, `*`, `DISTINCT`, `ORDER BY`, `SKIP`/`LIMIT`, aggregates)
/// runs through the **exact same** reference code path as [`run_read_query`]. The
/// pushdown result is therefore byte-identical to the in-memory reference by
/// construction; only the upstream filter equivalence has to be established per
/// backend.
pub(crate) fn project_nodes(
    var: &str,
    nodes: Vec<Node>,
    projection: &Projection,
    params: &CypherParameters,
) -> Result<CypherResultTable> {
    let binding_rows = nodes
        .into_iter()
        .map(|node| vec![(var.to_string(), PushedBinding::Node(node))])
        .collect();
    project_bindings(binding_rows, projection, params)
}

/// Project already-matched **multi-binding** rows (e.g. a relationship segment's
/// `(a, r, b)`) through a `RETURN`/`WITH` projection — the generalization of
/// [`project_nodes`] used by pushdown over patterns with more than one binding.
/// Each inner vector is one solution row: `(variable, bound element)` pairs.
pub(crate) fn project_bindings(
    binding_rows: Vec<Vec<(String, PushedBinding)>>,
    projection: &Projection,
    params: &CypherParameters,
) -> Result<CypherResultTable> {
    let rows = binding_rows_to_rows(binding_rows);
    let empty = Graph::default();
    project(GraphRef::Owned(&empty), &rows, projection, params)
}

fn binding_rows_to_rows(binding_rows: Vec<Vec<(String, PushedBinding)>>) -> Vec<Row> {
    binding_rows
        .into_iter()
        .map(|bindings| {
            let mut row = Row::new();
            for (var, binding) in bindings {
                row.insert(var, bound_from_pushed(binding));
            }
            row
        })
        .collect()
}

fn bound_from_pushed(binding: PushedBinding) -> Bound {
    match binding {
        PushedBinding::Node(node) => Bound::Node(node.into()),
        PushedBinding::Edge(edge) => Bound::Edge(edge.into(), None),
        PushedBinding::Null => Bound::Value(Value::Null),
    }
}

/// Run a `WITH`/`UNWIND`/`RETURN` tail pipeline over pre-matched binding rows —
/// the shared tail for backend pushdown of `MATCH … WITH … RETURN` (the leading
/// pattern's filter is pushed; the horizon runs here). Errors on a clause that
/// needs graph access (a further `MATCH`), which the planner excludes.
pub(crate) fn project_binding_pipeline(
    binding_rows: Vec<Vec<(String, PushedBinding)>>,
    tail: &[Clause],
    params: &CypherParameters,
) -> Result<CypherResultTable> {
    run_tail_pipeline(binding_rows_to_rows(binding_rows), tail, params)
}

/// Run a `WITH`/`UNWIND`/`RETURN` tail over already-materialized binding rows —
/// the shared pipeline core of [`project_binding_pipeline`] and the
/// catalog-procedure pushdown tail.
fn run_tail_pipeline(
    mut rows: Vec<Row>,
    tail: &[Clause],
    params: &CypherParameters,
) -> Result<CypherResultTable> {
    for clause in tail {
        match clause {
            Clause::With(w) => {
                rows = project_to_bindings(&w.projection, rows, params)?;
                if let Some(where_expr) = &w.where_clause {
                    rows = filter_rows(rows, where_expr, params)?;
                }
            }
            Clause::Unwind(u) => {
                rows = unwind_rows(rows, u, params)?;
            }
            Clause::Return(r) => {
                let empty = Graph::default();
                return project(GraphRef::Owned(&empty), &rows, &r.projection, params);
            }
            _ => {
                return Err(gql_execution(
                    "pushdown pipeline runs only WITH/UNWIND/RETURN tails",
                ));
            }
        }
    }
    Err(gql_execution("pushdown pipeline has no RETURN"))
}

/// Shared tail for catalog-procedure / TVF **read pushdown** (PUSHDOWN2 P1/P2):
/// a backend's SQL produced the procedure's full (pre-`YIELD`) rows; apply the
/// `CALL`'s `YIELD` projection/aliasing and `WHERE` exactly like the reference,
/// then run the remaining `WITH`/`UNWIND`/`RETURN` tail through the shared
/// pipeline (or shape the standalone-`CALL` result table when there is no
/// tail). Byte-identical to [`run_read_query`]'s `CALL` path by construction.
pub(crate) fn project_procedure_pipeline(
    call: &CallClause,
    full_cols: &[String],
    full_rows: Vec<Vec<Value>>,
    tail: &[Clause],
    params: &CypherParameters,
) -> Result<CypherResultTable> {
    let (out_cols, indices) = yield_projection(&call.name, full_cols, &call.yields)?;
    let mut rows: Vec<Row> = Vec::with_capacity(full_rows.len());
    for vals in &full_rows {
        let mut row = Row::new();
        for (col, &i) in out_cols.iter().zip(indices.iter()) {
            row.insert(
                col.clone(),
                Bound::Value(clone_value(&vals[i], "binding pushed procedure values")?),
            );
        }
        rows.push(row);
    }
    if let Some(where_expr) = &call.where_clause {
        rows = filter_rows(rows, where_expr, params)?;
    }
    if tail.is_empty() {
        // Standalone `CALL …`: the YIELD shape is the result table.
        return standalone_call_table(&rows, out_cols);
    }
    run_tail_pipeline(rows, tail, params)
}

/// Shape the standalone-`CALL` result table from the yielded columns.
fn standalone_call_table(rows: &[Row], out_cols: Vec<String>) -> Result<CypherResultTable> {
    let mut out_rows = Vec::with_capacity(rows.len());
    for row in rows {
        let mut values = Vec::with_capacity(out_cols.len());
        for col in &out_cols {
            values.push(match row.get(col) {
                Some(Bound::Value(value)) => clone_value(value, "shaping pushed procedure output")?,
                _ => Value::Null,
            });
        }
        out_rows.push(values);
    }
    Ok(CypherResultTable {
        columns: out_cols,
        rows: out_rows,
    })
}

/// Run a subquery's inner clause tail (`WITH`/`UNWIND` steps ending in the
/// subquery `RETURN`) over seeded rows — the reference's inner pipeline core,
/// shared with subquery pushdown.
fn run_subquery_tail(
    mut rows: Vec<Row>,
    clauses: &[Clause],
    params: &CypherParameters,
) -> Result<(Vec<String>, Vec<Row>)> {
    for clause in clauses {
        match clause {
            Clause::Return(r) => return project_subquery_return(&r.projection, rows, params),
            Clause::With(w) => {
                rows = project_to_bindings(&w.projection, rows, params)?;
                if let Some(where_expr) = &w.where_clause {
                    rows = filter_rows(rows, where_expr, params)?;
                }
            }
            Clause::Unwind(u) => {
                rows = unwind_rows(rows, u, params)?;
            }
            _ => {
                return Err(gql_execution(
                    "subquery pushdown runs only WITH/UNWIND/RETURN inner tails",
                ));
            }
        }
    }
    Err(gql_execution("CALL { … } subquery must end in RETURN"))
}

/// Shared tail for **uncorrelated `CALL { … }` pushdown** (PUSHDOWN2 P3): for
/// each outer row (its pushed bindings) and the pushed inner-scan nodes of its
/// group, seed the inner pipeline with the outer bindings plus each inner node
/// (exactly like the reference's per-row subquery execution), run the inner
/// `WITH`/`UNWIND`/`RETURN` tail, join the returned columns onto the outer
/// row, and finish with the outer tail. Byte-identical to [`run_read_query`]'s
/// subquery path by construction.
pub(crate) fn project_subquery_join_pipeline(
    groups: Vec<PushedNodeGroup>,
    inner_var: &str,
    inner_tail: &[Clause],
    outer_tail: &[Clause],
    params: &CypherParameters,
) -> Result<CypherResultTable> {
    let mut joined: Vec<Row> = Vec::new();
    for (outer_bindings, inner_nodes) in groups {
        let mut outer_row = Row::new();
        for (var, binding) in outer_bindings {
            outer_row.insert(var, bound_from_pushed(binding));
        }
        let seeds: Vec<Row> = inner_nodes
            .into_iter()
            .map(|node| -> Result<Row> {
                let mut row = clone_row(&outer_row, "seeding pushed subquery rows")?;
                row.insert(inner_var.to_string(), Bound::Node(node.into()));
                Ok(row)
            })
            .collect::<Result<_>>()?;
        let (columns, produced) = run_subquery_tail(seeds, inner_tail, params)?;
        for col in &columns {
            if outer_row.contains_key(col) {
                return Err(gql_name(format!(
                    "CALL {{ … }} returns `{col}`, which is already bound in the outer scope"
                )));
            }
        }
        for prow in produced {
            let mut next = clone_row(&outer_row, "joining pushed subquery rows")?;
            for col in &columns {
                let bound = match prow.get(col) {
                    Some(bound) => clone_bound(bound, "joining pushed subquery bindings")?,
                    None => Bound::Value(Value::Null),
                };
                next.insert(col.clone(), bound);
            }
            read_budget::charge_candidate_work(1, "joining pushed subquery rows")?;
            joined.push(next);
        }
    }
    run_tail_pipeline(joined, outer_tail, params)
}

/// Shared tail for **correlated TVF pushdown** (PUSHDOWN2 P4, `tvf.keys`):
/// each pushed row carries the outer bindings plus the procedure's full
/// (pre-`YIELD`) row; apply `YIELD`/`WHERE` like the reference and run the
/// remaining pipeline (or shape the standalone-`CALL` table).
pub(crate) fn project_correlated_procedure_pipeline(
    rows_in: Vec<PushedValueRow>,
    call: &CallClause,
    full_cols: &[String],
    tail: &[Clause],
    params: &CypherParameters,
) -> Result<CypherResultTable> {
    let (out_cols, indices) = yield_projection(&call.name, full_cols, &call.yields)?;
    let mut rows: Vec<Row> = Vec::with_capacity(rows_in.len());
    for (bindings, vals) in rows_in {
        let mut row = Row::new();
        for (var, binding) in bindings {
            row.insert(var, bound_from_pushed(binding));
        }
        for (col, &i) in out_cols.iter().zip(indices.iter()) {
            row.insert(
                col.clone(),
                Bound::Value(clone_value(
                    &vals[i],
                    "binding correlated procedure values",
                )?),
            );
        }
        rows.push(row);
    }
    if let Some(where_expr) = &call.where_clause {
        rows = filter_rows(rows, where_expr, params)?;
    }
    if tail.is_empty() {
        return standalone_call_table(&rows, out_cols);
    }
    run_tail_pipeline(rows, tail, params)
}

// ---------------------------------------------------------------------------
// Pattern matching
// ---------------------------------------------------------------------------

/// Per-query node lookup and adjacency. Over an owned graph it builds them;
/// over a typed index it builds nothing and answers from the index, visiting
/// candidates in the same order and charging the same work.
struct NodeIndex {
    by_id: HashMap<NodeId, usize>,
    outgoing_by_vertex: Option<CompressedAdjacency>,
    incoming_by_vertex: Option<CompressedAdjacency>,
    requirements: AdjacencyRequirements,
}

#[derive(Clone, Copy, Default)]
struct AdjacencyRequirements {
    outgoing: bool,
    incoming: bool,
}

struct CompressedAdjacency {
    offsets: Vec<usize>,
    edge_indexes: Vec<usize>,
}

impl CompressedAdjacency {
    fn edges_for(&self, vertex: usize) -> &[usize] {
        &self.edge_indexes[self.offsets[vertex]..self.offsets[vertex + 1]]
    }
}

impl NodeIndex {
    fn build(graph: GraphRef<'_>, requirements: AdjacencyRequirements) -> Result<Self> {
        // The same charge over either graph: an indexed read is budgeted as
        // the owned executor would be, not by what it happens to allocate.
        charge_intermediate_copy("building graph indexes", || {
            let nodes = graph.node_count();
            let id_index_bytes = (0..nodes).fold(
                nodes.saturating_mul(std::mem::size_of::<(NodeId, usize)>()),
                |bytes, slot| bytes.saturating_add(graph.node_id(slot).as_str().len()),
            );
            let adjacency_count = usize::from(requirements.outgoing)
                .saturating_add(usize::from(requirements.incoming));
            let adjacency_bytes = adjacency_count.saturating_mul(
                graph
                    .edge_count()
                    .saturating_mul(
                        std::mem::size_of::<(usize, usize)>() + std::mem::size_of::<usize>(),
                    )
                    .saturating_add(nodes.saturating_mul(2 * std::mem::size_of::<usize>())),
            );
            id_index_bytes.saturating_add(adjacency_bytes)
        })?;
        let GraphRef::Owned(graph) = graph else {
            // A typed index already resolves ids and holds typed adjacency.
            return Ok(NodeIndex {
                by_id: HashMap::new(),
                outgoing_by_vertex: None,
                incoming_by_vertex: None,
                requirements,
            });
        };
        let mut by_id = HashMap::with_capacity(graph.nodes.len());
        for (i, node) in graph.nodes.iter().enumerate() {
            by_id.insert(node.id.clone(), i);
        }
        let outgoing_by_vertex = requirements
            .outgoing
            .then(|| build_compressed_adjacency(graph, &by_id, |edge| &edge.from));
        let incoming_by_vertex = requirements
            .incoming
            .then(|| build_compressed_adjacency(graph, &by_id, |edge| &edge.to));
        Ok(NodeIndex {
            by_id,
            outgoing_by_vertex,
            incoming_by_vertex,
            requirements,
        })
    }

    fn get<'g>(&self, graph: GraphRef<'g>, id: &str) -> Option<Cow<'g, Node>> {
        match graph {
            GraphRef::Owned(graph) => self.by_id.get(id).map(|&i| Cow::Borrowed(&graph.nodes[i])),
            GraphRef::Indexed(index) => index.vertex_index(id).map(|vertex| index.node(vertex)),
        }
    }

    /// The relationship candidates a pattern step examines from `node`, in
    /// the order the owned executor examines them: its adjacency lists when
    /// the query needs adjacency, otherwise the whole edge vector.
    ///
    /// Over a typed index the whole-vector scan is replaced by the edges that
    /// touch `node`, which are the only ones the scan can accept, in the same
    /// edge-slot order. A candidate is `None` for an edge that is visited but
    /// never built: with `exact_scan` (a budget is counting, or the step's
    /// relationship variable is already bound) every slot of the scan is
    /// still visited, so the caller's per-slot checks charge and fail exactly
    /// as over the owned graph; otherwise nothing can observe the rejected
    /// slots and only the touching edges are visited.
    fn edges_of<'a>(
        &'a self,
        graph: GraphRef<'a>,
        node: &Node,
        direction: ast::Direction,
        exact_scan: bool,
    ) -> Result<EdgeCandidates<'a>> {
        let index = match graph {
            GraphRef::Owned(graph) => {
                return Ok(match self.indexed_edges(graph, node, direction) {
                    Some(edges) => EdgeCandidates::Adjacent(edges),
                    None => EdgeCandidates::Scan(graph.edges.iter().enumerate()),
                });
            }
            GraphRef::Indexed(index) => index,
        };
        let Some(vertex) = index.vertex_index(node.id.as_str()) else {
            // The owned executor scans every edge and accepts none.
            return Ok(if exact_scan {
                EdgeCandidates::scan_order(index, Vec::new())
            } else {
                EdgeCandidates::Slots(index, Vec::new().into_iter())
            });
        };
        let outgoing = || typed_edge_slots(index, vertex, false);
        let incoming = || typed_edge_slots(index, vertex, true);
        let adjacent = match direction {
            ast::Direction::Outgoing => self.requirements.outgoing,
            ast::Direction::Incoming => self.requirements.incoming,
            ast::Direction::Undirected => self.requirements.outgoing && self.requirements.incoming,
        };
        let slots: Vec<u32> = match direction {
            ast::Direction::Outgoing => outgoing().into_iter().map(|(edge, _)| edge).collect(),
            ast::Direction::Incoming => incoming().into_iter().map(|(edge, _)| edge).collect(),
            ast::Direction::Undirected if adjacent => {
                // Outgoing, then incoming without self-loops already listed.
                let mut slots: Vec<u32> = outgoing().into_iter().map(|(edge, _)| edge).collect();
                slots.extend(
                    incoming()
                        .into_iter()
                        .filter(|&(_, other)| other != vertex)
                        .map(|(edge, _)| edge),
                );
                slots
            }
            ast::Direction::Undirected => {
                // Edge-vector order; a self-loop is one edge.
                let mut slots: Vec<u32> = outgoing()
                    .into_iter()
                    .chain(incoming())
                    .map(|(edge, _)| edge)
                    .collect();
                slots.sort_unstable();
                slots.dedup();
                slots
            }
        };
        Ok(if exact_scan && !adjacent {
            EdgeCandidates::scan_order(index, slots)
        } else {
            EdgeCandidates::Slots(index, slots.into_iter())
        })
    }

    fn indexed_edges<'a>(
        &'a self,
        graph: &'a Graph,
        node: &Node,
        direction: ast::Direction,
    ) -> Option<IndexedEdges<'a>> {
        let &vertex = self.by_id.get(node.id.as_str())?;
        let (first, second, skip_second_self_loops) = match direction {
            ast::Direction::Outgoing => (
                self.outgoing_by_vertex.as_ref()?.edges_for(vertex).iter(),
                None,
                false,
            ),
            ast::Direction::Incoming => (
                self.incoming_by_vertex.as_ref()?.edges_for(vertex).iter(),
                None,
                false,
            ),
            ast::Direction::Undirected => (
                self.outgoing_by_vertex.as_ref()?.edges_for(vertex).iter(),
                Some(self.incoming_by_vertex.as_ref()?.edges_for(vertex).iter()),
                true,
            ),
        };
        Some(IndexedEdges {
            graph,
            first,
            second,
            skip_second_self_loops,
        })
    }
}

fn build_compressed_adjacency(
    graph: &Graph,
    by_id: &HashMap<NodeId, usize>,
    endpoint: impl Fn(&Edge) -> &NodeId,
) -> CompressedAdjacency {
    let mut endpoints = Vec::with_capacity(graph.edges.len());
    let mut offsets = vec![0; graph.nodes.len() + 1];
    for (edge_index, edge) in graph.edges.iter().enumerate() {
        let Some(&vertex) = by_id.get(endpoint(edge).as_str()) else {
            continue;
        };
        endpoints.push((edge_index, vertex));
        offsets[vertex + 1] += 1;
    }
    for vertex in 1..offsets.len() {
        offsets[vertex] += offsets[vertex - 1];
    }
    let mut cursor = offsets[..graph.nodes.len()].to_vec();
    let mut edge_indexes = vec![0; endpoints.len()];
    for (edge_index, vertex) in endpoints {
        edge_indexes[cursor[vertex]] = edge_index;
        cursor[vertex] += 1;
    }
    CompressedAdjacency {
        offsets,
        edge_indexes,
    }
}

struct IndexedEdges<'a> {
    graph: &'a Graph,
    first: std::slice::Iter<'a, usize>,
    second: Option<std::slice::Iter<'a, usize>>,
    skip_second_self_loops: bool,
}

impl<'a> Iterator for IndexedEdges<'a> {
    type Item = (usize, &'a Edge);

    fn next(&mut self) -> Option<Self::Item> {
        if let Some(index) = self.first.next() {
            return Some((*index, &self.graph.edges[*index]));
        }
        let second = self.second.as_mut()?;
        loop {
            let slot = *second.next()?;
            let edge = &self.graph.edges[slot];
            if !self.skip_second_self_loops || edge.from != edge.to {
                return Some((slot, edge));
            }
        }
    }
}

/// `(edge slot, other endpoint)` for every edge of every type leaving
/// (`reverse`: entering) `vertex`, in edge-slot order: the order of the owned
/// executor's compressed adjacency, which lists edges by edge-vector position.
fn typed_edge_slots(index: &TypedGraphIndex, vertex: u32, reverse: bool) -> Vec<(u32, u32)> {
    let mut slots = Vec::new();
    for relationship in index.relationship_types() {
        let view = index.adjacency(relationship.as_str());
        let row = if reverse {
            view.incoming(vertex)
        } else {
            view.outgoing(vertex)
        };
        slots.extend(row.iter().map(|neighbor| (neighbor.edge, neighbor.vertex)));
    }
    slots.sort_unstable();
    slots
}

/// Relationship candidates, borrowed from an owned graph or built one at a
/// time from a typed index's source. A `None` edge is a slot visited only for
/// the checks the owned scan makes before rejecting an edge that does not
/// touch the current node.
enum EdgeCandidates<'a> {
    Adjacent(IndexedEdges<'a>),
    Scan(std::iter::Enumerate<std::slice::Iter<'a, Edge>>),
    /// Only the listed slots, each built.
    Slots(&'a TypedGraphIndex, std::vec::IntoIter<u32>),
    /// Every slot in edge-vector order; only the sorted `incident` ones built.
    ScanOrder {
        index: &'a TypedGraphIndex,
        incident: std::iter::Peekable<std::vec::IntoIter<u32>>,
        next: u32,
        end: u32,
    },
}

impl<'a> EdgeCandidates<'a> {
    fn scan_order(index: &'a TypedGraphIndex, incident: Vec<u32>) -> Self {
        Self::ScanOrder {
            index,
            incident: incident.into_iter().peekable(),
            next: 0,
            // A validated index has at most u32::MAX edges.
            end: index.edge_count() as u32,
        }
    }
}

impl<'a> Iterator for EdgeCandidates<'a> {
    type Item = (usize, Option<Cow<'a, Edge>>);

    fn next(&mut self) -> Option<Self::Item> {
        match self {
            Self::Adjacent(edges) => edges
                .next()
                .map(|(slot, edge)| (slot, Some(Cow::Borrowed(edge)))),
            Self::Scan(edges) => edges
                .next()
                .map(|(slot, edge)| (slot, Some(Cow::Borrowed(edge)))),
            Self::Slots(index, slots) => slots
                .next()
                .map(|slot| (slot as usize, Some(index.edge(slot)))),
            Self::ScanOrder {
                index,
                incident,
                next,
                end,
            } => {
                if *next >= *end {
                    return None;
                }
                let slot = *next;
                *next += 1;
                let edge = incident.next_if_eq(&slot).map(|slot| index.edge(slot));
                Some((slot as usize, edge))
            }
        }
    }
}

const FIXED_SEGMENT_ADJACENCY_THRESHOLD: usize = 64;

fn query_adjacency_requirements(query: &SingleQuery) -> AdjacencyRequirements {
    let mut segment_count = 0;
    let mut needs_adjacency = false;
    let mut requirements = AdjacencyRequirements::default();
    for clause in &query.clauses {
        let Clause::Match(pattern_match) = clause else {
            continue;
        };
        for pattern in &pattern_match.patterns {
            needs_adjacency |= pattern.shortest.is_some();
            if !pattern.segments.is_empty() && pattern.start.properties.is_none() {
                needs_adjacency = true;
            }
            for segment in &pattern.segments {
                segment_count += 1;
                needs_adjacency |= segment.relationship.length.is_some();
                match segment.relationship.direction {
                    ast::Direction::Outgoing => requirements.outgoing = true,
                    ast::Direction::Incoming => requirements.incoming = true,
                    ast::Direction::Undirected => {
                        requirements.outgoing = true;
                        requirements.incoming = true;
                    }
                }
            }
        }
    }
    // A selective fixed path can scan the contiguous edge vector cheaply. Pay
    // to build adjacency only after enough repeated hops to amortize that
    // one-time index, while unbounded starts and variable-length paths opt in
    // above regardless of their syntactic segment count.
    if !needs_adjacency && segment_count < FIXED_SEGMENT_ADJACENCY_THRESHOLD {
        return AdjacencyRequirements::default();
    }
    requirements
}

/// All variables introduced by a set of path patterns (path, node, and
/// relationship variables), in first-seen order and de-duplicated.
fn pattern_variables(patterns: &[PathPattern]) -> Vec<String> {
    let mut vars: Vec<String> = Vec::new();
    let add = |opt: &Option<String>, vars: &mut Vec<String>| {
        if let Some(name) = opt
            && !vars.iter().any(|v| v == name)
        {
            vars.push(name.clone());
        }
    };
    for pattern in patterns {
        add(&pattern.variable, &mut vars);
        add(&pattern.start.variable, &mut vars);
        for segment in &pattern.segments {
            add(&segment.relationship.variable, &mut vars);
            add(&segment.node.variable, &mut vars);
        }
    }
    vars
}

fn expand_pattern(
    graph: GraphRef<'_>,
    index: &NodeIndex,
    pattern: &PathPattern,
    base_rows: Vec<MatchRow>,
    params: &CypherParameters,
) -> Result<Vec<MatchRow>> {
    if let Some(kind) = pattern.shortest {
        return expand_shortest(graph, index, pattern, kind, base_rows, params);
    }
    let path_var = pattern.variable.as_deref();
    if path_var.is_some()
        && pattern
            .segments
            .iter()
            .any(|s| s.relationship.length.is_some())
    {
        return Err(unsupported_gql_feature(
            GqlFeature::PathVariableBinding,
            GqlConformanceProfile::PortableGql,
            "path variables over variable-length relationships are not supported by the read reference executor yet",
        ));
    }
    let mut out = Vec::new();
    for row in base_rows {
        for start in node_candidates(graph, &pattern.start, &row, params)? {
            let mut next_row = row.copy("expanding MATCH patterns")?;
            if let Some(var) = &pattern.start.variable {
                next_row.insert(
                    var.clone(),
                    Bound::Node(clone_node(&start, "binding MATCH start nodes")?.into()),
                );
            }
            let acc_nodes = if path_var.is_some() {
                vec![clone_node(&start, "starting path-node accumulation")?]
            } else {
                Vec::new()
            };
            expand_segments(
                graph,
                index,
                &pattern.segments,
                0,
                &start,
                next_row,
                params,
                path_var,
                acc_nodes,
                Vec::new(),
                &mut out,
            )?;
        }
    }
    Ok(out)
}

/// `shortestPath(…)` / `allShortestPaths(…)` over a single relationship
/// segment: per (start, end) endpoint pair, find the minimal-length simple
/// path(s) whose every hop satisfies the relationship pattern. Lengths are
/// searched from the pattern's minimum upward (iterative lengthening over the
/// existing bounded var-length enumeration), so the first hit per endpoint is
/// shortest by construction; ties are kept for `All`, first-found (in
/// deterministic edge order) for `Single`.
fn expand_shortest(
    graph: GraphRef<'_>,
    index: &NodeIndex,
    pattern: &PathPattern,
    kind: ShortestKind,
    base_rows: Vec<MatchRow>,
    params: &CypherParameters,
) -> Result<Vec<MatchRow>> {
    let [segment] = pattern.segments.as_slice() else {
        return Err(unsupported_gql_feature(
            GqlFeature::ShortestPath,
            GqlConformanceProfile::Full39075,
            "shortestPath(…) expects exactly one relationship segment",
        ));
    };
    let rel = &segment.relationship;
    let min = rel.length.map(|r| r.min.unwrap_or(1)).unwrap_or(1) as usize;
    // No `*` means exactly one hop, matching pattern semantics everywhere
    // else (`-[:R]->` is a single relationship); only an explicit `*`/`*m..`
    // leaves the upper bound open.
    let max = match rel.length {
        None => Some(1),
        Some(range) => range.max.map(|m| m as usize),
    };
    // Simple paths never repeat a node, so no shortest path is longer than
    // |nodes| - 1 hops; that caps the open-ended `*` search.
    let cap = graph.node_count().saturating_sub(1);
    let cap = max.map_or(cap, |m| m.min(cap));

    let mut out = Vec::new();
    for row in base_rows {
        match_scope::require_unbound_trail(&row, rel.variable.as_deref())?;
        for start in node_candidates(graph, &pattern.start, &row, params)? {
            // end-node id -> minimal-length edge lists, in first-found order.
            let mut resolved: BTreeMap<String, Vec<EdgeTrail>> = BTreeMap::new();
            for length in min..=cap.max(min) {
                if length > cap {
                    break;
                }
                let mut paths: Vec<(Node, EdgeTrail)> = Vec::new();
                let mut visited = std::collections::HashSet::new();
                visited.insert(start.id.as_str().to_string());
                collect_var_length_paths(
                    graph,
                    index,
                    rel,
                    &start,
                    length,
                    Some(length),
                    &mut EdgeTrail::default(),
                    &mut visited,
                    &[],
                    params,
                    &mut paths,
                )?;
                // Same-length ties accumulate here, then merge; endpoints
                // resolved at an earlier (shorter) length are skipped.
                let mut found: BTreeMap<String, Vec<EdgeTrail>> = BTreeMap::new();
                for (end, edges) in paths {
                    let end_id = end.id.as_str().to_string();
                    if resolved.contains_key(&end_id) {
                        continue;
                    }
                    if !node_matches(&end, &segment.node, params)? {
                        continue;
                    }
                    if let Some(var) = &segment.node.variable
                        && let Some(Bound::Node(bound)) = row.get(var)
                        && bound.id != end.id
                    {
                        continue;
                    }
                    found.entry(end_id).or_default().push(edges);
                }
                resolved.extend(found);
            }

            for (end_id, edge_lists) in resolved {
                let Some(end_node) = index.get(graph, &end_id) else {
                    continue;
                };
                let picked: Vec<&EdgeTrail> = match kind {
                    ShortestKind::Single => edge_lists.iter().take(1).collect(),
                    ShortestKind::All => edge_lists.iter().collect(),
                };
                for trail in picked {
                    // Preserve shortest selection (including first-found ties),
                    // then apply MATCH uniqueness. Never substitute a longer
                    // path merely because a chosen shortest path reused an edge.
                    if !row.disjoint(&trail.slots)? {
                        continue;
                    }
                    let edges = &trail.edges;
                    let mut next_row = row.copy("producing shortest-path rows")?;
                    next_row.record(&trail.slots)?;
                    if let Some(var) = &pattern.start.variable {
                        next_row.insert(
                            var.clone(),
                            Bound::Node(
                                clone_node(&start, "binding shortest-path start nodes")?.into(),
                            ),
                        );
                    }
                    if let Some(var) = &segment.node.variable {
                        next_row.insert(
                            var.clone(),
                            Bound::Node(
                                clone_node(&end_node, "binding shortest-path end nodes")?.into(),
                            ),
                        );
                    }
                    if let Some(var) = &rel.variable {
                        let mut arr = Vec::with_capacity(edges.len());
                        for edge in edges {
                            arr.push(materialize_edge_json(
                                edge,
                                "materializing shortest-path relationships",
                            )?);
                        }
                        next_row.insert(
                            var.clone(),
                            Bound::Value(Value::Json(serde_json::Value::Array(arr))),
                        );
                    }
                    if let Some(path_var) = &pattern.variable {
                        let nodes = walk_path_nodes(graph, index, &start, edges, rel.direction)?;
                        next_row.insert(path_var.clone(), Bound::Value(path_value(&nodes, edges)?));
                    }
                    read_budget::charge_candidate_work(1, "producing shortest-path rows")?;
                    out.push(next_row);
                }
            }
        }
    }
    Ok(out)
}

/// Reconstruct the node sequence of a path from its start node and edge list.
fn walk_path_nodes(
    graph: GraphRef<'_>,
    index: &NodeIndex,
    start: &Node,
    edges: &[Edge],
    direction: ast::Direction,
) -> Result<Vec<Node>> {
    let mut nodes = vec![clone_node(start, "reconstructing shortest-path nodes")?];
    let mut current = clone_node(start, "tracking shortest-path endpoints")?;
    for edge in edges {
        let next_id = edge_other_endpoint(edge, &current, direction)
            .ok_or_else(|| gql_execution("shortest path edge does not connect to the path"))?;
        let next = index
            .get(graph, next_id)
            .ok_or_else(|| gql_execution("shortest path endpoint node not found"))?;
        nodes.push(clone_node(&next, "reconstructing shortest-path nodes")?);
        current = clone_node(&next, "tracking shortest-path endpoints")?;
    }
    Ok(nodes)
}

/// A bound first-class path value. `Value::to_json` preserves the historical
/// `{ "nodes": [...], "relationships": [...] }` serialization shape.
fn path_value(nodes: &[Node], edges: &[Edge]) -> Result<Value> {
    charge_intermediate_copy("materializing path values", || {
        nodes
            .iter()
            .fold(0usize, |bytes, node| {
                bytes.saturating_add(read_budget::node_copy_bytes(node))
            })
            .saturating_add(edges.iter().fold(0usize, |bytes, edge| {
                bytes.saturating_add(read_budget::edge_copy_bytes(edge))
            }))
    })?;
    Ok(Value::Path(PathValue::from_graph_parts(nodes, edges)))
}

#[allow(clippy::too_many_arguments)]
fn expand_segments(
    graph: GraphRef<'_>,
    index: &NodeIndex,
    segments: &[PathSegment],
    idx: usize,
    current: &Node,
    row: MatchRow,
    params: &CypherParameters,
    path_var: Option<&str>,
    acc_nodes: Vec<Node>,
    acc_edges: Vec<Edge>,
    out: &mut Vec<MatchRow>,
) -> Result<()> {
    if idx == segments.len() {
        let mut row = row;
        if let Some(p) = path_var {
            row.insert(
                p.to_string(),
                Bound::Value(path_value(&acc_nodes, &acc_edges)?),
            );
        }
        read_budget::charge_candidate_work(1, "producing MATCH rows")?;
        out.push(row);
        return Ok(());
    }
    let segment = &segments[idx];
    let rel = &segment.relationship;

    // Variable-length relationship: expand bounded paths (no repeated nodes, so
    // the search is finite even with an open upper bound). The relationship
    // variable binds to the list of traversed edges.
    if let Some(range) = rel.length {
        match_scope::require_unbound_trail(&row, rel.variable.as_deref())?;
        let min = range.min.unwrap_or(1) as usize;
        let max = range.max.map(|m| m as usize);
        let mut paths: Vec<(Node, EdgeTrail)> = Vec::new();
        let mut visited = std::collections::HashSet::new();
        visited.insert(current.id.as_str().to_string());
        collect_var_length_paths(
            graph,
            index,
            rel,
            current,
            min,
            max,
            &mut EdgeTrail::default(),
            &mut visited,
            row.slots(),
            params,
            &mut paths,
        )?;
        for (end_node, trail) in paths {
            if !node_matches(&end_node, &segment.node, params)? {
                continue;
            }
            if let Some(var) = &segment.node.variable
                && let Some(Bound::Node(bound)) = row.get(var)
                && bound.id != end_node.id
            {
                continue;
            }
            let mut next_row = row.copy("expanding variable-length paths")?;
            next_row.record(&trail.slots)?;
            let edges = trail.edges;
            if let Some(var) = &rel.variable {
                let mut arr = Vec::with_capacity(edges.len());
                for edge in &edges {
                    arr.push(materialize_edge_json(
                        edge,
                        "materializing variable-length relationships",
                    )?);
                }
                next_row.insert(
                    var.clone(),
                    Bound::Value(Value::Json(serde_json::Value::Array(arr))),
                );
            }
            if let Some(var) = &segment.node.variable {
                next_row.insert(
                    var.clone(),
                    Bound::Node(
                        clone_node(&end_node, "binding variable-length path endpoints")?.into(),
                    ),
                );
            }
            // path_var is guaranteed None here (rejected with variable-length).
            expand_segments(
                graph,
                index,
                segments,
                idx + 1,
                &end_node,
                next_row,
                params,
                path_var,
                clone_nodes(&acc_nodes, "carrying path-node accumulators")?,
                clone_edges(&acc_edges, "carrying path-edge accumulators")?,
                out,
            )?;
        }
        return Ok(());
    }

    // A bound relationship variable makes every scanned slot observable:
    // `fixed_binding_matches` can refuse it before its endpoints are read.
    let exact_scan = read_budget::intermediate_accounting_active()
        || rel
            .variable
            .as_ref()
            .is_some_and(|name| row.contains_key(name));
    let edges = index.edges_of(graph, current, rel.direction, exact_scan)?;
    expand_fixed_edges(
        edges, graph, index, segments, idx, current, &row, params, path_var, &acc_nodes,
        &acc_edges, out,
    )
}

#[allow(clippy::too_many_arguments)]
fn expand_fixed_edges<'a>(
    edges: impl Iterator<Item = (usize, Option<Cow<'a, Edge>>)>,
    graph: GraphRef<'_>,
    index: &NodeIndex,
    segments: &[PathSegment],
    idx: usize,
    current: &Node,
    row: &MatchRow,
    params: &CypherParameters,
    path_var: Option<&str>,
    acc_nodes: &[Node],
    acc_edges: &[Edge],
    out: &mut Vec<MatchRow>,
) -> Result<()> {
    let segment = &segments[idx];
    let rel = &segment.relationship;
    for (slot, edge) in edges {
        read_budget::charge_candidate_work(1, "scanning relationship candidates")?;
        if row.contains(slot)? {
            continue;
        }
        if !match_scope::fixed_binding_matches(row, rel.variable.as_deref(), slot)? {
            continue;
        }
        // An unbuilt slot does not touch `current`: the endpoint test rejects it.
        let Some(edge) = edge else {
            continue;
        };
        let Some(next_id) = edge_other_endpoint(&edge, current, rel.direction) else {
            continue;
        };
        if !rel.types.is_empty() && !rel.types.iter().any(|t| t == edge.label.as_str()) {
            continue;
        }
        if !props_match(&edge.props, rel.properties.as_ref(), params)? {
            continue;
        }
        let Some(next_node) = index.get(graph, next_id) else {
            continue;
        };
        if !node_matches(&next_node, &segment.node, params)? {
            continue;
        }
        // consistency with an already-bound next-node variable
        if let Some(var) = &segment.node.variable
            && let Some(Bound::Node(bound)) = row.get(var)
            && bound.id != next_node.id
        {
            continue;
        }
        let mut next_row = row.copy("expanding fixed relationship segments")?;
        next_row.record(&[slot])?;
        if let Some(var) = &rel.variable {
            next_row.insert(
                var.clone(),
                Bound::Edge(
                    clone_edge(&edge, "binding matched relationships")?.into(),
                    Some(slot),
                ),
            );
        }
        if let Some(var) = &segment.node.variable {
            next_row.insert(
                var.clone(),
                Bound::Node(clone_node(&next_node, "binding matched nodes")?.into()),
            );
        }
        let (na, ea) = if path_var.is_some() {
            let mut na = clone_nodes(acc_nodes, "carrying path-node accumulators")?;
            na.push(clone_node(&next_node, "extending path-node accumulators")?);
            let mut ea = clone_edges(acc_edges, "carrying path-edge accumulators")?;
            ea.push(clone_edge(&edge, "extending path-edge accumulators")?);
            (na, ea)
        } else {
            (Vec::new(), Vec::new())
        };
        expand_segments(
            graph,
            index,
            segments,
            idx + 1,
            &next_node,
            next_row,
            params,
            path_var,
            na,
            ea,
            out,
        )?;
    }
    Ok(())
}

/// Depth-first collection of variable-length paths from `node`. Records `(end,
/// edges)` for every prefix whose length is within `[min, max]`. Nodes are not
/// revisited within a path, so the search terminates even when `max` is open.
#[allow(clippy::too_many_arguments)]
fn collect_var_length_paths(
    graph: GraphRef<'_>,
    index: &NodeIndex,
    rel: &RelationshipPattern,
    node: &Node,
    min: usize,
    max: Option<usize>,
    edges_so_far: &mut EdgeTrail,
    visited: &mut std::collections::HashSet<String>,
    used_slots: &[usize],
    params: &CypherParameters,
    results: &mut Vec<(Node, EdgeTrail)>,
) -> Result<()> {
    let depth = edges_so_far.edges.len();
    if depth >= min {
        read_budget::charge_candidate_work(1, "collecting variable-length paths")?;
        results.push((
            clone_node(node, "collecting variable-length path endpoints")?,
            edges_so_far.copy()?,
        ));
    }
    if max.is_some_and(|m| depth >= m) {
        return Ok(());
    }
    let exact_scan = read_budget::intermediate_accounting_active();
    let edges = index.edges_of(graph, node, rel.direction, exact_scan)?;
    collect_var_length_edges(
        edges,
        graph,
        index,
        rel,
        node,
        min,
        max,
        edges_so_far,
        visited,
        used_slots,
        params,
        results,
    )
}

#[allow(clippy::too_many_arguments)]
fn collect_var_length_edges<'a>(
    edges: impl Iterator<Item = (usize, Option<Cow<'a, Edge>>)>,
    graph: GraphRef<'_>,
    index: &NodeIndex,
    rel: &RelationshipPattern,
    node: &Node,
    min: usize,
    max: Option<usize>,
    edges_so_far: &mut EdgeTrail,
    visited: &mut std::collections::HashSet<String>,
    used_slots: &[usize],
    params: &CypherParameters,
    results: &mut Vec<(Node, EdgeTrail)>,
) -> Result<()> {
    for (slot, edge) in edges {
        read_budget::charge_candidate_work(1, "searching variable-length paths")?;
        if match_scope::contains(used_slots, slot)? {
            continue;
        }
        // An unbuilt slot does not touch `node`: the endpoint test rejects it.
        let Some(edge) = edge else {
            continue;
        };
        let Some(next_id) = edge_other_endpoint(&edge, node, rel.direction) else {
            continue;
        };
        if !rel.types.is_empty() && !rel.types.iter().any(|t| t == edge.label.as_str()) {
            continue;
        }
        if !props_match(&edge.props, rel.properties.as_ref(), params)? {
            continue;
        }
        if visited.contains(next_id) {
            continue;
        }
        let Some(next_node) = index.get(graph, next_id) else {
            continue;
        };
        edges_so_far.push(slot, &edge)?;
        visited.insert(next_id.to_string());
        collect_var_length_paths(
            graph,
            index,
            rel,
            &next_node,
            min,
            max,
            edges_so_far,
            visited,
            used_slots,
            params,
            results,
        )?;
        visited.remove(next_id);
        edges_so_far.pop();
    }
    Ok(())
}

/// The id of the endpoint reached from `current` along `edge` given `direction`,
/// or `None` if `edge` does not connect to `current` in that direction.
fn edge_other_endpoint<'e>(
    edge: &'e Edge,
    current: &Node,
    direction: ast::Direction,
) -> Option<&'e str> {
    let from = edge.from.as_str();
    let to = edge.to.as_str();
    let cur = current.id.as_str();
    match direction {
        ast::Direction::Outgoing => (from == cur).then_some(to),
        ast::Direction::Incoming => (to == cur).then_some(from),
        ast::Direction::Undirected => {
            if from == cur {
                Some(to)
            } else if to == cur {
                Some(from)
            } else {
                None
            }
        }
    }
}

fn node_candidates(
    graph: GraphRef<'_>,
    np: &NodePattern,
    row: &Row,
    params: &CypherParameters,
) -> Result<Vec<Node>> {
    // Already bound? Filter to the bound node if it still matches.
    if let Some(var) = &np.variable
        && let Some(Bound::Node(bound)) = row.get(var)
    {
        read_budget::charge_candidate_work(1, "checking a bound node candidate")?;
        return Ok(if node_matches(bound, np, params)? {
            vec![clone_node(bound, "retaining bound node candidates")?]
        } else {
            vec![]
        });
    }
    let mut out = Vec::new();
    match graph {
        GraphRef::Owned(graph) => {
            for node in &graph.nodes {
                read_budget::charge_candidate_work(1, "scanning node candidates")?;
                if node_matches(node, np, params)? {
                    out.push(clone_node(node, "collecting matched node candidates")?);
                }
            }
        }
        GraphRef::Indexed(index) => {
            // Test labels and properties in place; build only the matches.
            for slot in 0..index.node_count() as u32 {
                read_budget::charge_candidate_work(1, "scanning node candidates")?;
                if node_slot_matches(index, slot, np, params)? {
                    out.push(clone_node(
                        &index.node(slot),
                        "collecting matched node candidates",
                    )?);
                }
            }
        }
    }
    Ok(out)
}

/// [`node_matches`] for the node in `slot`, read in place.
fn node_slot_matches(
    index: &TypedGraphIndex,
    slot: u32,
    np: &NodePattern,
    params: &CypherParameters,
) -> Result<bool> {
    let label = index.node_label(slot);
    for wanted in &np.labels {
        if label.as_str() != wanted {
            return Ok(false);
        }
    }
    props_match_by(
        |key| index.node_property(slot, key),
        np.properties.as_ref(),
        params,
    )
}

fn node_matches(node: &Node, np: &NodePattern, params: &CypherParameters) -> Result<bool> {
    // Conjunctive label semantics: every listed label must hold. Grust nodes
    // carry a single label, so `(n:A:B)` with distinct labels is simply
    // unsatisfiable — the same result Neo4j gives over singly-labeled nodes.
    for label in &np.labels {
        if node.label.as_str() != label {
            return Ok(false);
        }
    }
    props_match(&node.props, np.properties.as_ref(), params)
}

/// True when every entry in the inline pattern map equals the element's property.
fn props_match(props: &Props, map: Option<&MapLiteral>, params: &CypherParameters) -> Result<bool> {
    props_match_by(|key| props.get(key).map(Cow::Borrowed), map, params)
}

/// [`props_match`] over an element whose properties are read one key at a time.
fn props_match_by<'v>(
    get: impl Fn(&str) -> Option<Cow<'v, Value>>,
    map: Option<&MapLiteral>,
    params: &CypherParameters,
) -> Result<bool> {
    let Some(map) = map else {
        return Ok(true);
    };
    for (key, expr) in &map.entries {
        // Scalar-literal shortcuts still perform work and must retain the
        // cooperative checkpoint previously supplied by eval_constant.
        read_budget::charge_candidate_work(1, "checking inline property predicates")?;
        // Pure scalar literals can be compared by borrowing the graph value;
        // do not clone a large JSON property merely to reject its scalar type.
        if matches!(
            expr,
            Expr::Null | Expr::Boolean(_) | Expr::Integer(_) | Expr::Float(_) | Expr::String(_)
        ) {
            match get(key) {
                Some(actual) if count_predicate::literal_equal(&actual, expr)? => continue,
                _ => return Ok(false),
            }
        }
        // Preserve expression/parameter errors even when the property is absent.
        let expected = eval_constant(expr, params)?;
        match get(key) {
            Some(actual) if property_equality::checked(&actual, &expected)? == Some(true) => {}
            _ => return Ok(false),
        }
    }
    Ok(true)
}

// ---------------------------------------------------------------------------
// Projection
// ---------------------------------------------------------------------------

fn project(
    graph: GraphRef<'_>,
    rows: &[Row],
    projection: &Projection,
    params: &CypherParameters,
) -> Result<CypherResultTable> {
    let _ = graph;
    // Resolve which items to project (star expands to bound variables, sorted).
    let mut columns: Vec<String> = Vec::new();
    let mut exprs: Vec<Expr> = Vec::new();

    if projection.star {
        let mut vars: BTreeMap<String, ()> = BTreeMap::new();
        for row in rows {
            for var in row.keys() {
                vars.insert(var.clone(), ());
            }
        }
        for var in vars.keys() {
            columns.push(var.clone());
            exprs.push(Expr::Variable(var.clone()));
        }
    }
    for item in &projection.items {
        columns.push(
            item.alias
                .clone()
                .unwrap_or_else(|| column_name(&item.expr)),
        );
        exprs.push(item.expr.clone());
    }
    if exprs.is_empty() {
        return Err(gql_syntax("RETURN requires at least one item"));
    }

    // alias -> expr, so ORDER BY can reference output aliases.
    let aliases: HashMap<String, Expr> = projection
        .items
        .iter()
        .filter_map(|i| i.alias.clone().map(|a| (a, i.expr.clone())))
        .collect();

    let has_aggregate = exprs.iter().any(expr_has_aggregate);

    let mut out_rows: Vec<Vec<Value>> = if has_aggregate {
        // `RETURN *` was already expanded into `exprs` above, so the star's
        // variables participate as grouping keys.
        grouped_project(&exprs, rows, params)?
    } else {
        let mut rs = Vec::with_capacity(rows.len());
        for row in rows {
            read_budget::charge_candidate_work(1, "projecting RETURN rows")?;
            let mut values = Vec::with_capacity(exprs.len());
            for expr in &exprs {
                values.push(eval(expr, row, params)?);
            }
            rs.push(values);
        }
        rs
    };

    if projection.distinct {
        let mut seen = std::collections::HashSet::new();
        let mut deduped = Vec::new();
        for values in out_rows {
            let key = return_row_key(&values, "RETURN DISTINCT")?;
            if seen.insert(key) {
                deduped.push(values);
            }
        }
        out_rows = deduped;
    }

    if has_aggregate {
        // Grouped rows no longer align with the source bindings, so ORDER BY
        // resolves against the output columns instead.
        order_by_columns(&mut out_rows, &columns, &projection.order_by)?;
    } else if projection.distinct {
        // Deduped rows no longer align 1:1 with the source bindings either:
        // keys must resolve to projected items (by exact expression, output
        // alias, or rendered column name).
        order_after_distinct(&mut out_rows, &columns, &exprs, &projection.order_by)?;
    } else {
        apply_order_by(&mut out_rows, &projection.order_by, rows, &aliases, params)?;
    }
    apply_skip_limit(&mut out_rows, projection, params)?;

    Ok(CypherResultTable {
        columns,
        rows: out_rows,
    })
}

/// Aggregate function names recognized by the read reference executor.
fn is_aggregate_name(name: &str) -> bool {
    matches!(
        name.to_ascii_lowercase().as_str(),
        "count" | "sum" | "avg" | "min" | "max" | "collect"
    )
}

/// True if `expr` contains an aggregate function call anywhere.
pub(crate) fn expr_has_aggregate(expr: &Expr) -> bool {
    match expr {
        Expr::Function { name, args, .. } => {
            is_aggregate_name(name) || args.iter().any(expr_has_aggregate)
        }
        Expr::Property { base, .. } => expr_has_aggregate(base),
        Expr::Index { base, index } => expr_has_aggregate(base) || expr_has_aggregate(index),
        Expr::List(items) => items.iter().any(expr_has_aggregate),
        Expr::Map(entries) => entries.iter().any(|(_, e)| expr_has_aggregate(e)),
        Expr::Unary { operand, .. } => expr_has_aggregate(operand),
        Expr::Binary { lhs, rhs, .. } => expr_has_aggregate(lhs) || expr_has_aggregate(rhs),
        Expr::IsNull { operand, .. } => expr_has_aggregate(operand),
        Expr::Case {
            operand,
            branches,
            default,
        } => {
            operand.as_deref().is_some_and(expr_has_aggregate)
                || branches
                    .iter()
                    .any(|b| expr_has_aggregate(&b.when) || expr_has_aggregate(&b.then))
                || default.as_deref().is_some_and(expr_has_aggregate)
        }
        _ => false,
    }
}

/// Group rows by the non-aggregate (grouping-key) projection items and fold the
/// aggregate items per group. Each item must be either aggregate-free (a key) or
/// a single top-level aggregate call; nested aggregates are not supported.
fn grouped_project(
    exprs: &[Expr],
    rows: &[Row],
    params: &CypherParameters,
) -> Result<Vec<Vec<Value>>> {
    enum Kind<'a> {
        Key(&'a Expr),
        Aggregate(&'a Expr),
    }
    let mut kinds = Vec::with_capacity(exprs.len());
    for expr in exprs {
        match expr {
            Expr::Function { name, .. } if is_aggregate_name(name) => {
                kinds.push(Kind::Aggregate(expr))
            }
            _ if expr_has_aggregate(expr) => {
                return Err(unsupported_gql_feature(
                    GqlFeature::AggregateFunctionRegistry,
                    GqlConformanceProfile::PortableGql,
                    "aggregates nested inside larger expressions are not supported by the read reference executor yet",
                ));
            }
            _ => kinds.push(Kind::Key(expr)),
        }
    }

    let key_exprs: Vec<&Expr> = kinds
        .iter()
        .filter_map(|k| match k {
            Kind::Key(e) => Some(*e),
            Kind::Aggregate(_) => None,
        })
        .collect();

    // Group rows, preserving first-seen order for deterministic output.
    let mut order: Vec<String> = Vec::new();
    let mut groups: HashMap<String, (Vec<Value>, Vec<&Row>)> = HashMap::new();
    for row in rows {
        read_budget::charge_candidate_work(1, "grouping RETURN rows")?;
        let key_values: Vec<Value> = key_exprs
            .iter()
            .map(|e| eval(e, row, params))
            .collect::<Result<_>>()?;
        let key = return_row_key(&key_values, "GROUP BY")?;
        match groups.entry(key) {
            std::collections::hash_map::Entry::Occupied(mut entry) => {
                entry.get_mut().1.push(row);
            }
            std::collections::hash_map::Entry::Vacant(entry) => {
                read_budget::charge_intermediate_bytes(
                    entry.key().len(),
                    "recording RETURN grouping order",
                )?;
                order.push(entry.key().clone());
                entry.insert((key_values, vec![row]));
            }
        }
    }

    // A pure aggregate with no grouping keys yields exactly one row even over an
    // empty match (e.g. `RETURN count(*)` -> 0).
    if key_exprs.is_empty() && rows.is_empty() {
        order.push(String::new());
        groups.insert(String::new(), (Vec::new(), Vec::new()));
    }

    let mut out_rows = Vec::with_capacity(order.len());
    for key in &order {
        let (key_values, group_rows) = groups
            .remove(key)
            .expect("RETURN grouping order references an existing group");
        let mut key_iter = key_values.into_iter();
        let mut values = Vec::with_capacity(kinds.len());
        for kind in &kinds {
            match kind {
                Kind::Key(_) => values.push(key_iter.next().unwrap_or(Value::Null)),
                Kind::Aggregate(expr) => values.push(eval_aggregate(expr, &group_rows, params)?),
            }
        }
        read_budget::charge_candidate_work(1, "producing grouped RETURN rows")?;
        out_rows.push(values);
    }
    Ok(out_rows)
}

fn eval_aggregate(expr: &Expr, group_rows: &[&Row], params: &CypherParameters) -> Result<Value> {
    let Expr::Function {
        name,
        distinct,
        star,
        args,
    } = expr
    else {
        unreachable!("eval_aggregate called on a non-function expression");
    };
    let name = name.to_ascii_lowercase();

    if name == "count" && *star {
        let value = count_value(group_rows.len())?;
        charge_intermediate_copy("materializing aggregate results", || {
            read_budget::value_copy_bytes(&value)
        })?;
        return Ok(value);
    }
    if args.len() != 1 {
        return Err(gql_type(format!(
            "aggregate {name}() expects exactly one argument"
        )));
    }
    let arg = &args[0];

    // Evaluate the argument per row, dropping NULLs (standard aggregate rule).
    let mut values: Vec<Value> = Vec::with_capacity(group_rows.len());
    for row in group_rows {
        if let Some(v) = non_null_return_value(eval(arg, row, params)?) {
            values.push(v);
        }
    }
    if *distinct {
        values = distinct_return_values(values)?;
    }

    let value = match name.as_str() {
        "count" => count_value(values.len()),
        "sum" => sum_return_values(&values),
        "avg" => avg_return_values(&values),
        "collect" => {
            read_budget::check_intermediate_bytes_available(
                values
                    .len()
                    .saturating_mul(std::mem::size_of::<serde_json::Value>()),
                "materializing collect()",
            )?;
            let json: Vec<serde_json::Value> = values.into_iter().map(value_into_json).collect();
            Ok(Value::Json(serde_json::Value::Array(json)))
        }
        "min" | "max" => {
            let want_max = name == "max";
            let mut best: Option<Value> = None;
            for v in values {
                best = Some(match best {
                    None => v,
                    Some(current) => {
                        let ord = compare_return_values(&v, &current);
                        let pick_v = if want_max { ord.is_gt() } else { ord.is_lt() };
                        if pick_v { v } else { current }
                    }
                });
            }
            Ok(best.unwrap_or(Value::Null))
        }
        _ => unreachable!("is_aggregate_name gates the set"),
    }?;
    charge_intermediate_copy("materializing aggregate results", || {
        read_budget::value_copy_bytes(&value)
    })?;
    Ok(value)
}

/// ORDER BY for the aggregate path: keys must reference output columns by name.
fn order_by_columns(
    out_rows: &mut [Vec<Value>],
    columns: &[String],
    order_by: &[OrderItem],
) -> Result<()> {
    if order_by.is_empty() {
        return Ok(());
    }
    let mut keys = Vec::with_capacity(order_by.len());
    for item in order_by {
        let name = match &item.expr {
            Expr::Variable(name) => name.clone(),
            Expr::Property { base, key } => format!("{}.{}", column_name(base), key),
            _ => {
                return Err(unsupported_gql_feature(
                    GqlFeature::AggregateFunctionRegistry,
                    GqlConformanceProfile::PortableGql,
                    "ORDER BY with aggregates must reference an output column by name",
                ));
            }
        };
        let idx = columns.iter().position(|c| c == &name).ok_or_else(|| {
            gql_name(format!(
                "ORDER BY column `{name}` is not in the RETURN list"
            ))
        })?;
        keys.push((idx, item.descending));
    }
    out_rows.sort_by(|a, b| {
        for (idx, descending) in &keys {
            let ord = compare_return_values(&a[*idx], &b[*idx]);
            let ord = if *descending { ord.reverse() } else { ord };
            if ord != std::cmp::Ordering::Equal {
                return ord;
            }
        }
        std::cmp::Ordering::Equal
    });
    Ok(())
}

/// `ORDER BY` after `RETURN DISTINCT`: sort the deduplicated output rows by
/// projected columns. Each key must match a projected item — the exact
/// expression, an output alias, or the rendered column name — since the
/// source binding rows no longer align with the deduplicated output.
fn order_after_distinct(
    out_rows: &mut [Vec<Value>],
    columns: &[String],
    exprs: &[Expr],
    order_by: &[OrderItem],
) -> Result<()> {
    if order_by.is_empty() {
        return Ok(());
    }
    let mut keys = Vec::with_capacity(order_by.len());
    for item in order_by {
        let idx = exprs
            .iter()
            .position(|e| e == &item.expr)
            .or_else(|| {
                let name = match &item.expr {
                    Expr::Variable(name) => name.clone(),
                    other => column_name(other),
                };
                columns.iter().position(|c| c == &name)
            })
            .ok_or_else(|| {
                gql_name(
                    "with DISTINCT, ORDER BY must reference a projected item (by alias or the same expression)",
                )
            })?;
        keys.push((idx, item.descending));
    }
    out_rows.sort_by(|a, b| {
        for (idx, descending) in &keys {
            let ord = compare_return_values(&a[*idx], &b[*idx]);
            let ord = if *descending { ord.reverse() } else { ord };
            if ord != std::cmp::Ordering::Equal {
                return ord;
            }
        }
        std::cmp::Ordering::Equal
    });
    Ok(())
}

fn apply_order_by(
    out_rows: &mut Vec<Vec<Value>>,
    order_by: &[OrderItem],
    rows: &[Row],
    aliases: &HashMap<String, Expr>,
    params: &CypherParameters,
) -> Result<()> {
    if order_by.is_empty() {
        return Ok(());
    }
    // Compute sort keys against the source bindings (resolving aliases).
    let mut keyed: Vec<(usize, Vec<Value>)> = Vec::with_capacity(rows.len());
    for (i, row) in rows.iter().enumerate() {
        let mut keys = Vec::with_capacity(order_by.len());
        for item in order_by {
            let expr = match &item.expr {
                Expr::Variable(name) if aliases.contains_key(name) => &aliases[name],
                other => other,
            };
            keys.push(eval(expr, row, params)?);
        }
        keyed.push((i, keys));
    }
    // Sort indices, then reorder out_rows to match. rows and out_rows align 1:1
    // only when there is no DISTINCT; guard that.
    if keyed.len() != out_rows.len() {
        return Err(gql_execution(
            "ORDER BY with DISTINCT is not supported by the read reference executor yet",
        ));
    }
    let mut order: Vec<usize> = (0..out_rows.len()).collect();
    order.sort_by(|&a, &b| {
        for (k, item) in order_by.iter().enumerate() {
            let ord = compare_return_values(&keyed[a].1[k], &keyed[b].1[k]);
            let ord = if item.descending { ord.reverse() } else { ord };
            if ord != std::cmp::Ordering::Equal {
                return ord;
            }
        }
        std::cmp::Ordering::Equal
    });
    read_budget::charge_intermediate_bytes(
        out_rows
            .len()
            .saturating_mul(std::mem::size_of::<Vec<Value>>()),
        "reordering RETURN rows",
    )?;
    let mut original = std::mem::take(out_rows)
        .into_iter()
        .map(Some)
        .collect::<Vec<_>>();
    *out_rows = order
        .into_iter()
        .map(|index| original[index].take().expect("ORDER BY index is unique"))
        .collect();
    Ok(())
}

fn apply_skip_limit(
    out_rows: &mut Vec<Vec<Value>>,
    projection: &Projection,
    params: &CypherParameters,
) -> Result<()> {
    if let Some(skip) = &projection.skip {
        let n = eval_usize(skip, params, "SKIP")?;
        out_rows.drain(0..n.min(out_rows.len()));
    }
    if let Some(limit) = &projection.limit {
        let n = eval_usize(limit, params, "LIMIT")?;
        out_rows.truncate(n);
    }
    Ok(())
}

fn column_name(expr: &Expr) -> String {
    match expr {
        Expr::Variable(name) => name.clone(),
        Expr::Property { base, key } => format!("{}.{}", column_name(base), key),
        Expr::Parameter(name) => format!("${name}"),
        _ => "expr".to_string(),
    }
}

// ---------------------------------------------------------------------------
// Expression evaluation (bounded; general engine is Unit 7)
// ---------------------------------------------------------------------------

/// Evaluate an expression that must be a constant (no bound variables) — used
/// for inline pattern-map values.
fn eval_constant(expr: &Expr, params: &CypherParameters) -> Result<Value> {
    eval(expr, &Row::new(), params)
}

fn eval_usize(expr: &Expr, params: &CypherParameters, what: &str) -> Result<usize> {
    match eval(expr, &Row::new(), params)? {
        Value::Int(n) if n >= 0 => Ok(n as usize),
        other => Err(gql_type(format!(
            "{what} expects a non-negative integer, got {other:?}"
        ))),
    }
}

fn eval(expr: &Expr, row: &Row, params: &CypherParameters) -> Result<Value> {
    read_budget::checkpoint()?;
    let value = match expr {
        Expr::Null => Ok(Value::Null),
        Expr::Boolean(b) => Ok(Value::Bool(*b)),
        Expr::Integer(n) => Ok(Value::Int(*n)),
        Expr::Float(f) => Ok(Value::Float(*f)),
        Expr::String(s) => Ok(Value::String(s.clone())),
        Expr::Parameter(name) => match params.get(name) {
            Some(value) => clone_value(value, "reading query parameters"),
            None => Err(gql_name(format!("parameter ${name} was not provided"))),
        },
        Expr::Variable(name) => row
            .get(name)
            .ok_or_else(|| gql_name(format!("variable `{name}` is not bound")))
            .and_then(bound_value),
        Expr::Property { base, key } => eval_property(base, key, row, params),
        Expr::List(items) => {
            let mut out = Vec::new();
            for item in items {
                out.push(value_into_json(eval(item, row, params)?));
            }
            Ok(Value::Json(serde_json::Value::Array(out)))
        }
        Expr::Unary { op, operand } => eval_unary(*op, operand, row, params),
        Expr::Binary { op, lhs, rhs } => eval_binary(*op, lhs, rhs, row, params),
        Expr::IsNull { operand, negated } => {
            let is_null = matches!(eval(operand, row, params)?, Value::Null);
            Ok(Value::Bool(is_null != *negated))
        }
        Expr::Function {
            name,
            distinct,
            star,
            args,
        } => {
            if is_aggregate_name(name) {
                return Err(gql_execution(format!(
                    "aggregate {name}() is only allowed as a top-level RETURN item"
                )));
            }
            if *star || *distinct {
                return Err(unsupported_gql_feature(
                    GqlFeature::ScalarFunctionRegistry,
                    GqlConformanceProfile::PortableGql,
                    format!("`{name}(DISTINCT ...)`/`{name}(*)` is not a scalar function form"),
                ));
            }
            eval_scalar_function(name, args, row, params)
        }
        Expr::Case {
            operand,
            branches,
            default,
        } => eval_case(
            operand.as_deref(),
            branches,
            default.as_deref(),
            row,
            params,
        ),
        Expr::Map(entries) => {
            let mut out = serde_json::Map::new();
            for (key, expr) in entries {
                out.insert(key.clone(), value_into_json(eval(expr, row, params)?));
            }
            Ok(Value::Json(serde_json::Value::Object(out)))
        }
        Expr::Index { base, index } => indexing::evaluate(base, index, row, params),
    }?;
    charge_intermediate_copy("materializing expression results", || {
        read_budget::value_copy_bytes(&value)
    })?;
    Ok(value)
}

/// Flatten a list-shaped value into a vector of element `Value`s.
fn list_elements(value: Value) -> Vec<Value> {
    match value {
        Value::StringArray(xs) => xs.into_iter().map(Value::String).collect(),
        Value::IntArray(xs) => xs.into_iter().map(Value::Int).collect(),
        Value::FloatArray(xs) => xs.into_iter().map(Value::Float).collect(),
        Value::Json(serde_json::Value::Array(arr)) => {
            arr.into_iter().map(Value::from_json).collect()
        }
        _ => Vec::new(),
    }
}

/// `range(start, end[, step])` -> inclusive integer list.
fn eval_range(args: &[Expr], row: &Row, params: &CypherParameters) -> Result<Value> {
    if args.len() < 2 || args.len() > 3 {
        return Err(gql_type(
            "range() expects 2 or 3 integer arguments".to_string(),
        ));
    }
    let int_arg = |e: &Expr| -> Result<i64> {
        match eval(e, row, params)? {
            Value::Int(n) => Ok(n),
            other => Err(gql_type(format!("range() expects integers, got {other:?}"))),
        }
    };
    let start = int_arg(&args[0])?;
    let end = int_arg(&args[1])?;
    let step = if args.len() == 3 {
        int_arg(&args[2])?
    } else {
        1
    };
    if step == 0 {
        return Err(gql_execution("range() step must not be zero"));
    }
    let progresses = (step > 0 && start <= end) || (step < 0 && start >= end);
    if !progresses {
        return Ok(Value::IntArray(Vec::new()));
    }

    // Widen before subtraction/multiplication so both i64 extrema and a step
    // of i64::MIN are handled without debug panics or release-mode wrapping.
    let distance = if step > 0 {
        i128::from(end) - i128::from(start)
    } else {
        i128::from(start) - i128::from(end)
    };
    let step_magnitude = i128::from(step).abs();
    let count_i128 = distance / step_magnitude + 1;
    let count = usize::try_from(count_i128).unwrap_or(usize::MAX);
    read_budget::check_range_items(count)?;
    read_budget::check_intermediate_bytes_available(
        count.saturating_mul(std::mem::size_of::<i64>()),
        "allocating range()",
    )?;

    let mut out = Vec::with_capacity(count);
    for offset in 0..count {
        let value = i128::from(start) + i128::from(step) * offset as i128;
        let value = i64::try_from(value)
            .map_err(|_| gql_execution("range() value exceeded the integer domain"))?;
        out.push(value);
    }
    Ok(Value::IntArray(out))
}

/// `labels(n)` / `type(r)` / `id(n)`: read the element from its binding, or fall
/// back to the element's serialized JSON shape.
fn eval_element_function(
    name: &str,
    arg: &Expr,
    row: &Row,
    params: &CypherParameters,
) -> Result<Value> {
    if let Expr::Variable(v) = arg {
        match row.get(v) {
            Some(Bound::Node(n)) => {
                return Ok(match name {
                    "labels" => Value::StringArray(vec![n.label.as_str().to_string()]),
                    "id" => Value::String(n.id.as_str().to_string()),
                    _ => return Err(gql_type(format!("{name}() is not defined for a node"))),
                });
            }
            Some(Bound::Edge(e, _)) => {
                return Ok(match name {
                    "type" => Value::String(e.label.as_str().to_string()),
                    "id" => {
                        e.id.as_ref()
                            .map(|id| Value::String(id.as_str().to_string()))
                            .unwrap_or(Value::Null)
                    }
                    _ => {
                        return Err(gql_type(format!(
                            "{name}() is not defined for a relationship"
                        )));
                    }
                });
            }
            _ => {}
        }
    }
    // Fallback: evaluate to the element's JSON and read its fields.
    match eval(arg, row, params)? {
        Value::Null => Ok(Value::Null),
        Value::Json(serde_json::Value::Object(mut map)) => match name {
            "labels" => Ok(map
                .get("label")
                .and_then(|v| v.as_str())
                .map(|s| Value::StringArray(vec![s.to_string()]))
                .unwrap_or(Value::Null)),
            "type" => Ok(map
                .remove("label")
                .map(Value::from_json)
                .unwrap_or(Value::Null)),
            "id" => Ok(map
                .remove("id")
                .map(Value::from_json)
                .unwrap_or(Value::Null)),
            _ => Err(gql_type(format!("{name}() expects a node or relationship"))),
        },
        other => Err(gql_type(format!(
            "{name}() expects a node or relationship, got {other:?}"
        ))),
    }
}

/// Extract the `nodes`/`relationships` array from a path or graph value.
fn path_component(value: Value, key: &str) -> Result<Value> {
    match value {
        Value::Path(path) => match key {
            "nodes" => Ok(Value::Json(serde_json::Value::Array(path.nodes))),
            "relationships" => Ok(Value::Json(serde_json::Value::Array(path.relationships))),
            _ => Ok(Value::Null),
        },
        Value::Graph(graph) => match key {
            "nodes" => Ok(Value::Json(serde_json::Value::Array(graph.nodes))),
            "relationships" => Ok(Value::Json(serde_json::Value::Array(graph.relationships))),
            _ => Ok(Value::Null),
        },
        Value::Json(serde_json::Value::Object(mut m)) => {
            Ok(m.remove(key).map(Value::Json).unwrap_or(Value::Null))
        }
        Value::Null => Ok(Value::Null),
        other => Err(gql_type(format!(
            "{key}() expects a path or graph value, got {other:?}"
        ))),
    }
}

/// `graph(nodes, relationships)` -> a first-class graph value (Full39075 F7).
/// Each argument is a (possibly empty or NULL) list of node/relationship
/// elements, e.g. from `collect(n)`; construction deduplicates by identity.
fn eval_graph_constructor(args: &[Expr], row: &Row, params: &CypherParameters) -> Result<Value> {
    let [nodes_expr, rels_expr] = args else {
        return Err(gql_type(
            "graph() expects exactly two arguments: (nodes, relationships)".to_string(),
        ));
    };
    let nodes = graph_element_list(eval(nodes_expr, row, params)?, "nodes")?;
    let relationships = graph_element_list(eval(rels_expr, row, params)?, "relationships")?;
    Ok(Value::Graph(GraphValue::new(nodes, relationships)))
}

fn graph_element_list(value: Value, what: &str) -> Result<Vec<serde_json::Value>> {
    match value {
        Value::Null => Ok(Vec::new()),
        Value::Json(serde_json::Value::Array(elements)) => Ok(elements),
        other => Err(gql_type(format!(
            "graph() expects a list of {what} elements, got {other:?}"
        ))),
    }
}

/// Evaluate a `CASE` expression. Simple form (`CASE x WHEN v THEN ...`) compares
/// `x` to each branch value; searched form (`CASE WHEN cond THEN ...`) takes the
/// first branch whose condition is TRUE. Falls back to `ELSE` / NULL.
fn eval_case(
    operand: Option<&Expr>,
    branches: &[CaseBranch],
    default: Option<&Expr>,
    row: &Row,
    params: &CypherParameters,
) -> Result<Value> {
    match operand {
        Some(op) => {
            let target = eval(op, row, params)?;
            for branch in branches {
                let candidate = eval(&branch.when, row, params)?;
                if values_equal(&target, &candidate) == Some(true) {
                    return eval(&branch.then, row, params);
                }
            }
        }
        None => {
            for branch in branches {
                if matches!(eval(&branch.when, row, params)?, Value::Bool(true)) {
                    return eval(&branch.then, row, params);
                }
            }
        }
    }
    match default {
        Some(d) => eval(d, row, params),
        None => Ok(Value::Null),
    }
}

/// Scalar function registry for the read reference executor. Reuses the crate's
/// existing `restricted_*_value` evaluators rather than reimplementing them.
fn eval_scalar_function(
    name: &str,
    args: &[Expr],
    row: &Row,
    params: &CypherParameters,
) -> Result<Value> {
    let lower = name.to_ascii_lowercase();

    // `coalesce` is variadic and null-aware; handle it before the unary helpers.
    if lower == "coalesce" {
        if args.is_empty() {
            return Err(gql_type(
                "coalesce() expects at least one argument".to_string(),
            ));
        }
        for arg in args {
            let value = eval(arg, row, params)?;
            if !matches!(value, Value::Null) {
                return Ok(value);
            }
        }
        return Ok(Value::Null);
    }

    // `range(a, b[, step])` builds an inclusive integer list.
    if lower == "range" {
        return eval_range(args, row, params);
    }

    // `graph(nodes, relationships)` constructs a first-class graph value.
    if lower == "graph" {
        return eval_graph_constructor(args, row, params);
    }

    // Element-introspection functions need the binding (or the element's JSON).
    if matches!(lower.as_str(), "labels" | "type" | "id") {
        let [arg] = args else {
            return Err(gql_type(format!("{lower}() expects exactly one argument")));
        };
        return eval_element_function(&lower, arg, row, params);
    }

    // All remaining functions are unary.
    let [arg] = args else {
        return Err(unsupported_gql_feature(
            GqlFeature::ScalarFunctionRegistry,
            GqlConformanceProfile::PortableGql,
            format!(
                "scalar function `{name}` with {} arguments is not supported yet",
                args.len()
            ),
        ));
    };
    let value = eval(arg, row, params)?;
    // Cypher scalar functions are null-propagating.
    if matches!(value, Value::Null) {
        return Ok(Value::Null);
    }

    match lower.as_str() {
        "toupper" => restricted_string_transform_value(value, CypherReturnStringTransform::Upper),
        "tolower" => restricted_string_transform_value(value, CypherReturnStringTransform::Lower),
        "trim" => restricted_string_trim_value(value, CypherReturnStringTrim::Both),
        "ltrim" => restricted_string_trim_value(value, CypherReturnStringTrim::Left),
        "rtrim" => restricted_string_trim_value(value, CypherReturnStringTrim::Right),
        "reverse" => restricted_string_reverse_value(value),
        "tostring" => restricted_to_string_value(value),
        "tointeger" => restricted_to_integer_value(value),
        "tofloat" => restricted_to_float_value(value),
        "toboolean" => restricted_to_boolean_value(value),
        "abs" => restricted_abs_value(value),
        "sign" => restricted_numeric_sign_value(value),
        "ceil" => restricted_numeric_round_value(value, CypherReturnNumericRound::Ceil),
        "floor" => restricted_numeric_round_value(value, CypherReturnNumericRound::Floor),
        "round" => match value {
            Value::Int(n) => Ok(Value::Int(n)),
            Value::Float(f) => Ok(Value::Float(f.round())),
            other => Err(gql_type(format!("round() expects a number, got {other:?}"))),
        },
        "sqrt" => unary_float_fn(value, "sqrt", f64::sqrt),
        "exp" => unary_float_fn(value, "exp", f64::exp),
        "log" | "ln" => unary_float_fn(value, &lower, f64::ln),
        "log10" => unary_float_fn(value, "log10", f64::log10),
        "sin" => unary_float_fn(value, "sin", f64::sin),
        "cos" => unary_float_fn(value, "cos", f64::cos),
        "tan" => unary_float_fn(value, "tan", f64::tan),
        "size" => restricted_size_value(value),
        // `length` is the path hop count for a path value; otherwise falls back
        // to collection size.
        "length" => match &value {
            Value::Path(path) => Ok(Value::Int(path.relationships.len() as i64)),
            Value::Json(serde_json::Value::Object(m)) if m.contains_key("relationships") => Ok(
                Value::Int(m["relationships"].as_array().map_or(0, |a| a.len()) as i64),
            ),
            _ => restricted_size_value(value),
        },
        "nodes" => path_component(value, "nodes"),
        "relationships" | "rels" => path_component(value, "relationships"),
        "head" => Ok(list_elements(value)
            .into_iter()
            .next()
            .unwrap_or(Value::Null)),
        "last" => Ok(list_elements(value)
            .into_iter()
            .last()
            .unwrap_or(Value::Null)),
        "isempty" => restricted_is_empty_value(value),
        // Temporal/decimal constructors (Unit T). `duration` takes an ISO 8601
        // string; `decimal` accepts a numeral string or coerces an int/float.
        "duration" => match value {
            Value::String(s) => Value::duration(&s),
            Value::Duration(_) => Ok(value),
            other => Err(gql_type(format!(
                "duration() expects an ISO 8601 string, got {other:?}"
            ))),
        },
        "decimal" => match value {
            Value::String(s) => Value::decimal(&s),
            Value::Int(n) => Value::decimal(n.to_string()),
            Value::Float(f) => Value::decimal(f.to_string()),
            Value::Decimal(_) => Ok(value),
            other => Err(gql_type(format!(
                "decimal() expects a numeral string or number, got {other:?}"
            ))),
        },
        _ => Err(unsupported_gql_feature(
            GqlFeature::ScalarFunctionRegistry,
            GqlConformanceProfile::PortableGql,
            format!("scalar function `{name}` is not supported by the read reference executor yet"),
        )),
    }
}

/// Apply a unary `f64 -> f64` math function (`sqrt`, `ln`, `sin`, …) to a
/// numeric value, returning a `Float`. Non-numeric operands are a type error;
/// `Null` is handled by the caller (null-propagating).
fn unary_float_fn(value: Value, name: &str, f: fn(f64) -> f64) -> Result<Value> {
    match numeric(&value) {
        Some(x) => Ok(Value::Float(f(x))),
        None => Err(gql_type(format!(
            "{name}() expects a number, got {value:?}"
        ))),
    }
}

fn eval_property(base: &Expr, key: &str, row: &Row, params: &CypherParameters) -> Result<Value> {
    if let Expr::Variable(name) = base {
        return match row.get(name) {
            Some(Bound::Node(node)) if key == "label" => {
                read_budget::charge_intermediate_bytes(
                    node.label.as_str().len(),
                    "projecting node labels",
                )?;
                Ok(Value::from(node.label.as_str()))
            }
            Some(Bound::Node(node)) => match node.props.get(key) {
                Some(value) => clone_value(value, "projecting node properties"),
                None => Ok(Value::Null),
            },
            Some(Bound::Edge(edge, _)) => match edge.props.get(key) {
                Some(value) => clone_value(value, "projecting relationship properties"),
                None => Ok(Value::Null),
            },
            Some(Bound::Value(Value::Json(serde_json::Value::Object(map)))) => match map.get(key) {
                Some(value) => clone_json_value(value, "projecting map properties"),
                None => Ok(Value::Null),
            },
            Some(Bound::Value(_)) => Ok(Value::Null),
            None => Err(gql_name(format!("variable `{name}` is not bound"))),
        };
    }
    // Nested access: evaluate the base to a JSON object and index it.
    match eval(base, row, params)? {
        Value::Json(serde_json::Value::Object(mut map)) => {
            Ok(map.remove(key).map(Value::from_json).unwrap_or(Value::Null))
        }
        _ => Ok(Value::Null),
    }
}

fn eval_unary(op: UnaryOp, operand: &Expr, row: &Row, params: &CypherParameters) -> Result<Value> {
    let value = eval(operand, row, params)?;
    match op {
        UnaryOp::Not => match value {
            Value::Bool(b) => Ok(Value::Bool(!b)),
            Value::Null => Ok(Value::Null),
            other => Err(gql_type(format!("NOT expects a boolean, got {other:?}"))),
        },
        UnaryOp::Negate => match value {
            Value::Int(n) => Ok(Value::Int(-n)),
            Value::Float(f) => Ok(Value::Float(-f)),
            Value::Null => Ok(Value::Null),
            other => Err(gql_type(format!("unary - expects a number, got {other:?}"))),
        },
        UnaryOp::Plus => match value {
            v @ (Value::Int(_) | Value::Float(_) | Value::Null) => Ok(v),
            other => Err(gql_type(format!("unary + expects a number, got {other:?}"))),
        },
    }
}

fn eval_binary(
    op: BinaryOp,
    lhs: &Expr,
    rhs: &Expr,
    row: &Row,
    params: &CypherParameters,
) -> Result<Value> {
    use BinaryOp::*;
    // Boolean connectives implement three-valued logic with short-circuit-free
    // evaluation (both sides are pure here).
    if matches!(op, And | Or | Xor) {
        let a = as_bool(eval(lhs, row, params)?)?;
        let b = as_bool(eval(rhs, row, params)?)?;
        return Ok(three_valued(op, a, b));
    }

    // `IN` is handled before evaluating the right side so a list literal stays a
    // list of `Value`s (round-tripping through JSON would be lossy).
    if op == In {
        let a = eval(lhs, row, params)?;
        return membership(&a, rhs, row, params);
    }

    let a = eval(lhs, row, params)?;
    let b = eval(rhs, row, params)?;
    match op {
        Add | Subtract | Multiply | Divide | Modulo | Power => arithmetic(op, a, b),
        Eq | Ne | Lt | Le | Gt | Ge => Ok(comparison(op, &a, &b)),
        StartsWith | EndsWith | Contains => string_predicate(op, &a, &b),
        In | And | Or | Xor => unreachable!("handled above"),
    }
}

/// Coerce a value to an optional boolean (None == NULL/UNKNOWN).
fn as_bool(value: Value) -> Result<Option<bool>> {
    match value {
        Value::Bool(b) => Ok(Some(b)),
        Value::Null => Ok(None),
        other => Err(gql_type(format!("expected a boolean, got {other:?}"))),
    }
}

fn three_valued(op: BinaryOp, a: Option<bool>, b: Option<bool>) -> Value {
    let result = match op {
        BinaryOp::And => match (a, b) {
            (Some(false), _) | (_, Some(false)) => Some(false),
            (Some(true), Some(true)) => Some(true),
            _ => None,
        },
        BinaryOp::Or => match (a, b) {
            (Some(true), _) | (_, Some(true)) => Some(true),
            (Some(false), Some(false)) => Some(false),
            _ => None,
        },
        BinaryOp::Xor => match (a, b) {
            (Some(x), Some(y)) => Some(x != y),
            _ => None,
        },
        _ => None,
    };
    match result {
        Some(b) => Value::Bool(b),
        None => Value::Null,
    }
}

fn comparison(op: BinaryOp, a: &Value, b: &Value) -> Value {
    match op {
        BinaryOp::Eq => to_bool_or_null(values_equal(a, b)),
        BinaryOp::Ne => to_bool_or_null(values_equal(a, b).map(|eq| !eq)),
        _ => match value_order(a, b) {
            Some(ord) => Value::Bool(match op {
                BinaryOp::Lt => ord.is_lt(),
                BinaryOp::Le => ord.is_le(),
                BinaryOp::Gt => ord.is_gt(),
                BinaryOp::Ge => ord.is_ge(),
                _ => unreachable!(),
            }),
            None => Value::Null,
        },
    }
}

fn to_bool_or_null(b: Option<bool>) -> Value {
    match b {
        Some(b) => Value::Bool(b),
        None => Value::Null,
    }
}

fn membership(a: &Value, list_expr: &Expr, row: &Row, params: &CypherParameters) -> Result<Value> {
    if matches!(a, Value::Null) {
        return Ok(Value::Null);
    }
    // Evaluate the candidate values directly (no JSON round trip).
    let candidates: Vec<Value> = match list_expr {
        Expr::List(items) => items
            .iter()
            .map(|e| eval(e, row, params))
            .collect::<Result<_>>()?,
        other => match eval(other, row, params)? {
            Value::StringArray(xs) => xs.into_iter().map(Value::String).collect(),
            Value::IntArray(xs) => xs.into_iter().map(Value::Int).collect(),
            Value::FloatArray(xs) => xs.into_iter().map(Value::Float).collect(),
            Value::Json(serde_json::Value::Array(arr)) => {
                arr.into_iter().map(Value::from_json).collect()
            }
            Value::Null => return Ok(Value::Null),
            other => return Err(gql_type(format!("IN expects a list, got {other:?}"))),
        },
    };
    let mut saw_null = false;
    for v in &candidates {
        match values_equal(a, v) {
            Some(true) => return Ok(Value::Bool(true)),
            None => saw_null = true,
            Some(false) => {}
        }
    }
    Ok(if saw_null {
        Value::Null
    } else {
        Value::Bool(false)
    })
}

fn string_predicate(op: BinaryOp, a: &Value, b: &Value) -> Result<Value> {
    let (Value::String(haystack), Value::String(needle)) = (a, b) else {
        if matches!(a, Value::Null) || matches!(b, Value::Null) {
            return Ok(Value::Null);
        }
        return Err(gql_type(
            "string predicates expect string operands".to_string(),
        ));
    };
    let result = match op {
        BinaryOp::StartsWith => haystack.starts_with(needle),
        BinaryOp::EndsWith => haystack.ends_with(needle),
        BinaryOp::Contains => haystack.contains(needle),
        _ => unreachable!(),
    };
    Ok(Value::Bool(result))
}

fn arithmetic(op: BinaryOp, a: Value, b: Value) -> Result<Value> {
    if matches!(a, Value::Null) || matches!(b, Value::Null) {
        return Ok(Value::Null);
    }
    // String concatenation with `+`.
    if op == BinaryOp::Add
        && let (Value::String(x), Value::String(y)) = (&a, &b)
    {
        return Ok(Value::String(format!("{x}{y}")));
    }

    // Duration arithmetic: `+`/`-` over two durations stay a duration.
    if let (Value::Duration(x), Value::Duration(y)) = (&a, &b) {
        let r = match op {
            BinaryOp::Add => x.checked_add(y),
            BinaryOp::Subtract => x.checked_add(&y.negated()),
            _ => {
                return Err(gql_type(
                    "durations support only + and - arithmetic".to_string(),
                ));
            }
        };
        return r
            .map(Value::Duration)
            .ok_or_else(|| gql_execution("duration arithmetic overflow"));
    }

    // Exact decimal arithmetic: when at least one operand is a decimal and no
    // float is involved, `+`/`-`/`*` stay lossless decimals (ints coerce exactly).
    // Division / modulo / power, or any float operand, fall to the f64 path below.
    if matches!(op, BinaryOp::Add | BinaryOp::Subtract | BinaryOp::Multiply)
        && (matches!(a, Value::Decimal(_)) || matches!(b, Value::Decimal(_)))
        && !matches!(a, Value::Float(_))
        && !matches!(b, Value::Float(_))
        && let (Some(x), Some(y)) = (as_decimal_operand(&a), as_decimal_operand(&b))
    {
        let r = match op {
            BinaryOp::Add => x.checked_add(&y),
            BinaryOp::Subtract => x.checked_sub(&y),
            BinaryOp::Multiply => x.checked_mul(&y),
            _ => unreachable!(),
        };
        return r
            .map(Value::Decimal)
            .ok_or_else(|| gql_execution("decimal arithmetic overflow"));
    }

    match (numeric(&a), numeric(&b)) {
        (Some(x), Some(y)) => {
            let both_int = matches!(a, Value::Int(_)) && matches!(b, Value::Int(_));
            let r = match op {
                BinaryOp::Add => x + y,
                BinaryOp::Subtract => x - y,
                BinaryOp::Multiply => x * y,
                BinaryOp::Divide => {
                    if y == 0.0 {
                        return Err(gql_execution("division by zero"));
                    }
                    x / y
                }
                BinaryOp::Modulo => {
                    if y == 0.0 {
                        return Err(gql_execution("modulo by zero"));
                    }
                    x % y
                }
                BinaryOp::Power => x.powf(y),
                _ => unreachable!(),
            };
            if both_int && op != BinaryOp::Divide && op != BinaryOp::Power && r.fract() == 0.0 {
                Ok(Value::Int(r as i64))
            } else {
                Ok(Value::Float(r))
            }
        }
        _ => Err(gql_type("arithmetic expects numeric operands".to_string())),
    }
}

fn numeric(value: &Value) -> Option<f64> {
    match value {
        Value::Int(n) => Some(*n as f64),
        Value::Float(f) => Some(*f),
        // Decimals coerce (lossily) into float arithmetic/comparison when mixed
        // with a float; exact decimal paths are handled before this is reached.
        Value::Decimal(d) => Some(d.to_f64()),
        _ => None,
    }
}

/// A decimal-compatible operand for exact arithmetic: decimals as-is, integers
/// coerced exactly. Floats are excluded (they route to the lossy f64 path).
fn as_decimal_operand(value: &Value) -> Option<grust_core::Decimal> {
    match value {
        Value::Decimal(d) => Some(*d),
        Value::Int(n) => Some(grust_core::Decimal::from_parts(*n as i128, 0)),
        _ => None,
    }
}

/// Equality with NULL propagation (None == one side NULL / incomparable types).
fn values_equal(a: &Value, b: &Value) -> Option<bool> {
    match property_equality::decision(a, b) {
        property_equality::Decision::Known(result) => result,
        property_equality::Decision::JsonFallback => Some(value_to_json(a) == value_to_json(b)),
    }
}

/// Ordering with NULL propagation (None == one side NULL / incomparable).
fn value_order(a: &Value, b: &Value) -> Option<std::cmp::Ordering> {
    if matches!(a, Value::Null) || matches!(b, Value::Null) {
        return None;
    }
    // Exact same-type ordering before any lossy mixed-numeric f64 coercion.
    match (a, b) {
        (Value::Int(x), Value::Int(y)) => return Some(x.cmp(y)),
        (Value::Decimal(x), Value::Decimal(y)) => return Some(x.cmp(y)),
        (Value::Duration(x), Value::Duration(y)) => return Some(x.cmp(y)),
        _ => {}
    }
    if let (Some(x), Some(y)) = (numeric(a), numeric(b)) {
        return x.partial_cmp(&y);
    }
    match (a, b) {
        (Value::String(x), Value::String(y)) => Some(x.cmp(y)),
        (Value::Bool(x), Value::Bool(y)) => Some(x.cmp(y)),
        // Temporal ordering: lexicographic over the RFC 3339 form (chronological
        // for a consistent offset). `WHERE`/`ORDER BY` on datetimes use this.
        (Value::DateTime(x), Value::DateTime(y)) => Some(x.as_str().cmp(y.as_str())),
        _ => None,
    }
}

fn value_to_json(value: &Value) -> serde_json::Value {
    value.to_json()
}

fn value_into_json(value: Value) -> serde_json::Value {
    match value {
        Value::Null => serde_json::Value::Null,
        Value::Bool(value) => serde_json::Value::Bool(value),
        Value::Int(value) => serde_json::Value::from(value),
        Value::Float(value) => serde_json::Value::from(value),
        Value::String(value) => serde_json::Value::String(value),
        Value::DateTime(value) => serde_json::Value::String(value.as_str().to_string()),
        Value::Decimal(value) => serde_json::Value::String(value.to_canonical_string()),
        Value::Duration(value) => serde_json::Value::String(value.to_iso_string()),
        Value::StringArray(values) => serde_json::Value::from(values),
        Value::IntArray(values) => serde_json::Value::from(values),
        Value::FloatArray(values) => serde_json::Value::from(values),
        Value::Path(path) => serde_json::Value::Object(serde_json::Map::from_iter([
            ("nodes".to_string(), serde_json::Value::Array(path.nodes)),
            (
                "relationships".to_string(),
                serde_json::Value::Array(path.relationships),
            ),
        ])),
        Value::Graph(graph) => serde_json::Value::Object(serde_json::Map::from_iter([
            ("nodes".to_string(), serde_json::Value::Array(graph.nodes)),
            (
                "relationships".to_string(),
                serde_json::Value::Array(graph.relationships),
            ),
        ])),
        Value::Json(value) => value,
    }
}

#[cfg(test)]
#[path = "read_tests.rs"]
mod tests;
