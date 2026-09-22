//! Which cooperative checks an execution performs at its kernels' charge points.
//!
//! Every execution counts work and observes cancellation unless its caller
//! says otherwise, by name, at construction. Nothing here is inferred from
//! limits: `ExecutionLimits { work_units: usize::MAX, .. }` is "no budget, still
//! counted", and stays so. The opt-outs exist so that a comparison against a
//! library that performs no accounting can be run like-for-like, and so that
//! the result can say which mode ran.
//!
//! Memory admission is not switchable here. It is charged once per allocation,
//! not once per visited entry, and it is what stops a projection from taking
//! the machine down; an execution with every opt-out below still admits memory
//! before allocating it and still fails at its memory limit.

use std::fmt;

/// Whether an execution counts the work its kernels perform.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash)]
pub enum WorkAccounting {
    /// Every charge is admitted against the shared counter, the work budget is
    /// enforced exactly, and usage reports the cumulative total.
    #[default]
    Counted,
    /// Charges admit nothing and count nothing: the shared counter, the block
    /// grants of work meters and the budget comparison are all skipped, and
    /// usage reports [`WorkCount::NotCounted`]. Requires an unlimited work
    /// budget, because a budget nobody counts against cannot be enforced.
    Disabled,
}

/// Whether charge points and checkpoints observe cancellation and the deadline.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash)]
pub enum Interruption {
    /// Cancellation is observed at every charge and checkpoint; the deadline is
    /// sampled at charges and read exactly at checkpoints and reservations.
    #[default]
    Observed,
    /// No charge, checkpoint or reservation reads the cancellation flag or the
    /// clock. A running kernel cannot be stopped: [`crate::ExecutionContext::cancel`]
    /// is refused rather than accepted and ignored, and a deadline is refused at
    /// construction.
    Disabled,
}

/// The cooperative checks an execution performs, chosen once at construction
/// with [`crate::ExecutionContext::with_accounting`].
///
/// The two switches are independent because they give up different things.
/// Disabling work counting gives up a work budget and a work total; the
/// execution can still be cancelled and still times out. Disabling
/// interruption gives up the ability to stop a running kernel, which is the
/// larger trade and is never implied by the first.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash)]
pub struct Accounting {
    /// Whether work is counted and a work budget enforced.
    pub work: WorkAccounting,
    /// Whether cancellation and the deadline are observed.
    pub interruption: Interruption,
}

impl Accounting {
    /// The default: work counted, cancellation and the deadline observed.
    pub const COUNTED: Self = Self {
        work: WorkAccounting::Counted,
        interruption: Interruption::Observed,
    };

    /// Work is not counted; cancellation and the deadline are still observed.
    pub const WORK_UNCOUNTED: Self = Self {
        work: WorkAccounting::Disabled,
        interruption: Interruption::Observed,
    };

    /// Neither work nor interruption is checked inside kernels. Only memory
    /// admission remains. Nothing can stop a kernel once it starts.
    pub const UNCHECKED: Self = Self {
        work: WorkAccounting::Disabled,
        interruption: Interruption::Disabled,
    };

    /// Whether charges admit work against the shared counter.
    #[inline]
    pub const fn counts_work(self) -> bool {
        matches!(self.work, WorkAccounting::Counted)
    }

    /// Whether charges and checkpoints observe cancellation and the deadline.
    #[inline]
    pub const fn observes_interruption(self) -> bool {
        matches!(self.interruption, Interruption::Observed)
    }

    /// A stable name for this mode, for a benchmark row or a log line.
    pub const fn label(self) -> &'static str {
        match (self.work, self.interruption) {
            (WorkAccounting::Counted, Interruption::Observed) => "counted",
            (WorkAccounting::Disabled, Interruption::Observed) => "work-uncounted",
            (WorkAccounting::Counted, Interruption::Disabled) => "uninterruptible",
            (WorkAccounting::Disabled, Interruption::Disabled) => "unchecked",
        }
    }
}

impl fmt::Display for Accounting {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.label())
    }
}

/// Cumulative work as reported by [`crate::ExecutionContext::usage`].
///
/// `NotCounted` is not zero: it means the execution disabled work accounting,
/// so no total exists. A caller that wants a number must say what it does in
/// that case, which is the point.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum WorkCount {
    /// Work was counted; this is the cumulative admitted total.
    Counted(usize),
    /// The execution ran with [`WorkAccounting::Disabled`]; nothing was counted.
    NotCounted,
}

impl WorkCount {
    /// The counted total, or `None` when the execution did not count work.
    #[inline]
    pub const fn counted(self) -> Option<usize> {
        match self {
            Self::Counted(units) => Some(units),
            Self::NotCounted => None,
        }
    }
}

impl Default for WorkCount {
    fn default() -> Self {
        Self::Counted(0)
    }
}

impl fmt::Display for WorkCount {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Counted(units) => write!(formatter, "{units}"),
            Self::NotCounted => formatter.write_str("not counted"),
        }
    }
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::Ordering;

    use super::Accounting;
    use crate::{ExecutionContext, ExecutionLimits};

    fn unbounded(accounting: Accounting) -> ExecutionContext {
        ExecutionContext::with_accounting(
            ExecutionLimits {
                memory_bytes: 1 << 20,
                work_units: usize::MAX,
                batch_rows: 8,
                deadline: None,
            },
            accounting,
        )
        .expect("valid")
    }

    /// The opt-out is only worth having if the work is gone, not merely
    /// unbounded: no admission into the shared counter, no block grant, and no
    /// registration in the meter registry, whose lock a counted meter takes on
    /// creation and drop.
    #[test]
    fn uncounted_charges_touch_no_shared_work_state() {
        for accounting in [Accounting::WORK_UNCOUNTED, Accounting::UNCHECKED] {
            let execution = unbounded(accounting);
            execution.charge_work(5_000).expect("uncounted");
            let mut meters: Vec<_> = (0..4).map(|_| execution.work_meter()).collect();
            let registered = execution
                .0
                .grants
                .read()
                .unwrap_or_else(|poison| poison.into_inner())
                .len();
            assert_eq!(registered, 0, "{accounting}");
            for meter in &mut meters {
                for _ in 0..10 * super::super::WORK_BLOCK_UNITS {
                    meter.charge(1).expect("uncounted");
                }
                assert_eq!(
                    meter.balance.units.load(Ordering::Relaxed),
                    0,
                    "{accounting}"
                );
            }
            drop(meters);
            assert_eq!(
                execution.0.work_units.load(Ordering::Relaxed),
                0,
                "{accounting}"
            );
        }
        // The control: the same charges, counted, do reach the shared state.
        let execution = unbounded(Accounting::COUNTED);
        execution.charge_work(5_000).expect("counted");
        let mut meter = execution.work_meter();
        meter.charge(1).expect("counted");
        assert_eq!(
            execution
                .0
                .grants
                .read()
                .unwrap_or_else(|poison| poison.into_inner())
                .len(),
            1
        );
        drop(meter);
        assert_eq!(execution.0.work_units.load(Ordering::Relaxed), 5_001);
    }
}
