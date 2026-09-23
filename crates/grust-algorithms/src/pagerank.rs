//! Weighted PageRank and ArticleRank, with explicit convergence and
//! dangling-node semantics.

use crate::{AlgorithmError, GraphProjection, Result, buffer::Buffer, score::Score};

mod pull;

/// Which rank to compute. The iteration is the same; the two differ only in what
/// a source divides its score by before sending it along an arc.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum RankVariant {
    /// A source divides its score by its own outgoing weight, so every source
    /// sends all of its score onward and the scores sum to one.
    #[default]
    PageRank,
    /// A source divides by its outgoing weight **plus the mean outgoing weight
    /// over all nodes**, which damps what a low-degree source can confer: a node
    /// cited once by a node that cites once gains less than PageRank gives it.
    /// The inflated divisor means a source sends on less than its whole score,
    /// so ArticleRank scores do not sum to one, and comparing their magnitudes
    /// with PageRank's is meaningless. Their order is the point.
    ArticleRank,
}

/// PageRank controls. Scores start uniformly and dangling mass is redistributed
/// according to personalization (uniform when omitted).
#[derive(Clone, Copy, Debug)]
pub struct PageRankOptions<'a> {
    /// PageRank, or ArticleRank's damped divisor.
    pub variant: RankVariant,
    /// Probability of following an edge; finite and in [0, 1).
    pub damping: f64,
    /// Stop when the L1 difference between iterations is at most this value.
    /// The difference is summed in `f64` at either score precision; with
    /// `f32` scores it is a sum of rounded moves, which tracks the `f64`
    /// kernel's residual closely until the scores stop moving altogether
    /// (see [`pagerank_f32`]).
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
            variant: RankVariant::PageRank,
            damping: 0.85,
            tolerance: 1e-8,
            max_iterations: 1000,
            personalization: None,
        }
    }
}

/// The mean outgoing weight over all nodes, which is what ArticleRank adds to
/// each source's divisor. Dangling rows count as zero and still count towards
/// the mean, so a graph with many dangling nodes damps more, which is the
/// behaviour ArticleRank is asked for. The sum is taken in node order in fixed
/// chunks, so it does not depend on the worker count.
fn mean_outgoing<F: Score>(totals: &[F]) -> F {
    if totals.is_empty() {
        return F::ZERO;
    }
    let mut sum = F::ZERO;
    for chunk in totals.chunks(crate::parallel::REDUCTION_CHUNK_LEN) {
        let mut part = F::ZERO;
        for &total in chunk {
            part += total;
        }
        sum += part;
    }
    sum / F::from_f64(totals.len() as f64)
}

/// The same quantity as [`mean_outgoing`] for an unweighted projection, from the
/// arc count instead of a per-node array.
///
/// Every unweighted arc contributes exactly `1.0` to its source's total, so the
/// totals are the out-degrees and their mean is `arcs / nodes`. The parallel
/// unweighted path does not build those totals — reading two extra
/// `f64`-per-node arrays in the inner loop cost it 1.5x — so it takes the mean
/// from the offsets it already holds. This agrees with [`mean_outgoing`] bit for
/// bit rather than approximately: a sum of integer-valued `f64` is exact while
/// the running total stays below 2^53, so chunking cannot change it and neither
/// can the order. At `f32` the same holds up to 2^24 arcs, where both the
/// chunked sum and the cast of the count are still the exact arc count.
fn mean_out_degree<F: Score>(nodes: usize, arcs: usize) -> F {
    if nodes == 0 {
        return F::ZERO;
    }
    F::from_f64(arcs as f64) / F::from_f64(nodes as f64)
}

/// Scores and convergence evidence. Exhausting the iteration limit returns
/// `converged() == false`; it never silently asserts convergence.
///
/// `F` is the precision the scores were computed and are kept in: `f64` from
/// [`pagerank`], `f32` from [`pagerank_f32`]. The residual is `f64` in both.
pub struct PageRank<F = f64> {
    graph: GraphProjection,
    scores: Buffer<F>,
    iterations: usize,
    residual: f64,
    converged: bool,
}

impl<F> PageRank<F> {
    /// Projection supplying external IDs and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// Score per selected node, in projection row order.
    pub fn values(&self) -> &[F] {
        &self.scores.values
    }
    /// Number of completed updates; zero for an empty graph.
    pub fn iterations(&self) -> usize {
        self.iterations
    }
    /// Last L1 update difference, summed in `f64` whatever the score
    /// precision, or zero for an empty graph.
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
    rank(graph, options)
}

