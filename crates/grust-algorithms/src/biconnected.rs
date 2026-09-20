//! Bridges, articulation points and biconnected components from one
//! depth-first pass.

use crate::{
    AlgorithmError, GraphProjection, Orientation, Result,
    buffer::Buffer,
    meter::Meter,
    table::{NodeColumn, NodeTable},
};

const UNSEEN: usize = usize::MAX;

/// What one low-link pass learns about an undirected multigraph.
pub struct Biconnectivity {
    graph: GraphProjection,
    /// Per edge slot: the smallest edge ordinal in its component; `None` for a
    /// self-loop, which lies in no component.
    components: Buffer<Option<usize>>,
    bridges: Buffer<usize>,
    articulation: Buffer<usize>,
}

impl Biconnectivity {
    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// Bridges, as ascending indices into [`GraphProjection::edges`].
    pub fn bridges(&self) -> &[usize] {
        &self.bridges.values
    }
    /// Articulation points, as ascending projection rows.
    pub fn articulation_points(&self) -> &[usize] {
        &self.articulation.values
    }
    /// Per entry of [`GraphProjection::edges`], its component, named by the
    /// smallest edge ordinal in it. A self-loop has none.
    pub fn components(&self) -> &[Option<usize>] {
        &self.components.values
    }

    /// Rows of `sourceNodeId`, `targetNodeId`, `edgeOrdinal`, one per bridge.
    pub fn into_bridge_table(self) -> Result<NodeTable> {
        let slots = self.bridges;
        edge_table(&self.graph, &slots.values, None)
    }

    /// Rows of `nodeId`, one per articulation point.
    pub fn into_articulation_table(self) -> Result<NodeTable> {
        NodeTable::keyed(&self.graph, "nodeId", self.articulation)
    }

    /// Rows of `sourceNodeId`, `targetNodeId`, `edgeOrdinal`, `componentId`, one
    /// per edge that is not a self-loop.
    pub fn into_component_table(self) -> Result<NodeTable> {
        let context = self.graph.execution();
        let mut slots = Buffer::capacity(self.components.values.len(), context)?;
        slots.values.extend(
            (0..self.components.values.len())
                .filter(|&slot| self.components.values[slot].is_some()),
        );
        edge_table(&self.graph, &slots.values, Some(&self.components.values))
    }
}

fn edge_table(
    graph: &GraphProjection,
    slots: &[usize],
    components: Option<&[Option<usize>]>,
) -> Result<NodeTable> {
    let context = graph.execution();
    context.charge_work(slots.len())?;
    let integer = |value: usize| {
        i64::try_from(value).map_err(|_| AlgorithmError::Numerical("ordinal exceeds Int64".into()))
    };
    let mut sources = Buffer::capacity(slots.len(), context)?;
    let mut targets = Buffer::capacity(slots.len(), context)?;
    let mut ordinals = Buffer::capacity(slots.len(), context)?;
    for &slot in slots {
        let edge = &graph.edges()[slot];
        sources.values.push(edge.source);
        targets.values.push(edge.target);
        ordinals.values.push(integer(edge.ordinal)?);
    }
    let mut table = NodeTable::keyed(graph, "sourceNodeId", sources)?
        .column("targetNodeId", NodeColumn::Node(targets))?
        .column("edgeOrdinal", NodeColumn::Integer(ordinals))?;
    if let Some(components) = components {
        let mut ids = Buffer::capacity(slots.len(), context)?;
        for &slot in slots {
            ids.values
                .push(integer(components[slot].unwrap_or_default())?);
        }
        table = table.column("componentId", NodeColumn::Integer(ids))?;
    }
    Ok(table)
}

