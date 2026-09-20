//! FastRP node embeddings: very sparse random projection, averaged over
//! neighbourhoods of growing radius (Chen, Sultan, Tian, Chen and Skiena, 2019).

use crate::{
    AlgorithmError, GraphProjection, Result,
    buffer::Buffer,
    meter::Meter,
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

/// Nodes per chunk; fixed, so nothing depends on the pool width.
const CHUNK: usize = 1024;

/// Embed every node.
///
/// **Round zero.** Each node draws a vector whose entries are `+√3`, `0`, `-√3`
/// with probabilities 1/6, 2/3, 1/6, scaled by `degree ^ normalization_strength`
/// (a node of degree zero scales by zero unless the strength is zero). Entry
/// `j` of node `v` is a pure function of `(seed, v, j)`, so neither the order
/// of work nor the pool can change it.
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
    parallel::for_chunks(&mut current.values, CHUNK * d, |first, chunk| {
        let mut meter = Meter::new(context);
        for (offset, row) in chunk.chunks_mut(d).enumerate() {
            let node = first / d + offset;
            meter.tick(d + adjacency.range(node).len())?;
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
        meter.flush()
    })?;
    accumulate(
        &mut result.values,
        &current.values,
        d,
        options.self_influence as f32,
        context,
    )?;

    for &weight in options.iteration_weights {
        let previous = &current.values;
        parallel::for_chunks(&mut next.values, CHUNK * d, |first, chunk| {
            let mut meter = Meter::new(context);
            for (offset, row) in chunk.chunks_mut(d).enumerate() {
                let node = first / d + offset;
                let range = adjacency.range(node);
                meter.tick(d * (1 + range.len()))?;
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
            meter.flush()
        })?;
        std::mem::swap(&mut current, &mut next);
        accumulate(
            &mut result.values,
            &current.values,
            d,
            weight as f32,
            context,
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
    weight: f32,
    context: &grust_procedures::ExecutionContext,
) -> Result<()> {
    if weight == 0.0 {
        return Ok(());
    }
    parallel::for_chunks(into, CHUNK * d, |first, chunk| {
        context.charge_work(chunk.len())?;
        for (offset, row) in chunk.chunks_mut(d).enumerate() {
            let source = &from[first + offset * d..first + (offset + 1) * d];
            let norm = source.iter().map(|v| v * v).sum::<f32>().sqrt();
            if norm > 0.0 {
                for (value, &theirs) in row.iter_mut().zip(source) {
                    *value += weight * theirs / norm;
                }
            }
        }
        Ok(())
    })?;
    Ok(())
}