/// [`pagerank`] with `f32` scores.
///
/// The same kernel, options, paths and work charges as [`pagerank`], with every
/// score, per-arc probability, dangling mass, teleport share and `base` formed
/// and accumulated in `f32`; the personalization is normalized in `f64` and
/// rounded once. The L1 residual is summed in `f64` from the `f32` differences,
/// and the run stops when it is at most `tolerance`, as at `f64`. This is the
/// arrangement `neo4j-labs/graph` uses, whose stop is `residual < tolerance`;
/// the two rules differ only at a residual exactly equal to the tolerance,
/// which a sum of `f32` differences does not land on at a tolerance such as
/// 1e-8, and both stop at a residual of zero.
///
/// The bits are the same at any worker count, as at `f64`: the reductions run
/// in the fixed chunks of `REDUCTION_CHUNK_LEN`, whatever the pool width.
///
/// What to expect of the iteration count, from `tests/pagerank_f32.rs`. The
/// `f32` residual is a sum of rounded moves, and rounding to nearest is
/// unbiased, so on a graph of 1e5 nodes it tracks the `f64` residual to a few
/// percent until the scores stop moving: at tolerance 1e-8 the two runs stop
/// at the same iteration, or one apart where the `f64` residual lands within
/// that few percent of the tolerance. A score stops moving once its true
/// update is under half an ulp, and an `f32` ulp is 2^29 `f64` ulps, so the
/// `f32` run reaches an exact fixed point, residual zero, well before the
/// `f64` run does: at tolerance zero, 147 iterations against 261 on that
/// fixture. A graph whose dangling mass is a long sum is the exception: with
/// half of 2e5 nodes dangling, the `f32` run needed about twice the `f64`
/// run's iterations at every tolerance of 1e-6 and below, and summing that
/// one reduction in `f64` instead, as an experiment, recovered most of the
/// gap. The `f32` sum of 1e5 scores rounds `base` differently each iteration;
/// the kernel keeps the sum in `f32`, as the precision asked for.
///
/// A tolerance below one ulp of a moving score cannot be met at `f32` except
/// at an exact fixed point, and the rounded iteration can settle into a
/// one-ulp oscillation instead: on a four-node graph whose two largest scores
/// are near 0.45, where an `f32` ulp is 2^-25, the default tolerance 1e-8 is
/// never reached, the residual is exactly 2^-24 for all 1000 iterations and
/// `converged()` is false, while 1e-6 is met in 80 iterations. Scores near
/// `1/n` on a large graph have ulps far below 1e-8; a hub holding a large
/// share of the mass does not.
pub fn pagerank_f32(
    graph: &GraphProjection,
    options: PageRankOptions<'_>,
) -> Result<PageRank<f32>> {
    rank(graph, options)
}

