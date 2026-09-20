//! Single-source shortest paths with negative weights, or the negative cycle
//! that makes them meaningless.

use crate::{
    AlgorithmError, GraphProjection, Result,
    buffer::Buffer,
    table::{NodeColumn, NodeTable, TableScalar},
};

const NONE: usize = usize::MAX;

/// Distances from one source, or a witness that there are none to give.
pub struct BellmanFord {
    graph: GraphProjection,
    source: usize,
    distances: Buffer<f64>,
    cycle: Option<Buffer<usize>>,
}

impl BellmanFord {
    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// The source's projection row.
    pub fn source(&self) -> usize {
        self.source
    }
    /// Distance per node, infinite where unreachable; `None` when a negative
    /// cycle is reachable from the source, because then no distance past it is
    /// a minimum of anything.
    pub fn distances(&self) -> Option<&[f64]> {
        self.cycle
            .is_none()
            .then_some(self.distances.values.as_slice())
    }
    /// A negative cycle reachable from the source, as projection rows in the
    /// order its arcs run: each node has an arc to the next and the last to the
    /// first, and the weights along it sum below zero.
    pub fn negative_cycle(&self) -> Option<&[usize]> {
        self.cycle.as_ref().map(|cycle| cycle.values.as_slice())
    }

    /// `nodeId`, `distance` (null where unreachable, and everywhere when there
    /// is a negative cycle), `cycleIndex` (a node's position on the witness
    /// cycle, `-1` off it), then the `negativeCycle` scalar.
    pub fn into_table(self) -> Result<NodeTable> {
        let context = self.graph.execution();
        let n = self.graph.node_count();
        context.charge_work(n)?;
        let mut distances = self.distances;
        let mut index = Buffer::filled(n, -1i64, context)?;
        if let Some(cycle) = &self.cycle {
            distances.values.fill(f64::NAN);
            for (position, &node) in cycle.values.iter().enumerate() {
                index.values[node] = i64::try_from(position)
                    .map_err(|_| AlgorithmError::Numerical("cycle exceeds Int64".into()))?;
            }
        } else {
            for distance in &mut distances.values {
                if distance.is_infinite() {
                    *distance = f64::NAN;
                }
            }
        }
        Ok(NodeTable::new(&self.graph)
            .column("distance", NodeColumn::OptionalNumber(distances))?
            .column("cycleIndex", NodeColumn::Integer(index))?
            .scalar("negativeCycle", TableScalar::Boolean(self.cycle.is_some())))
    }
}

/// Shortest-path distances from `source` when weights may be negative.
///
/// This is the one kernel that accepts a *signed* projection (see
/// [`GraphProjection::from_signed_topology`]); it runs on an ordinary one too,
/// where it agrees with [`crate::dijkstra`] and costs more.
///
/// **A negative cycle is a result, not an error.** If one can be reached from
/// the source, distances beyond it have no minimum: every lap lowers them. The
/// kernel then reports no distances and returns the cycle itself as a witness a
/// caller can check — the arcs exist, and their weights sum below zero.
/// `topologicalSort` reports a cycle the same way.
///
/// **Undirected projections.** An undirected edge of negative weight is a
/// negative cycle of two arcs, there and back, and is reported as one. That is
/// the definition applied, not a quirk: on such a graph shortest *walks* do not
/// exist, and shortest *simple paths* are a different, NP-hard problem.
///
/// The queue-based form (Bellman-Ford-Moore, "SPFA"): a node is rescanned only
/// after its distance improves. A path of `n` arcs must repeat a node, so a node
/// whose best path reaches `n` arcs lies after a negative cycle, and walking its
/// predecessors `n` times lands on that cycle. Worst case `O(nm)`; every arc
/// scan is charged, so the work budget bounds it. Sequential, and deterministic:
/// first-in first-out, arcs in adjacency order. Parallel arcs and self-loops are
/// arcs like any other; a negative self-loop is a cycle of one.
pub fn bellman_ford(graph: &GraphProjection, source: &str) -> Result<BellmanFord> {
    let context = graph.execution();
    context.checkpoint()?;
    let source = graph.source(source)?;
    let n = graph.node_count();
    let adjacency = graph.outgoing();
    let mut meter = context.work_meter();

    let mut distances = Buffer::filled(n, f64::INFINITY, context)?;
    let mut parent = Buffer::filled(n, NONE, context)?;
    // Arcs on the best path found so far: reaching `n` proves a repeated node.
    let mut length = Buffer::filled(n, 0usize, context)?;
    let mut queued = Buffer::filled(n, false, context)?;
    // A ring of `n` slots: a node is in the queue at most once.
    let mut ring = Buffer::filled(n, 0usize, context)?;
    let (mut head, mut count) = (0usize, 0usize);

    distances.values[source] = 0.0;
    ring.values[0] = source;
    count += 1;
    queued.values[source] = true;
    let mut beyond_cycle = NONE;

    'scan: while count > 0 {
        let node = ring.values[head];
        head = (head + 1) % n;
        count -= 1;
        queued.values[node] = false;
        let range = adjacency.range(node);
        meter.charge(1 + range.len())?;
        for arc in range {
            let next = adjacency.targets.values[arc];
            let candidate = distances.values[node] + adjacency.weight(arc);
            if candidate < distances.values[next] {
                distances.values[next] = candidate;
                parent.values[next] = node;
                length.values[next] = length.values[node] + 1;
                if length.values[next] >= n {
                    // A best path of `n` arcs repeated a node, so a negative
                    // cycle exists. Predecessors may have been re-pointed since,
                    // though, and the chain from here can still run back to the
                    // source. Then correct the count and keep scanning: labels
                    // keep falling around the cycle until the chain closes.
                    meter.charge(n)?;
                    let mut steps = 0;
                    let mut back = next;
                    while steps < n && parent.values[back] != NONE {
                        back = parent.values[back];
                        steps += 1;
                    }
                    if steps == n {
                        beyond_cycle = next;
                        break 'scan;
                    }
                    length.values[next] = steps;
                }
                if !queued.values[next] {
                    queued.values[next] = true;
                    ring.values[(head + count) % n] = next;
                    count += 1;
                }
            }
        }
    }

    let cycle = if beyond_cycle == NONE {
        if distances
            .values
            .iter()
            .any(|d| d.is_nan() || *d == f64::NEG_INFINITY)
        {
            return Err(AlgorithmError::Numerical(
                "distance left the finite range".into(),
            ));
        }
        None
    } else {
        meter.charge(2 * n)?;
        // `n` steps back cannot still be on the tail leading into the cycle.
        let mut on_cycle = beyond_cycle;
        for _ in 0..n {
            on_cycle = parent.values[on_cycle];
        }
        let mut cycle = Buffer::capacity(n, context)?;
        let mut node = on_cycle;
        loop {
            cycle.values.push(node);
            node = parent.values[node];
            if node == on_cycle {
                break;
            }
        }
        // Predecessors run against the arcs; the witness runs along them.
        cycle.values.reverse();
        Some(cycle)
    };
    Ok(BellmanFord {
        graph: graph.clone(),
        source,
        distances,
        cycle,
    })
}
