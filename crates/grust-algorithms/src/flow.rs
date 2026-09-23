//! Maximum flow and minimum cut by Dinic's algorithm.

use crate::{
    AlgorithmError, GraphProjection, Result,
    buffer::Buffer,
    table::{NodeColumn, NodeTable, TableScalar},
};

const UNSEEN: usize = usize::MAX;

/// A maximum flow and the minimum cut that proves it.
pub struct MaxFlow {
    graph: GraphProjection,
    value: f64,
    from: Buffer<usize>,
    to: Buffer<usize>,
    edges: Buffer<usize>,
    flows: Buffer<f64>,
    source_side: Buffer<bool>,
}

impl MaxFlow {
    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// The flow's value, which is also the cut's capacity.
    pub fn value(&self) -> f64 {
        self.value
    }
    /// One entry per edge carrying flow: (from row, to row, index into
    /// [`GraphProjection::edges`], flow), in edge order. `from -> to` is the
    /// direction the flow travels, whichever way the edge was stored.
    pub fn flows(&self) -> impl Iterator<Item = (usize, usize, usize, f64)> + '_ {
        (0..self.flows.values.len()).map(|row| {
            (
                self.from.values[row],
                self.to.values[row],
                self.edges.values[row],
                self.flows.values[row],
            )
        })
    }
    /// Per node, whether it lies on the source's side of the minimum cut.
    pub fn source_side(&self) -> &[bool] {
        &self.source_side.values
    }

    /// Rows of `sourceNodeId`, `targetNodeId`, `edgeOrdinal`, `flow`, one per
    /// edge carrying flow, then the `maxFlow` scalar.
    pub fn into_flow_table(self) -> Result<NodeTable> {
        let context = self.graph.execution();
        let count = self.edges.values.len();
        context.charge_work(count)?;
        let mut ordinals = Buffer::capacity(count, context)?;
        for &slot in &self.edges.values {
            ordinals.values.push(
                i64::try_from(self.graph.edges()[slot].ordinal)
                    .map_err(|_| AlgorithmError::Numerical("edge ordinal exceeds Int64".into()))?,
            );
        }
        Ok(NodeTable::keyed(&self.graph, "sourceNodeId", self.from)?
            .column("targetNodeId", NodeColumn::Node(self.to))?
            .column("edgeOrdinal", NodeColumn::Integer(ordinals))?
            .column("flow", NodeColumn::Number(self.flows))?
            .scalar("maxFlow", TableScalar::Number(self.value)))
    }

    /// Rows of `nodeId`, `sourceSide`, one per node, then the `maxFlow` scalar.
    pub fn into_cut_table(self) -> Result<NodeTable> {
        Ok(NodeTable::new(&self.graph)
            .column("sourceSide", NodeColumn::Boolean(self.source_side))?
            .scalar("maxFlow", TableScalar::Number(self.value)))
    }
}

