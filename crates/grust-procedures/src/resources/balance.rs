//! A work meter's balance, padded so that no other balance, and none of the
//! small chunks the allocator recycles, shares its cache line.
//!
//! Each [`super::WorkMeter`] spends its admitted block from one shared
//! `AtomicUsize`, exchanged once per visited entry by the worker that owns the
//! meter and reset, rarely, by a meter that has run out. As a bare
//! `Arc<AtomicUsize>` that word was a 32-byte heap chunk, and glibc's tcache
//! handed it out beside whatever the same size class had just freed: since the
//! projection build went parallel (`db00ee7`), that is the pool's own
//! bookkeeping, which other cores keep writing. Every such write took the line
//! from the worker, and its next `lock cmpxchg` had to fetch it back; at
//! sixteen workers the pull-arc loop of PageRank on a path spent more than
//! half its cycles there, 2.5 times slower than 0.22.0. Disabling tcache with
//! the same code recovered it, which settled that mechanism.
//!
//! The word is followed by 56 bytes of padding, so the struct is a whole line
//! and two balances can never share one, and it leaves the 32-byte class
//! altogether. It is not over-aligned: the `#[repr(align(64))]` form, whose
//! `Arc` takes the aligned allocation path, measured slower on triangles at
//! sixteen workers, and this form did not. Padding on both sides, which puts
//! the whole line inside the allocation wherever it lands, was also measured
//! and rejected: it recovered PageRank equally but left sequential WCC 10%
//! slower than 0.22.0, exactly as the unpadded word did, while this shape and
//! every other chunk size tried brought it within 1–2%. What the one-worker
//! case responds to is therefore the balance's chunk size class, not its line,
//! and that mechanism is unexplained. Nothing about what is counted or when a
//! budget refuses depends on this layout.

use std::sync::atomic::AtomicUsize;

/// The line size this layout is sized for. Every x86-64 core and most
/// AArch64 cores use 64-byte lines; hosts with 128-byte lines (Apple silicon)
/// may still pair two balances, which is no worse than before.
const CACHE_LINE: usize = 64;

/// Bytes after the word that fill the rest of a line.
const PAD: usize = CACHE_LINE - size_of::<AtomicUsize>();

/// One meter's admitted, unspent units, padded to a whole cache line.
///
/// `repr(C)` keeps the word first and the padding after it, as measured;
/// under the default representation the compiler may reorder fields.
#[repr(C)]
#[derive(Debug)]
pub(super) struct MeterBalance {
    pub(super) units: AtomicUsize,
    _pad: [u8; PAD],
}

impl MeterBalance {
    /// An empty balance.
    pub(super) fn new() -> Self {
        Self {
            units: AtomicUsize::new(0),
            _pad: [0; PAD],
        }
    }
}

/// The layout the module comment promises, checked when the crate is built:
/// the word leads, the struct is exactly one line, and it is not over-aligned.
const _: () = {
    assert!(std::mem::offset_of!(MeterBalance, units) == 0);
    assert!(size_of::<MeterBalance>() == CACHE_LINE);
    assert!(align_of::<MeterBalance>() == align_of::<AtomicUsize>());
};

#[cfg(test)]
mod tests {
    use std::collections::HashSet;
    use std::sync::Arc;

    use super::{CACHE_LINE, MeterBalance};
    use crate::resources::{Accounting, ExecutionContext, ExecutionLimits, WorkMeter};

    /// The index of the cache line holding `balance.units`.
    fn line_of(balance: &MeterBalance) -> usize {
        std::ptr::from_ref(&balance.units) as usize / CACHE_LINE
    }

    #[test]
    fn the_balance_is_one_line_with_the_word_first_and_not_over_aligned() {
        assert_eq!(size_of::<MeterBalance>(), 64);
        assert_eq!(std::mem::offset_of!(MeterBalance, units), 0);
        assert_eq!(align_of::<MeterBalance>(), align_of::<usize>());
    }

    #[test]
    fn consecutively_allocated_balances_never_share_a_line() {
        // Allocated back to back and kept alive together, as a kernel's
        // meters are. A whole line per balance is what makes two of them
        // unable to share one, wherever the allocator puts them.
        let balances: Vec<Arc<MeterBalance>> =
            (0..64).map(|_| Arc::new(MeterBalance::new())).collect();
        let lines: HashSet<usize> = balances.iter().map(|balance| line_of(balance)).collect();
        assert_eq!(
            lines.len(),
            balances.len(),
            "two balances share a cache line"
        );
    }

    #[test]
    fn a_kernels_meters_each_own_their_line() {
        // Through the public path: a counted execution hands out meters whose
        // balances are registered, as a parallel region creates them, one per
        // worker chunk, and they must not share lines with one another.
        let context = ExecutionContext::with_accounting(
            ExecutionLimits {
                memory_bytes: usize::MAX,
                work_units: usize::MAX,
                batch_rows: 1,
                deadline: None,
            },
            Accounting::COUNTED,
        )
        .expect("valid limits");
        let meters: Vec<WorkMeter> = (0..32).map(|_| context.work_meter()).collect();
        let lines: HashSet<usize> = meters.iter().map(|meter| line_of(&meter.balance)).collect();
        assert_eq!(lines.len(), meters.len(), "two meters share a cache line");
    }
}
