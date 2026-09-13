use super::*;

/// Exercise execution-phase checkpoints without sleeps or scheduler races.
pub(crate) fn expire_deadline_for_test() {
    BUDGETS.with(|budgets| {
        budgets
            .borrow_mut()
            .last_mut()
            .expect("deadline expiry requires an active test budget")
            .limits
            .deadline = Instant::now();
    });
}
