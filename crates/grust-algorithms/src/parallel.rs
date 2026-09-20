//! Where kernels get their threads, and the rules they keep when they use them.
//!
//! Four properties hold for every parallel kernel in this crate.
//!
//! **The threads are the execution's, never the machine's.** How many threads a
//! query may add is [`ExecutionContext::concurrency`], which an embedder sets
//! per execution and which defaults to none at all; [`workers`] reports it, and
//! an execution that asked for nothing runs the sequential code. Nothing here
//! reads the CPU count, because these kernels also run inside a server that
//! owns its own runtime and thread pool.
//!
//! **Partitions follow the work for disjoint writes, and are fixed for
//! reductions.** A pass whose tasks write their own output slots, or merge into
//! shared atomics, may cut its work by the worker count, and should: see
//! [`balanced_ranges`] and [`chunk_len`]. A pass whose results are summed may
//! not, because regrouping the terms of a float sum changes its low bits.
//! Those use a fixed chunk, through [`map_chunks`], [`for_chunks`] or
//! [`ordered_blocks`].
//!
//! **Results are combined in index order, never in completion order**, so a
//! kernel's answer is bit-for-bit the same at one worker and at sixteen, and
//! identifiers and orderings a kernel emits come from node rows rather than
//! from worker identity.
//!
//! **The sequential path stays.** Below a measured floor a kernel runs its
//! sequential code, because a pool costs more than it saves on small inputs,
//! and without the `parallel` feature only that code is compiled. It is also
//! the differential oracle the parallel paths are tested against.
//!
//! The two halves of this module came from two branches that grew in parallel:
//! the range and block helpers from the analytics catalog, the execution-bound
//! worker count, pool and work meters from the rayon branch. [`width`] is the
//! catalog's original source of the worker count, kept only until its kernels
//! move onto [`workers`]; it reads the ambient rayon pool, which is exactly what
//! an embedded server must not do.

use grust_procedures::{ExecutionContext, Result};


/// Work units below which kernels stay sequential.
///
/// Measured on quegee (Xeon Platinum 8124M, 8 physical cores and 16 threads)
/// with `examples/scaling`, on prefixes of roadNet-CA at 20,000 to 500,000
/// edges. PageRank and components were already faster in parallel at the
/// smallest size measured (4.4x and 4.3x at 20,000 edges), because their
/// parallel forms are better algorithms as well as threaded ones, so the
/// crossover for them is below the smallest graph worth measuring. This
/// constant sits just under that size: small enough not to withhold a win,
/// large enough that a graph of a few thousand edges never pays for a pool.
///
/// Breadth-first search is the exception and does not use this constant alone:
/// on a high-diameter graph its levels are tiny, and at these sizes the
/// parallel expansion was 0.16x to 0.94x of sequential. It decides level by
/// level instead, on the size of the frontier it is about to expand.
pub(crate) const SEQUENTIAL_BELOW_UNITS: usize = 1 << 14;

/// Work units below which breadth-first search stays sequential.
///
/// Measured on roadNet-CA prefixes: at 20,000 edges the parallel expansion ran
/// at 0.78x of the sequential queue even with every level expanded in place,
/// because claiming a node with a compare-exchange costs more than testing a
/// distance when nothing contends. It reached 1.37x at 200,000 edges and 2.7x on
/// the whole graph, so the crossover is a few hundred thousand units; this sits
/// at the conservative end of that range.
pub(crate) const BREADTH_FIRST_SEQUENTIAL_BELOW_UNITS: usize = 1 << 18;

/// Frontier size below which one breadth-first level expands sequentially.
///
/// Measured on the same runs: on roadNet-CA, whose levels hold hundreds of
/// nodes, whole-kernel parallelism lost until the graph reached millions of
/// edges, while on com-Orkut, whose frontiers reach millions, it gained 7.8x.
/// Deciding per level keeps both: a small frontier costs nothing to expand in
/// place, and a large one is worth spreading.
pub(crate) const SEQUENTIAL_FRONTIER_BELOW: usize = 2048;

