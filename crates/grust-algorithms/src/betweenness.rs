//! Betweenness centrality by Brandes' algorithm, exact or from sampled sources.

use crate::{
    AlgorithmError, GraphProjection, Orientation, Result,
    buffer::Buffer,
    parallel, random,
    shortest::MinHeap,
    table::{NodeColumn, NodeTable},
};
use grust_procedures::ExecutionContext;

/// Betweenness controls.
#[derive(Clone, Copy, Debug, Default)]
pub struct BetweennessOptions {
    /// Use this many source nodes, drawn without replacement, and scale the sum
    /// by `n / samplingSize` so it estimates the exact score. `None`, or a size
    /// of at least `n`, is exact.
    pub sampling_size: Option<usize>,
    /// Seed for the draw. The same seed draws the same sources.
    pub seed: u64,
    /// Divide by the number of ordered pairs a node could lie between:
    /// `(n-1)(n-2)`, or half that on an undirected projection.
    pub normalized: bool,
}

/// A betweenness score per node.
pub struct Betweenness {
    graph: GraphProjection,
    scores: Buffer<f64>,
}

impl Betweenness {
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

/// Blocks to aim for, and the most sources any one block may hold.
///
/// A block of a fixed 64 sources left a sampled run with one block and therefore
/// one thread: `samplingSize` of 64, the size a sampled betweenness is usually
/// asked for, is exactly one block. Measured on facebook_combined at sixteen
/// workers, 64 sampled sources: 1.00x before, because there was nothing to
/// spread. The block size is now derived from the number of sources alone, never
/// from the worker count, so which sums are formed and in what order still does
/// not depend on how many threads run them.
const BLOCKS: usize = 64;
const MAX_SOURCES_PER_BLOCK: usize = 64;

/// Sources per block for `count` sources.
fn block_size(count: usize) -> usize {
    count.div_ceil(BLOCKS).clamp(1, MAX_SOURCES_PER_BLOCK)
}

/// For every node `v`, the sum over ordered pairs `s != v != t` of the share of
/// shortest `s`-`t` paths that pass through `v`.
///
/// **Orientation.** Paths follow the projection's arcs. On an undirected
/// projection each unordered pair is reached from both ends, so the sum is
/// halved, as Brandes specifies.
///
/// **Multigraphs.** Parallel edges are distinct shortest paths and each counts.
/// Self-loops lie on no shortest path.
///
/// **Weights.** An unweighted projection uses hop counts. A weighted one uses
/// Dijkstra and treats two path costs as tied when they are equal as `f64`,
/// which is exact for integral and dyadic weights and only approximate
/// otherwise. A zero weight makes the number of shortest paths ill-defined and
/// is rejected.
///
/// Sources run in blocks of 64 on as many workers as the execution asked for and are merged in
/// block order; scores, and the work charged, are identical at any worker count.
/// Memory held at once does grow with the workers: one workspace per running block.
pub fn betweenness(graph: &GraphProjection, options: BetweennessOptions) -> Result<Betweenness> {
    graph.require_nonnegative("betweenness")?;
    let context = graph.execution();
    context.checkpoint()?;
    let n = graph.node_count();
    let adjacency = graph.outgoing();
    if options.sampling_size == Some(0) {
        return Err(AlgorithmError::InvalidArguments(
            "samplingSize must be positive".into(),
        ));
    }
    let weighted = adjacency.weights.is_some();
    if let Some(weights) = &adjacency.weights {
        let mut meter = context.work_meter();
        for &weight in &weights.values {
            meter.charge(1)?;
            if weight == 0.0 {
                return Err(AlgorithmError::InvalidArguments(
                    "betweenness needs positive weights: a zero weight makes the number of shortest paths ill-defined".into(),
                ));
            }
        }
    }

    // The sources, ascending, so an exhaustive sample is the exact run bit for bit.
    let mut sources = Buffer::capacity(n, context)?;
    sources.values.extend(0..n);
    let sampled = options.sampling_size.is_some_and(|size| size < n);
    if let (true, Some(size)) = (sampled, options.sampling_size) {
        for index in 0..size {
            let pick = index + random::below(options.seed, 0, index as u64, n - index);
            sources.values.swap(index, pick);
        }
        sources.values.truncate(size);
        sources.values.sort_unstable();
    }
    let source_count = sources.values.len();

    let mut scores = Buffer::filled(n, 0.0f64, context)?;
    let workers = parallel::concurrency(
        context,
        source_count.saturating_mul(n.saturating_add(adjacency.targets.values.len())),
    );
    let block = block_size(source_count);
    parallel::ordered_blocks(
        workers,
        source_count.div_ceil(block),
        |block_index| {
            let first = block_index * block;
            let last = (first + block).min(source_count);
            let mut workspace = Workspace::new(n, weighted, context)?;
            for &source in &sources.values[first..last] {
                workspace.accumulate(graph, source)?;
            }
            Ok(workspace.local)
        },
        |_, local: Buffer<f64>| {
            context.charge_work(n)?;
            for (score, part) in scores.values.iter_mut().zip(&local.values) {
                *score += part;
            }
            Ok(())
        },
    )?;

    let mut factor = 1.0;
    if graph.orientation() == Orientation::Undirected {
        factor *= 0.5;
    }
    if sampled {
        factor *= n as f64 / source_count as f64;
    }
    if options.normalized {
        let pairs = (n as f64 - 1.0) * (n as f64 - 2.0);
        let pairs = if graph.orientation() == Orientation::Undirected {
            pairs / 2.0
        } else {
            pairs
        };
        // Undirected sums were already halved above; the pair count is halved too.
        factor = if pairs > 0.0 { factor / pairs } else { 0.0 };
    }
    for score in &mut scores.values {
        *score *= factor;
    }
    Ok(Betweenness {
        graph: graph.clone(),
        scores,
    })
}

/// Per-block scratch: one single-source pass at a time, summed into `local`.
struct Workspace {
    /// One meter for the block: creating a meter registers it, which is too
    /// much to pay per node.
    meter: grust_procedures::WorkMeter,
    distance: Buffer<f64>,
    paths: Buffer<f64>,
    dependency: Buffer<f64>,
    order: Buffer<usize>,
    heap: Option<MinHeap>,
    local: Buffer<f64>,
}

impl Workspace {
    fn new(n: usize, weighted: bool, context: &ExecutionContext) -> Result<Self> {
        Ok(Self {
            meter: context.work_meter(),
            distance: Buffer::filled(n, f64::INFINITY, context)?,
            paths: Buffer::filled(n, 0.0, context)?,
            dependency: Buffer::filled(n, 0.0, context)?,
            order: Buffer::capacity(n, context)?,
            heap: weighted.then(|| MinHeap::new(n, context)).transpose()?,
            local: Buffer::filled(n, 0.0, context)?,
        })
    }

