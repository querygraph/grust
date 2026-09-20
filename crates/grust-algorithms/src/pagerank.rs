//! Weighted PageRank with explicit convergence and dangling-node semantics.

use crate::{AlgorithmError, GraphProjection, Result, buffer::Buffer};

/// PageRank controls. Scores start uniformly and dangling mass is redistributed
/// according to personalization (uniform when omitted).
#[derive(Clone, Copy, Debug)]
pub struct PageRankOptions<'a> {
    /// Probability of following an edge; finite and in [0, 1).
    pub damping: f64,
    /// Stop when the L1 difference between iterations is at most this value.
    pub tolerance: f64,
    /// Positive maximum number of iterations.
    pub max_iterations: usize,
    /// Nonnegative finite weight per selected node, normalized by this kernel.
    /// At least one entry must be positive on a nonempty graph.
    pub personalization: Option<&'a [f64]>,
}

impl Default for PageRankOptions<'_> {
    fn default() -> Self {
        Self {
            damping: 0.85,
            tolerance: 1e-8,
            max_iterations: 1000,
            personalization: None,
        }
    }
}

/// Scores and convergence evidence. Exhausting the iteration limit returns
/// `converged() == false`; it never silently asserts convergence.
pub struct PageRank {
    graph: GraphProjection,
    scores: Buffer<f64>,
    iterations: usize,
    residual: f64,
    converged: bool,
}

impl PageRank {
    /// Projection supplying external IDs and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// Score per selected node, in projection row order.
    pub fn values(&self) -> &[f64] {
        &self.scores.values
    }
    /// Number of completed updates; zero for an empty graph.
    pub fn iterations(&self) -> usize {
        self.iterations
    }
    /// Last L1 update difference, or zero for an empty graph.
    pub fn residual(&self) -> f64 {
        self.residual
    }
    /// Whether the requested tolerance was reached.
    pub fn converged(&self) -> bool {
        self.converged
    }
}

/// Compute weighted PageRank following the selected orientation. Zero outgoing
/// weight is dangling even if structural edges exist. Parallel edges contribute
/// independently; isolates receive teleportation and redistributed dangling mass.
pub fn pagerank(graph: &GraphProjection, options: PageRankOptions<'_>) -> Result<PageRank> {
    let context = graph.execution();
    context.checkpoint()?;
    if !options.damping.is_finite()
        || !(0.0..1.0).contains(&options.damping)
        || !options.tolerance.is_finite()
        || options.tolerance < 0.0
        || options.max_iterations == 0
    {
        return Err(AlgorithmError::InvalidArguments("PageRank requires damping in [0,1), nonnegative finite tolerance and positive max_iterations".into()));
    }
    let n = graph.node_count();
    if options
        .personalization
        .is_some_and(|values| values.len() != n)
    {
        return Err(AlgorithmError::InvalidArguments(
            "personalization length must equal node count".into(),
        ));
    }
    let mut teleport = Buffer::filled(n, if n == 0 { 0.0 } else { 1.0 / n as f64 }, context)?;
    if let Some(values) = options.personalization {
        let mut maximum = 0.0f64;
        for &value in values {
            context.charge_work(1)?;
            if !value.is_finite() || value < 0.0 {
                return Err(AlgorithmError::InvalidArguments(
                    "personalization must be finite and nonnegative".into(),
                ));
            }
            maximum = maximum.max(value);
        }
        if n != 0 && maximum == 0.0 {
            return Err(AlgorithmError::InvalidArguments(
                "personalization must have positive mass".into(),
            ));
        }
        let mut total = 0.0;
        for (target, &value) in teleport.values.iter_mut().zip(values) {
            context.charge_work(1)?;
            *target = value / maximum;
            total += *target;
        }
        for value in &mut teleport.values {
            context.charge_work(1)?;
            *value /= total;
        }
    }
    let mut scores = Buffer::filled(n, if n == 0 { 0.0 } else { 1.0 / n as f64 }, context)?;
    if n == 0 {
        return Ok(PageRank {
            graph: graph.clone(),
            scores,
            iterations: 0,
            residual: 0.0,
            converged: true,
        });
    }
    let adjacency = graph.outgoing();
    // An unweighted projection has a probability of 1/out-degree on every arc,
    // so the iteration can be computed by pulling into each target instead of
    // pushing out of each source. Pulling is what makes it parallel: targets own
    // their own sums, so no worker writes where another might read, and each sum
    // stays in reverse-CSR order, so the result does not depend on the division
    // of work. A weighted projection needs the source's weight total per arc and
    // keeps the sequential push below.
    let workers = crate::parallel::workers(
        context,
        n.saturating_add(adjacency.targets.values.len())
            .saturating_mul(2),
    );
    if let Some(workers) = workers
        && !graph.is_weighted()
    {
        return pull(graph, options, &teleport.values, scores, workers);
    }
    let mut next = Buffer::filled(n, 0.0, context)?;
    // Scale each row by its largest edge weight before summing, preventing
    // overflow for valid finite weights such as two f64::MAX parallel edges.
    let mut scales = Buffer::filled(n, 0.0f64, context)?;
    let mut totals = Buffer::filled(n, 0.0, context)?;
    for source in 0..n {
        context.charge_work(1)?;
        for arc in adjacency.range(source) {
            context.charge_work(1)?;
            scales.values[source] = scales.values[source].max(adjacency.weight(arc));
        }
        if scales.values[source] > 0.0 {
            for arc in adjacency.range(source) {
                context.charge_work(1)?;
                totals.values[source] += adjacency.weight(arc) / scales.values[source];
            }
        }
    }
    let mut residual = f64::INFINITY;
    for iteration in 1..=options.max_iterations {
        let mut dangling = 0.0;
        for (source, &score) in scores.values.iter().enumerate() {
            context.charge_work(1)?;
            if scales.values[source] == 0.0 {
                dangling += score;
            }
        }
        let base = (1.0 - options.damping) + options.damping * dangling;
        for (value, &probability) in next.values.iter_mut().zip(&teleport.values) {
            context.charge_work(1)?;
            *value = base * probability;
        }
        for source in 0..n {
            context.charge_work(1)?;
            if scales.values[source] == 0.0 {
                continue;
            }
            let mass = options.damping * scores.values[source];
            for arc in adjacency.range(source) {
                context.charge_work(1)?;
                let probability =
                    (adjacency.weight(arc) / scales.values[source]) / totals.values[source];
                next.values[adjacency.targets.values[arc]] += mass * probability;
            }
        }
        residual = 0.0;
        for (&before, &after) in scores.values.iter().zip(&next.values) {
            context.charge_work(1)?;
            if !after.is_finite() {
                return Err(AlgorithmError::Numerical(
                    "PageRank produced a nonfinite score".into(),
                ));
            }
            residual += (after - before).abs();
        }
        std::mem::swap(&mut scores, &mut next);
        if residual <= options.tolerance {
            return Ok(PageRank {
                graph: graph.clone(),
                scores,
                iterations: iteration,
                residual,
                converged: true,
            });
        }
    }
    Ok(PageRank {
        graph: graph.clone(),
        scores,
        iterations: options.max_iterations,
        residual,
        converged: false,
    })
}

