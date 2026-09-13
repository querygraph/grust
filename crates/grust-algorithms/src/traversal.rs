//! Unweighted traversal and canonical connected components.

use crate::{GraphProjection, Result, buffer::Buffer};

/// One distance per selected node, in projection row order.
/// Positive infinity denotes an unreachable node. The result shares its immutable
/// projection so external IDs and their memory admission remain alive.
pub struct Distances {
    graph: GraphProjection,
    pub(crate) distances: Buffer<f64>,
}

impl Distances {
    pub(crate) fn new(graph: &GraphProjection, distances: Buffer<f64>) -> Self {
        Self {
            graph: graph.clone(),
            distances,
        }
    }
    /// Projection supplying external IDs and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// Distances, including infinity for unreachable nodes.
    pub fn values(&self) -> &[f64] {
        &self.distances.values
    }
}

/// A partition whose component labels are the minimum node row in each set.
/// Labels are deterministic for a fixed node table, independent of edge order.
pub struct Components {
    graph: GraphProjection,
    labels: Buffer<usize>,
}

impl Components {
    /// Projection supplying external IDs and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// Canonical component row for every selected vertex, including isolates.
    pub fn values(&self) -> &[usize] {
        &self.labels.values
    }
}

/// Minimum hop counts following the projection orientation. Weights are ignored.
pub fn bfs(graph: &GraphProjection, source: &str) -> Result<Distances> {
    bfs_sources(graph, std::iter::once(source))
}

/// Minimum hop distance from any supplied external source ID. Duplicate sources
/// are harmless, source order breaks discovery ties, and an empty set is invalid.
pub fn multi_source_bfs(graph: &GraphProjection, sources: &[String]) -> Result<Distances> {
    if sources.is_empty() {
        return Err(crate::AlgorithmError::InvalidArguments(
            "at least one BFS source is required".into(),
        ));
    }
    bfs_sources(graph, sources.iter().map(String::as_str))
}

fn bfs_sources<'a>(
    graph: &GraphProjection,
    sources: impl Iterator<Item = &'a str>,
) -> Result<Distances> {
    let context = graph.execution();
    context.checkpoint()?;
    let mut distances = Buffer::filled(graph.node_count(), f64::INFINITY, context)?;
    let mut queue = Buffer::capacity(graph.node_count(), context)?;
    for source in sources {
        context.charge_work(1)?;
        let source = graph.source(source)?;
        if distances.values[source].is_infinite() {
            distances.values[source] = 0.0;
            queue.values.push(source);
        }
    }
    let adjacency = graph.outgoing();
    let mut head = 0;
    while head < queue.values.len() {
        context.charge_work(1)?;
        let node = queue.values[head];
        head += 1;
        for arc in adjacency.range(node) {
            context.charge_work(1)?;
            let next = adjacency.targets.values[arc];
            if distances.values[next].is_infinite() {
                distances.values[next] = distances.values[node] + 1.0;
                queue.values.push(next);
            }
        }
    }
    Ok(Distances::new(graph, distances))
}

/// Connected components after ignoring edge direction. Union by size and path
/// halving use O(V) scratch and never require reverse adjacency.
pub fn weakly_connected_components(graph: &GraphProjection) -> Result<Components> {
    let context = graph.execution();
    let n = graph.node_count();
    let mut parents = Buffer::capacity(n, context)?;
    for node in 0..n {
        context.charge_work(1)?;
        parents.values.push(node);
    }
    let mut sizes = Buffer::filled(n, 1usize, context)?;
    for edge in graph.edges() {
        context.charge_work(1)?;
        let mut left = root(&mut parents.values, edge.source, context)?;
        let mut right = root(&mut parents.values, edge.target, context)?;
        if left == right {
            continue;
        }
        if sizes.values[left] < sizes.values[right] {
            std::mem::swap(&mut left, &mut right);
        }
        parents.values[right] = left;
        sizes.values[left] += sizes.values[right];
    }
    // Reuse the size buffer for each root's canonical minimum row.
    sizes.values.fill(usize::MAX);
    for node in 0..n {
        context.charge_work(1)?;
        let representative = root(&mut parents.values, node, context)?;
        parents.values[node] = representative;
        sizes.values[representative] = sizes.values[representative].min(node);
    }
    for representative in &mut parents.values {
        context.charge_work(1)?;
        *representative = sizes.values[*representative];
    }
    Ok(Components {
        graph: graph.clone(),
        labels: parents,
    })
}

fn root(
    parents: &mut [usize],
    mut node: usize,
    context: &crate::ExecutionContext,
) -> Result<usize> {
    while parents[node] != node {
        context.charge_work(1)?;
        parents[node] = parents[parents[node]];
        node = parents[node];
    }
    Ok(node)
}

/// Strong components via two iterative depth-first passes. Stack usage is O(V)
/// in admitted heap buffers, including on chains with millions of vertices.
pub fn strongly_connected_components(graph: &GraphProjection) -> Result<Components> {
    let context = graph.execution();
    let n = graph.node_count();
    let adjacency = graph.outgoing();
    let mut seen = Buffer::filled(n, false, context)?;
    let mut order = Buffer::capacity(n, context)?;
    let mut stack = Buffer::capacity(n, context)?;
    for seed in 0..n {
        context.charge_work(1)?;
        if seen.values[seed] {
            continue;
        }
        seen.values[seed] = true;
        stack.values.push((seed, adjacency.range(seed).start));
        while let Some(&mut (node, ref mut next_arc)) = stack.values.last_mut() {
            context.charge_work(1)?;
            if *next_arc == adjacency.range(node).end {
                order.values.push(node);
                stack.values.pop();
            } else {
                let next = adjacency.targets.values[*next_arc];
                *next_arc += 1;
                if !seen.values[next] {
                    seen.values[next] = true;
                    stack.values.push((next, adjacency.range(next).start));
                }
            }
        }
    }
    drop(stack);
    drop(seen);
    let reverse = graph.reverse()?;
    let mut labels = Buffer::filled(n, usize::MAX, context)?;
    let mut members = Buffer::capacity(n, context)?;
    for &seed in order.values.iter().rev() {
        context.charge_work(1)?;
        if labels.values[seed] != usize::MAX {
            continue;
        }
        members.values.clear();
        members.values.push(seed);
        labels.values[seed] = seed;
        let mut minimum = seed;
        let mut head = 0;
        while head < members.values.len() {
            context.charge_work(1)?;
            let node = members.values[head];
            head += 1;
            for arc in reverse.range(node) {
                context.charge_work(1)?;
                let next = reverse.targets.values[arc];
                if labels.values[next] == usize::MAX {
                    labels.values[next] = seed;
                    minimum = minimum.min(next);
                    members.values.push(next);
                }
            }
        }
        for &node in &members.values {
            context.charge_work(1)?;
            labels.values[node] = minimum;
        }
    }
    Ok(Components {
        graph: graph.clone(),
        labels,
    })
}
