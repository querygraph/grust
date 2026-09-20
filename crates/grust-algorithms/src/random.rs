//! A counter-based generator: every draw is a pure function of
//! `(seed, stream, counter)`, so a parallel schedule cannot change a result and
//! no generator state is shared. SplitMix64's finalizer over a mixed key.

#[inline]
fn mix(mut z: u64) -> u64 {
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

/// The `counter`-th 64-bit draw of `stream` under `seed`.
#[inline]
pub(crate) fn draw(seed: u64, stream: u64, counter: u64) -> u64 {
    mix(mix(seed ^ 0x9E37_79B9_7F4A_7C15).wrapping_add(mix(stream)) ^ mix(counter.wrapping_add(1)))
}

/// A uniform index below `bound` (which must be positive), by Lemire's
/// multiply-shift; the bias is below 2^-64 * bound and irrelevant here.
#[inline]
pub(crate) fn below(seed: u64, stream: u64, counter: u64, bound: usize) -> usize {
    ((u128::from(draw(seed, stream, counter)) * bound as u128) >> 64) as usize
}

/// Fisher–Yates over `values`, reproducible from `(seed, stream)`.
pub(crate) fn shuffle(values: &mut [usize], seed: u64, stream: u64) {
    for index in (1..values.len()).rev() {
        values.swap(index, below(seed, stream, index as u64, index + 1));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn draws_are_pure_well_spread_and_in_range() {
        assert_eq!(draw(7, 1, 42), draw(7, 1, 42));
        assert_ne!(draw(7, 1, 42), draw(7, 1, 43));
        assert_ne!(draw(7, 1, 42), draw(7, 2, 42));
        assert_ne!(draw(7, 1, 42), draw(8, 1, 42));
        let mut buckets = [0usize; 8];
        for counter in 0..80_000 {
            let value = below(3, 0, counter, 8);
            assert!(value < 8);
            buckets[value] += 1;
        }
        assert!(
            buckets
                .iter()
                .all(|&count| (9_500..10_500).contains(&count)),
            "{buckets:?}"
        );
    }

    #[test]
    fn shuffles_are_permutations_and_reproducible() {
        let mut a: Vec<usize> = (0..100).collect();
        let mut b = a.clone();
        shuffle(&mut a, 11, 0);
        shuffle(&mut b, 11, 0);
        assert_eq!(a, b);
        assert_ne!(a, (0..100).collect::<Vec<_>>());
        let mut sorted = a.clone();
        sorted.sort_unstable();
        assert_eq!(sorted, (0..100).collect::<Vec<_>>());
        let mut c: Vec<usize> = (0..100).collect();
        shuffle(&mut c, 12, 0);
        assert_ne!(a, c);
    }
}
