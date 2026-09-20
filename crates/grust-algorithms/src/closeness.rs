//! Closeness and harmonic centrality: one shortest-path sweep per node.

use crate::{
    AlgorithmError, GraphProjection, Result,
    buffer::Buffer,
    parallel,
    shortest::MinHeap,
    table::{NodeColumn, NodeTable},
};
use grust_procedures::ExecutionContext;

/// Closeness controls.
#[derive(Clone, Copy, Debug, Default)]
pub struct ClosenessOptions {
    /// Scale each score by the share of other nodes reached, `r / (n-1)`, as
    /// Wasserman and Faust do, so a node central only to a small component does
    /// not rank with one central to a large component.
    pub wasserman_faust: bool,
}

/// Harmonic controls.
#[derive(Clone, Copy, Debug)]
pub struct HarmonicOptions {
    /// Divide by `n-1`, the most any node can score on an unweighted graph.
    pub normalized: bool,
}

impl Default for HarmonicOptions {
    fn default() -> Self {
        Self { normalized: true }
    }
}

/// A distance-based centrality score per node.
pub struct DistanceCentrality {
    graph: GraphProjection,
    scores: Buffer<f64>,
}

impl DistanceCentrality {
    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// Score per node, in projection row order.
    pub fn values(&self) -> &[f64] {
        &self.scores.values
    }
    /// The result as a node table with a `score` column.
    pub fn into_table(self) -> Result<NodeTable> {
        NodeTable::new(&self.graph).column("score", NodeColumn::Number(self.scores))
    }
}

/// Closeness of `v`: `r / Σ d(v, u)` over the `r` other nodes `v` reaches, and
/// zero when it reaches none.
///
/// **Disconnected graphs** are the whole question. This is the per-component
/// form: the mean distance to what is reachable, inverted. It never divides by
/// an infinite distance, but it lets a node in a two-node component score 1.
/// `wasserman_faust` multiplies by `r / (n-1)` to correct that.
///
/// **Direction.** Distances run *from* the node along the projection's arcs.
/// Project with the opposite orientation to measure distances *to* the node.
///
/// **Weights** are distances when the projection has them; a zero weight is
/// rejected, because a zero distance between distinct nodes has no reciprocal.
/// Parallel edges and self-loops change no distance.
///
/// Scores and charged work are identical at any worker count; memory held at once
/// is one workspace per running block of 64 sources.
pub fn closeness(graph: &GraphProjection, options: ClosenessOptions) -> Result<DistanceCentrality> {
    let others = graph.node_count().saturating_sub(1) as f64;
    sweep(graph, |reached, distance_sum, _| {
        if reached == 0 {
            return 0.0;
        }
        let reached = reached as f64;
        let score = reached / distance_sum;
        if options.wasserman_faust {
            score * reached / others
        } else {
            score
        }
    })
}

/// Harmonic centrality of `v`: `Σ 1 / d(v, u)` over the other nodes `v` reaches.
/// An unreachable node contributes zero, so no convention for disconnected
/// graphs is needed. Direction, weights and determinism are as for
/// [`closeness`].
pub fn harmonic(graph: &GraphProjection, options: HarmonicOptions) -> Result<DistanceCentrality> {
    let others = graph.node_count().saturating_sub(1) as f64;
    sweep(graph, |_, _, reciprocal_sum| {
        if options.normalized && others > 0.0 {
            reciprocal_sum / others
        } else {
            reciprocal_sum
        }
    })
}

/// Sources per block; fixed, so nothing depends on the worker count.
const BLOCK: usize = 64;

