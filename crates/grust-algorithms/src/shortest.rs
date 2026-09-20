//! Nonnegative shortest paths with an indexed O(V) heap and reusable path output.

use std::ops::ControlFlow;

use crate::{AlgorithmError, Distances, ExecutionContext, GraphProjection, Result, buffer::Buffer};

/// One shortest-path tree. Equal-cost alternatives keep the first discovered
/// predecessor in stable adjacency order. Only strict improvements change it,
/// so zero-weight cycles cannot create cyclic predecessor chains.
pub struct ShortestPaths {
    distances: Distances,
    parents: Buffer<Option<(usize, usize)>>,
    source: usize,
}

/// Borrowed full path valid only during a visitor call. Node rows map through
/// `GraphProjection::node_ids`; edge slots map through `GraphProjection::edges`.
pub struct PathView<'a> {
    /// Destination row in the projection.
    pub target: usize,
    /// Source first, destination last.
    pub nodes: &'a [usize],
    /// Cumulative cost at each node, starting at zero.
    pub costs: &'a [f64],
    /// Original edge slots, with one entry per hop.
    pub edges: &'a [usize],
}

impl ShortestPaths {
    /// Distances for all selected nodes, including unreachable nodes.
    pub fn distances(&self) -> &Distances {
        &self.distances
    }

    /// Visit one full path per reachable node in projection row order, including
    /// the zero-hop source path. Scratch is allocated once and reused. Every
    /// reconstructed node and edge is consumed normally; no path-size formula
    /// substitutes for reconstruction. Returning `Break` stops immediately.
    pub fn visit_paths<B>(
        &self,
        mut visitor: impl FnMut(PathView<'_>) -> Result<ControlFlow<B>>,
    ) -> Result<ControlFlow<B>> {
        let mut buffers = PathBuffers::new(self)?;
        while let Some(target) = buffers.advance(self)? {
            if let ControlFlow::Break(value) = visitor(buffers.view(target))? {
                return Ok(ControlFlow::Break(value));
            }
        }
        Ok(ControlFlow::Continue(()))
    }

    /// Transfer this tree to a pull cursor owning reusable admitted path buffers.
    pub fn into_cursor(self) -> Result<PathCursor> {
        let buffers = PathBuffers::new(&self)?;
        Ok(PathCursor {
            state: Some((self, buffers)),
            failed: false,
        })
    }
}

/// Demand-driven full paths. A returned view borrows the cursor until the next
/// poll, preventing accidental reuse of its scratch while the view is live.
/// Failure and completion release kernel and scratch storage immediately.
pub struct PathCursor {
    state: Option<(ShortestPaths, PathBuffers)>,
    failed: bool,
}

impl PathCursor {
    /// Reconstruct the next reachable path, including the zero-hop source path.
    pub fn next_path(&mut self) -> Result<Option<PathView<'_>>> {
        if self.failed {
            return Err(AlgorithmError::CursorFailed);
        }
        let outcome = match self.state.as_mut() {
            Some((paths, buffers)) => buffers.advance(paths),
            None => return Ok(None),
        };
        match outcome {
            Ok(Some(target)) => Ok(self.state.as_ref().map(|(_, buffers)| buffers.view(target))),
            Ok(None) => {
                self.state = None;
                Ok(None)
            }
            Err(error) => {
                self.failed = true;
                self.state = None;
                Err(error)
            }
        }
    }
}

struct PathBuffers {
    nodes: Buffer<usize>,
    costs: Buffer<f64>,
    edges: Buffer<usize>,
    next: usize,
}

impl PathBuffers {
    fn new(paths: &ShortestPaths) -> Result<Self> {
        let graph = paths.distances.projection();
        let context = graph.execution();
        Ok(Self {
            nodes: Buffer::capacity(graph.node_count(), context)?,
            costs: Buffer::capacity(graph.node_count(), context)?,
            edges: Buffer::capacity(graph.node_count().saturating_sub(1), context)?,
            next: 0,
        })
    }

    fn advance(&mut self, paths: &ShortestPaths) -> Result<Option<usize>> {
        let graph = paths.distances.projection();
        let context = graph.execution();
        while self.next < graph.node_count() {
            context.charge_work(1)?;
            let target = self.next;
            self.next += 1;
            if paths.distances.values()[target].is_infinite() {
                continue;
            }
            self.nodes.values.clear();
            self.costs.values.clear();
            self.edges.values.clear();
            // One unit per step, as `reverse` charges: in blocks of at most 1024
            // steps, because a per-step admit cost more than the step.
            let mut node = target;
            let mut uncharged = 0usize;
            loop {
                uncharged += 1;
                if uncharged == 1024 {
                    context.charge_work(std::mem::take(&mut uncharged))?;
                }
                self.nodes.values.push(node);
                self.costs.values.push(paths.distances.values()[node]);
                if node == paths.source {
                    context.charge_work(uncharged)?;
                    break;
                }
                let (parent, edge) = paths.parents.values[node].ok_or_else(|| {
                    AlgorithmError::Numerical("missing shortest-path predecessor".into())
                })?;
                self.edges.values.push(edge);
                node = parent;
            }
            reverse(&mut self.nodes.values, context)?;
            reverse(&mut self.costs.values, context)?;
            reverse(&mut self.edges.values, context)?;
            return Ok(Some(target));
        }
        Ok(None)
    }

