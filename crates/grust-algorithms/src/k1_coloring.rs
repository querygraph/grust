//! Greedy graph colouring by conflict resolution, on a seeded priority order.

use crate::{
    AlgorithmError, GraphProjection, Orientation, Result,
    buffer::Buffer,
    random,
    table::{NodeColumn, NodeTable, TableScalar},
};

/// No colour yet: what every node holds before the first pass.
const UNCOLORED: usize = usize::MAX;

/// k1-colouring controls.
#[derive(Clone, Copy, Debug)]
pub struct K1ColoringOptions {
    /// Stop after this many colouring passes, conflict-free or not. A graph can
    /// need as many passes as it has nodes; `converged` reports which happened.
    pub max_iterations: usize,
    /// The priority order that decides which endpoint of a conflicting edge
    /// gives way. `None` is row order; a seed shuffles it once, deterministically.
    pub seed: Option<u64>,
}

impl Default for K1ColoringOptions {
    fn default() -> Self {
        Self {
            max_iterations: 10,
            seed: None,
        }
    }
}

/// A colour per node.
pub struct K1Coloring {
    table: NodeTable,
    converged: bool,
}

impl K1Coloring {
    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        self.table.projection()
    }
    /// Colour per node, in projection row order. Colours are dense from zero
    /// only in the sense that every colour is at most the node's degree; the
    /// set actually used need not be contiguous.
    pub fn colors(&self) -> &[i64] {
        self.table
            .integers("color")
            .expect("k1Coloring declares color")
    }
    /// Distinct colours used. Zero for an empty graph.
    pub fn color_count(&self) -> i64 {
        match self.table.scalar_value("colorCount") {
            Some(TableScalar::Integer(value)) => value,
            _ => 0,
        }
    }
    /// Colouring passes run, including the one that found no conflict.
    pub fn iterations(&self) -> i64 {
        match self.table.scalar_value("iterations") {
            Some(TableScalar::Integer(value)) => value,
            _ => 0,
        }
    }
    /// Whether the run ended with no conflicting edge, rather than with
    /// `max_iterations` stopping it.
    pub fn converged(&self) -> bool {
        self.converged
    }
    /// `color`, then the `colorCount`, `iterations` and `converged` scalars.
    pub fn into_table(self) -> NodeTable {
        self.table
    }
}

