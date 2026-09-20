//! Where kernels get their threads, and the rules they keep when they use them.
//!
//! Three properties hold for every parallel kernel in this crate.
//!
//! **The pool is bounded by the execution, never by the machine.** An embedder
//! may be running these kernels inside a server that already owns a runtime and
//! a thread pool of its own, so the number of threads a query may add is
//! what the execution asked for, and an execution that asked for nothing runs
//! the sequential code. Nothing here reads the CPU count.
//!
//! **Results do not depend on thread count or scheduling.** Reductions combine
//! partial results in index order (see [`map_chunks`] and [`reduce_in_order`]),
//! never in completion order, so a sum is bit-for-bit the same at one thread and
//! at sixteen. Identifiers and orderings that a kernel emits are derived from
//! node rows, not from worker identity.
//!
//! **The sequential path stays.** Below [`SEQUENTIAL_BELOW_UNITS`] of work a
//! kernel runs its sequential code, because a pool costs more than it saves on
//! small inputs, and without the `parallel` feature only the sequential code is
//! compiled at all. That path is also the differential oracle in tests.
use grust_procedures::ExecutionContext;

/// Work units below which kernels stay sequential.
///
/// Provisional: this is a starting value, to be replaced by the crossover the
/// scaling benchmark measures on a machine with real cores. Until that number
/// exists, the constant is deliberately high, so small inputs keep today's
/// behavior rather than paying for a pool that may not earn it.
pub(crate) const SEQUENTIAL_BELOW_UNITS: usize = 1 << 18;

/// Worker count for this execution, or `None` when the kernel should run its
/// sequential path: too little work, no concurrency asked for, or a build
/// without the `parallel` feature.
///
/// An execution that explicitly asks for one worker gets `Some(1)`, which runs
/// the parallel implementation on one thread. That distinction is what lets the
/// scaling benchmark separate a change of algorithm from the cost of threads.
pub(crate) fn workers(context: &ExecutionContext, units: usize) -> Option<usize> {
    if units < SEQUENTIAL_BELOW_UNITS {
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