/// Run one sweep per node and score it from (nodes reached, Σ d, Σ 1/d).
fn sweep(
    graph: &GraphProjection,
    score: impl Fn(usize, f64, f64) -> f64 + Sync,
) -> Result<DistanceCentrality> {
    let context = graph.execution();
    context.checkpoint()?;
    let n = graph.node_count();
    let adjacency = graph.outgoing();
    let weighted = adjacency.weights.is_some();
    if let Some(weights) = &adjacency.weights {
        let mut meter = context.work_meter();
        for &weight in &weights.values {
            meter.charge(1)?;
            if weight == 0.0 {
                return Err(AlgorithmError::InvalidArguments(
                    "distance centralities need positive weights: a zero distance between distinct nodes has no reciprocal".into(),
                ));
            }
        }
    }
    let mut scores = Buffer::filled(n, 0.0f64, context)?;
    let workers = parallel::concurrency(
        context,
        n.saturating_mul(n.saturating_add(adjacency.targets.values.len())),
    );
    parallel::ordered_blocks(
        workers,
        n.div_ceil(BLOCK),
        |block| {
            let first = block * BLOCK;
            let last = (first + BLOCK).min(n);
            let mut workspace = Workspace::new(n, weighted, context)?;
            let mut part = Buffer::capacity(last - first, context)?;
            for source in first..last {
                let (reached, distance_sum, reciprocal_sum) = workspace.run(graph, source)?;
                part.values
                    .push(score(reached, distance_sum, reciprocal_sum));
            }
            Ok(part)
        },
        |block, part: Buffer<f64>| {
            let first = block * BLOCK;
            scores.values[first..first + part.values.len()].copy_from_slice(&part.values);
            Ok(())
        },
    )?;
    Ok(DistanceCentrality {
        graph: graph.clone(),
        scores,
    })
}

struct Workspace {
    /// One meter for the block: creating a meter registers it, which is too
    /// much to pay per node.
    meter: grust_procedures::WorkMeter,
    distance: Buffer<f64>,
    order: Buffer<usize>,
    heap: Option<MinHeap>,
}

impl Workspace {
    fn new(n: usize, weighted: bool, context: &ExecutionContext) -> Result<Self> {
        Ok(Self {
            meter: context.work_meter(),
            distance: Buffer::filled(n, f64::INFINITY, context)?,
            order: Buffer::capacity(n, context)?,
            heap: weighted.then(|| MinHeap::new(n, context)).transpose()?,
        })
    }

    /// Settle everything reachable from `source`, summing in settle order, which
    /// the queue and the heap's tie-break make a function of the graph alone.
    fn run(&mut self, graph: &GraphProjection, source: usize) -> Result<(usize, f64, f64)> {
        let adjacency = graph.outgoing();
        self.order.values.clear();
        self.distance.values[source] = 0.0;
        if let Some(heap) = &mut self.heap {
            heap.improve(source, 0.0, &mut self.meter)?;
            while let Some((cost, node)) = heap.pop(&mut self.meter)? {
                self.order.values.push(node);
                let range = adjacency.range(node);
                self.meter.charge(1 + range.len())?;
                for arc in range {
                    let next = adjacency.targets.values[arc];
                    let candidate = cost + adjacency.weight(arc);
                    if candidate < self.distance.values[next] {
                        self.distance.values[next] = candidate;
                        heap.improve(next, candidate, &mut self.meter)?;
                    }
                }
            }
        } else {
            self.order.values.push(source);
            let mut head = 0;
            while head < self.order.values.len() {
                let node = self.order.values[head];
                head += 1;
                let range = adjacency.range(node);
                self.meter.charge(1 + range.len())?;
                for arc in range {
                    let next = adjacency.targets.values[arc];
                    if self.distance.values[next].is_infinite() {
                        self.distance.values[next] = self.distance.values[node] + 1.0;
                        self.order.values.push(next);
                    }
                }
            }
        }
        let (mut distance_sum, mut reciprocal_sum) = (0.0, 0.0);
        for &node in &self.order.values[1..] {
            distance_sum += self.distance.values[node];
            reciprocal_sum += 1.0 / self.distance.values[node];
        }
        let reached = self.order.values.len() - 1;
        for &node in &self.order.values {
            self.distance.values[node] = f64::INFINITY;
        }
        Ok((reached, distance_sum, reciprocal_sum))
    }
}