/// Colour an undirected projection so that no edge joins two nodes of the same
/// colour, greedily and without trying to reach the chromatic number.
///
/// **Schedule.** One pass gives every uncoloured-or-conflicted node the
/// smallest colour none of its neighbours holds, reading the colours the
/// previous pass left; the pass then finds every edge whose endpoints now
/// agree and queues the *lower-priority* endpoint of each to be recoloured.
/// Because the higher-priority endpoint keeps its colour, the highest-priority
/// node never moves, the second never moves after it has once given way, and so
/// on: a graph of `n` nodes is conflict-free within `n` passes. Priority is the
/// projection's row order, or a single seeded shuffle of it — never thread
/// order, and never the order in which a pass happens to visit nodes, which the
/// snapshot makes irrelevant to the result.
///
/// **Bound.** A node's colour is the smallest non-negative integer missing from
/// its neighbours' colours, so it never exceeds that node's number of distinct
/// neighbours. Colours therefore stay within `0..=Δ` and at most `Δ + 1` of
/// them are used, whether or not the run converged.
///
/// **Multigraph and self-loops.** Parallel edges impose the one constraint
/// their endpoints already impose. A **self-loop is ignored**: a node is not
/// its own neighbour here, because a loop is a constraint no colouring can
/// satisfy, and rejecting every graph that carries one would be worse than
/// colouring the rest of it.
///
/// **Weights are not read.** Colouring is a constraint on topology alone, so
/// `weightProperty` changes nothing. A *signed* projection is still refused,
/// as every kernel but `bellmanFord` refuses one: it is built to admit negative
/// weights, and accepting it here would suggest they had been taken into
/// account.
///
/// Any orientation but undirected is rejected rather than silently symmetrized,
/// as `kCore` rejects it: on a directed projection only one endpoint of an arc
/// can see the other, and the answer would depend on which.
///
/// The kernel is **sequential**. Each pass is O(V + A) with a small constant,
/// and the conflict resolution is a shared-state argument about priority order
/// rather than a reduction; a pool would buy little and would have to prove
/// itself bit-for-bit, so it is not used.
pub fn k1_coloring(graph: &GraphProjection, options: K1ColoringOptions) -> Result<K1Coloring> {
    graph.require_nonnegative("k1Coloring")?;
    let context = graph.execution();
    context.checkpoint()?;
    if options.max_iterations == 0 {
        return Err(AlgorithmError::InvalidArguments(
            "maxIterations must be positive".into(),
        ));
    }
    if graph.orientation() != Orientation::Undirected {
        return Err(AlgorithmError::InvalidArguments(
            "k1Coloring is defined on undirected graphs; project with orientation \"undirected\""
                .into(),
        ));
    }
    let n = graph.node_count();
    let adjacency = graph.outgoing();
    let mut meter = context.work_meter();

    // Priority: `rank[node]` small means the node keeps its colour in a
    // conflict. A seed shuffles the order once; every pass then uses it.
    let mut order = Buffer::capacity(n, context)?;
    order.values.extend(0..n);
    if let Some(seed) = options.seed {
        meter.charge(n)?;
        random::shuffle(&mut order.values, seed, 0);
    }
    let mut rank = Buffer::indexed(n, 0usize, context)?;
    meter.charge(n)?;
    for (position, &node) in order.values.iter().enumerate() {
        rank.values[node] = position;
    }

    // Every node is uncoloured until the first pass; an uncoloured neighbour
    // forbids nothing, so that pass gives a graph with no edges colour zero
    // throughout and lets the conflict passes separate what has to differ.
    let mut colors = Buffer::filled(n, UNCOLORED, context)?;
    let mut assigned = Buffer::indexed(n, 0usize, context)?;
    // `seen[colour] == stamp` marks a colour taken by a neighbour of the node
    // in hand. A colour never exceeds the degree, so `n` entries always suffice
    // and the array never has to be cleared.
    let mut seen = Buffer::filled(n + 1, usize::MAX, context)?;
    let mut stamp = 0usize;
    // The nodes a pass must colour: everything first, then the conflicted.
    let mut pending = Buffer::capacity(n, context)?;
    pending.values.extend(order.values.iter().copied());
    let mut conflicted = Buffer::filled(n, false, context)?;

    let mut iterations = 0usize;
    let mut converged = pending.values.is_empty();
    while !converged && iterations < options.max_iterations {
        iterations += 1;
        // Colour from the snapshot the previous pass left, so that the result
        // does not depend on the order within a pass.
        for &node in &pending.values {
            let range = adjacency.range(node);
            meter.charge(2 + range.len())?;
            for arc in range {
                let other = adjacency.targets.values[arc];
                let color = colors.values[other];
                if other != node && color != UNCOLORED {
                    seen.values[color] = stamp;
                }
            }
            let mut color = 0usize;
            while seen.values[color] == stamp {
                color += 1;
            }
            assigned.values[node] = color;
            stamp += 1;
        }
        for &node in &pending.values {
            colors.values[node] = assigned.values[node];
        }

        // An edge whose endpoints agree queues its lower-priority endpoint.
        pending.values.clear();
        for node in 0..n {
            let range = adjacency.range(node);
            meter.charge(1 + range.len())?;
            for arc in range {
                let other = adjacency.targets.values[arc];
                if other != node
                    && colors.values[other] == colors.values[node]
                    && rank.values[node] > rank.values[other]
                {
                    conflicted.values[node] = true;
                    break;
                }
            }
        }
        meter.charge(n)?;
        for &node in &order.values {
            if std::mem::replace(&mut conflicted.values[node], false) {
                pending.values.push(node);
            }
        }
        converged = pending.values.is_empty();
    }

    meter.charge(2 * n)?;
    let mut used = Buffer::filled(n + 1, false, context)?;
    let mut color_count = 0i64;
    let mut values = Buffer::capacity(n, context)?;
    for &color in &colors.values {
        if !std::mem::replace(&mut used.values[color], true) {
            color_count += 1;
        }
        values.values.push(
            i64::try_from(color)
                .map_err(|_| AlgorithmError::Numerical("colour exceeds Int64".into()))?,
        );
    }
    let iterations = i64::try_from(iterations)
        .map_err(|_| AlgorithmError::Numerical("iteration count exceeds Int64".into()))?;
    let table = NodeTable::new(graph)
        .column("color", NodeColumn::Integer(values))?
        .scalar("colorCount", TableScalar::Integer(color_count))
        .scalar("iterations", TableScalar::Integer(iterations))
        .scalar("converged", TableScalar::Boolean(converged));
    Ok(K1Coloring { table, converged })
}