    fn view(&self, target: usize) -> PathView<'_> {
        PathView {
            target,
            nodes: &self.nodes.values,
            costs: &self.costs.values,
            edges: &self.edges.values,
        }
    }
}

fn reverse<T>(values: &mut [T], context: &ExecutionContext) -> Result<()> {
    for start in (0..values.len() / 2).step_by(1024) {
        let end = start + (values.len() / 2 - start).min(1024);
        context.charge_work(end - start)?;
        for index in start..end {
            values.swap(index, values.len() - index - 1);
        }
    }
    Ok(())
}

/// Minimum weighted distances. Unit weights are used when none were projected.
/// A reachable cost that overflows finite f64 is an explicit numerical error.
pub fn dijkstra(graph: &GraphProjection, source: &str) -> Result<Distances> {
    graph.require_nonnegative("dijkstra")?;
    let (distances, _) = run(graph, source, false)?;
    Ok(distances)
}

/// Compute a predecessor tree for streaming full shortest paths.
pub fn shortest_paths(graph: &GraphProjection, source: &str) -> Result<ShortestPaths> {
    graph.require_nonnegative("shortestPaths")?;
    let source_row = graph.source(source)?;
    let (distances, parents) = run(graph, source, true)?;
    let parents = parents.ok_or_else(|| {
        AlgorithmError::Numerical("shortest-path predecessor storage missing".into())
    })?;
    Ok(ShortestPaths {
        distances,
        parents,
        source: source_row,
    })
}

type Parents = Buffer<Option<(usize, usize)>>;

fn run(graph: &GraphProjection, source: &str, paths: bool) -> Result<(Distances, Option<Parents>)> {
    let context = graph.execution();
    let mut meter = context.work_meter();
    context.checkpoint()?;
    let source = graph.source(source)?;
    let n = graph.node_count();
    let mut distances = Buffer::filled(n, f64::INFINITY, context)?;
    let mut parents = paths
        .then(|| Buffer::filled(n, None, context))
        .transpose()?;
    let mut heap = MinHeap::new(n, context)?;
    distances.values[source] = 0.0;
    heap.improve(source, 0.0, &mut meter)?;
    let adjacency = graph.outgoing();
    while let Some((cost, node)) = heap.pop(&mut meter)? {
        meter.charge(1)?;
        for arc in adjacency.range(node) {
            meter.charge(1)?;
            let next = adjacency.targets.values[arc];
            let candidate = cost + adjacency.weight(arc);
            if !candidate.is_finite() {
                return Err(AlgorithmError::Numerical(
                    "shortest-path cost overflow".into(),
                ));
            }
            if candidate < distances.values[next] {
                distances.values[next] = candidate;
                if let Some(parents) = &mut parents {
                    parents.values[next] = Some((node, adjacency.edge_slot(arc)));
                }
                heap.improve(next, candidate, &mut meter)?;
            }
        }
    }
    Ok((Distances::new(graph, distances), parents))
}

// Each vertex occupies at most one heap entry. Dense inverse positions avoid
// unbounded stale entries on graphs with many parallel edges or relaxations.
pub(crate) struct MinHeap {
    entries: Buffer<(f64, usize)>,
    positions: Buffer<usize>,
}

impl MinHeap {
    pub(crate) fn new(n: usize, context: &ExecutionContext) -> Result<Self> {
        Ok(Self {
            entries: Buffer::capacity(n, context)?,
            positions: Buffer::filled(n, usize::MAX, context)?,
        })
    }

    fn less(&self, left: usize, right: usize) -> bool {
        let (a, ai) = self.entries.values[left];
        let (b, bi) = self.entries.values[right];
        a.total_cmp(&b).then_with(|| ai.cmp(&bi)).is_lt()
    }

    fn swap(&mut self, left: usize, right: usize) {
        self.entries.values.swap(left, right);
        self.positions.values[self.entries.values[left].1] = left;
        self.positions.values[self.entries.values[right].1] = right;
    }

    pub(crate) fn improve(
        &mut self,
        node: usize,
        cost: f64,
        meter: &mut grust_procedures::WorkMeter,
    ) -> Result<()> {
        let mut index = self.positions.values[node];
        if index == usize::MAX {
            index = self.entries.values.len();
            self.entries.values.push((cost, node));
            self.positions.values[node] = index;
        } else {
            self.entries.values[index].0 = cost;
        }
        while index > 0 {
            meter.charge(1)?;
            let parent = (index - 1) / 2;
            if !self.less(index, parent) {
                break;
            }
            self.swap(index, parent);
            index = parent;
        }
        Ok(())
    }

    pub(crate) fn pop(
        &mut self,
        meter: &mut grust_procedures::WorkMeter,
    ) -> Result<Option<(f64, usize)>> {
        if self.entries.values.is_empty() {
            return Ok(None);
        }
        let result = self.entries.values.swap_remove(0);
        self.positions.values[result.1] = usize::MAX;
        if self.entries.values.is_empty() {
            return Ok(Some(result));
        }
        self.positions.values[self.entries.values[0].1] = 0;
        let mut index = 0;
        while index < self.entries.values.len() / 2 {
            meter.charge(1)?;
            let left = index * 2 + 1;
            let right = left + 1;
            let child = if right < self.entries.values.len() && self.less(right, left) {
                right
            } else {
                left
            };
            if !self.less(child, index) {
                break;
            }
            self.swap(index, child);
            index = child;
        }
        Ok(Some(result))
    }
}