/// Worker count for this execution, or `None` when the kernel should run its
/// sequential path: too little work, no concurrency asked for, or a build
/// without the `parallel` feature.
///
/// An execution that explicitly asks for one worker gets `Some(1)`, which runs
/// the parallel implementation on one thread. That distinction is what lets the
/// scaling benchmark separate a change of algorithm from the cost of threads.
pub(crate) fn workers(context: &ExecutionContext, units: usize) -> Option<usize> {
    workers_above(context, units, SEQUENTIAL_BELOW_UNITS)
}

/// As [`workers`], for a kernel whose own crossover is higher than the shared
/// one. Breadth-first search is the one such kernel today.
pub(crate) fn workers_above(
    context: &ExecutionContext,
    units: usize,
    minimum: usize,
) -> Option<usize> {
    if units < minimum {
        return None;
    }
    #[cfg(feature = "parallel")]
    {
        context.concurrency_requested()
    }
    #[cfg(not(feature = "parallel"))]
    {
        let _ = context;
        None
    }
}

/// Number of items per chunk so that `workers` threads each get a few chunks,
/// which keeps a skewed workload balanced without making chunks so small that
/// the per-chunk work meter dominates.
pub(crate) fn chunk_len(items: usize, workers: usize) -> usize {
    if workers <= 1 {
        return items.max(1);
    }
    items.div_ceil(workers.saturating_mul(4)).max(1024)
}

/// Combine per-chunk results in chunk order, so the combination is independent
/// of the order in which the chunks finished.
pub(crate) fn reduce_in_order<T: Copy, R>(
    parts: &[T],
    initial: R,
    mut fold: impl FnMut(R, T) -> R,
) -> R {
    let mut accumulated = initial;
    for part in parts {
        accumulated = fold(accumulated, *part);
    }
    accumulated
}

/// Run `body` over `items` split into chunks, in parallel when `workers > 1`.
///
/// `body` receives the chunk's starting index, its own mutable output slice and
/// a work meter of its own. Output slices are disjoint, so no kernel needs a
/// lock or an atomic to write its results.
#[cfg(feature = "parallel")]
pub(crate) fn for_each_chunk<T: Send>(
    context: &ExecutionContext,
    workers: usize,
    output: &mut [T],
    body: impl Fn(usize, &mut [T], &mut grust_procedures::WorkMeter) -> crate::Result<()> + Send + Sync,
) -> crate::Result<()> {
    let chunk = chunk_len(output.len(), workers);
    if workers <= 1 {
        let mut meter = context.work_meter();
        for (index, slice) in output.chunks_mut(chunk).enumerate() {
            body(index * chunk, slice, &mut meter)?;
        }
        return Ok(());
    }
    use rayon::prelude::*;
    pool(workers)?.install(|| {
        output
            .par_chunks_mut(chunk)
            .enumerate()
            .try_for_each(|(index, slice)| {
                let mut meter = context.work_meter();
                body(index * chunk, slice, &mut meter)
            })
    })
}

/// The sequential form, compiled when the `parallel` feature is off.
#[cfg(not(feature = "parallel"))]
pub(crate) fn for_each_chunk<T>(
    context: &ExecutionContext,
    workers: usize,
    output: &mut [T],
    body: impl Fn(usize, &mut [T], &mut grust_procedures::WorkMeter) -> crate::Result<()>,
) -> crate::Result<()> {
    let _ = workers;
    let chunk = chunk_len(output.len(), 1);
    let mut meter = context.work_meter();
    for (index, slice) in output.chunks_mut(chunk).enumerate() {
        body(index * chunk, slice, &mut meter)?;
    }
    Ok(())
}

