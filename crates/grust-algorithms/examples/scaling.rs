//! Time the parallel kernels against their sequential paths on a real graph.
//!
//!     scaling <edge-list> [--workers 0,1,2,4,8,16] [--iterations 10]
//!             [--undirected] [--weighted] [--repeat 2]
//!             [--kernels degree,pagerank,bfs,wcc]
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
    BetweennessOptions, ClosenessOptions, ExecutionContext, ExecutionLimits, FastRpOptions,
    GraphProjection, HarmonicOptions, IterationOptions, KatzOptions, LabelPropagationOptions,
    LouvainOptions, NodeSimilarityOptions, Orientation, PageRankOptions, ProjectionEdge,
    SnapshotIdentity, SpanningTreeOptions, TriangleOptions, betweenness, bfs, biconnectivity,
    closeness, degree, eigenvector, fast_rp, harmonic, hits, k_core, katz, label_propagation,
    leiden, louvain, max_flow, node_similarity, pagerank, spanning_tree, triangles,
    weakly_connected_components,
};

/// Largest score, as a checksum that does not depend on summation order.
fn top(values: &[f64]) -> f64 {
    values.iter().copied().fold(0.0f64, f64::max)
}

/// The iteration count and largest value of one column of an iterated result.
fn scored(scores: &grust_algorithms::IteratedScores, column: &str) -> String {
    let values = scores.values(column).unwrap_or(&[]);
    format!("iterations {} top {:.9}", scores.iterations(), top(values))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let path = args.next().ok_or("usage: scaling <edge-list> [options]")?;
    // Zero means the sequential kernels: an execution that never asks for
    // threads, which is what an embedder gets by default.
    let mut workers = vec![0usize, 1, 2, 4, 8, 16];
    let mut iterations = 10usize;
    // A kernel that builds a cached structure on first use (PageRank builds the
    // reverse topology) pays for it once. Timing a second call separates that
    // one-off cost from the iteration it amortises over.
    let mut repeat = 1usize;
    let mut rounds = 2usize;
    let mut orientation = Orientation::Outgoing;
    let mut weighted = false;
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
            "--repeat" => repeat = value()?.parse()?,
            "--rounds" => rounds = value()?.parse()?,
            "--undirected" => orientation = Orientation::Undirected,
            // Weights are synthesised from the edge position, so a run is
            // reproducible and every row has a different scale.
            "--weighted" => weighted = true,
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

    // Samples per (kernel, worker count), gathered over counterbalanced rounds.
    let mut samples: HashMap<(String, usize), Vec<f64>> = HashMap::new();
    let mut results: HashMap<(String, usize), String> = HashMap::new();
    let mut builds: HashMap<usize, f64> = HashMap::new();
    for round in 0..rounds.max(1) {
        // Reverse the order on alternate rounds. A machine that drifts during a
        // run then moves the first and last cells in opposite directions, which
        // shows up as spread rather than as a difference between worker counts.
        let order: Vec<usize> = if round % 2 == 0 {
            workers.clone()
        } else {
            workers.iter().rev().copied().collect()
        };
        for &threads in &order {
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
                weighted.then(|| {
                    pairs
                        .iter()
                        .enumerate()
                        .map(|(ordinal, _)| 1.0 + (ordinal % 9) as f64)
                        .collect()
                }),
                orientation,
                &context,
            )?;
            let build = build.elapsed().as_secs_f64();
            builds.insert(threads, build);
            for kernel in &kernels {
                for pass in 1..=repeat {
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
                            let reached =
                                distances.values().iter().filter(|d| d.is_finite()).count();
                            let sum: f64 =
                                distances.values().iter().filter(|d| d.is_finite()).sum();
                            format!("reached {reached} sum {sum}")
                        }
                        "wcc" => {
                            let components = weakly_connected_components(&graph)?;
                            let mut labels: Vec<usize> = components.values().to_vec();
                            labels.sort_unstable();
                            labels.dedup();
                            format!("components {}", labels.len())
                        }
                        // The catalog kernels. Each prints something the kernel
                        // computed, so a speedup cannot come from doing less.
                        "kcore" => {
                            let cores = k_core(&graph)?;
                            format!("degeneracy {}", cores.degeneracy())
                        }
                        "triangles" => {
                            let counts = triangles(&graph, TriangleOptions::default())?;
                            format!("triangles {}", counts.triangles().iter().sum::<i64>())
                        }
                        "betweenness" => {
                            // Exact betweenness is O(V·E); sample on anything large.
                            let options = BetweennessOptions {
                                sampling_size: Some(64),
                                seed: 42,
                                normalized: false,
                            };
                            let scores = betweenness(&graph, options)?;
                            format!("total {:.6}", scores.values().iter().sum::<f64>())
                        }
                        "closeness" => {
                            let scores = closeness(&graph, ClosenessOptions::default())?;
                            format!("total {:.6}", scores.values().iter().sum::<f64>())
                        }
                        "harmonic" => {
                            let scores = harmonic(&graph, HarmonicOptions::default())?;
                            format!("total {:.6}", scores.values().iter().sum::<f64>())
                        }
                        "similarity" => {
                            let pairs = node_similarity(&graph, NodeSimilarityOptions::default())?;
                            format!(
                                "pairs {} total {:.6}",
                                pairs.first().len(),
                                pairs.similarity().iter().sum::<f64>()
                            )
                        }
                        "louvain" => {
                            let communities = louvain(&graph, LouvainOptions::default())?;
                            format!("modularity {:.9}", communities.modularity())
                        }
                        "leiden" => {
                            let communities = leiden(&graph, LouvainOptions::default())?;
                            format!("modularity {:.9}", communities.modularity())
                        }
                        "labelprop" => {
                            let communities =
                                label_propagation(&graph, LabelPropagationOptions::default())?;
                            let mut labels: Vec<usize> = communities.communities().to_vec();
                            labels.sort_unstable();
                            labels.dedup();
                            format!("communities {}", labels.len())
                        }
                        "eigenvector" => {
                            let scores = eigenvector(&graph, IterationOptions::default())?;
                            scored(&scores, "score")
                        }
                        "katz" => {
                            let scores = katz(&graph, KatzOptions::default())?;
                            scored(&scores, "score")
                        }
                        "hits" => {
                            let scores = hits(&graph, IterationOptions::default())?;
                            scored(&scores, "hub")
                        }
                        "biconnected" => {
                            let parts = biconnectivity(&graph)?;
                            format!("articulation {}", parts.articulation_points().len())
                        }
                        "spanning" => {
                            let forest = spanning_tree(&graph, SpanningTreeOptions::default())?;
                            format!("edges {}", forest.edges().len())
                        }
                        "fastrp" => {
                            let embedding = fast_rp(&graph, FastRpOptions::default())?;
                            format!("dimension {}", embedding.dimension())
                        }
                        "maxflow" => {
                            let flow = max_flow(&graph, names[0], names[names.len() / 2])?;
                            format!("value {:.6}", flow.value())
                        }
                        other => return Err(format!("unknown kernel `{other}`").into()),
                    };
                    let seconds = started.elapsed().as_secs_f64();
                    // Only the last pass is a measurement; the earlier ones warm
                    // whatever the kernel builds on first use.
                    if pass == repeat {
                        let key = (kernel.clone(), threads);
                        samples.entry(key.clone()).or_default().push(seconds);
                        match results.get(&key) {
                            // A kernel must compute the same thing every time and at
                            // every worker count, or a speedup means nothing.
                            Some(seen) if seen != &result => {
                                return Err(format!(
                                    "{kernel} at {threads} workers returned `{result}`, \
                                 having returned `{seen}` before"
                                )
                                .into());
                            }
                            _ => {
                                results.insert(key, result);
                            }
                        }
                    }
                }
            }
        }
    }

    let median = |values: &mut Vec<f64>| -> f64 {
        values.sort_by(f64::total_cmp);
        values[values.len() / 2]
    };
    println!(
        "{:<12} {:>10} {:>8} {:>10} {:>9} {:>8}  result",
        "kernel", "workers", "build s", "median s", "vs seq", "spread"
    );
    for kernel in &kernels {
        let mut baseline: Option<f64> = None;
        for &threads in &workers {
            let key = (kernel.clone(), threads);
            let Some(values) = samples.get(&key) else {
                continue;
            };
            let mut values = values.clone();
            let (low, high) = (
                values.iter().copied().fold(f64::MAX, f64::min),
                values.iter().copied().fold(0.0f64, f64::max),
            );
            let middle = median(&mut values);
            let speedup = match baseline {
                Some(first) => format!("{:.2}x", first / middle),
                None => {
                    baseline = Some(middle);
                    "-".to_string()
                }
            };
            // Spread across rounds, as a share of the median: how much of a
            // ratio is the machine rather than the change.
            let spread = if middle > 0.0 {
                format!("{:.0}%", 100.0 * (high - low) / middle)
            } else {
                "-".to_string()
            };
            let label = if threads == 0 {
                "sequential".to_string()
            } else {
                threads.to_string()
            };
            let build = builds.get(&threads).copied().unwrap_or_default();
            let result = results.get(&key).cloned().unwrap_or_default();
            println!(
                "{kernel:<12} {label:>10} {build:>8.1} {middle:>10.3} {speedup:>9} {spread:>8}  {result}"
            );
        }
    }
    Ok(())
}
