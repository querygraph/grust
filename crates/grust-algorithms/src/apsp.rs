//! All-pairs shortest paths, streamed: one row per reachable pair, never a matrix.
//!
//! NetworKit's `distance/APSP` fills an n×n matrix. At 65,536 nodes that is 4.3
//! billion cells, so this kernel does not: it runs one Dijkstra at a time over a
//! single reused workspace and hands each source's pairs out through a pull
//! cursor before starting the next source. Admitted memory is the projection,
//! one source's working set (four O(n) buffers) and whatever batch the consumer
//! is holding; it does not grow with the number of pairs produced.

use grust_procedures::WorkMeter;

use crate::{AlgorithmError, GraphProjection, Result, buffer::Buffer, shortest::MinHeap};

/// Options for [`all_pairs_shortest_paths`].
#[derive(Clone, Copy, Debug, Default)]
pub struct AllPairsOptions<'a> {
    /// Restrict the sources to these external ids; `None` means every node.
    /// Targets are always every node. The order given does not matter: sources
    /// are visited in projection row order. A duplicate or an id outside the
    /// projection is rejected. An empty list is an explicit empty selection
    /// and produces no rows.
    pub source_nodes: Option<&'a [String]>,
}

/// One reachable ordered pair and its shortest distance.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ShortestPair {
    /// Source row in the projection.
    pub source: usize,
    /// Target row in the projection.
    pub target: usize,
    /// Minimum total weight from `source` to `target`; finite and nonnegative.
    pub distance: f64,
}

/// A pull cursor over every reachable `(source, target)` pair.
///
/// Nothing is computed when this is created beyond validating the options and
/// admitting the workspace. Each [`Self::next_pair`] either returns the next
/// pair of the current source or, when that source is exhausted, runs Dijkstra
/// from the next one. Failure and completion release the workspace at once;
/// after a failure every call returns [`AlgorithmError::CursorFailed`].
pub struct AllPairsShortestPaths {
    graph: GraphProjection,
    state: Option<Workspace>,
    failed: bool,
}

struct Workspace {
    /// Source rows, ascending.
    sources: Buffer<usize>,
    next_source: usize,
    /// Row of the source whose pairs are being handed out.
    current: usize,
    /// Infinite everywhere except the current source's reached set.
    distances: Buffer<f64>,
    heap: MinHeap,
    /// Rows the current source reaches, ascending once settled.
    reached: Buffer<usize>,
    next_target: usize,
    meter: WorkMeter,
}