/// The parallel iteration for an unweighted projection.
///
/// Each iteration computes, for every target `v`,
/// `next[v] = base * teleport[v] + damping * Σ score[u] / out_degree(u)`
/// over the in-arcs of `v`, which is the same distribution the push loop above
/// produces, summed in a different but equally fixed order. Every reduction over
/// nodes, the dangling mass and the residual, combines per-chunk partial sums in
/// chunk order, so the sequence of iterations and the final scores are identical
/// at one worker and at sixteen.
fn pull(
    graph: &GraphProjection,
    options: PageRankOptions<'_>,
    teleport: &[f64],
    mut scores: Buffer<f64>,
    workers: usize,
) -> Result<PageRank> {
    let context = graph.execution();
    let n = graph.node_count();
    let adjacency = graph.outgoing();
    let offsets = &adjacency.offsets.values;
    let reverse = graph.reverse()?;
    let mut next = Buffer::indexed(n, 0.0f64, context)?;
    let mut residual = f64::INFINITY;
    for iteration in 1..=options.max_iterations {
        // Dangling mass: scores of nodes with no outgoing arc.
        let dangling = crate::parallel::map_chunks(
            context,
            workers,
            &scores.values,
            |first, slice, meter| {
                meter.charge(slice.len())?;
                let mut sum = 0.0;
                for (index, &score) in slice.iter().enumerate() {
                    let node = first + index;
                    if offsets[node + 1] == offsets[node] {
                        sum += score;
                    }
                }
                Ok(sum)
            },
        )?;
        let dangling = crate::parallel::reduce_in_order(&dangling, 0.0, |total, part| total + part);
        let base = (1.0 - options.damping) + options.damping * dangling;
        let scores_now = &scores.values;
        let nonfinite = std::sync::atomic::AtomicBool::new(false);
        crate::parallel::for_each_chunk(
            context,
            workers,
            &mut next.values,
            |first, slice, meter| {
                for (index, value) in slice.iter_mut().enumerate() {
                    let node = first + index;
                    let arcs = reverse.range(node);
                    meter.charge(1 + arcs.len())?;
                    let mut sum = 0.0;
                    for arc in arcs {
                        let source = reverse.targets.values[arc];
                        let out_degree = offsets[source + 1] - offsets[source];
                        // A node with no outgoing arc contributes through the
                        // dangling mass in `base`, never through an arc.
                        sum += scores_now[source] / out_degree as f64;
                    }
                    let updated = base * teleport[node] + options.damping * sum;
                    if !updated.is_finite() {
                        nonfinite.store(true, std::sync::atomic::Ordering::Relaxed);
                    }
                    *value = updated;
                }
                Ok(())
            },
        )?;
        if nonfinite.load(std::sync::atomic::Ordering::Relaxed) {
            return Err(AlgorithmError::Numerical(
                "PageRank produced a nonfinite score".into(),
            ));
        }
        let parts = crate::parallel::map_chunks(
            context,
            workers,
            &scores.values,
            |first, slice, meter| {
                meter.charge(slice.len())?;
                let mut sum = 0.0;
                for (index, &before) in slice.iter().enumerate() {
                    sum += (next.values[first + index] - before).abs();
                }
                Ok(sum)
            },
        )?;
        residual = crate::parallel::reduce_in_order(&parts, 0.0, |total, part| total + part);
        std::mem::swap(&mut scores, &mut next);
        if residual <= options.tolerance {
            return Ok(PageRank {
                graph: graph.clone(),
                scores,
                iterations: iteration,
                residual,
                converged: true,
            });
        }
    }
    Ok(PageRank {
        graph: graph.clone(),
        scores,
        iterations: options.max_iterations,
        residual,
        converged: false,
    })
}