/// Map each chunk of `items` to one value, in parallel when `workers > 1`, and
/// return the values in chunk order for an ordered reduction.
#[cfg(feature = "parallel")]
pub(crate) fn map_chunks<T: Send + Sync, R: Send>(
    context: &ExecutionContext,
    workers: usize,
    items: &[T],
    body: impl Fn(usize, &[T], &mut grust_procedures::WorkMeter) -> crate::Result<R> + Send + Sync,
) -> crate::Result<Vec<R>> {
    let chunk = chunk_len(items.len(), workers);
    if workers <= 1 {
        let mut meter = context.work_meter();
        return items
            .chunks(chunk)
            .enumerate()
            .map(|(index, slice)| body(index * chunk, slice, &mut meter))
            .collect();
    }
    use rayon::prelude::*;
    pool(workers)?.install(|| {
        items
            .par_chunks(chunk)
            .enumerate()
            .map(|(index, slice)| {
                let mut meter = context.work_meter();
                body(index * chunk, slice, &mut meter)
            })
            .collect()
    })
}

#[cfg(not(feature = "parallel"))]
pub(crate) fn map_chunks<T, R>(
    context: &ExecutionContext,
    workers: usize,
    items: &[T],
    body: impl Fn(usize, &[T], &mut grust_procedures::WorkMeter) -> crate::Result<R>,
) -> crate::Result<Vec<R>> {
    let _ = workers;
    let chunk = chunk_len(items.len(), 1);
    let mut meter = context.work_meter();
    items
        .chunks(chunk)
        .enumerate()
        .map(|(index, slice)| body(index * chunk, slice, &mut meter))
        .collect()
}

/// One pool per worker count, built on first use and reused afterwards.
///
/// A pool per kernel call would pay thread creation on every query; a pool
/// sized to the machine would ignore the execution's limit. Keying the cache by
/// worker count gives each distinct limit its own bounded pool, shared by every
/// query that asks for that many threads.
#[cfg(feature = "parallel")]
fn pool(workers: usize) -> crate::Result<std::sync::Arc<rayon::ThreadPool>> {
    use std::collections::HashMap;
    use std::sync::{Arc, Mutex, OnceLock};

    use grust_procedures::ProcedureError;

    static POOLS: OnceLock<Mutex<HashMap<usize, Arc<rayon::ThreadPool>>>> = OnceLock::new();
    let pools = POOLS.get_or_init(|| Mutex::new(HashMap::new()));
    let mut pools = pools
        .lock()
        .map_err(|_| ProcedureError::ResourceStatePoisoned)?;
    if let Some(pool) = pools.get(&workers) {
        return Ok(Arc::clone(pool));
    }
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(workers)
        .thread_name(|index| format!("grust-algorithms-{index}"))
        .build()
        .map_err(|error| ProcedureError::Provider(Box::new(error)))?;
    let pool = Arc::new(pool);
    pools.insert(workers, Arc::clone(&pool));
    Ok(pool)
}


/// Tasks the caller's pool can run at once; 1 without the `parallel` feature.
pub(crate) fn width() -> usize {
    #[cfg(feature = "parallel")]
    {
        rayon::current_num_threads().max(1)
    }
    #[cfg(not(feature = "parallel"))]
    {
        1
    }
}

/// Split `0..weights.len()` into at most `parts` contiguous ranges of roughly
/// equal total weight. Every node lands in exactly one range, in order.
pub(crate) fn balanced_ranges(weights: &[usize], parts: usize) -> Vec<std::ops::Range<usize>> {
    let n = weights.len();
    if n == 0 {
        return Vec::new();
    }
    let parts = parts.clamp(1, n);
    let total: u128 = weights.iter().map(|&w| w as u128 + 1).sum();
    let mut ranges = Vec::with_capacity(parts);
    let mut start = 0;
    let mut seen: u128 = 0;
    for (node, &weight) in weights.iter().enumerate() {
        seen += weight as u128 + 1;
        let filled = ranges.len() as u128 + 1;
        if seen * parts as u128 >= total * filled && ranges.len() + 1 < parts {
            ranges.push(start..node + 1);
            start = node + 1;
        }
    }
    ranges.push(start..n);
    ranges.retain(|range| !range.is_empty());
    ranges
}