impl AllPairsShortestPaths {
    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }

    /// The next reachable pair, or `None` when every source is done.
    ///
    /// Pairs come in source row order, and within one source in target row
    /// order. Every source reaches itself, at zero.
    pub fn next_pair(&mut self) -> Result<Option<ShortestPair>> {
        if self.failed {
            return Err(AlgorithmError::CursorFailed);
        }
        let Some(workspace) = self.state.as_mut() else {
            return Ok(None);
        };
        match workspace.advance(&self.graph) {
            Ok(Some(pair)) => Ok(Some(pair)),
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

impl Workspace {
    fn advance(&mut self, graph: &GraphProjection) -> Result<Option<ShortestPair>> {
        loop {
            if let Some(&target) = self.reached.values.get(self.next_target) {
                // The per-pair charge: output is work, and it is what grows
                // quadratically, so it is what a budget must be able to stop.
                self.meter.charge(1)?;
                self.next_target += 1;
                return Ok(Some(ShortestPair {
                    source: self.current,
                    target,
                    distance: self.distances.values[target],
                }));
            }
            // Restore only what the finished source touched, so a source that
            // reaches k nodes costs O(k) here rather than O(n).
            self.meter.charge(self.reached.values.len())?;
            for &node in &self.reached.values {
                self.distances.values[node] = f64::INFINITY;
            }
            self.reached.values.clear();
            self.next_target = 0;
            let Some(&source) = self.sources.values.get(self.next_source) else {
                return Ok(None);
            };
            self.next_source += 1;
            self.current = source;
            graph.execution().checkpoint()?;
            self.settle(graph, source)?;
        }
    }

    /// Dijkstra from `source`, recording every settled node. With nonnegative
    /// weights every node that ever gets a finite distance is pushed and later
    /// popped, so the settled list is exactly the set to report and to reset.
    fn settle(&mut self, graph: &GraphProjection, source: usize) -> Result<()> {
        let adjacency = graph.outgoing();
        self.distances.values[source] = 0.0;
        self.heap.improve(source, 0.0, &mut self.meter)?;
        while let Some((cost, node)) = self.heap.pop(&mut self.meter)? {
            self.meter.charge(1)?;
            self.reached.values.push(node);
            for arc in adjacency.range(node) {
                self.meter.charge(1)?;
                let next = adjacency.targets.values[arc];
                let candidate = cost + adjacency.weight(arc);
                if !candidate.is_finite() {
                    return Err(AlgorithmError::Numerical(
                        "shortest-path cost overflow".into(),
                    ));
                }
                if candidate < self.distances.values[next] {
                    self.distances.values[next] = candidate;
                    self.heap.improve(next, candidate, &mut self.meter)?;
                }
            }
        }
        // Settle order is by distance; report order is by row, which is what
        // `dijkstra` reports and what does not move when a weight ties.
        let reached = self.reached.values.len();
        self.meter.charge(
            reached.saturating_mul(usize::BITS as usize - reached.leading_zeros() as usize),
        )?;
        self.reached.values.sort_unstable();
        Ok(())
    }
}

/// Shortest distances between every reachable ordered pair, streamed.
///
/// **Output.** One [`ShortestPair`] per ordered pair `(s, t)` with `t`
/// reachable from `s`, including `(s, s)` at distance zero, which is what
/// [`crate::dijkstra`] reports for its source. Sources in projection row order,
/// targets in row order within each source. Nothing is materialised: the result
/// is a cursor, and the n×n matrix is never formed.
///
/// **Unreachable pairs are omitted, not emitted as null.** The set of targets is
/// the projection, so a missing row carries the same information as a null one.
/// Emitting nulls would make every source cost O(n) in output whatever it
/// reaches, and on a graph of many small components nearly all the n² rows
/// would be nulls. Omitting them keeps both output and work proportional to
/// the reachable pairs.
///
/// **Semantics.** Orientation is the projection's, as for `dijkstra`: pairs
/// follow out-arcs, in-arcs, or either. Parallel edges contribute their
/// cheapest weight. A self-loop cannot shorten anything, since weights are
/// nonnegative. Isolates reach only themselves. Unit weights are used when none
/// were projected. Weights must be nonnegative; a signed projection is refused,
/// and a reachable cost that overflows finite `f64` is a numerical error when
/// the source that reaches it is run.
///
/// **Cost.** Work is charged per heap operation and per arc scanned, as in
/// `dijkstra`, plus one unit per pair produced and per reached node reset. A
/// source that reaches k nodes costs its Dijkstra plus O(k): the workspace is
/// reset by its reached list, not refilled. Admitted memory is four O(n)
/// buffers, fixed for the whole run.
///
/// **Sequential.** One source at a time. A parallel version would have to
/// buffer the pairs of every source computed ahead of the one being drained, so
/// that rows still stream in source order; that is memory proportional to
/// workers times output per source, and is not done here.
pub fn all_pairs_shortest_paths(
    graph: &GraphProjection,
    options: AllPairsOptions<'_>,
) -> Result<AllPairsShortestPaths> {
    graph.require_nonnegative("allPairsShortestPaths")?;
    let context = graph.execution();
    context.checkpoint()?;
    let n = graph.node_count();
    let sources = match options.source_nodes {
        None => {
            context.charge_work(n)?;
            let mut sources = Buffer::capacity(n, context)?;
            sources.values.extend(0..n);
            sources
        }
        Some(ids) => {
            context.charge_work(ids.len())?;
            let mut sources = Buffer::capacity(ids.len(), context)?;
            for id in ids {
                sources.values.push(graph.source(id).map_err(|_| {
                    AlgorithmError::InvalidArguments(format!(
                        "sourceNodes names a node that is not selected: {id}"
                    ))
                })?);
            }
            sources.values.sort_unstable();
            if let Some(pair) = sources.values.windows(2).find(|pair| pair[0] == pair[1]) {
                return Err(AlgorithmError::InvalidArguments(format!(
                    "sourceNodes names {} more than once",
                    graph.node_ids()[pair[0]].as_str()
                )));
            }
            sources
        }
    };
    Ok(AllPairsShortestPaths {
        graph: graph.clone(),
        state: Some(Workspace {
            sources,
            next_source: 0,
            current: 0,
            distances: Buffer::filled(n, f64::INFINITY, context)?,
            heap: MinHeap::new(n, context)?,
            reached: Buffer::capacity(n, context)?,
            next_target: 0,
            meter: context.work_meter(),
        }),
        failed: false,
    })
}
