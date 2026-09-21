//! A* : shortest path to one destination, guided by an estimate of what is left.

use crate::{
    AlgorithmError, GraphProjection, NodeProperties, PropertyKind, PropertyRequest, Result,
    buffer::Buffer,
    shortest::MinHeap,
    table::{NodeColumn, NodeTable, TableScalar},
};

const NONE: usize = usize::MAX;

/// One shortest path, and what finding it cost.
pub struct AStarPath {
    graph: GraphProjection,
    source: usize,
    target: usize,
    /// Source first, destination last; empty when the target is unreachable.
    nodes: Buffer<usize>,
    /// Cumulative cost at each node, starting at zero.
    costs: Buffer<f64>,
    /// Original edge slots, one per hop.
    edges: Buffer<usize>,
    settled: usize,
}

impl AStarPath {
    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// Source and destination rows.
    pub fn endpoints(&self) -> (usize, usize) {
        (self.source, self.target)
    }
    /// The path as projection rows, source first; empty when unreachable.
    pub fn nodes(&self) -> &[usize] {
        &self.nodes.values
    }
    /// Cumulative cost at each node of [`Self::nodes`].
    pub fn costs(&self) -> &[f64] {
        &self.costs.values
    }
    /// Edge slots, one per hop, indexing [`GraphProjection::edges`].
    pub fn edges(&self) -> &[usize] {
        &self.edges.values
    }
    /// Total cost, or `None` when the target cannot be reached.
    pub fn total_cost(&self) -> Option<f64> {
        self.costs.values.last().copied()
    }
    /// Nodes settled before the destination was reached. The measure of what
    /// the heuristic saved: a heuristic of zero settles what Dijkstra settles.
    pub fn settled(&self) -> usize {
        self.settled
    }

    /// One row per node on the path, in order: `nodeId`, `costFromSource`,
    /// `edgeOrdinal` (`-1` on the source, which was reached by no edge), then
    /// the `totalCost` and `settled` scalars. No rows when unreachable.
    pub fn into_table(self) -> Result<NodeTable> {
        let context = self.graph.execution();
        let rows = self.nodes.values.len();
        context.charge_work(rows)?;
        let mut ordinals = Buffer::capacity(rows, context)?;
        for hop in 0..rows {
            // The source is entered by no edge; every later node by one.
            ordinals.values.push(if hop == 0 {
                -1
            } else {
                i64::try_from(self.graph.edges()[self.edges.values[hop - 1]].ordinal)
                    .map_err(|_| AlgorithmError::Numerical("edge ordinal exceeds Int64".into()))?
            });
        }
        let settled = i64::try_from(self.settled)
            .map_err(|_| AlgorithmError::Numerical("settled count exceeds Int64".into()))?;
        let total = self.total_cost().unwrap_or(f64::NAN);
        Ok(NodeTable::keyed(&self.graph, "nodeId", self.nodes)?
            .column("costFromSource", NodeColumn::Number(self.costs))?
            .column("edgeOrdinal", NodeColumn::Integer(ordinals))?
            .scalar("totalCost", TableScalar::Number(total))
            .scalar("settled", TableScalar::Integer(settled)))
    }
}

