//! Minimum or maximum spanning forest by Kruskal's algorithm.

use crate::{
    AlgorithmError, GraphProjection, Orientation, Result,
    buffer::Buffer,
    parallel,
    table::{NodeColumn, NodeTable, TableScalar},
};

/// Which forest to build.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum SpanningObjective {
    /// Least total weight.
    #[default]
    Minimum,
    /// Greatest total weight.
    Maximum,
}

/// Spanning forest controls.
#[derive(Clone, Copy, Debug, Default)]
pub struct SpanningTreeOptions<'a> {
    /// Minimum or maximum.
    pub objective: SpanningObjective,
    /// Return only the tree that spans this node's component.
    pub source: Option<&'a str>,
}

/// The chosen edges.
pub struct SpanningForest {
    graph: GraphProjection,
    edges: Buffer<usize>,
    weights: Buffer<f64>,
    total: f64,
}

impl SpanningForest {
    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// Chosen edges, as ascending indices into [`GraphProjection::edges`].
    pub fn edges(&self) -> &[usize] {
        &self.edges.values
    }
    /// Weight of each chosen edge; one when the projection has no weights.
    pub fn weights(&self) -> &[f64] {
        &self.weights.values
    }
    /// Sum of the chosen weights, added in the order of [`Self::edges`].
    pub fn total_weight(&self) -> f64 {
        self.total
    }
    /// Rows of `sourceNodeId`, `targetNodeId`, `edgeOrdinal`, `weight`, then the
    /// `totalWeight` scalar.
    pub fn into_table(self) -> Result<NodeTable> {
        let context = self.graph.execution();
        let count = self.edges.values.len();
        context.charge_work(count)?;
        let mut sources = Buffer::capacity(count, context)?;
        let mut targets = Buffer::capacity(count, context)?;
        let mut ordinals = Buffer::capacity(count, context)?;
        for &slot in &self.edges.values {
            let edge = &self.graph.edges()[slot];
            sources.values.push(edge.source);
            targets.values.push(edge.target);
            ordinals.values.push(
                i64::try_from(edge.ordinal)
                    .map_err(|_| AlgorithmError::Numerical("edge ordinal exceeds Int64".into()))?,
            );
        }
        Ok(NodeTable::keyed(&self.graph, "sourceNodeId", sources)?
            .column("targetNodeId", NodeColumn::Node(targets))?
            .column("edgeOrdinal", NodeColumn::Integer(ordinals))?
            .column("weight", NodeColumn::Number(self.weights))?
            .scalar("totalWeight", TableScalar::Number(self.total)))
    }
}

/// Choose, from an undirected projection, a forest that spans every component
/// with the least (or greatest) total weight.
///
/// **Ties** go to the smaller edge ordinal. Edges are therefore in a total
/// order, and the forest is *the* greedy one for that order rather than one of
/// several equally light ones: the same projection always gives the same edges.
/// Of parallel edges the best is taken; a self-loop never is. Without weights
/// every edge weighs one and the result is the spanning forest of smallest
/// ordinals.
///
/// **`source`** keeps only the tree spanning that node's component, which is
/// what a Prim run from that node would return.
///
/// Kruskal with union by size and path halving. Only the sort runs on the
/// execution's workers; its order is total, so the result does not depend on them.
/// Defined on undirected graphs; project with `orientation: "undirected"`.
pub fn spanning_tree(
    graph: &GraphProjection,
    options: SpanningTreeOptions<'_>,
) -> Result<SpanningForest> {
    graph.require_nonnegative("spanningTree")?;
    let context = graph.execution();
    context.checkpoint()?;
    if graph.orientation() != Orientation::Undirected {
        return Err(AlgorithmError::InvalidArguments(
            "a spanning tree is defined on undirected graphs; project with orientation \"undirected\"".into(),
        ));
    }
    let source = options.source.map(|id| graph.source(id)).transpose()?;
    let n = graph.node_count();
    let edges = graph.edges();
    let adjacency = graph.outgoing();
    let mut meter = context.work_meter();

    // Weight per edge, read off either of its arcs.
    let mut weight = Buffer::filled(edges.len(), 1.0f64, context)?;
    if adjacency.weights.is_some() {
        for node in 0..n {
            let range = adjacency.range(node);
            meter.charge(1 + range.len())?;
            for arc in range {
                weight.values[adjacency.edge_slot(arc)] = adjacency.weight(arc);
            }
        }
    }

    let mut order = Buffer::capacity(edges.len(), context)?;
    order.values.extend(0..edges.len());
    let count = edges.len();
    meter.charge(count.saturating_mul(count.max(2).ilog2() as usize))?;
    let maximum = options.objective == SpanningObjective::Maximum;
    let workers =
        parallel::concurrency(context, count.saturating_mul(count.max(2).ilog2() as usize));
    parallel::sort_total(workers, &mut order.values, |&a: &usize, &b: &usize| {
        let by_weight = weight.values[a].total_cmp(&weight.values[b]);
        let by_weight = if maximum {
            by_weight.reverse()
        } else {
            by_weight
        };
        by_weight.then(edges[a].ordinal.cmp(&edges[b].ordinal))
    })?;

    let mut parent = Buffer::capacity(n, context)?;
    parent.values.extend(0..n);
    let mut size = Buffer::filled(n, 1usize, context)?;
    let find = |parent: &mut [usize], mut node: usize| {
        while parent[node] != node {
            parent[node] = parent[parent[node]];
            node = parent[node];
        }
        node
    };
    let mut chosen = Buffer::filled(edges.len(), false, context)?;
    let mut remaining = n.saturating_sub(1);
    for &slot in &order.values {
        if remaining == 0 {
            break;
        }
        meter.charge(1)?;
        let a = find(&mut parent.values, edges[slot].source);
        let b = find(&mut parent.values, edges[slot].target);
        if a == b {
            continue;
        }
        let (small, large) = if size.values[a] < size.values[b] {
            (a, b)
        } else {
            (b, a)
        };
        parent.values[small] = large;
        size.values[large] += size.values[small];
        chosen.values[slot] = true;
        remaining -= 1;
    }

    let wanted = source.map(|node| find(&mut parent.values, node));
    meter.charge(edges.len())?;
    let mut kept = Buffer::capacity(n.saturating_sub(1).min(edges.len()), context)?;
    let mut weights = Buffer::capacity(n.saturating_sub(1).min(edges.len()), context)?;
    let mut total = 0.0;
    for (slot, edge) in edges.iter().enumerate() {
        if chosen.values[slot]
            && wanted.is_none_or(|root| find(&mut parent.values, edge.source) == root)
        {
            kept.values.push(slot);
            weights.values.push(weight.values[slot]);
            total += weight.values[slot];
        }
    }
    Ok(SpanningForest {
        graph: graph.clone(),
        edges: kept,
        weights,
        total,
    })
}