    fn accumulate(&mut self, graph: &GraphProjection, source: usize) -> Result<()> {
        let adjacency = graph.outgoing();
        self.order.values.clear();
        self.distance.values[source] = 0.0;
        self.paths.values[source] = 1.0;

        // Forward: settle nodes in nondecreasing distance, counting shortest paths.
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
                        self.paths.values[next] = self.paths.values[node];
                        heap.improve(next, candidate, &mut self.meter)?;
                    } else if candidate == self.distance.values[next] {
                        self.paths.values[next] += self.paths.values[node];
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
                let candidate = self.distance.values[node] + 1.0;
                for arc in range {
                    let next = adjacency.targets.values[arc];
                    if self.distance.values[next].is_infinite() {
                        self.distance.values[next] = candidate;
                        self.order.values.push(next);
                    }
                    if self.distance.values[next] == candidate {
                        self.paths.values[next] += self.paths.values[node];
                    }
                }
            }
        }

        // Backward: a node inherits from each successor on a shortest path the
        // share of that successor's paths that came through it.
        for &node in self.order.values.iter().rev() {
            let range = adjacency.range(node);
            self.meter.charge(1 + range.len())?;
            for arc in range {
                let next = adjacency.targets.values[arc];
                if next != node
                    && self.distance.values[next]
                        == self.distance.values[node] + adjacency.weight(arc)
                {
                    self.dependency.values[node] += self.paths.values[node]
                        / self.paths.values[next]
                        * (1.0 + self.dependency.values[next]);
                }
            }
            if node != source {
                self.local.values[node] += self.dependency.values[node];
            }
        }

        // Reset only what this source touched.
        for &node in &self.order.values {
            self.distance.values[node] = f64::INFINITY;
            self.paths.values[node] = 0.0;
            self.dependency.values[node] = 0.0;
        }
        Ok(())
    }
}
