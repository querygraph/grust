//! k-core decomposition by bucket peeling (Batagelj and Zaversnik), O(V + A).

use crate::{
    AlgorithmError, GraphProjection, Orientation, Result,
    buffer::Buffer,
    table::{NodeColumn, NodeTable, TableScalar},
};

/// Core number per node. The k-core is the maximal subgraph in which every node
/// has degree at least k; a node's core number is the largest k whose core
/// contains it.
pub struct KCore {
    table: NodeTable,
}

impl KCore {
    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        self.table.projection()
    }
    /// Core number per node, in projection row order; isolates have core 0.
    pub fn core_values(&self) -> &[i64] {
        self.table
            .integers("coreValue")
            .expect("k-core declares coreValue")
    }
    /// The largest core number: the graph's degeneracy. Zero for an empty graph.
    pub fn degeneracy(&self) -> i64 {
        match self.table.scalar_value("degeneracy") {
            Some(TableScalar::Integer(value)) => value,
            _ => 0,
        }
    }
    /// The result as a node table: `coreValue`, then the `degeneracy` scalar.
    pub fn into_table(self) -> NodeTable {
        self.table
    }
}

/// Decompose an undirected projection into cores.
///
/// Degree counts incident arcs with multiplicity, so **parallel edges each
/// count**; two nodes joined by three edges form a 3-core. **Self-loops are
/// ignored**: a loop never helps a node stay in a core. Any other orientation
/// is rejected rather than silently symmetrized — project with
/// `orientation: "undirected"`.
pub fn k_core(graph: &GraphProjection) -> Result<KCore> {
    graph.require_nonnegative("kCore")?;
    let context = graph.execution();
    context.checkpoint()?;
    if graph.orientation() != Orientation::Undirected {
        return Err(AlgorithmError::InvalidArguments(
            "kCore is defined on undirected graphs; project with orientation \"undirected\"".into(),
        ));
    }
    let n = graph.node_count();
    let adjacency = graph.outgoing();
    let mut meter = context.work_meter();

    // Degree without self-loops. Under the undirected arc contract a loop
    // appears once in its node's row, every other edge once in each endpoint's.
    let mut degree = Buffer::filled(n, 0usize, context)?;
    let mut maximum = 0usize;
    for node in 0..n {
        let range = adjacency.range(node);
        meter.charge(1 + range.len())?;
        let loops = adjacency
            .row_targets(node)
            .filter(|&target| target == node)
            .count();
        degree.values[node] = range.len() - loops;
        maximum = maximum.max(degree.values[node]);
    }

    // Counting sort of nodes by degree: `bin[d]` is where degree d starts in
    // `order`, and `position[v]` is where v sits.
    let mut bin = Buffer::filled(maximum + 2, 0usize, context)?;
    for node in 0..n {
        bin.values[degree.values[node] + 1] += 1;
    }
    for d in 0..=maximum {
        bin.values[d + 1] += bin.values[d];
    }
    let mut order = Buffer::filled(n, 0usize, context)?;
    let mut position = Buffer::filled(n, 0usize, context)?;
    {
        let mut next = Buffer::filled(maximum + 1, 0usize, context)?;
        next.values.copy_from_slice(&bin.values[..=maximum]);
        for node in 0..n {
            let slot = next.values[degree.values[node]];
            next.values[degree.values[node]] += 1;
            order.values[slot] = node;
            position.values[node] = slot;
        }
    }
    meter.charge(n)?;

    // Peel in nondecreasing degree. Removing `node` lowers each heavier
    // neighbour by one per arc, moving it one bin down by swapping it with the
    // first node of its bin. A neighbour never drops below the current degree.
    for index in 0..n {
        let node = order.values[index];
        let range = adjacency.range(node);
        meter.charge(1 + range.len())?;
        for arc in range {
            let other = adjacency.target(arc);
            if other == node || degree.values[other] <= degree.values[node] {
                continue;
            }
            let d = degree.values[other];
            let first = bin.values[d];
            let swapped = order.values[first];
            if swapped != other {
                let at = position.values[other];
                order.values[first] = other;
                order.values[at] = swapped;
                position.values[other] = first;
                position.values[swapped] = at;
            }
            bin.values[d] += 1;
            degree.values[other] -= 1;
        }
    }

    let mut cores = Buffer::capacity(n, context)?;
    let mut degeneracy = 0i64;
    for &value in &degree.values {
        let value = i64::try_from(value)
            .map_err(|_| AlgorithmError::Numerical("core number exceeds Int64".into()))?;
        degeneracy = degeneracy.max(value);
        cores.values.push(value);
    }
    let table = NodeTable::new(graph)
        .column("coreValue", NodeColumn::Integer(cores))?
        .scalar("degeneracy", TableScalar::Integer(degeneracy));
    Ok(KCore { table })
}
