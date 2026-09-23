//! The parallel PageRank iteration: a pull over in-arcs, one pass per
//! iteration.
//!
//! Each iteration computes, for every target `v`,
//! `next[v] = base * teleport[v] + damping * Σ score[u] · p(u → v)`
//! over the in-arcs of `v`, where `p` is the same arc probability the push
//! loop derives from the source's scaled weight total. It is therefore the
//! same distribution, summed in a different but equally fixed order. Pulling
//! is what makes it parallel: targets own their own sums, so no worker writes
//! where another might read, and each sum stays in in-arc order, so the result
//! does not depend on the division of work.
//!
//! **One pass per iteration.** The iteration used to be three passes over the
//! nodes: one forming each source's share `score / (out-degree + damp)` and
//! the dangling mass, one pulling, and one summing the residual. They are one
//! pass now. Visiting `v`, it sums the in-arc shares, forms `next[v]`, adds
//! `|next[v] - score[v]|` to the residual, and forms `v`'s share of `next[v]`
//! for the *next* iteration, or adds `next[v]` to the next iteration's
//! dangling mass when `v` has no out-arc. The dangling mass of pass `k` feeds
//! `base` of pass `k + 1`: that is the same arithmetic as the old shares pass
//! over the scores pass `k` had just written, from the same operands, so every
//! score, iteration count and residual keeps its bits
//! (`tests/pagerank_pinned.rs`, `tests/pagerank_fused.rs`). Only the initial
//! shares, before the first pass, are formed by a pass of their own.
//!
//! **Why the sums keep their bits at every width.** The residual and the
//! dangling mass are float sums, so their grouping must not follow the worker
//! count. Each worker's chunk is a whole number of [`REDUCTION_CHUNK_LEN`]
//! chunks starting on a chunk boundary ([`reduction_aligned_chunk_len`]), and
//! the pass forms one partial per fixed chunk, in node order, into a slot
//! indexed by that chunk. The partials are then folded in chunk order. That is
//! the grouping and the order the three passes used, so the two sums are the
//! same numbers at one worker and at sixteen, as they were.
//!
//! **What is charged, and where.** The three passes charged one unit per
//! node, `1 + in-arcs` per node, and one unit per node, in that order, every
//! iteration. The fused pass charges `1 + in-arcs` per node as it visits it.
//! The residual's units are charged in the same fixed chunks right after the
//! pass, and the next iteration's share units at the start of that iteration,
//! before its pass: the same units in the same order as before, so a budget
//! refuses at the unit it always refused at and leaves the same count behind.
//! The two chunked charges name work the pass has already done alongside the
//! node visits it charged; they are kept so the account is the one every
//! caller, test and budget was written against.
//!
//! **Memory.** Unweighted, the shares are double-buffered and the scores are
//! updated in place, since no arc reads a score: three arrays of `n` scores,
//! as before, plus one partial per fixed chunk. Weighted, each in-arc's
//! probability is formed once before the iterations, one score-sized value
//! per arc, and the per-row scales are released before the iterations begin;
//! the scores are double-buffered because the arcs read them. The uniform
//! teleport array is released on entry, since the uniform path never reads it.

use std::sync::atomic::{AtomicBool, Ordering};

use super::{
    PageRank, PageRankOptions, RankVariant, damping, mean_out_degree, mean_outgoing, uniform_share,
};
use crate::parallel::{REDUCTION_CHUNK_LEN, reduce_in_order, reduction_aligned_chunk_len};
use crate::projection::Adjacency;
use crate::{
    AlgorithmError, ExecutionContext, GraphProjection, Result, buffer::Buffer, score::Score,
};

/// What one fixed reduction chunk contributes to one iteration's two sums.
#[derive(Clone, Copy)]
struct Partial<F> {
    /// `Σ |next - score|` over the chunk's nodes, in node order, in `f64` at
    /// either score precision.
    residual: f64,
    /// `Σ next` over the chunk's dangling nodes, in node order.
    dangling: F,
}

/// One iteration's `base`, and how each node's teleport term is formed from
/// it: `base * teleport[node]` under a personalization, else the one product
/// `base * (1 / n)`, formed once. A uniform teleport array holds `1 / n` at
/// the score precision in every slot, so the two are the same bits
/// (`tests/pagerank_fused.rs`).
struct Teleport<'a, F> {
    base: F,
    uniform: F,
    shares: Option<&'a [F]>,
}

