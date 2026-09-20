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
/// Each node's count and strength depend only on its own arc range, so workers
/// write disjoint slices of the output and need no synchronization. Weighted
/// sums stay in CSR order within a node, which is why the result does not depend
/// on how the nodes were divided.
pub fn degree(graph: &GraphProjection) -> Result<Degrees> {
    graph.require_nonnegative("degree")?;
    let context = graph.execution();
    context.checkpoint()?;
    let adjacency = graph.outgoing();
    let n = graph.node_count();
    let mut counts = Buffer::indexed(n, 0usize, context)?;
    let mut strengths = adjacency
        .weights
        .as_ref()
        .map(|_| Buffer::indexed(n, 0.0f64, context))
        .transpose()?;
    let arcs = adjacency.targets.values.len();
    let workers = crate::parallel::workers(context, n.saturating_add(arcs)).unwrap_or(1);
    let offsets = &adjacency.offsets.values;
    let weights = adjacency.weights.as_ref().map(|weights| &weights.values);

    // Counts first: O(V) from the CSR offsets alone.
    crate::parallel::for_each_chunk(
        context,
        workers,
        &mut counts.values,
        |first, slice, meter| {
            meter.charge(slice.len())?;
            for (index, count) in slice.iter_mut().enumerate() {
                let node = first + index;
                *count = offsets[node + 1] - offsets[node];
            }
            Ok(())
        },
    )?;

    if let (Some(weights), Some(strengths)) = (weights, &mut strengths) {
        crate::parallel::for_each_chunk(
            context,
            workers,
            &mut strengths.values,
            |first, slice, meter| {
                for (index, strength) in slice.iter_mut().enumerate() {
                    let node = first + index;
                    let (start, end) = (offsets[node], offsets[node + 1]);
                    // The counts pass already charged this node; charge its arcs
                    // before summing them, so a high-degree node cannot run
                    // unmetered and cancellation stays prompt.
                    meter.charge(end - start)?;
                    let mut sum = 0.0;
                    for &weight in &weights[start..end] {
                        sum += weight;
                    }
                    // Nonnegative finite inputs cannot recover after overflowing.
                    if !sum.is_finite() {
                        return Err(AlgorithmError::Numerical(
                            "weighted degree exceeds finite Float64 domain".into(),
                        ));
                    }
                    *strength = sum;
                }
                Ok(())
            },
        )?;
    }
    context.checkpoint()?;
    Ok(Degrees {
        graph: graph.clone(),
        counts,
        strengths,
    })
}
