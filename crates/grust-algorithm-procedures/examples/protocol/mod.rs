//! Adapter for the neutral companion harness's text/binary process protocol.
//! This module imports only upstream Grust implementations.
use grust_algorithms::*;
use grust_core::{Edge, Graph, Node, Props, Value};
use grust_cypher::{CypherParameters, ReadQueryPolicy, run_bounded_read_query_with_registry};
use grust_procedures::RegistryBuilder;
use std::{
    error::Error,
    fs,
    io::{BufWriter, Write},
    ops::ControlFlow,
    time::{Duration, Instant},
};

type Result<T> = std::result::Result<T, Box<dyn Error>>;
const MEMORY_BYTES: usize = 256 * 1024 * 1024;

// Each executable chooses its mode at compilation, never by a query-name heuristic.
#[allow(dead_code)]
pub enum Mode {
    Direct,
    Cypher,
}

#[derive(Default)]
struct Output {
    values: Vec<f64>,
    iterations: usize,
    reachable: u64,
    path_entries: u64,
    node_sum: u64,
    cost_sum: f64,
    query: Option<String>,
    preparation_ms: Option<f64>,
    verification_ms: Option<f64>,
    execution_ms: f64,
}

pub fn run(mode: Mode) -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 5 {
        return Err(
            "usage: BENCH INPUT.txt ALGORITHM OUTPUT.bin SOURCE (IPC mode unsupported)".into(),
        );
    }
    let end_to_end = Instant::now();
    let loading = Instant::now();
    let text = fs::read_to_string(&args[1])?;
    let mut input = text.split_whitespace();
    let n: usize = input.next().ok_or("missing node count")?.parse()?;
    let m: usize = input.next().ok_or("missing edge count")?.parse()?;
    if n > 1_000_000 || m > 10_000_000 {
        return Err("input exceeds participant graph envelope".into());
    }
    let mut nodes = Vec::new();
    nodes.try_reserve_exact(n)?;
    for node in 0..n {
        nodes.push(Node {
            id: node.to_string().into(),
            label: "Node".into(),
            props: Props::new(),
        });
    }
    let mut edges = Vec::new();
    edges.try_reserve_exact(m)?;
    for _ in 0..m {
        let from = input.next().ok_or("missing source")?;
        let to = input.next().ok_or("missing target")?;
        let weight: f64 = input.next().ok_or("missing weight")?.parse()?;
        edges.push(Edge::new(
            "EDGE",
            from,
            to,
            [("weight".into(), Value::Float(weight))],
        ));
    }
    if input.next().is_some() {
        return Err("trailing graph input".into());
    }
    let graph = Graph::new(nodes, edges);
    drop(text);
    let loading_ms = loading.elapsed().as_secs_f64() * 1000.0;
    let output = match mode {
        Mode::Direct => direct(&graph, &args[2], &args[4])?,
        Mode::Cypher => cypher(&graph, &args[2], &args[4])?,
    };
    let serialization = Instant::now();
    let mut file = BufWriter::new(fs::File::create(&args[3])?);
    for value in &output.values {
        file.write_all(&value.to_le_bytes())?;
    }
    file.flush()?;
    let serialization_ms = serialization.elapsed().as_secs_f64() * 1000.0;
    println!(
        "{}",
        serde_json::json!({
            "provider": "grust.algorithms", "crate_version": env!("CARGO_PKG_VERSION"), "participant": match mode { Mode::Direct => "grust_upstream_direct", Mode::Cypher => "grust_upstream_cypher" },
            "execution_class": "explicit_local_snapshot", "ms": output.execution_ms,
            "loading_ms": loading_ms, "preparation_ms": output.preparation_ms,
            "verification_ms": output.verification_ms, "serialization_ms": serialization_ms,
            "end_to_end_ms": end_to_end.elapsed().as_secs_f64() * 1000.0,
            "iterations": output.iterations, "reachable": output.reachable,
            "path_entries": output.path_entries, "node_sum": output.node_sum,
            "cost_sum": output.cost_sum, "query": output.query,
            "memory_allowance_bytes": MEMORY_BYTES, "concurrency": 1,
        "deadline_seconds": match mode { Mode::Direct => None, Mode::Cypher => Some(86400) },
            "timer_boundary": match mode { Mode::Direct => "kernel and result conversion, including actual full paths when requested; projection separate", Mode::Cypher => "ordinary query including parse, policy validation, projection and consumption; separate distance verification after full-path query" },
            "status": "pass"
        })
    );
    Ok(())
}