impl<F: Score> Teleport<'_, F> {
    #[inline(always)]
    fn at(&self, node: usize) -> F {
        match self.shares {
            Some(shares) => self.base * shares[node],
            None => self.uniform,
        }
    }
}

/// What every node of every pass reads.
struct Pass<'a, F> {
    context: &'a ExecutionContext,
    workers: usize,
    /// Nodes per worker task: a multiple of [`REDUCTION_CHUNK_LEN`].
    chunk: usize,
    reverse: &'a Adjacency,
    /// The projection's own offsets: a node's out-degree.
    offsets: &'a [usize],
    damping: F,
    /// Zero for PageRank; ArticleRank's mean outgoing weight.
    damp: F,
    /// Weighted only: each row's scaled weight total, zero for a dangling row.
    totals: &'a [F],
    /// Weighted only: each in-arc's probability.
    probabilities: &'a [F],
}

pub(super) fn pull<F: Score>(
    graph: &GraphProjection,
    options: PageRankOptions<'_>,
    teleport: Buffer<F>,
    mut scores: Buffer<F>,
    workers: usize,
) -> Result<PageRank<F>> {
    let context = graph.execution();
    let n = graph.node_count();
    let adjacency = graph.outgoing();
    let reverse = graph.incoming()?;
    let weighted = graph.is_weighted();
    let (damping, retained) = damping::<F>(&options);
    let uniform = uniform_share::<F>(n);
    // Without a personalization every slot holds `uniform`, which the passes
    // form from the scalar instead; the array is not read again.
    let personalized = options.personalization.is_some().then_some(teleport);
    let teleport = personalized.as_deref();

    let mut totals = Buffer::indexed(if weighted { n } else { 0 }, F::ZERO, context)?;
    let arcs = reverse.targets.values.len();
    let mut probabilities = Buffer::indexed(if weighted { arcs } else { 0 }, F::ZERO, context)?;
    // PageRank divides by the source's own outgoing weight; ArticleRank adds
    // the mean over all nodes, so a source with few arcs confers less.
    //
    // Unweighted there is no `totals` to take the mean of, and none is needed:
    // every unweighted arc contributes exactly `1.0` to its source's total, so
    // the mean outgoing weight *is* the mean out-degree, `arcs / nodes`. It is
    // the same value `mean_outgoing` would return over the array that is not
    // built: summing integer-valued degrees is exact below 2^53, so the
    // chunked sum and the arc count agree bit for bit.
    let damp = if weighted {
        weigh(
            context,
            workers,
            options.variant,
            adjacency,
            &reverse,
            &mut totals.values,
            &mut probabilities.values,
        )?
    } else {
        match options.variant {
            RankVariant::PageRank => F::ZERO,
            RankVariant::ArticleRank => mean_out_degree(n, arcs),
        }
    };

    let pass = Pass {
        context,
        workers,
        chunk: reduction_aligned_chunk_len(n, workers),
        reverse: &reverse,
        offsets: &adjacency.offsets.values,
        damping,
        damp,
        totals: &totals.values,
        probabilities: &probabilities.values,
    };
    // Unweighted, each source's share of its score, `score / (out-degree +
    // damp)`, is what an arc reads: one randomly indexed array instead of
    // `scores` and both ends of the source's `offsets` row. The quotient is the
    // one the arc loop once formed per arc, from the same operands, and the
    // arcs add it in the same order. Weighted, an arc reads the source's score
    // and its own probability instead.
    let mut shares_now = Buffer::indexed(if weighted { 0 } else { n }, F::ZERO, context)?;
    let mut shares_next = Buffer::indexed(if weighted { 0 } else { n }, F::ZERO, context)?;
    let mut next = Buffer::indexed(if weighted { n } else { 0 }, F::ZERO, context)?;
    let blank = Partial {
        residual: 0.0,
        dangling: F::ZERO,
    };
    let mut partials = Buffer::indexed(n.div_ceil(REDUCTION_CHUNK_LEN), blank, context)?;

    // The first iteration's shares and dangling mass, from the initial
    // scores: the pass every later iteration fuses into the one before it.
    let mut dangling = if weighted {
        pass.dangling_of(&scores.values)?
    } else {
        pass.shares_of(&scores.values, &mut shares_now.values)?
    };
    let mut residual = f64::INFINITY;
    for iteration in 1..=options.max_iterations {
        if iteration > 1 {
            // This iteration's shares and dangling mass were formed by the
            // last pass. Their units are charged here, where the pass that
            // formed them used to run, and never for an iteration that does
            // not happen: see the module comment.
            charge_chunks(context, n)?;
        }
        let base = retained + damping * dangling;
        let teleport = Teleport {
            base,
            uniform: base * uniform,
            shares: teleport,
        };
        let finite = if weighted {
            pass.weighted(
                &teleport,
                &scores.values,
                &mut next.values,
                &mut partials.values,
            )?
        } else {
            pass.unweighted(
                &teleport,
                &shares_now.values,
                &mut scores.values,
                &mut shares_next.values,
                &mut partials.values,
            )?
        };
        if !finite {
            return Err(AlgorithmError::Numerical(
                "PageRank produced a nonfinite score".into(),
            ));
        }
        // The residual's units, as its own pass charged them.
        charge_chunks(context, n)?;
        residual = reduce_in_order(&partials.values, 0.0, |total, part| total + part.residual);
        dangling = reduce_in_order(&partials.values, F::ZERO, |total, part| {
            total + part.dangling
        });
        if weighted {
            std::mem::swap(&mut scores, &mut next);
        } else {
            std::mem::swap(&mut shares_now, &mut shares_next);
        }
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

/// Charge `n` units in the fixed chunks a reduction pass over `n` nodes
/// charges, in chunk order, on the execution directly. No meter is live when
/// this runs, so a refusal leaves exactly the work performed on the counter.
fn charge_chunks(context: &ExecutionContext, n: usize) -> Result<()> {
    let mut start = 0;
    while start < n {
        let len = (n - start).min(REDUCTION_CHUNK_LEN);
        context.charge_work(len)?;
        start += len;
    }
    Ok(())
}

/// The weighted setup: each row's scaled weight total, ArticleRank's `damp`,
/// and each in-arc's probability, formed once.
///
/// Every row is scaled by its largest weight before summing, exactly as the
/// push loop does, so two arcs of `f64::MAX` still sum finitely, and a row of
/// zero weight is dangling even where arcs exist. An arc's probability is
/// `F(weight / scale) / (total + damp)`, the expression the pull once formed
/// per arc per iteration from the same operands, so the stored value is that
/// value's bits. An arc out of a dangling row, which the pull skipped, is
/// stored as zero: a finite nonnegative score times zero is `+0.0`, and adding
/// `+0.0` to a sum of nonnegative terms leaves every bit of it, in either
/// precision, so the arc loop no longer branches.
///
/// Two passes, charged as the two they replace were. The first charges one
/// unit per row and one per arc and forms the row's scale and total together,
/// reading the row twice while it is hot; the second charges one unit per
/// out-arc of each row, in row order, as the totals pass did, and visits the
/// same arcs by target. The units, their order and the unit a budget refuses
/// at are unchanged. The scales live only here.
fn weigh<F: Score>(
    context: &ExecutionContext,
    workers: usize,
    variant: RankVariant,
    adjacency: &Adjacency,
    reverse: &Adjacency,
    totals: &mut [F],
    probabilities: &mut [F],
) -> Result<F> {
    let n = totals.len();
    let chunk = crate::parallel::chunk_len(n, workers);
    let mut scales = Buffer::indexed(n, 0.0f64, context)?;
    let rows: Vec<_> = scales
        .values
        .chunks_mut(chunk)
        .zip(totals.chunks_mut(chunk))
        .enumerate()
        .map(|(index, (scales, totals))| (index * chunk, scales, totals))
        .collect();
    crate::parallel::for_each_owned(workers, rows, |_, (first, scales, totals)| {
        let mut meter = context.work_meter();
        for (index, (scale, total)) in scales.iter_mut().zip(totals.iter_mut()).enumerate() {
            let range = adjacency.range(first + index);
            meter.charge(1 + range.len())?;
            let mut largest = 0.0f64;
            for arc in range.clone() {
                largest = largest.max(adjacency.weight(arc));
            }
            *scale = largest;
            if largest <= 0.0 {
                continue;
            }
            let mut sum = F::ZERO;
            for arc in range {
                sum += F::from_f64(adjacency.weight(arc) / largest);
            }
            *total = sum;
        }
        Ok(())
    })?;
    let damp = match variant {
        RankVariant::PageRank => F::ZERO,
        RankVariant::ArticleRank => mean_outgoing(totals),
    };
    let (scales, totals) = (&scales.values, &*totals);
    // Each task owns the probabilities of the in-arcs of its rows, which are
    // contiguous in the transpose.
    let mut rest = probabilities;
    let mut tasks = Vec::with_capacity(n.div_ceil(chunk.max(1)));
    let mut first = 0;
    while first < n {
        let last = (first + chunk).min(n);
        let len = reverse.offsets.values[last] - reverse.offsets.values[first];
        let (own, tail) = std::mem::take(&mut rest).split_at_mut(len);
        rest = tail;
        tasks.push((first, last, own));
        first = last;
    }
    crate::parallel::for_each_owned(workers, tasks, |_, (first, last, own)| {
        let mut meter = context.work_meter();
        let base = reverse.offsets.values[first];
        for node in first..last {
            meter.charge(adjacency.range(node).len())?;
            for arc in reverse.range(node) {
                let source = reverse.targets.values[arc];
                own[arc - base] = if totals[source] <= F::ZERO {
                    F::ZERO
                } else {
                    F::from_f64(reverse.weight(arc) / scales[source]) / (totals[source] + damp)
                };
            }
        }
        Ok(())
    })?;
    Ok(damp)
}

impl<F: Score> Pass<'_, F> {
    /// Each node's share of its score for the first iteration, and the
    /// dangling mass of the initial scores, summed in the fixed chunks: the
    /// pass every later iteration fuses into the one before it, on the same
    /// chunks with the same charges.
    fn shares_of(&self, scores: &[F], shares: &mut [F]) -> Result<F> {
        let parts = crate::parallel::for_chunks(
            self.workers,
            shares,
            REDUCTION_CHUNK_LEN,
            |first, chunk| {
                // `for_chunks` hands out no meter, so each fixed chunk is
                // charged on the execution directly: one exchange per 4,096
                // nodes, which is what a meter did too, since a charge that
                // size never fits in its 1,024-unit block. Admission is exact
                // either way (`tests/pagerank_pinned.rs`).
                self.context.charge_work(chunk.len())?;
                let mut sum = F::ZERO;
                for (index, share) in chunk.iter_mut().enumerate() {
                    let node = first + index;
                    let score = scores[node];
                    let out_degree = self.offsets[node + 1] - self.offsets[node];
                    // Unweighted, having no arc is the whole of dangling. A
                    // dangling node contributes through `base`, never through
                    // an arc, so its share is never read.
                    if out_degree == 0 {
                        sum += score;
                        *share = F::ZERO;
                    } else {
                        // `damp` is zero for PageRank, so this is one add on
                        // a divisor that was already being formed.
                        *share = score / (F::from_f64(out_degree as f64) + self.damp);
                    }
                }
                Ok(sum)
            },
        )?;
        Ok(reduce_in_order(&parts, F::ZERO, |total, part| total + part))
    }

    /// The weighted form of [`Self::shares_of`]: the dangling mass of the
    /// initial scores alone, since a weighted arc reads the score itself.
    fn dangling_of(&self, scores: &[F]) -> Result<F> {
        let parts = crate::parallel::map_chunks(
            self.context,
            self.workers,
            scores,
            |first, slice, meter| {
                meter.charge(slice.len())?;
                let mut sum = F::ZERO;
                for (index, &score) in slice.iter().enumerate() {
                    // A row of zero outgoing weight is dangling even where
                    // arcs exist, which is the push kernel's rule too.
                    if self.totals[first + index] <= F::ZERO {
                        sum += score;
                    }
                }
                Ok(sum)
            },
        )?;
        Ok(reduce_in_order(&parts, F::ZERO, |total, part| total + part))
    }

    /// One unweighted iteration. Reads `shares_now`, updates `scores` in
    /// place, writes `shares_next` and one partial per fixed chunk. Returns
    /// whether every updated score is finite.
    fn unweighted(
        &self,
        teleport: &Teleport<'_, F>,
        shares_now: &[F],
        scores: &mut [F],
        shares_next: &mut [F],
        partials: &mut [Partial<F>],
    ) -> Result<bool> {
        let nonfinite = AtomicBool::new(false);
        let tasks: Vec<_> = scores
            .chunks_mut(self.chunk)
            .zip(shares_next.chunks_mut(self.chunk))
            .zip(partials.chunks_mut(self.chunk / REDUCTION_CHUNK_LEN))
            .enumerate()
            .map(|(index, ((scores, shares), partials))| {
                (index * self.chunk, scores, shares, partials)
            })
            .collect();
        crate::parallel::for_each_owned(
            self.workers,
            tasks,
            |_, (first, scores, shares_next, partials)| {
                let mut meter = self.context.work_meter();
                let blocks = scores
                    .chunks_mut(REDUCTION_CHUNK_LEN)
                    .zip(shares_next.chunks_mut(REDUCTION_CHUNK_LEN));
                debug_assert_eq!(blocks.len(), partials.len());
                for (block, ((scores, shares_next), partial)) in
                    blocks.zip(partials.iter_mut()).enumerate()
                {
                    let first = first + block * REDUCTION_CHUNK_LEN;
                    let mut residual = 0.0f64;
                    let mut dangling = F::ZERO;
                    for (index, (score, share)) in
                        scores.iter_mut().zip(shares_next.iter_mut()).enumerate()
                    {
                        let node = first + index;
                        let arcs = self.reverse.range(node);
                        meter.charge(1 + arcs.len())?;
                        let mut sum = F::ZERO;
                        for arc in arcs {
                            sum += shares_now[self.reverse.targets.values[arc]];
                        }
                        let updated = teleport.at(node) + self.damping * sum;
                        if !updated.is_finite() {
                            nonfinite.store(true, Ordering::Relaxed);
                        }
                        // The residual is `f64` at either precision, from the
                        // score differences formed at the scores' own.
                        residual += (updated - *score).abs().to_f64();
                        *score = updated;
                        let out_degree = self.offsets[node + 1] - self.offsets[node];
                        if out_degree == 0 {
                            dangling += updated;
                            *share = F::ZERO;
                        } else {
                            *share = updated / (F::from_f64(out_degree as f64) + self.damp);
                        }
                    }
                    *partial = Partial { residual, dangling };
                }
                Ok(())
            },
        )?;
        Ok(!nonfinite.load(Ordering::Relaxed))
    }

    /// One weighted iteration. Reads `scores_now`, writes `next` and one
    /// partial per fixed chunk. Returns whether every updated score is finite.
    fn weighted(
        &self,
        teleport: &Teleport<'_, F>,
        scores_now: &[F],
        next: &mut [F],
        partials: &mut [Partial<F>],
    ) -> Result<bool> {
        let nonfinite = AtomicBool::new(false);
        let tasks: Vec<_> = next
            .chunks_mut(self.chunk)
            .zip(partials.chunks_mut(self.chunk / REDUCTION_CHUNK_LEN))
            .enumerate()
            .map(|(index, (next, partials))| (index * self.chunk, next, partials))
            .collect();
        crate::parallel::for_each_owned(self.workers, tasks, |_, (first, next, partials)| {
            let mut meter = self.context.work_meter();
            let blocks = next.chunks_mut(REDUCTION_CHUNK_LEN);
            debug_assert_eq!(blocks.len(), partials.len());
            for (block, (next, partial)) in blocks.zip(partials.iter_mut()).enumerate() {
                let first = first + block * REDUCTION_CHUNK_LEN;
                let mut residual = 0.0f64;
                let mut dangling = F::ZERO;
                for (index, value) in next.iter_mut().enumerate() {
                    let node = first + index;
                    let arcs = self.reverse.range(node);
                    meter.charge(1 + arcs.len())?;
                    let mut sum = F::ZERO;
                    for arc in arcs {
                        sum +=
                            scores_now[self.reverse.targets.values[arc]] * self.probabilities[arc];
                    }
                    let updated = teleport.at(node) + self.damping * sum;
                    if !updated.is_finite() {
                        nonfinite.store(true, Ordering::Relaxed);
                    }
                    residual += (updated - scores_now[node]).abs().to_f64();
                    if self.totals[node] <= F::ZERO {
                        dangling += updated;
                    }
                    *value = updated;
                }
                *partial = Partial { residual, dangling };
            }
            Ok(())
        })?;
        Ok(!nonfinite.load(Ordering::Relaxed))
    }
}