/// Shortest path from `source` to `target`, guided by `heuristic`.
///
/// **What the heuristic must be.** `heuristic(v)` estimates the cost still to
/// come from `v` to the target. It must never exceed the true remaining cost —
/// it must be *admissible* — and it must be finite and nonnegative. Given that,
/// the path returned is a shortest path, the same one [`crate::dijkstra`] would
/// find. Overestimate and the search becomes faster and wrong, which is the one
/// failure this kernel cannot detect for you: an estimate that is too large is
/// indistinguishable from a graph that is genuinely more expensive.
///
/// **Units are yours to keep straight.** The estimate is compared against
/// accumulated edge weights, so it must be in their units. Great-circle metres
/// against weights in metres is admissible; the same metres against weights in
/// seconds is not, and is the usual way this goes wrong.
///
/// **What it saves.** A heuristic of zero makes this exactly Dijkstra, settling
/// the same nodes in the same order. A good one settles far fewer, which
/// [`AStarPath::settled`] reports so the saving is measured rather than assumed.
///
/// A node may be settled more than once: with an admissible but inconsistent
/// heuristic a shorter route to an already-settled node can appear later, and
/// reopening it is what keeps the result optimal rather than merely plausible.
/// Weights must be nonnegative, as for Dijkstra; `bellmanFord` is the kernel
/// that admits negative ones.
pub fn astar(
    graph: &GraphProjection,
    source: &str,
    target: &str,
    heuristic: impl Fn(usize) -> f64,
) -> Result<AStarPath> {
    graph.require_nonnegative("astar")?;
    let context = graph.execution();
    context.checkpoint()?;
    let source = graph.source(source)?;
    let target = graph.source(target)?;
    let n = graph.node_count();
    let adjacency = graph.outgoing();
    let mut meter = context.work_meter();

    let estimate = |node: usize| -> Result<f64> {
        let value = heuristic(node);
        if !value.is_finite() || value < 0.0 {
            return Err(AlgorithmError::InvalidArguments(format!(
                "the heuristic returned {value} for node {node}: it must be finite and nonnegative"
            )));
        }
        Ok(value)
    };

    // `cost` is the best known distance from the source; the heap is ordered by
    // that plus the estimate, so the queue explores toward the target while the
    // recorded costs stay comparable with Dijkstra's.
    let mut cost = Buffer::filled(n, f64::INFINITY, context)?;
    let mut parent = Buffer::filled(n, (NONE, NONE), context)?;
    let mut heap = MinHeap::new(n, context)?;
    cost.values[source] = 0.0;
    heap.improve(source, estimate(source)?, &mut meter)?;
    let mut settled = 0usize;
    let mut reached = false;

    while let Some((_, node)) = heap.pop(&mut meter)? {
        settled += 1;
        if node == target {
            reached = true;
            break;
        }
        let range = adjacency.range(node);
        meter.charge(1 + range.len())?;
        let here = cost.values[node];
        for arc in range {
            let next = adjacency.targets.values[arc];
            let candidate = here + adjacency.weight(arc);
            if candidate < cost.values[next] {
                cost.values[next] = candidate;
                parent.values[next] = (node, adjacency.edge_slot(arc));
                // Re-inserting a settled node is deliberate: see the note above.
                heap.improve(next, candidate + estimate(next)?, &mut meter)?;
            }
        }
    }

    let mut nodes = Buffer::capacity(if reached { n } else { 0 }, context)?;
    let mut edges = Buffer::capacity(if reached { n } else { 0 }, context)?;
    let mut costs = Buffer::capacity(if reached { n } else { 0 }, context)?;
    if reached {
        // Walk the predecessors back, then reverse: the path is built from its
        // destination and reported from its source.
        let mut node = target;
        while node != source {
            meter.charge(1)?;
            nodes.values.push(node);
            let (previous, slot) = parent.values[node];
            edges.values.push(slot);
            node = previous;
        }
        nodes.values.push(source);
        nodes.values.reverse();
        edges.values.reverse();
        for &node in &nodes.values {
            costs.values.push(cost.values[node]);
        }
    }
    Ok(AStarPath {
        graph: graph.clone(),
        source,
        target,
        nodes,
        costs,
        edges,
        settled,
    })
}

/// Mean Earth radius in metres, as WGS-84 defines it for a sphere.
const EARTH_RADIUS_METRES: f64 = 6_371_008.8;

/// The node properties [`astar_haversine`] reads: latitude and longitude in
/// degrees, required on every projected node.
pub fn haversine_requests<'a>(latitude: &'a str, longitude: &'a str) -> [PropertyRequest<'a>; 2] {
    [
        PropertyRequest::required(latitude, PropertyKind::Number),
        PropertyRequest::required(longitude, PropertyKind::Number),
    ]
}

/// [`astar`] with the great-circle distance to the target as its heuristic,
/// read from two node properties in degrees.
///
/// **This is admissible only when the weights are distances in metres**, since
/// no route between two points is shorter than the great circle between them.
/// With weights in any other unit — travel time, a toll, a hop count — it is
/// not a lower bound and the result is not a shortest path. The kernel cannot
/// check this, so it is stated here and in the procedure's documentation.
///
/// A latitude outside ±90° or a longitude outside ±180° is rejected: it is
/// almost always a column in the wrong order.
pub fn astar_haversine(
    properties: &NodeProperties,
    source: &str,
    target: &str,
    latitude: &str,
    longitude: &str,
) -> Result<AStarPath> {
    let graph = properties.projection();
    let latitudes = properties.numbers(latitude)?;
    let longitudes = properties.numbers(longitude)?;
    let context = graph.execution();
    context.charge_work(latitudes.len())?;
    for (row, (&lat, &lon)) in latitudes.iter().zip(longitudes).enumerate() {
        if !(-90.0..=90.0).contains(&lat) || !(-180.0..=180.0).contains(&lon) {
            return Err(AlgorithmError::InvalidArguments(format!(
                "node row {row} has latitude {lat} and longitude {lon}: latitude must be within ±90° and longitude within ±180°"
            )));
        }
    }
    let destination = graph.source(target)?;
    let (target_lat, target_lon) = (
        latitudes[destination].to_radians(),
        longitudes[destination].to_radians(),
    );
    astar(graph, source, target, |node| {
        haversine(
            latitudes[node].to_radians(),
            longitudes[node].to_radians(),
            target_lat,
            target_lon,
        )
    })
}

/// Great-circle distance in metres between two points given in radians.
fn haversine(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    let half_lat = (lat2 - lat1) / 2.0;
    let half_lon = (lon2 - lon1) / 2.0;
    let a = half_lat.sin().powi(2) + lat1.cos() * lat2.cos() * half_lon.sin().powi(2);
    // `a` can exceed 1 by a rounding step at antipodal points, where `asin`
    // would return NaN and the heuristic would be rejected as not finite.
    2.0 * EARTH_RADIUS_METRES * a.clamp(0.0, 1.0).sqrt().asin()
}
