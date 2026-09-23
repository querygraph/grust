//! Longest paths in a directed acyclic graph, or the cycle that makes them
//! meaningless.

use crate::{
    AlgorithmError, GraphProjection, Result, TopologicalOrder,
    buffer::Buffer,
    ordering::topological_sort,
    table::{NodeColumn, NodeTable, TableScalar},
};

/// The heaviest path ending at each node, or a witness that there is no answer.
pub struct LongestPaths {
    graph: GraphProjection,
    distances: Buffer<f64>,
    hops: Buffer<i64>,
    cycle: Option<Buffer<usize>>,
}

impl LongestPaths {
    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }

    /// Total weight of the heaviest directed path ending at each node, zero
    /// where that path is empty; `None` when the projection holds a cycle,
    /// because then no path is longest — every lap around the cycle is longer.
    pub fn distances(&self) -> Option<&[f64]> {
        self.cycle
            .is_none()
            .then_some(self.distances.values.as_slice())
    }

    /// Arcs on the path [`Self::distances`] reports, per node; `None` under a
    /// cycle, for the same reason. On an unweighted projection every arc weighs
    /// one, so the distance is this count as a double.
    pub fn hops(&self) -> Option<&[i64]> {
        self.cycle.is_none().then_some(self.hops.values.as_slice())
    }

    /// A directed cycle, as projection rows in the order its arcs run: each node
    /// has an arc to the next and the last to the first. No node is repeated.
    pub fn cycle(&self) -> Option<&[usize]> {
        self.cycle.as_ref().map(|cycle| cycle.values.as_slice())
    }

    /// `nodeId`, `distance` (null on every row when there is a cycle), `hops`
    /// (`-1` likewise), `cycleIndex` (a node's position on the witness cycle,
    /// `-1` off it and everywhere on an acyclic graph), then the `cyclic`
    /// scalar. The witness is the rows with a nonnegative `cycleIndex`, read in
    /// that order — a variable-length list column, which the catalog's note
    /// calls `cycleNodeIds`, does not exist on this result shape yet.
    pub fn into_table(self) -> Result<NodeTable> {
        let context = self.graph.execution();
        let n = self.graph.node_count();
        context.charge_work(n)?;
        let mut distances = self.distances;
        let mut hops = self.hops;
        let mut index = Buffer::filled(n, -1i64, context)?;
        if let Some(cycle) = &self.cycle {
            distances.values.fill(f64::NAN);
            hops.values.fill(-1);
            for (position, &node) in cycle.values.iter().enumerate() {
                index.values[node] = i64::try_from(position)
                    .map_err(|_| AlgorithmError::Numerical("cycle exceeds Int64".into()))?;
            }
        }
        Ok(NodeTable::new(&self.graph)
            .column("distance", NodeColumn::OptionalNumber(distances))?
            .column("hops", NodeColumn::Integer(hops))?
            .column("cycleIndex", NodeColumn::Integer(index))?
            .scalar("cyclic", TableScalar::Boolean(self.cycle.is_some())))
    }
}

/// The heaviest directed path ending at each node of a DAG.
///
/// Dynamic programming over a topological order: a node's answer is fixed
/// before any of its out-arcs is relaxed, so one pass over the arcs suffices and
/// the result is exact, not a heuristic. The empty path counts, so every node
/// scores at least zero and a node no arc enters scores exactly zero. Weights
/// come from the projection; without them every arc weighs one and the distance
/// is the hop count.
///
/// **A cycle is a result, not an error.** On a graph with a directed cycle no
/// path is longest — going round again is longer — so the kernel reports no
/// distances and returns the cycle itself as a witness a caller can check: the
/// arcs exist and they close. `topologicalSort` and `bellmanFord` report a cycle
/// the same way, and this kernel finds its cycle with `topologicalSort`.
///
/// **Undirected projections.** Under `Undirected` each non-loop edge is two
/// arcs, there and back, which is a cycle of two; such a projection therefore
/// almost always answers with a cycle. That is the definition applied, not a
/// quirk: the longest *walk* on such a graph is unbounded, and the longest
/// *simple path* is a different, NP-hard problem this kernel does not solve. A
/// self-loop is a cycle of one, in any orientation.
///
/// **Parallel arcs** are arcs like any other: the heaviest of them wins. Ties in
/// distance keep the path found first in topological order, so `hops` is one
/// witness among equals; the distance itself is unambiguous.
///
/// **Negative weights are refused**, though the recurrence would survive them:
/// unlike Dijkstra this kernel makes no assumption that weights are
/// nonnegative — it takes each node's value as final because the topological
/// order says every predecessor came first, not because distances only grow. The
/// guard is a catalog rule rather than a mathematical need. A projection that
/// admits negative weights is built only for `bellmanFord`, no registered path
/// hands one to this kernel, and a kernel that quietly accepted one would be
/// claiming a behaviour nothing exercises. If signed weights are wanted here
/// later, lifting the guard is a documented change with its own tests, not an
/// accident.
///
/// Sequential, and deterministic: the topological order is, and one pass over
/// the arcs in adjacency order follows it. `O(n + m)`; every arc scan is
/// charged.
pub fn longest_path(graph: &GraphProjection) -> Result<LongestPaths> {
    graph.require_nonnegative("longestPath")?;
    let context = graph.execution();
    context.checkpoint()?;
    let n = graph.node_count();

    let order = match topological_sort(graph)? {
        TopologicalOrder::Acyclic(order) => order,
        TopologicalOrder::Cycle(witness) => {
            // The witness closes by repeating its first row; the result reports
            // each node once, in the order the arcs run.
            let rows = witness.values();
            let rows = &rows[..rows.len().saturating_sub(1)];
            context.charge_work(rows.len())?;
            let mut cycle = Buffer::capacity(rows.len(), context)?;
            cycle.values.extend_from_slice(rows);
            return Ok(LongestPaths {
                graph: graph.clone(),
                distances: Buffer::filled(n, 0.0, context)?,
                hops: Buffer::filled(n, 0i64, context)?,
                cycle: Some(cycle),
            });
        }
    };

    let adjacency = graph.outgoing();
    let mut meter = context.work_meter();
    let mut distances = Buffer::filled(n, 0.0f64, context)?;
    let mut hops = Buffer::filled(n, 0i64, context)?;
    for &node in order.values() {
        let range = adjacency.range(node);
        meter.charge(1 + range.len())?;
        let (here, steps) = (distances.values[node], hops.values[node]);
        for arc in range {
            let next = adjacency.target(arc);
            let candidate = here + adjacency.weight(arc);
            if candidate > distances.values[next] {
                distances.values[next] = candidate;
                hops.values[next] = steps + 1;
            }
        }
    }
    if distances.values.iter().any(|value| !value.is_finite()) {
        return Err(AlgorithmError::Numerical(
            "distance left the finite range".into(),
        ));
    }
    Ok(LongestPaths {
        graph: graph.clone(),
        distances,
        hops,
        cycle: None,
    })
}
