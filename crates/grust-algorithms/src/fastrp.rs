//! FastRP node embeddings: very sparse random projection, averaged over
//! neighbourhoods of growing radius (Chen, Sultan, Tian, Chen and Skiena, 2019).

use crate::{
    AlgorithmError, GraphProjection, Result,
    buffer::Buffer,
    parallel, random,
    table::{NodeColumn, NodeTable},
};

/// FastRP controls.
#[derive(Clone, Copy, Debug)]
pub struct FastRpOptions<'a> {
    /// Floats per node; positive.
    pub dimension: usize,
    /// Weight of each averaging round in the result: entry `k` weighs the
    /// embedding after `k + 1` rounds. Finite; the number of rounds is its length.
    pub iteration_weights: &'a [f64],
    /// Weight of the node's own random vector, round zero.
    pub self_influence: f64,
    /// Scale a node's random vector by `degree ^ strength`. Negative values
    /// damp hubs, positive ones favour them.
    pub normalization_strength: f64,
    /// The same seed gives the same embedding.
    pub seed: u64,
}

impl Default for FastRpOptions<'_> {
    fn default() -> Self {
        Self {
            dimension: 128,
            iteration_weights: &[0.0, 1.0, 1.0],
            self_influence: 0.0,
            normalization_strength: 0.0,
            seed: 0,
        }
    }
}

/// Width of the registers the neighbourhood sums are formed in. Storage is
/// `f32` in every case: this names the accumulator, not the column.
///
/// This exists to measure whether the accumulator's width is visible in the
/// embedding. The default path is unchanged.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Accumulator {
    /// Sum neighbour contributions in `f32`, as the shipped kernel does.
    Single,
    /// Sum in `f64` and narrow once per round on store.
    Double,
    /// Sum in `f64` with Neumaier compensation; the reference the other two
    /// are measured against.
    Compensated,
}

/// An embedding per node.
pub struct FastRp {
    graph: GraphProjection,
    values: Buffer<f32>,
    dimension: usize,
}

impl FastRp {
    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// Floats per node.
    pub fn dimension(&self) -> usize {
        self.dimension
    }
    /// Embeddings row by row, in projection row order.
    pub fn values(&self) -> &[f32] {
        &self.values.values
    }
    /// The embedding of one projection row.
    pub fn embedding(&self, row: usize) -> &[f32] {
        &self.values.values[row * self.dimension..(row + 1) * self.dimension]
    }
    /// `nodeId`, `embedding`.
    pub fn into_table(self) -> Result<NodeTable> {
        NodeTable::new(&self.graph).column(
            "embedding",
            NodeColumn::Vector {
                values: self.values,
                dimension: self.dimension,
            },
        )
    }
}

/// Nodes per chunk; fixed, so nothing depends on the worker count.
const CHUNK: usize = 1024;

/// Embed every node.
///
/// **Round zero.** Each node draws a vector whose entries are `+√3`, `0`, `-√3`
/// with probabilities 1/6, 2/3, 1/6, scaled by `degree ^ normalization_strength`
/// (a node of degree zero scales by zero unless the strength is zero). Entry
/// `j` of node `v` is a pure function of `(seed, v, j)`, so neither the order
/// of work nor the worker count can change it.
///
/// **Each round** replaces a node's vector with the weighted mean of the
/// vectors of the nodes its arcs reach, so after `k` rounds a node reflects its
/// `k`-hop out-neighbourhood; a node with no arcs goes to zero. Parallel edges
/// and self-loops count as arcs. Each round's vectors are scaled to unit length
/// and added to the result with that round's weight. `degree` is the weighted
/// out-degree.
///
/// Arithmetic is single precision, as the output is. Identical at any pool
/// width. The embedding is not a function of the graph alone — it depends on
/// the seed and on node rows — so compare embeddings only within one run.
pub fn fast_rp(graph: &GraphProjection, options: FastRpOptions<'_>) -> Result<FastRp> {
    fast_rp_with(graph, options, Accumulator::Single)
}

