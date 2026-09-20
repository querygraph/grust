//! Deterministic fan-out. A kernel splits its nodes into contiguous blocks of
//! roughly equal work, runs one task per block on the caller's rayon pool, and
//! combines the block results **in block order**. The partition depends only on
//! the graph and the pool width, and every combination used with it is exact
//! (integer sums, per-node writes to disjoint slots), so the answer is the same
//! at any width. Without the `parallel` feature the blocks run in a plain loop.

use grust_procedures::Result;

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
