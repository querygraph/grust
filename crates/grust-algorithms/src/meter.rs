//! Work accounting in blocks. A kernel's inner loop does a few nanoseconds of
//! work per arc; admitting each arc separately costs more than the arc. A meter
//! counts locally and admits at most every 1024 units, so budgets, cancellation
//! and deadlines are still observed promptly and totals stay exact.

use grust_procedures::{ExecutionContext, Result};

const BLOCK: usize = 1024;

pub(crate) struct Meter<'a> {
    context: &'a ExecutionContext,
    pending: usize,
}

impl<'a> Meter<'a> {
    pub(crate) fn new(context: &'a ExecutionContext) -> Self {
        Self {
            context,
            pending: 0,
        }
    }

    /// Count `units` of work, admitting a block once enough has accumulated.
    #[inline]
    pub(crate) fn tick(&mut self, units: usize) -> Result<()> {
        self.pending += units;
        if self.pending >= BLOCK {
            self.flush()?;
        }
        Ok(())
    }

    /// Admit whatever is still counted. Call before returning a result: work
    /// left unadmitted would make a budget look larger than it is.
    pub(crate) fn flush(&mut self) -> Result<()> {
        if self.pending > 0 {
            self.context
                .charge_work(std::mem::take(&mut self.pending))?;
        }
        Ok(())
    }
}
