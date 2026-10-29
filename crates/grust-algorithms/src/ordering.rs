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

struct Topology<'a>(&'a GraphProjection);

impl grust_topology::DirectedGraph for Topology<'_> {
    fn node_count(&self) -> usize {
        self.0.node_count()
    }

    fn outgoing(&self, node: usize) -> std::ops::Range<usize> {
        self.0.outgoing().range(node)
    }

    fn target(&self, arc: usize) -> usize {
        self.0.outgoing().target(arc)
    }
}

/// Topological ordering using iterative DFS. Directed orientation follows the
/// projection; undirected non-loop edges consequently produce a two-edge cycle.
/// On cyclic input returns the first back-edge witness in node/adjacency order.
pub fn topological_sort(graph: &GraphProjection) -> Result<TopologicalOrder> {
    graph.require_nonnegative("topologicalSort")?;
    let context = graph.execution();
    let mut meter = context.work_meter();
    let n = graph.node_count();
    let mut colors = Buffer::filled(n, grust_topology::Visit::Unseen, context)?;
    let mut finished = Buffer::capacity(n, context)?;
    let mut stack = Buffer::capacity(n, context)?;
    let outcome = grust_topology::topological_sort(
        &Topology(graph),
        grust_topology::Scratch {
            visits: &mut colors.values,
            order: &mut finished.values,
            stack: &mut stack.values,
        },
        |cost| meter.charge(cost),
    )?;
    if let grust_topology::Outcome::Cycle { entry } = outcome {
        let mut witness = Buffer::capacity(n.saturating_add(1), context)?;
        let mut inside = false;
        for &(ancestor, _) in &stack.values {
            meter.charge(1)?;
            inside |= ancestor == entry;
            if inside {
                witness.values.push(ancestor);
            }
        }
        witness.values.push(entry);
        return Ok(TopologicalOrder::Cycle(NodeOrder {
            graph: graph.clone(),
            nodes: witness,
        }));
    }
    Ok(TopologicalOrder::Acyclic(NodeOrder {
        graph: graph.clone(),
        nodes: finished,
    }))
}