fn direct(graph: &Graph, algorithm: &str, source: &str) -> Result<Output> {
    let context = ExecutionContext::new(ExecutionLimits {
        memory_bytes: MEMORY_BYTES,
        work_units: usize::MAX,
        batch_rows: 1024,
        deadline: None,
    })?;
    let preparation = Instant::now();
    let graph = GraphProjection::from_graph(
        graph,
        SnapshotIdentity::new(
            "benchmark".into(),
            "input".into(),
            "benchmark-reader".into(),
        )?,
        ProjectionOptions {
            weight: WeightSelection::Property {
                key: "weight",
                missing: MissingWeight::Reject,
            },
            ..Default::default()
        },
        &context,
    )?;
    let mut output = Output {
        preparation_ms: Some(preparation.elapsed().as_secs_f64() * 1000.0),
        ..Default::default()
    };
    let start = Instant::now();
    match algorithm {
        "bfs" => output.values = distances(bfs(&graph, source)?.values()),
        "dijkstra" => output.values = distances(dijkstra(&graph, source)?.values()),
        "dijkstra-full" => {
            let paths = shortest_paths(&graph, source)?;
            let _: ControlFlow<()> = paths.visit_paths(|path| {
                context.charge_work(path.nodes.len().saturating_add(path.costs.len()))?;
                output.reachable += 1;
                for &node in std::hint::black_box(path.nodes) {
                    // The input protocol fixes external IDs to these numeric rows.
                    output.path_entries += 1;
                    output.node_sum += node as u64;
                }
                for &cost in std::hint::black_box(path.costs) {
                    output.cost_sum += cost;
                }
                Ok(ControlFlow::Continue(()))
            })?;
            output.values = distances(paths.distances().values());
        }
        "wcc" => {
            output.values = weakly_connected_components(&graph)?
                .values()
                .iter()
                .map(|&value| value as f64)
                .collect()
        }
        "scc" => {
            output.values = strongly_connected_components(&graph)?
                .values()
                .iter()
                .map(|&value| value as f64)
                .collect()
        }
        "pagerank" => {
            let rank = pagerank(&graph, PageRankOptions::default())?;
            if !rank.converged() {
                return Err("PageRank did not converge".into());
            }
            output.iterations = rank.iterations();
            output.values = rank.values().to_vec();
        }
        _ => return Err("unsupported algorithm".into()),
    }
    output.execution_ms = start.elapsed().as_secs_f64() * 1000.0;
    Ok(output)
}

fn distances(values: &[f64]) -> Vec<f64> {
    values
        .iter()
        .map(|&value| if value.is_finite() { value } else { -1.0 })
        .collect()
}

