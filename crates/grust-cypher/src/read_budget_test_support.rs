use super::*;

/// Exercise execution-phase checkpoints without sleeps or scheduler races.
pub(crate) fn expire_deadline_for_test() {
    BUDGETS.with(|budgets| {
        let mut budgets = budgets.borrow_mut();
        let budget = budgets
            .last_mut()
            .expect("deadline expiry requires an active test budget");
        budget.limits.deadline = Instant::now();
        // Expiry is observed on a sampled tick; make the next tick a read.
        budget.ticks_since_deadline_read.set(0);
    });
}