/// The kernel behind [`pagerank`] and [`pagerank_f32`].
fn rank<F: Score>(graph: &GraphProjection, options: PageRankOptions<'_>) -> Result<PageRank<F>> {
    graph.require_nonnegative("pagerank")?;
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
    let uniform = uniform_share::<F>(n);
    let mut teleport = Buffer::filled(n, uniform, context)?;
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
        // Normalized in `f64` as given, and rounded to the score precision
        // once, as each share is formed.
        let mut total = 0.0;
        for (target, &value) in teleport.values.iter_mut().zip(values) {
            context.charge_work(1)?;
            let share = value / maximum;
            *target = F::from_f64(share);
            total += share;
        }
        for value in &mut teleport.values {
            context.charge_work(1)?;
            *value = F::from_f64(value.to_f64() / total);
        }
    }
    let mut scores = Buffer::filled(n, uniform, context)?;
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
    // The iteration can be computed by pulling into each target instead of
    // pushing out of each source. Pulling is what makes it parallel: targets own
    // their own sums, so no worker writes where another might read, and each sum
    // stays in in-arc order, so the result does not depend on the division of
    // work. A weighted projection pulls too, because the projection's in-arc
    // index carries each arc's weight; the push loop below stays as the
    // sequential path and the oracle the pull is tested against.
    let workers = crate::parallel::workers(
        context,
        n.saturating_add(adjacency.arc_count()).saturating_mul(2),
    );
    if let Some(workers) = workers {
        return pull::pull(graph, options, teleport, scores, workers);
    }
    let mut next = Buffer::filled(n, F::ZERO, context)?;
    // Scale each row by its largest edge weight before summing, preventing
    // overflow for valid finite weights such as two f64::MAX parallel edges.
    // The scales stay `f64`, the weights' type; each scaled weight is in
    // [0, 1] and is rounded to the score precision as it is summed.
    let mut scales = Buffer::filled(n, 0.0f64, context)?;
    let mut totals = Buffer::filled(n, F::ZERO, context)?;
    for source in 0..n {
        let scale = &mut scales.values[source];
        charged_arcs(context, 1, adjacency.range(source), |arc| {
            *scale = scale.max(adjacency.weight(arc));
        })?;
        let scale = *scale;
        if scale > 0.0 {
            let total = &mut totals.values[source];
            charged_arcs(context, 0, adjacency.range(source), |arc| {
                *total += F::from_f64(adjacency.weight(arc) / scale);
            })?;
        }
    }
    // PageRank divides by the source's own outgoing weight; ArticleRank adds the
    // mean, so a source with few arcs confers less.
    let damp = match options.variant {
        RankVariant::PageRank => F::ZERO,
        RankVariant::ArticleRank => mean_outgoing(&totals.values),
    };
    let (damping, retained) = damping::<F>(&options);
    // Weighted, each arc's probability is formed in the first iteration, where
    // it always was, and kept, one score per arc, so the later iterations read
    // it instead of dividing twice per arc. It is that iteration's value, so
    // every score keeps its bits, and nothing is charged for keeping it. An
    // unweighted arc's probability is `1 / out-degree`, formed per arc as
    // before; a row's arcs would all hold the same value.
    let weighted = graph.is_weighted();
    let mut probabilities = Buffer::indexed(
        if weighted { adjacency.arc_count() } else { 0 },
        F::ZERO,
        context,
    )?;
    let mut residual = f64::INFINITY;
    for iteration in 1..=options.max_iterations {
        let mut dangling = F::ZERO;
        for (source, &score) in scores.values.iter().enumerate() {
            context.charge_work(1)?;
            if scales.values[source] == 0.0 {
                dangling += score;
            }
        }
        let base = retained + damping * dangling;
        for (value, &probability) in next.values.iter_mut().zip(&teleport.values) {
            context.charge_work(1)?;
            *value = base * probability;
        }
        for source in 0..n {
            let scale = scales.values[source];
            if scale == 0.0 {
                // A dangling row's arcs are not visited, so they are not charged.
                context.charge_work(1)?;
                continue;
            }
            // `damp` is zero for PageRank; hoisted out of the arc loop, the
            // divisor is the same `f64` the loop formed per arc.
            let total = totals.values[source] + damp;
            let mass = damping * scores.values[source];
            let next = &mut next.values;
            let targets = adjacency.targets();
            let range = adjacency.range(source);
            if !weighted {
                charged_arcs(context, 1, range, |arc| {
                    let probability = F::from_f64(adjacency.weight(arc) / scale) / total;
                    next[targets[arc] as usize] += mass * probability;
                })?;
            } else if iteration == 1 {
                let probabilities = &mut probabilities.values;
                charged_arcs(context, 1, range, |arc| {
                    let probability = F::from_f64(adjacency.weight(arc) / scale) / total;
                    probabilities[arc] = probability;
                    next[targets[arc] as usize] += mass * probability;
                })?;
            } else {
                let probabilities = &probabilities.values;
                charged_arcs(context, 1, range, |arc| {
                    next[targets[arc] as usize] += mass * probabilities[arc];
                })?;
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
            residual += (after - before).abs().to_f64();
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

/// The damping factor and its complement, `1 - damping`, at the score
/// precision. The complement is formed in `f64` and rounded, so the `f64`
/// kernel's `base` is the expression it always was.
fn damping<F: Score>(options: &PageRankOptions<'_>) -> (F, F) {
    (
        F::from_f64(options.damping),
        F::from_f64(1.0 - options.damping),
    )
}

/// The uniform teleport share, `1 / n`, at the score precision: every node's
/// initial score, and every node's teleport share when no personalization is
/// given. The pull's uniform path forms `base * uniform` once from this same
/// value instead of reading it back from the teleport array per node.
fn uniform_share<F: Score>(n: usize) -> F {
    F::from_f64(if n == 0 { 0.0 } else { 1.0 / n as f64 })
}

/// Arcs the push loop visits between two charges.
///
/// It used to charge every arc, and each charge is a compare-exchange on the
/// execution's shared counter. Charging a source's arcs together takes that out
/// of the arc loop; capping a charge at this many arcs keeps cancellation and
/// the sampled deadline polled within that many arcs, however large a source's
/// out-degree, where a charge per source would leave a hub unpolled for the
/// whole of its row.
const ARC_CHARGE_CHUNK: usize = 1024;

/// Charge `lead` units and then every arc of `arcs` before visiting it, in
/// chunks of at most [`ARC_CHARGE_CHUNK`] arcs, the first carrying `lead`.
///
/// The units are the ones a charge per unit would make, in the same order, so
/// the total is unchanged and a budget refuses at the same unit: see
/// [`charge_exactly`].
fn charged_arcs(
    context: &crate::ExecutionContext,
    lead: usize,
    arcs: std::ops::Range<usize>,
    mut visit: impl FnMut(usize),
) -> Result<()> {
    let mut lead = lead;
    let mut start = arcs.start;
    loop {
        let end = arcs.end.min(start.saturating_add(ARC_CHARGE_CHUNK));
        charge_exactly(context, lead + (end - start))?;
        for arc in start..end {
            visit(arc);
        }
        if end >= arcs.end {
            return Ok(());
        }
        lead = 0;
        start = end;
    }
}

/// Charge `units` at once, stopping where charging them one at a time would.
///
/// A charge that does not fit is refused whole, which would leave the
/// execution's counter short of the budget where a unit at a time would have
/// filled it to the last unit. When the whole charge is refused, the units are
/// charged singly until one is refused, so the counter a caller reads after the
/// refusal, and the unit at which it happened, are those of a charge per unit.
fn charge_exactly(context: &crate::ExecutionContext, units: usize) -> Result<()> {
    if units == 0 {
        return Ok(());
    }
    match context.charge_work(units) {
        Err(AlgorithmError::BudgetExceeded { .. }) => {
            for _ in 0..units {
                context.charge_work(1)?;
            }
            Ok(())
        }
        other => other,
    }
}