/// `fast_rp` with the accumulator width named explicitly. `Accumulator::Single`
/// is bit-for-bit what `fast_rp` computes.
pub fn fast_rp_with(
    graph: &GraphProjection,
    options: FastRpOptions<'_>,
    accumulator: Accumulator,
) -> Result<FastRp> {
    graph.require_nonnegative("fastRP")?;
    let context = graph.execution();
    context.checkpoint()?;
    let d = options.dimension;
    if d == 0
        || !options.self_influence.is_finite()
        || !options.normalization_strength.is_finite()
        || options.iteration_weights.iter().any(|w| !w.is_finite())
    {
        return Err(AlgorithmError::InvalidArguments(
            "FastRP needs a positive embeddingDimension and finite weights".into(),
        ));
    }
    let n = graph.node_count();
    let adjacency = graph.outgoing();
    let length = n.checked_mul(d).ok_or_else(|| {
        AlgorithmError::InvalidArguments("embedding size overflows the address space".into())
    })?;
    let mut current = Buffer::filled(length, 0.0f32, context)?;
    let mut next = Buffer::filled(length, 0.0f32, context)?;
    let mut result = Buffer::filled(length, 0.0f32, context)?;
    if n == 0 {
        return Ok(FastRp {
            graph: graph.clone(),
            values: result,
            dimension: d,
        });
    }
    let degree =
        |node: usize| -> f64 { adjacency.range(node).map(|arc| adjacency.weight(arc)).sum() };

    // Round zero.
    let root3 = 3.0f32.sqrt();
    // Chunks are fixed, so the worker count cannot change a value.
    let workers = parallel::concurrency(
        context,
        length.saturating_add(adjacency.targets.values.len().saturating_mul(d)),
    );
    parallel::for_chunks(workers, &mut current.values, CHUNK * d, |first, chunk| {
        let mut meter = context.work_meter();
        for (offset, row) in chunk.chunks_mut(d).enumerate() {
            let node = first / d + offset;
            meter.charge(d + adjacency.range(node).len())?;
            let scale = if options.normalization_strength == 0.0 {
                1.0
            } else {
                degree(node).powf(options.normalization_strength) as f32
            };
            let scale = if scale.is_finite() { scale } else { 0.0 };
            for (index, value) in row.iter_mut().enumerate() {
                *value = match random::below(options.seed, node as u64, index as u64, 6) {
                    0 => root3 * scale,
                    1 => -root3 * scale,
                    _ => 0.0,
                };
            }
        }
        Ok(())
    })?;
    accumulate(
        &mut result.values,
        &current.values,
        d,
        options.self_influence,
        context,
        accumulator,
    )?;

    for &weight in options.iteration_weights {
        let previous = &current.values;
        parallel::for_chunks(workers, &mut next.values, CHUNK * d, |first, chunk| {
            let mut meter = context.work_meter();
            // Scratch registers for the wide paths. One row's worth, reused
            // down the chunk, so the allocation does not scale with the graph.
            let mut wide = vec![
                0.0f64;
                if accumulator == Accumulator::Single {
                    0
                } else {
                    d
                }
            ];
            let mut carry = vec![
                0.0f64;
                if accumulator == Accumulator::Compensated {
                    d
                } else {
                    0
                }
            ];
            for (offset, row) in chunk.chunks_mut(d).enumerate() {
                let node = first / d + offset;
                let range = adjacency.range(node);
                meter.charge(d * (1 + range.len()))?;
                match accumulator {
                    Accumulator::Single => {
                        row.fill(0.0);
                        let mut total = 0.0f32;
                        for arc in range {
                            let arc_weight = adjacency.weight(arc) as f32;
                            total += arc_weight;
                            let other = adjacency.targets.values[arc];
                            for (value, &theirs) in
                                row.iter_mut().zip(&previous[other * d..(other + 1) * d])
                            {
                                *value += arc_weight * theirs;
                            }
                        }
                        if total > 0.0 {
                            for value in row.iter_mut() {
                                *value /= total;
                            }
                        }
                    }
                    Accumulator::Double => {
                        wide.fill(0.0);
                        let mut total = 0.0f64;
                        for arc in range {
                            let arc_weight = adjacency.weight(arc);
                            total += arc_weight;
                            let other = adjacency.targets.values[arc];
                            for (value, &theirs) in
                                wide.iter_mut().zip(&previous[other * d..(other + 1) * d])
                            {
                                *value += arc_weight * f64::from(theirs);
                            }
                        }
                        let scale = if total > 0.0 { 1.0 / total } else { 1.0 };
                        for (value, &sum) in row.iter_mut().zip(wide.iter()) {
                            *value = (sum * scale) as f32;
                        }
                    }
                    Accumulator::Compensated => {
                        wide.fill(0.0);
                        carry.fill(0.0);
                        let mut total = 0.0f64;
                        let mut total_carry = 0.0f64;
                        for arc in range {
                            let arc_weight = adjacency.weight(arc);
                            neumaier(&mut total, &mut total_carry, arc_weight);
                            let other = adjacency.targets.values[arc];
                            let theirs = &previous[other * d..(other + 1) * d];
                            for ((value, compensation), &their) in
                                wide.iter_mut().zip(carry.iter_mut()).zip(theirs)
                            {
                                neumaier(value, compensation, arc_weight * f64::from(their));
                            }
                        }
                        let total = total + total_carry;
                        let scale = if total > 0.0 { 1.0 / total } else { 1.0 };
                        for ((value, &sum), &compensation) in
                            row.iter_mut().zip(wide.iter()).zip(carry.iter())
                        {
                            *value = ((sum + compensation) * scale) as f32;
                        }
                    }
                }
            }
            Ok(())
        })?;
        std::mem::swap(&mut current, &mut next);
        accumulate(
            &mut result.values,
            &current.values,
            d,
            weight,
            context,
            accumulator,
        )?;
    }
    if result.values.iter().any(|value| !value.is_finite()) {
        return Err(AlgorithmError::Numerical(
            "embedding left the finite range".into(),
        ));
    }
    Ok(FastRp {
        graph: graph.clone(),
        values: result,
        dimension: d,
    })
}