/// Find every bridge, articulation point and biconnected component.
///
/// A **bridge** is an edge whose removal disconnects its endpoints. An
/// **articulation point** is a node whose removal disconnects two of its
/// neighbours. A **biconnected component** is a maximal set of edges in which
/// any two lie on a common simple cycle; a bridge is a component of one edge.
///
/// **Multigraphs.** Parallel edges form a cycle of length two, so neither is a
/// bridge and both share a component. The pass tracks the edge it arrived by,
/// not the node it arrived from, which is what makes that come out right.
/// Self-loops disconnect nothing and lie in no component.
///
/// The pass is iterative, so a path of a million nodes does not overflow a
/// stack, and sequential: low-link order is the algorithm. Roots are taken in
/// row order and arcs in adjacency order, so the result is a function of the
/// projection alone. Defined on undirected graphs; project with
/// `orientation: "undirected"`.
pub fn biconnectivity(graph: &GraphProjection) -> Result<Biconnectivity> {
    let context = graph.execution();
    context.checkpoint()?;
    if graph.orientation() != Orientation::Undirected {
        return Err(AlgorithmError::InvalidArguments(
            "bridges, articulation points and biconnected components are defined on undirected graphs; project with orientation \"undirected\"".into(),
        ));
    }
    let n = graph.node_count();
    let edges = graph.edges();
    let adjacency = graph.outgoing();
    let mut meter = Meter::new(context);

    let mut discovered = Buffer::filled(n, UNSEEN, context)?;
    let mut low = Buffer::filled(n, UNSEEN, context)?;
    let mut is_articulation = Buffer::filled(n, false, context)?;
    let mut is_bridge = Buffer::filled(edges.len(), false, context)?;
    let mut components = Buffer::filled(edges.len(), None, context)?;
    // (node, next arc to look at, edge slot it was reached by).
    let mut path: Buffer<(usize, usize, usize)> = Buffer::capacity(n, context)?;
    // Edges seen since the component in progress began. Each enters once.
    let mut pending: Buffer<usize> = Buffer::capacity(edges.len(), context)?;
    let mut clock = 0usize;

    for root in 0..n {
        meter.tick(1)?;
        if discovered.values[root] != UNSEEN {
            continue;
        }
        discovered.values[root] = clock;
        low.values[root] = clock;
        clock += 1;
        let mut root_children = 0usize;
        path.values
            .push((root, adjacency.range(root).start, UNSEEN));
        while let Some(&mut (node, ref mut next, arrived_by)) = path.values.last_mut() {
            if *next < adjacency.range(node).end {
                let arc = *next;
                *next += 1;
                meter.tick(1)?;
                let slot = adjacency.edge_slots.values[arc];
                let other = adjacency.targets.values[arc];
                if slot == arrived_by || other == node {
                    continue;
                }
                if discovered.values[other] == UNSEEN {
                    discovered.values[other] = clock;
                    low.values[other] = clock;
                    clock += 1;
                    pending.values.push(slot);
                    path.values
                        .push((other, adjacency.range(other).start, slot));
                } else if discovered.values[other] < discovered.values[node] {
                    // Back to an ancestor. The other direction of the same edge,
                    // met later from the ancestor's side, fails this test.
                    pending.values.push(slot);
                    low.values[node] = low.values[node].min(discovered.values[other]);
                }
                continue;
            }
            path.values.pop();
            let Some(&(parent, _, _)) = path.values.last() else {
                break;
            };
            low.values[parent] = low.values[parent].min(low.values[node]);
            if parent == root {
                root_children += 1;
            }
            if low.values[node] >= discovered.values[parent] {
                // Nothing below `node` reaches above `parent`: a component ends.
                if parent != root {
                    is_articulation.values[parent] = true;
                }
                is_bridge.values[arrived_by] = low.values[node] > discovered.values[parent];
                let start = pending
                    .values
                    .iter()
                    .rposition(|&slot| slot == arrived_by)
                    .ok_or_else(|| {
                        AlgorithmError::OutputContract(
                            "tree edge missing from its component".into(),
                        )
                    })?;
                meter.tick(pending.values.len() - start)?;
                let name = pending.values[start..]
                    .iter()
                    .map(|&slot| edges[slot].ordinal)
                    .min();
                for &slot in &pending.values[start..] {
                    components.values[slot] = name;
                }
                pending.values.truncate(start);
            }
        }
        is_articulation.values[root] = root_children > 1;
    }

    meter.tick(n + edges.len())?;
    let count = |flags: &[bool]| flags.iter().filter(|&&flag| flag).count();
    let mut bridges = Buffer::capacity(count(&is_bridge.values), context)?;
    bridges
        .values
        .extend((0..edges.len()).filter(|&slot| is_bridge.values[slot]));
    let mut articulation = Buffer::capacity(count(&is_articulation.values), context)?;
    articulation
        .values
        .extend((0..n).filter(|&node| is_articulation.values[node]));
    meter.flush()?;
    Ok(Biconnectivity {
        graph: graph.clone(),
        components,
        bridges,
        articulation,
    })
}