fn cypher(graph: &Graph, algorithm: &str, source: &str) -> Result<Output> {
    let mut builder = RegistryBuilder::default();
    grust_algorithm_procedures::register_algorithms(&mut builder)?;
    let registry = builder.build();
    // This identity check is also used by the companion harness to reject an
    // accidentally substituted historical participant/binary.
    if registry
        .resolve("grust.algorithms.shortestPaths")?
        .definition()
        .provider
        != "grust.algorithms"
    {
        return Err("unexpected registered algorithm provider".into());
    }
    let params = CypherParameters::from([("source".into(), Value::String(source.into()))]);
    let scalar = match algorithm {
        "bfs" => {
            "CALL grust.algorithms.bfs($source) YIELD nodeId, distance RETURN nodeId, distance"
        }
        "dijkstra" | "dijkstra-full" => {
            "CALL grust.algorithms.dijkstra($source, {weightProperty: 'weight'}) YIELD nodeId, distance RETURN nodeId, distance"
        }
        "wcc" => "CALL grust.algorithms.wcc() YIELD nodeId, componentId RETURN nodeId, componentId",
        "scc" => "CALL grust.algorithms.scc() YIELD nodeId, componentId RETURN nodeId, componentId",
        "pagerank" => {
            "CALL grust.algorithms.pagerank({weightProperty: 'weight'}) YIELD nodeId, score, iterations, converged RETURN nodeId, score, iterations, converged"
        }
        _ => return Err("unsupported algorithm".into()),
    };
    let scalar = format!("{scalar} LIMIT {}", graph.nodes.len().max(1));
    let policy = ReadQueryPolicy {
        require_match: false,
        allow_read_procedures: true,
        max_graph_nodes: 1_000_000,
        max_graph_edges: 10_000_000,
        max_graph_bytes: 1024 * 1024 * 1024,
        max_intermediate_bytes: MEMORY_BYTES,
        max_candidate_work: usize::MAX,
        max_result_rows: graph.nodes.len().max(1),
        max_output_bytes: MEMORY_BYTES,
        max_range_items: graph.nodes.len().max(1),
        // The public bounded policy requires a finite deadline. This participant
        // discloses its 24-hour ceiling; historical native full-path runs had none.
        max_execution_time: Duration::from_secs(24 * 3600),
        ..Default::default()
    };
    let start = Instant::now();
    let mut output = Output::default();
    if algorithm == "dijkstra-full" {
        let query = "CALL grust.algorithms.shortestPaths($source, {weightProperty: 'weight'}) YIELD nodeIds, costs UNWIND range(0, size(costs) - 1) AS i RETURN count(nodeIds[i]), sum(toInteger(nodeIds[i])), sum(costs[i]) LIMIT 1";
        let table = run_bounded_read_query_with_registry(
            graph,
            "benchmark",
            query,
            &params,
            &policy,
            &registry,
        )?;
        let [row] = table.rows.as_slice() else {
            return Err("missing full-path aggregate row".into());
        };
        let [Value::Int(count), Value::Int(sum), Value::Float(cost)] = row.as_slice() else {
            return Err("unexpected full-path aggregate types".into());
        };
        output.path_entries = u64::try_from(*count)?;
        output.node_sum = u64::try_from(*sum)?;
        output.cost_sum = *cost;
        output.query = Some(query.into());
        output.execution_ms = start.elapsed().as_secs_f64() * 1000.0;
    } else {
        output.query = Some(scalar.clone());
    }
    let verification = Instant::now();
    let table = run_bounded_read_query_with_registry(
        graph,
        "benchmark",
        &scalar,
        &params,
        &policy,
        &registry,
    )?;
    output.values.try_reserve_exact(graph.nodes.len())?;
    for (index, row) in table.rows.iter().enumerate() {
        let Some(Value::String(id)) = row.first() else {
            return Err("missing result node ID".into());
        };
        if id.parse::<usize>()? != index {
            return Err("unexpected result identity/order".into());
        }
        let value = match row.get(1) {
            Some(Value::Float(value)) => *value,
            Some(Value::String(value)) => value.parse::<usize>()? as f64,
            Some(Value::Null) => -1.0,
            _ => return Err("unexpected scalar output type".into()),
        };
        output.values.push(value);
        if algorithm == "pagerank" {
            let [_, _, Value::Int(iterations), Value::Bool(true)] = row.as_slice() else {
                return Err("PageRank did not converge".into());
            };
            output.iterations = usize::try_from(*iterations)?;
        }
    }
    if algorithm == "dijkstra-full" {
        output.reachable = output.values.iter().filter(|&&value| value >= 0.0).count() as u64;
        output.verification_ms = Some(verification.elapsed().as_secs_f64() * 1000.0);
    } else {
        output.execution_ms = start.elapsed().as_secs_f64() * 1000.0;
    }
    Ok(output)
}