/// The most that can be sent from `source` to `target` when each arc carries at
/// most its weight, and a minimum cut: the nodes still reachable from `source`
/// once the flow is in place. Arcs leaving that set are full, and their
/// capacities sum to the flow's value.
///
/// **Capacities** are the projection's weights, or one per arc without them.
/// Parallel edges are separate capacities. Self-loops and zero capacities carry
/// nothing. On an undirected projection an edge carries up to its capacity in
/// either direction, and its row reports the net flow in the direction it runs.
///
/// **Exactness.** With integral capacities every quantity is exact. With
/// fractional ones the flow is a sum of floating-point augmentations: it is
/// feasible, and maximal up to rounding.
///
/// Dinic's algorithm, iteratively, so a long path does not overflow a stack.
/// Sequential: a blocking flow is built one augmenting path at a time.
pub fn max_flow(graph: &GraphProjection, source: &str, target: &str) -> Result<MaxFlow> {
    graph.require_nonnegative("maxFlow")?;
    let context = graph.execution();
    context.checkpoint()?;
    let source = graph.source(source)?;
    let target = graph.source(target)?;
    if source == target {
        return Err(AlgorithmError::InvalidArguments(
            "max flow needs a target other than its source".into(),
        ));
    }
    let n = graph.node_count();
    let adjacency = graph.outgoing();
    let mut meter = context.work_meter();
    let carries =
        |node: usize, arc: usize| adjacency.target(arc) != node && adjacency.weight(arc) > 0.0;

    // Residual arcs grouped by tail: each projection arc, and its reverse.
    let mut offsets = Buffer::filled(n + 1, 0usize, context)?;
    for node in 0..n {
        let range = adjacency.range(node);
        meter.charge(1 + range.len())?;
        for arc in range {
            if carries(node, arc) {
                offsets.values[node + 1] += 1;
                offsets.values[adjacency.target(arc) + 1] += 1;
            }
        }
    }
    for node in 0..n {
        offsets.values[node + 1] += offsets.values[node];
    }
    let count = offsets.values[n];
    let mut head = Buffer::filled(count, 0usize, context)?;
    let mut capacity = Buffer::filled(count, 0.0f64, context)?;
    let mut pair = Buffer::filled(count, 0usize, context)?;
    // The edge a forward arc stands for; `UNSEEN` marks a reverse arc.
    let mut edge = Buffer::filled(count, UNSEEN, context)?;
    let mut cursor = Buffer::capacity(n, context)?;
    cursor.values.extend_from_slice(&offsets.values[..n]);
    for node in 0..n {
        let range = adjacency.range(node);
        meter.charge(1 + range.len())?;
        for arc in range {
            if !carries(node, arc) {
                continue;
            }
            let other = adjacency.target(arc);
            let forward = cursor.values[node];
            cursor.values[node] += 1;
            let backward = cursor.values[other];
            cursor.values[other] += 1;
            head.values[forward] = other;
            capacity.values[forward] = adjacency.weight(arc);
            pair.values[forward] = backward;
            edge.values[forward] = adjacency.edge_slot(arc);
            head.values[backward] = node;
            pair.values[backward] = forward;
        }
    }

    let mut level = Buffer::filled(n, UNSEEN, context)?;
    let mut queue = Buffer::capacity(n, context)?;
    let mut path: Buffer<usize> = Buffer::capacity(n, context)?;
    let mut value = 0.0f64;
    loop {
        // Layer the residual graph by distance from the source.
        level.values.fill(UNSEEN);
        queue.values.clear();
        level.values[source] = 0;
        queue.values.push(source);
        let mut front = 0;
        meter.charge(n)?;
        while front < queue.values.len() {
            let node = queue.values[front];
            front += 1;
            let range = offsets.values[node]..offsets.values[node + 1];
            meter.charge(1 + range.len())?;
            for arc in range {
                let next = head.values[arc];
                if capacity.values[arc] > 0.0 && level.values[next] == UNSEEN {
                    level.values[next] = level.values[node] + 1;
                    queue.values.push(next);
                }
            }
        }
        if level.values[target] == UNSEEN {
            break;
        }
        // Saturate it: augment along layered paths until none is left. An arc
        // that led nowhere is never tried again within this layering.
        cursor.values.copy_from_slice(&offsets.values[..n]);
        loop {
            path.values.clear();
            let mut node = source;
            while node != target {
                meter.charge(1)?;
                let arc = cursor.values[node];
                if arc < offsets.values[node + 1] {
                    let next = head.values[arc];
                    if capacity.values[arc] > 0.0 && level.values[next] == level.values[node] + 1 {
                        path.values.push(arc);
                        node = next;
                    } else {
                        cursor.values[node] += 1;
                    }
                } else if let Some(arc) = path.values.pop() {
                    // Dead end: step back and give up on the arc that led here.
                    node = head.values[pair.values[arc]];
                    cursor.values[node] += 1;
                } else {
                    break;
                }
            }
            if node != target {
                break;
            }
            let bottleneck = path
                .values
                .iter()
                .map(|&arc| capacity.values[arc])
                .fold(f64::INFINITY, f64::min);
            meter.charge(path.values.len())?;
            for &arc in &path.values {
                capacity.values[arc] -= bottleneck;
                capacity.values[pair.values[arc]] += bottleneck;
            }
            value += bottleneck;
        }
    }
    if !value.is_finite() {
        return Err(AlgorithmError::Numerical("flow value is not finite".into()));
    }

    // Net flow per edge. A reverse arc's capacity is exactly what its forward
    // arc carries; an undirected edge has two forward arcs, one each way.
    let edges = graph.edges();
    let mut net = Buffer::filled(edges.len(), 0.0f64, context)?;
    // Which way the edge's first-seen forward arc runs: (tail, head).
    let mut along = Buffer::filled(edges.len(), (UNSEEN, UNSEEN), context)?;
    for node in 0..n {
        let range = offsets.values[node]..offsets.values[node + 1];
        meter.charge(1 + range.len())?;
        for arc in range {
            let slot = edge.values[arc];
            if slot == UNSEEN {
                continue;
            }
            let carried = capacity.values[pair.values[arc]];
            if along.values[slot].0 == UNSEEN {
                along.values[slot] = (node, head.values[arc]);
                net.values[slot] += carried;
            } else {
                net.values[slot] -= carried;
            }
        }
    }
    let used = net.values.iter().filter(|&&flow| flow != 0.0).count();
    meter.charge(edges.len() + n)?;
    let mut from = Buffer::capacity(used, context)?;
    let mut to = Buffer::capacity(used, context)?;
    let mut slots = Buffer::capacity(used, context)?;
    let mut flows = Buffer::capacity(used, context)?;
    for slot in 0..edges.len() {
        let flow = net.values[slot];
        if flow == 0.0 {
            continue;
        }
        let (tail, tip) = along.values[slot];
        let (tail, tip) = if flow > 0.0 { (tail, tip) } else { (tip, tail) };
        from.values.push(tail);
        to.values.push(tip);
        slots.values.push(slot);
        flows.values.push(flow.abs());
    }
    let mut source_side = Buffer::capacity(n, context)?;
    source_side
        .values
        .extend(level.values.iter().map(|&depth| depth != UNSEEN));
    Ok(MaxFlow {
        graph: graph.clone(),
        value,
        from,
        to,
        edges: slots,
        flows,
        source_side,
    })
}
