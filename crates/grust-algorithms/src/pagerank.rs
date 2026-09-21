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
    // The iteration can be computed by pulling into each target instead of
    // pushing out of each source. Pulling is what makes it parallel: targets own
    // their own sums, so no worker writes where another might read, and each sum
    // stays in in-arc order, so the result does not depend on the division of
    // work. A weighted projection pulls too, because the projection's in-arc
    // index carries each arc's weight; the push loop below stays as the
    // sequential path and the oracle the pull is tested against.
    let workers = crate::parallel::workers(
        context,
        n.saturating_add(adjacency.targets.values.len())
            .saturating_mul(2),
    );
    if let Some(workers) = workers {
        return pull(graph, options, &teleport.values, scores, workers);
    }
    let mut next = Buffer::filled(n, 0.0, context)?;
    // Scale each row by its largest edge weight before summing, preventing
    // overflow for valid finite weights such as two f64::MAX parallel edges.
    let mut scales = Buffer::filled(n, 0.0f64, context)?;
    let mut totals = Buffer::filled(n, 0.0, context)?;
    for source in 0..n {
        let scale = &mut scales.values[source];
        charged_arcs(context, 1, adjacency.range(source), |arc| {
            *scale = scale.max(adjacency.weight(arc));
        })?;
        let scale = *scale;
        if scale > 0.0 {
            let total = &mut totals.values[source];
            charged_arcs(context, 0, adjacency.range(source), |arc| {
                *total += adjacency.weight(arc) / scale;
            })?;
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
            let scale = scales.values[source];
            if scale == 0.0 {
                // A dangling row's arcs are not visited, so they are not charged.
                context.charge_work(1)?;
                continue;
            }
            let total = totals.values[source];
            let mass = options.damping * scores.values[source];
            let next = &mut next.values;
            charged_arcs(context, 1, adjacency.range(source), |arc| {
                let probability = (adjacency.weight(arc) / scale) / total;
                next[adjacency.targets.values[arc]] += mass * probability;
            })?;
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

/// The parallel iteration, weighted or not.
///
/// Each iteration computes, for every target `v`,
/// `next[v] = base * teleport[v] + damping * Σ score[u] · p(u → v)`
/// over the in-arcs of `v`, where `p` is the same arc probability the push loop
/// derives from the source's scaled weight total. It is therefore the same
/// distribution, summed in a different but equally fixed order. Every reduction
/// over nodes, the dangling mass and the residual, combines per-chunk partial
/// sums in fixed-size chunks in chunk order, so the sequence of iterations and
/// the final scores are identical at one worker and at sixteen.
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
    let reverse = graph.incoming()?;
    // Per-source arc probability, exactly as the push loop derives it: each row
    // is scaled by its largest weight before summing, so two arcs of f64::MAX
    // still sum finitely, and a row of zero weight is dangling.
    //
    // Only a weighted projection needs them. An unweighted arc's probability is
    // `1/out-degree`, which `offsets` already holds. Deriving it from `scales`
    // and `totals` instead added two more 8-byte-per-node streams under the
    // same random index as `scores` and `offsets`; on roadNet-CA that is 48 MB
    // of randomly touched arrays against a 24.8 MB L3 where 32 MB fitted
    // before, and it cost the kernel a measured 1.5x at every worker count.
    // The per-source shares below go the other way: one 8-byte stream under
    // the random index instead of those two.
    let weighted = graph.is_weighted();
    let factored = if weighted { n } else { 0 };
    let mut scales = Buffer::indexed(factored, 0.0f64, context)?;
    let mut totals = Buffer::indexed(factored, 0.0f64, context)?;
    if weighted {
        crate::parallel::for_each_chunk(
            context,
            workers,
            &mut scales.values,
            |first, slice, meter| {
                for (index, scale) in slice.iter_mut().enumerate() {
                    let node = first + index;
                    let range = offsets[node]..offsets[node + 1];
                    meter.charge(1 + range.len())?;
                    let mut largest = 0.0f64;
                    for arc in range {
                        largest = largest.max(adjacency.weight(arc));
                    }
                    *scale = largest;
                }
                Ok(())
            },
        )?;
        let scaled = &scales.values;
        crate::parallel::for_each_chunk(
            context,
            workers,
            &mut totals.values,
            |first, slice, meter| {
                for (index, total) in slice.iter_mut().enumerate() {
                    let node = first + index;
                    let range = offsets[node]..offsets[node + 1];
                    meter.charge(range.len())?;
                    if scaled[node] <= 0.0 {
                        continue;
                    }
                    let mut sum = 0.0;
                    for arc in range {
                        sum += adjacency.weight(arc) / scaled[node];
                    }
                    *total = sum;
                }
                Ok(())
            },
        )?;
    }
    let scales = &scales.values;
    let totals = &totals.values;
    // Unweighted, each source's share of its score, `score / out-degree`, is
    // formed once per iteration, in the dangling pass that already reads each
    // node's score and `offsets` row in order, so an arc reads one randomly
    // indexed array, `shares`, instead of `scores` and both ends of the
    // source's `offsets` row. The quotient is the one the arc loop used to form
    // per arc, from the same operands, and the arcs add it in the same order,
    // so every score keeps its bits (`tests/pagerank_pinned.rs`).
    //
    // It costs one f64 per node, admitted here. At scale it also narrows the
    // randomly touched set the comment above measured, from `scores` and
    // `offsets` to `shares` alone. Forming the shares is not charged: it is part
    // of visiting a node in the dangling pass, which charges it, so a work
    // budget still fails at the same unit.
    let mut shares = Buffer::indexed(if weighted { 0 } else { n }, 0.0f64, context)?;
    let mut next = Buffer::indexed(n, 0.0f64, context)?;
    let mut residual = f64::INFINITY;
    for iteration in 1..=options.max_iterations {
        // Dangling mass: scores of nodes with no outgoing arc, summed in the
        // fixed chunks of `REDUCTION_CHUNK_LEN` on both branches.
        let scores_now = &scores.values;
        let dangling = if weighted {
            crate::parallel::map_chunks(context, workers, scores_now, |first, slice, meter| {
                meter.charge(slice.len())?;
                let mut sum = 0.0;
                for (index, &score) in slice.iter().enumerate() {
                    // A row of zero outgoing weight is dangling even where arcs
                    // exist, which is the push kernel's rule too.
                    if scales[first + index] <= 0.0 {
                        sum += score;
                    }
                }
                Ok(sum)
            })?
        } else {
            crate::parallel::for_chunks(
                workers,
                &mut shares.values,
                crate::parallel::REDUCTION_CHUNK_LEN,
                |first, chunk| {
                    // `for_chunks` hands out no meter, so each fixed chunk is
                    // charged on the execution directly: one exchange per 4,096
                    // nodes, which is what a meter did too, since a charge that
                    // size never fits in its 1,024-unit block. Admission is
                    // exact either way (`tests/pagerank_pinned.rs`).
                    context.charge_work(chunk.len())?;
                    let mut sum = 0.0;
                    for (index, share) in chunk.iter_mut().enumerate() {
                        let node = first + index;
                        let score = scores_now[node];
                        let out_degree = offsets[node + 1] - offsets[node];
                        // Unweighted, having no arc is the whole of dangling. A
                        // dangling node contributes through `base`, never
                        // through an arc, so its share is never read.
                        if out_degree == 0 {
                            sum += score;
                            *share = 0.0;
                        } else {
                            *share = score / out_degree as f64;
                        }
                    }
                    Ok(sum)
                },
            )?
        };
        let dangling = crate::parallel::reduce_in_order(&dangling, 0.0, |total, part| total + part);
        let base = (1.0 - options.damping) + options.damping * dangling;
        let shares = &shares.values;
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
                    if weighted {
                        for arc in arcs {
                            let source = reverse.targets.values[arc];
                            // A dangling row contributes through `base`, never
                            // through an arc; its total is zero and would
                            // divide.
                            if totals[source] <= 0.0 {
                                continue;
                            }
                            let probability =
                                (reverse.weight(arc) / scales[source]) / totals[source];
                            sum += scores_now[source] * probability;
                        }
                    } else {
                        for arc in arcs {
                            sum += shares[reverse.targets.values[arc]];
                        }
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
