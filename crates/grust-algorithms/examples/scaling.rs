//! Time the parallel kernels against their sequential paths on a real graph.
//!
//!     scaling <edge-list> [--workers 1,2,4,8,16] [--iterations 10]
//!             [--undirected] [--kernels degree,pagerank,bfs,wcc]
//!
//! The edge list is one `source target` pair per line, `#` comments ignored,
//! as SNAP and the strain harness datasets ship them. The same projection is
//! built once per worker count, because concurrency belongs to the execution
//! that owns the projection; build time is reported separately from kernel
//! time, so a kernel's scaling is not diluted by a sequential load.
//!
//! Every row prints the result the kernel produced (a component count, a
//! reachable count, a score checksum) so that a speedup cannot come from doing
//! less work: the values must match across worker counts.
use std::collections::HashMap;
use std::time::Instant;

use grust_algorithms::{
    ExecutionContext, ExecutionLimits, GraphProjection, Orientation, PageRankOptions,
    ProjectionEdge, SnapshotIdentity, bfs, degree, pagerank, weakly_connected_components,
};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let path = args.next().ok_or("usage: scaling <edge-list> [options]")?;
    // Zero means the sequential kernels: an execution that never asks for
    // threads, which is what an embedder gets by default.
    let mut workers = vec![0usize, 1, 2, 4, 8, 16];
    let mut iterations = 10usize;
    let mut orientation = Orientation::Outgoing;
    let mut kernels = vec![
        "degree".to_string(),
        "pagerank".to_string(),
        "bfs".to_string(),
        "wcc".to_string(),
    ];
    while let Some(flag) = args.next() {
        let mut value = || args.next().ok_or_else(|| format!("{flag} needs a value"));
        match flag.as_str() {
            "--workers" => {
                workers = value()?
                    .split(',')
                    .map(|part| part.parse::<usize>())
                    .collect::<Result<_, _>>()?;
            }
            "--iterations" => iterations = value()?.parse()?,
            "--undirected" => orientation = Orientation::Undirected,
            "--kernels" => kernels = value()?.split(',').map(String::from).collect(),
            other => return Err(format!("unknown argument `{other}`").into()),
        }
    }

    let started = Instant::now();
    let text = std::fs::read_to_string(&path)?;
    // Rows are numbered on first appearance, as the strain harness does, so the
    // node table is the graph's own order rather than a sorted one.
    let mut rows: HashMap<&str, usize> = HashMap::new();
    let mut names: Vec<&str> = Vec::new();
    let mut pairs: Vec<(usize, usize)> = Vec::new();
    for line in text.lines() {
        if line.starts_with('#') || line.trim().is_empty() {
            continue;
        }
        let mut fields = line.split_whitespace();
        let (Some(source), Some(target)) = (fields.next(), fields.next()) else {
            continue;
        };
        let source = match rows.get(source) {
            Some(&row) => row,
            None => {
                let row = names.len();
                names.push(source);
                rows.insert(source, row);
                row
            }
        };
        let target = match rows.get(target) {
            Some(&row) => row,
            None => {
                let row = names.len();
                names.push(target);
                rows.insert(target, row);
                row
            }
        };
        pairs.push((source, target));
    }
    println!(
        "{path}: {} nodes, {} edges, parsed in {:.1}s",
        names.len(),
        pairs.len(),
        started.elapsed().as_secs_f64()
    );

    println!(
        "{:<10} {:>10} {:>10} {:>10} {:>9}  result",
        "kernel", "workers", "build s", "kernel s", "vs seq"
    );
    let mut baseline: HashMap<String, f64> = HashMap::new();
    for &threads in &workers {
        let context = ExecutionContext::new(ExecutionLimits {
            memory_bytes: 18 << 30,
            work_units: usize::MAX,
            batch_rows: 8192,
            deadline: None,
        })?;
        let context = if threads == 0 {
            context
        } else {
            context.with_concurrency(threads)?
        };
        let build = Instant::now();
        let graph = GraphProjection::from_topology(
            SnapshotIdentity::new("scaling".into(), "r1".into(), "bench".into())?,
            names.iter().map(|name| (*name).into()).collect(),
            pairs
                .iter()
                .enumerate()
                .map(|(ordinal, &(source, target))| ProjectionEdge {
                    source,
                    target,
                    ordinal,
                    id: None,
                })
                .collect(),
            None,
            orientation,
            &context,
        )?;
        let build = build.elapsed().as_secs_f64();
        for kernel in &kernels {
            let started = Instant::now();
            let result = match kernel.as_str() {
                "degree" => {
                    let degrees = degree(&graph)?;
                    format!("arcs {}", degrees.counts().iter().sum::<usize>())
                }
                "pagerank" => {
                    let ranks = pagerank(
                        &graph,
                        PageRankOptions {
                            damping: 0.85,
                            tolerance: 0.0,
                            max_iterations: iterations,
                            personalization: None,
                        },
                    )?;
                    format!(
                        "iterations {} top {:.9}",
                        ranks.iterations(),
                        ranks.values().iter().copied().fold(0.0f64, f64::max)
                    )
                }
                "bfs" => {
                    let distances = bfs(&graph, names[0])?;
                    let reached = distances.values().iter().filter(|d| d.is_finite()).count();
                    let sum: f64 = distances.values().iter().filter(|d| d.is_finite()).sum();
                    format!("reached {reached} sum {sum}")
                }
                "wcc" => {
                    let components = weakly_connected_components(&graph)?;
                    let mut labels: Vec<usize> = components.values().to_vec();
                    labels.sort_unstable();
                    labels.dedup();
                    format!("components {}", labels.len())
                }
                other => return Err(format!("unknown kernel `{other}`").into()),
            };
            let seconds = started.elapsed().as_secs_f64();
            let speedup = match baseline.get(kernel) {
                Some(&first) => format!("{:.2}x", first / seconds),
                None => {
                    baseline.insert(kernel.clone(), seconds);
                    "-".to_string()
                }
            };
            let label = if threads == 0 {
                "sequential".to_string()
            } else {
                threads.to_string()
            };
            println!(
                "{kernel:<10} {label:>10} {build:>10.1} {seconds:>10.3} {speedup:>9}  {result}"
            );
        }
    }
    Ok(())
}
