//! Iterative traversal order and topological ordering with explicit cycle evidence.

use crate::{GraphProjection, Result, buffer::Buffer};

/// Ordered dense node rows sharing their immutable external-ID mapping.
pub struct NodeOrder {
    graph: GraphProjection,
    nodes: Buffer<usize>,
}

impl NodeOrder {
    /// Projection supplying external IDs and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// Ordered node rows. A cycle witness repeats its first row at the end.
    pub fn values(&self) -> &[usize] {
        &self.nodes.values
    }
}

/// A complete topological order or a concrete closed directed cycle. A cyclic
/// graph never produces a partial order disguised as successful sorting.
pub enum TopologicalOrder {
    Acyclic(NodeOrder),
    Cycle(NodeOrder),
}

/// Depth-first discovery order from one external source. Adjacency order breaks
/// ties; each reachable node appears once. Weights are ignored.
pub fn depth_first(graph: &GraphProjection, source: &str) -> Result<NodeOrder> {
    graph.require_nonnegative("dfs")?;
    let context = graph.execution();
    let mut meter = context.work_meter();
    context.checkpoint()?;
    let source = graph.source(source)?;
    let adjacency = graph.outgoing();
    let mut seen = Buffer::filled(graph.node_count(), false, context)?;
    let mut nodes = Buffer::capacity(graph.node_count(), context)?;
    let mut stack = Buffer::capacity(graph.node_count(), context)?;
    seen.values[source] = true;
    nodes.values.push(source);
    stack.values.push((source, adjacency.range(source).start));
    while let Some(&mut (node, ref mut next)) = stack.values.last_mut() {
        meter.charge(1)?;
        if *next == adjacency.range(node).end {
            stack.values.pop();
            continue;
        }
        let target = adjacency.target(*next);
        *next += 1;
        if !seen.values[target] {
            seen.values[target] = true;
            nodes.values.push(target);
            stack.values.push((target, adjacency.range(target).start));
        }
    }
    Ok(NodeOrder {
        graph: graph.clone(),
        nodes,
    })
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Color {
    Unseen,
    Active,
    Finished,
}

/// Topological ordering using iterative DFS. Directed orientation follows the
/// projection; undirected non-loop edges consequently produce a two-edge cycle.
/// On cyclic input returns the first back-edge witness in node/adjacency order.
pub fn topological_sort(graph: &GraphProjection) -> Result<TopologicalOrder> {
    graph.require_nonnegative("topologicalSort")?;
    let context = graph.execution();
    let mut meter = context.work_meter();
    let n = graph.node_count();
    let adjacency = graph.outgoing();
    let mut colors = Buffer::filled(n, Color::Unseen, context)?;
    let mut finished = Buffer::capacity(n, context)?;
    let mut stack = Buffer::capacity(n, context)?;
    for seed in 0..n {
        meter.charge(1)?;
        if colors.values[seed] != Color::Unseen {
            continue;
        }
        colors.values[seed] = Color::Active;
        stack.values.push((seed, adjacency.range(seed).start));
        while let Some(&mut (node, ref mut next)) = stack.values.last_mut() {
            meter.charge(1)?;
            if *next == adjacency.range(node).end {
                colors.values[node] = Color::Finished;
                finished.values.push(node);
                stack.values.pop();
                continue;
            }
            let target = adjacency.target(*next);
            *next += 1;
            match colors.values[target] {
                Color::Unseen => {
                    colors.values[target] = Color::Active;
                    stack.values.push((target, adjacency.range(target).start));
                }
                Color::Active => {
                    let mut witness = Buffer::capacity(n.saturating_add(1), context)?;
                    let mut inside = false;
                    for &(ancestor, _) in &stack.values {
                        meter.charge(1)?;
                        inside |= ancestor == target;
                        if inside {
                            witness.values.push(ancestor);
                        }
                    }
                    witness.values.push(target);
                    return Ok(TopologicalOrder::Cycle(NodeOrder {
                        graph: graph.clone(),
                        nodes: witness,
                    }));
                }
                Color::Finished => {}
            }
        }
    }
    for index in 0..finished.values.len() / 2 {
        meter.charge(1)?;
        finished.values.swap(index, n - index - 1);
    }
    Ok(TopologicalOrder::Acyclic(NodeOrder {
        graph: graph.clone(),
        nodes: finished,
    }))
}