/// `into[v] += weight * from[v] / |from[v]|`; a zero vector adds nothing.
fn accumulate(
    into: &mut [f32],
    from: &[f32],
    d: usize,
    weight: f64,
    context: &grust_procedures::ExecutionContext,
    accumulator: Accumulator,
) -> Result<()> {
    if weight == 0.0 {
        return Ok(());
    }
    let workers = parallel::concurrency(context, into.len());
    parallel::for_chunks(workers, into, CHUNK * d, |first, chunk| {
        context.charge_work(chunk.len())?;
        for (offset, row) in chunk.chunks_mut(d).enumerate() {
            let source = &from[first + offset * d..first + (offset + 1) * d];
            match accumulator {
                Accumulator::Single => {
                    let weight = weight as f32;
                    let norm = source.iter().map(|v| v * v).sum::<f32>().sqrt();
                    if norm > 0.0 {
                        for (value, &theirs) in row.iter_mut().zip(source) {
                            *value += weight * theirs / norm;
                        }
                    }
                }
                Accumulator::Double => {
                    let norm = source
                        .iter()
                        .map(|v| f64::from(*v) * f64::from(*v))
                        .sum::<f64>()
                        .sqrt();
                    if norm > 0.0 {
                        for (value, &theirs) in row.iter_mut().zip(source) {
                            *value = (f64::from(*value) + weight * f64::from(theirs) / norm) as f32;
                        }
                    }
                }
                Accumulator::Compensated => {
                    let mut sum = 0.0f64;
                    let mut carry = 0.0f64;
                    for &v in source {
                        neumaier(&mut sum, &mut carry, f64::from(v) * f64::from(v));
                    }
                    let norm = (sum + carry).sqrt();
                    if norm > 0.0 {
                        for (value, &theirs) in row.iter_mut().zip(source) {
                            *value = (f64::from(*value) + weight * f64::from(theirs) / norm) as f32;
                        }
                    }
                }
            }
        }
        Ok(())
    })?;
    Ok(())
}

/// One Neumaier step: add `term` to `sum`, routing the lost low bits into
/// `carry`. `sum + carry` is the compensated total.
#[inline]
fn neumaier(sum: &mut f64, carry: &mut f64, term: f64) {
    let updated = *sum + term;
    *carry += if sum.abs() >= term.abs() {
        (*sum - updated) + term
    } else {
        (term - updated) + *sum
    };
    *sum = updated;
}
