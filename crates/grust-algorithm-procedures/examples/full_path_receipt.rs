//! Local correctness/resource receipt; never substitutes formulas for consumption.

use grust_algorithms::{
    ExecutionContext, ExecutionLimits, GraphProjection, ProjectionOptions, SnapshotIdentity,
    shortest_paths,
};
use grust_core::{Edge, Graph, Node, Props, Value};
use grust_cypher::{CypherParameters, ReadQueryPolicy, run_bounded_read_query_with_registry};
use grust_procedures::RegistryBuilder;
use std::{
    error::Error,
    ops::ControlFlow,
    time::{Duration, Instant},
};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().collect();
    let mode = args.get(1).map(String::as_str).unwrap_or("direct");
    let n: usize = args.get(2).map(String::as_str).unwrap_or("1024").parse()?;
    if n == 0 || n > 65_536 {
        return Err("node count must be in 1..=65536".into());
    }
    let input_started = Instant::now();
    let graph = Graph::new(
        (0..n)
            .map(|node| Node::new("Vertex", node.to_string(), Props::new()))
            .collect(),
        (1..n)
            .map(|node| {
                Edge::new(
                    "NEXT",
                    (node - 1).to_string(),
                    node.to_string(),
                    Props::new(),
                )
            })
            .collect(),
    );
    let input_seconds = input_started.elapsed().as_secs_f64();
    let memory_bytes = 256 * 1024 * 1024;
    let started = Instant::now();
    let (nodes_consumed, costs_consumed, node_sum, cost_sum, extra) = match mode {
        "direct" => {
            let execution = ExecutionContext::new(ExecutionLimits {
                memory_bytes,
                work_units: usize::MAX,
                batch_rows: 1024,
                deadline: Some(started + Duration::from_secs(3600)),
            })?;
            let projection = GraphProjection::from_graph(
                &graph,
                SnapshotIdentity::new(
                    "path".into(),
                    format!("generated-{n}"),
                    "local-receipt".into(),
                )?,
                ProjectionOptions::default(),
                &execution,
            )?;
            let preparation_seconds = started.elapsed().as_secs_f64();
            let paths = shortest_paths(&projection, "0")?;
            let mut nodes_consumed = 0u64;
            let mut costs_consumed = 0u64;
            let mut node_sum = 0u64;
            let mut cost_sum = 0.0;
            let _: ControlFlow<()> = paths.visit_paths(|path| {
                execution.charge_work(path.nodes.len().saturating_add(path.costs.len()))?;
                for &node in path.nodes {
                    nodes_consumed += 1;
                    node_sum += node as u64;
                }
                for &cost in path.costs {
                    costs_consumed += 1;
                    cost_sum += cost;
                }
                Ok(ControlFlow::Continue(()))
            })?;
            let usage = execution.usage()?;
            (
                nodes_consumed,
                costs_consumed,
                node_sum,
                cost_sum,
                serde_json::json!({"preparation_seconds": preparation_seconds, "accounted_peak_bytes": usage.peak_bytes, "work_units": usage.work_units}),
            )
        }
        "cypher" => {
            let mut builder = RegistryBuilder::default();
            grust_algorithm_procedures::register_algorithms(&mut builder)?;
            let policy = ReadQueryPolicy {
                require_match: false,
                allow_read_procedures: true,
                max_intermediate_bytes: memory_bytes,
                max_candidate_work: usize::MAX,
                max_range_items: n,
                max_execution_time: Duration::from_secs(3600),
                ..Default::default()
            };
            let result = run_bounded_read_query_with_registry(
                &graph,
                "path",
                "CALL grust.algorithms.shortestPaths('0') YIELD nodeIds, costs UNWIND range(0, size(costs) - 1) AS i RETURN count(nodeIds[i]), count(costs[i]), sum(toInteger(nodeIds[i])), sum(costs[i]) LIMIT 1",
                &CypherParameters::new(),
                &policy,
                &builder.build(),
            )?;
            let [row] = result.rows.as_slice() else {
                return Err("expected one aggregate row".into());
            };
            let [
                Value::Int(nodes),
                Value::Int(costs),
                Value::Int(node_sum),
                Value::Float(cost_sum),
            ] = row.as_slice()
            else {
                return Err("unexpected aggregate types".into());
            };
            (
                *nodes as u64,
                *costs as u64,
                *node_sum as u64,
                *cost_sum,
                serde_json::json!({"preparation_seconds": null, "accounted_peak_bytes": null, "work_units": null}),
            )
        }
        _ => return Err("mode must be direct or cypher".into()),
    };
    let seconds = started.elapsed().as_secs_f64();
    // Closed forms are independent assertions after actual element consumption.
    let expected_count = (n as u64) * (n as u64 + 1) / 2;
    let expected_sum = (n as u64 - 1) * (n as u64) * (n as u64 + 1) / 6;
    if nodes_consumed != expected_count
        || costs_consumed != expected_count
        || node_sum != expected_sum
        || cost_sum != expected_sum as f64
    {
        return Err("full-path checksum mismatch".into());
    }
    println!(
        "{}",
        serde_json::json!({"mode": mode, "family": "directed_unit_path", "nodes": n, "edges": n - 1, "input_seconds": input_seconds, "execution_seconds": seconds, "memory_limit_bytes": memory_bytes, "concurrency": 1, "node_entries_consumed": nodes_consumed, "cost_entries_consumed": costs_consumed, "node_checksum": node_sum, "cost_checksum": cost_sum, "status": "pass", "details": extra})
    );
    Ok(())
}