/// Run `task` on every range and return the results in range order.
pub(crate) fn map_ranges<T: Send>(
    ranges: &[std::ops::Range<usize>],
    task: impl Fn(std::ops::Range<usize>) -> Result<T> + Sync,
) -> Result<Vec<T>> {
    #[cfg(feature = "parallel")]
    {
        use rayon::prelude::*;
        ranges
            .par_iter()
            .map(|range| task(range.clone()))
            .collect::<Result<Vec<T>>>()
    }
    #[cfg(not(feature = "parallel"))]
    {
        ranges.iter().map(|range| task(range.clone())).collect()
    }
}

/// Run `task(block)` for `0..blocks` and hand each result to `merge` **in block
/// order**. Blocks run `width()` at a time, so at most that many results are
/// alive at once; which blocks exist, what each computes and the order they are
/// merged in do not depend on the pool, so neither does a floating-point sum
/// built by `merge`.
pub(crate) fn ordered_blocks<T: Send>(
    blocks: usize,
    task: impl Fn(usize) -> Result<T> + Sync,
    mut merge: impl FnMut(usize, T) -> Result<()>,
) -> Result<()> {
    let wave = width();
    let mut first = 0;
    while first < blocks {
        let last = (first + wave).min(blocks);
        let indices: Vec<usize> = (first..last).collect();
        #[cfg(feature = "parallel")]
        let results = {
            use rayon::prelude::*;
            indices
                .par_iter()
                .map(|&block| task(block))
                .collect::<Result<Vec<T>>>()?
        };
        #[cfg(not(feature = "parallel"))]
        let results = indices
            .iter()
            .map(|&block| task(block))
            .collect::<Result<Vec<T>>>()?;
        for (block, result) in indices.into_iter().zip(results) {
            merge(block, result)?;
        }
        first = last;
    }
    Ok(())
}

/// Run `task(first_index, chunk)` over fixed-size chunks of `values` and return
/// the results in chunk order. Chunks are cut by `size` alone, so a reduction
/// the caller folds over the returned vector groups its terms the same way at
/// any pool width.
pub(crate) fn for_chunks<T: Send, R: Send>(
    values: &mut [T],
    size: usize,
    task: impl Fn(usize, &mut [T]) -> Result<R> + Sync,
) -> Result<Vec<R>> {
    #[cfg(feature = "parallel")]
    {
        use rayon::prelude::*;
        values
            .par_chunks_mut(size)
            .enumerate()
            .map(|(index, chunk)| task(index * size, chunk))
            .collect()
    }
    #[cfg(not(feature = "parallel"))]
    values
        .chunks_mut(size)
        .enumerate()
        .map(|(index, chunk)| task(index * size, chunk))
        .collect()
}

/// Sort by a **total** order. The result is then the same whatever the pool
/// does, so the parallel sort is safe to use where a result must not vary.
pub(crate) fn sort_total<T: Send>(
    values: &mut [T],
    order: impl Fn(&T, &T) -> std::cmp::Ordering + Sync,
) {
    #[cfg(feature = "parallel")]
    {
        use rayon::prelude::*;
        values.par_sort_unstable_by(order);
    }
    #[cfg(not(feature = "parallel"))]
    values.sort_unstable_by(order);
}

#[cfg(test)]
mod tests {
    use super::balanced_ranges;

    #[test]
    fn ranges_cover_every_node_once_in_order_and_balance_weight() {
        for parts in 1..9 {
            for weights in [
                vec![],
                vec![0],
                vec![5, 0, 0, 0, 5],
                vec![1; 17],
                vec![100, 1, 1, 1],
            ] {
                let ranges = balanced_ranges(&weights, parts);
                let covered: Vec<usize> = ranges.iter().flat_map(|r| r.clone()).collect();
                assert_eq!(covered, (0..weights.len()).collect::<Vec<_>>());
                assert!(ranges.len() <= parts.max(1));
            }
        }
        // A heavy head does not drag the light tail into its block.
        assert_eq!(balanced_ranges(&[100, 1, 1, 1], 2), vec![0..1, 1..4]);
    }
}
