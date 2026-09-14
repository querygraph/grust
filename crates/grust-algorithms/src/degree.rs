//! Exact projected arc counts and optional nonnegative weighted strength.

use crate::{AlgorithmError, GraphProjection, Result, buffer::Buffer};

/// Per-node degree results retaining projection identity and memory admission.
/// Counts include parallel arcs and zero-weight arcs. Weighted strength is the
/// sum of arc weights, and is absent when the projection is unweighted.
pub struct Degrees {
    graph: GraphProjection,
    counts: Buffer<usize>,
    strengths: Option<Buffer<f64>>,
}

impl Degrees {
    /// Projection supplying external node IDs, orientation and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// Exact counts in projection node order; isolates have degree zero.
    pub fn counts(&self) -> &[usize] {
        &self.counts.values
    }
    /// Finite strengths in projection node order, or None without weights.
    pub fn strengths(&self) -> Option<&[f64]> {
        self.strengths
            .as_ref()
            .map(|values| values.values.as_slice())
    }
}

/// Count outgoing arcs of the selected projection. Incoming orientation therefore
/// computes incoming degree; undirected orientation counts each incident edge,
/// with self-loops counted once, following the projection's arc contract.
///
/// Unweighted execution takes O(V) work from existing CSR offsets. Weighted
/// execution takes O(V + A) work and sums weights in stable CSR order. Projection
/// weights must already be finite and nonnegative; a nonfinite sum is a numerical
/// error. No reverse index, graph copy, or implicit normalization is built.
pub fn degree(graph: &GraphProjection) -> Result<Degrees> {
    let context = graph.execution();
    context.checkpoint()?;
    let adjacency = graph.outgoing();
    let mut counts = Buffer::capacity(graph.node_count(), context)?;
    let mut strengths = adjacency
        .weights
        .as_ref()
        .map(|_| Buffer::capacity(graph.node_count(), context))
        .transpose()?;
    // Precharge bounded chunks, as Buffer initialization does, instead of
    // locking the execution context for every scalar. Arc charges span node
    // boundaries so low-degree graphs also amortize the accounting lock.
    let mut arcs_charged_until = 0;
    for first in (0..graph.node_count()).step_by(1024) {
        let last = first.saturating_add(1024).min(graph.node_count());
        context.charge_work(last - first)?;
        for node in first..last {
            let start = adjacency.offsets.values[node];
            let end = adjacency.offsets.values[node + 1];
            counts.values.push(end - start);
            if let (Some(weights), Some(strengths)) = (&adjacency.weights, &mut strengths) {
                let mut sum = 0.0;
                let mut position = start;
                while position < end {
                    if position == arcs_charged_until {
                        arcs_charged_until =
                            position.saturating_add(1024).min(weights.values.len());
                        context.charge_work(arcs_charged_until - position)?;
                    }
                    let stop = end.min(arcs_charged_until);
                    for &weight in &weights.values[position..stop] {
                        sum += weight;
                    }
                    position = stop;
                }
                // Nonnegative finite inputs cannot recover after overflowing.
                if !sum.is_finite() {
                    return Err(AlgorithmError::Numerical(
                        "weighted degree exceeds finite Float64 domain".into(),
                    ));
                }
                strengths.values.push(sum);
            }
        }
    }
    context.checkpoint()?;
    Ok(Degrees {
        graph: graph.clone(),
        counts,
        strengths,
    })
}
