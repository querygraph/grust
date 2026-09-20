//! Projection inspection and explicitly scoped CSR sizing, without kernel work.

use crate::{GraphProjection, Orientation, Result};
use grust_procedures::ProcedureError;

/// Exact selected topology counts, independent of any algorithm result.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ProjectionStatistics {
    pub nodes: usize,
    /// Original selected edges; parallel edges each contribute one.
    pub edges: usize,
    /// Traversal arcs after applying orientation; undirected loops count once.
    pub arcs: usize,
    pub self_loops: usize,
    pub weighted: bool,
    /// Nominal packed outgoing CSR buffer bytes, excluding all other storage.
    pub csr_bytes: usize,
}

/// Nominal buffer sizing from upper-bound input counts. This is **not** a peak
/// memory estimate or an admission decision. It excludes the input graph, IDs,
/// maps, original edge table, allocator overhead, kernels and output. Selection
/// may reduce the counts; undirected loops make the arc upper bound conservative.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct CsrEstimate {
    pub max_arcs: usize,
    pub outgoing_bytes: usize,
    /// Additional lazy reverse topology used by SCC, without weights/edge slots.
    pub reverse_bytes: usize,
    /// Temporary insertion positions needed while building either orientation.
    pub positions_bytes: usize,
}

impl CsrEstimate {
    /// O(1) checked sizing. Counts need not come from a materialized graph.
    pub fn upper_bound(
        nodes: usize,
        edges: usize,
        orientation: Orientation,
        weighted: bool,
    ) -> Result<Self> {
        let arcs = edges.checked_mul(if orientation == Orientation::Undirected {
            2
        } else {
            1
        });
        let max_arcs = arcs.ok_or_else(overflow)?;
        let offsets = nodes
            .checked_add(1)
            .and_then(|n| n.checked_mul(size_of::<usize>()))
            .ok_or_else(overflow)?;
        let reverse_bytes = max_arcs
            .checked_mul(size_of::<usize>())
            .and_then(|n| n.checked_add(offsets))
            .ok_or_else(overflow)?;
        Ok(Self {
            max_arcs,
            outgoing_bytes: csr_bytes(nodes, max_arcs, weighted)?,
            reverse_bytes,
            positions_bytes: nodes.checked_mul(size_of::<usize>()).ok_or_else(overflow)?,
        })
    }
}

impl GraphProjection {
    /// Inspect this selected projection. Scanning loops is O(E), cancellable and
    /// charged as work; this does not execute an analytics kernel or build reverse CSR.
    pub fn statistics(&self) -> Result<ProjectionStatistics> {
        let context = self.execution();
        // Counting loops is a sum over edges, so workers count their own ranges
        // and the partials are added in chunk order. Integer addition is
        // associative, so the total is the same however the edges were divided.
        let self_loops = match crate::parallel::workers(context, self.edge_count()) {
            Some(workers) => {
                let parts = crate::parallel::map_chunks(
                    context,
                    workers,
                    self.edges(),
                    |_, slice, meter| {
                        meter.charge(slice.len())?;
                        Ok(slice
                            .iter()
                            .filter(|edge| edge.source == edge.target)
                            .count())
                    },
                )?;
                crate::parallel::reduce_in_order(&parts, 0usize, |total, part| total + part)
            }
            None => {
                let mut self_loops = 0;
                for edge in self.edges() {
                    context.charge_work(1)?;
                    self_loops += usize::from(edge.source == edge.target);
                }
                self_loops
            }
        };
        context.checkpoint()?;
        let arcs = self.outgoing().targets.values.len();
        Ok(ProjectionStatistics {
            nodes: self.node_count(),
            edges: self.edge_count(),
            arcs,
            self_loops,
            weighted: self.is_weighted(),
            csr_bytes: csr_bytes(self.node_count(), arcs, self.is_weighted())?,
        })
    }
}

fn csr_bytes(nodes: usize, arcs: usize, weighted: bool) -> Result<usize> {
    let arc_bytes = 2 * size_of::<usize>() + if weighted { size_of::<f64>() } else { 0 };
    nodes
        .checked_add(1)
        .and_then(|n| n.checked_mul(size_of::<usize>()))
        .and_then(|n| arcs.checked_mul(arc_bytes).and_then(|a| n.checked_add(a)))
        .ok_or_else(overflow)
}

fn overflow() -> ProcedureError {
    ProcedureError::Numerical("CSR byte estimate exceeds usize".into())
}
