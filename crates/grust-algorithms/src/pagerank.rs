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
    let mut next = Buffer::filled(n, 0.0, context)?;
    let adjacency = graph.outgoing();
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
