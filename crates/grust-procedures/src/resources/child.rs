//! Child executions: one memory budget shared by many independently stopped,
//! budgeted and deadlined executions.
//!
//! An embedder serving concurrent queries needs one memory budget for the
//! process, so that N queries cannot together exceed the machine, and needs
//! each query to be cancellable, budgeted and deadlined on its own. A root
//! [`ExecutionContext`] is the process budget; each query runs on a child of
//! it. What the child shares with its parent and what it keeps for itself:
//!
//! | | child |
//! |---|---|
//! | memory | admitted against the child's sub-limit, if it set one, *and* every ancestor's budget, atomically; see `ExecutionContext::admit_memory` |
//! | work | its own counter, meters and budget; the parent neither counts nor bounds it |
//! | cancellation | its own; cancelling the parent cancels it, cancelling it reaches nothing above |
//! | deadline | its own, never later than the parent's |
//! | accounting mode | its own, except that a child of an interruptible execution must be interruptible |
//! | batch rows, concurrency | the parent's unless the child sets its own |

use std::sync::Arc;
use std::sync::atomic::Ordering;
use std::time::Instant;

use super::{Accounting, ExecutionContext, ExecutionLimits, Shared, validate};
use crate::{ProcedureError, Result};

/// What a child execution sets for itself. Everything left as `None` is
/// inherited from the parent. See [`ExecutionContext::child`].
#[derive(Clone, Copy, Debug)]
pub struct ChildLimits {
    /// A memory ceiling of the child's own, enforced in addition to its
    /// parent's budget and never larger than the parent's limit. `None` bounds
    /// the child by its ancestors' budgets alone, and costs less per charge.
    pub memory_bytes: Option<usize>,
    /// The child's own cumulative work budget, counted on its own counter.
    /// Must be `usize::MAX` when `accounting` does not count work.
    pub work_units: usize,
    /// The child's own deadline. The parent's deadline, if earlier, applies as
    /// well: a child never outlives the execution it belongs to.
    pub deadline: Option<Instant>,
    /// The checks the child performs. Independent of the parent's, except that
    /// a child of an execution that observes interruption must observe it too.
    pub accounting: Accounting,
    /// Maximum rows in one provider batch; the parent's when `None`.
    pub batch_rows: Option<usize>,
    /// Threads kernels may use; the parent's request when `None`. A child is
    /// shared with its parent from birth, so this cannot be set afterwards with
    /// [`ExecutionContext::with_concurrency`].
    pub concurrency: Option<usize>,
}

impl Default for ChildLimits {
    /// No memory sub-limit, no work budget (still counted), no deadline of the
    /// child's own, and the parent's batch size and concurrency.
    fn default() -> Self {
        Self {
            memory_bytes: None,
            work_units: usize::MAX,
            deadline: None,
            accounting: Accounting::COUNTED,
            batch_rows: None,
            concurrency: None,
        }
    }
}

impl ExecutionContext {
    /// A child execution that draws memory from this one's budget and keeps
    /// its own work counter, work budget, cancellation and deadline.
    ///
    /// Every byte the child admits is admitted by this execution too, and by
    /// its ancestors, in one decision: concurrent children cannot jointly
    /// exceed the parent, and a charge the parent refuses is not counted in the
    /// child. Bytes return to every level when their reservation or account
    /// drops; bytes the child charged cumulatively return to the parent when
    /// the child itself drops. [`Self::usage`] reports each level's own live
    /// and peak figures, a parent's including its children's.
    ///
    /// Work is not shared: the child counts on its own counter, so concurrent
    /// children never contend on one, and the parent's usage and work budget
    /// cover only the work charged to the parent itself. Aggregating children's
    /// work into the parent exactly would mean charging the parent's counter
    /// too, which is the contention this exists to remove.
    ///
    /// Cancelling the parent cancels the child, including a child created
    /// after the parent was cancelled, which starts cancelled. Cancelling the
    /// child reaches neither its parent nor its siblings.
    ///
    /// # Errors
    /// Rejects a memory sub-limit larger than the parent's limit, a child that
    /// would not observe interruption under a parent that does (cancelling the
    /// parent could not reach it), zero batch rows or concurrency, and any
    /// limit [`Self::with_accounting`] would refuse for the child's mode.
    pub fn child(&self, limits: ChildLimits) -> Result<ExecutionContext> {
        let parent = self.0.limits;
        if let Some(bytes) = limits.memory_bytes
            && bytes > parent.memory_bytes
        {
            return Err(ProcedureError::InvalidArguments(format!(
                "a child's memory limit of {bytes} bytes exceeds its parent's {}; the parent's \
                 budget bounds the child, so a larger limit could never be reached",
                parent.memory_bytes
            )));
        }
        if self.0.accounting.observes_interruption() && !limits.accounting.observes_interruption() {
            return Err(ProcedureError::InvalidArguments(
                "a child of an interruptible execution must observe interruption; otherwise \
                 cancelling the parent, or its deadline, could not stop the child"
                    .into(),
            ));
        }
        if limits.concurrency == Some(0) {
            return Err(ProcedureError::InvalidArguments(
                "concurrency must be at least one".into(),
            ));
        }
        let deadline = match (limits.deadline, parent.deadline) {
            (Some(own), Some(inherited)) => Some(own.min(inherited)),
            (own, inherited) => own.or(inherited),
        };
        let child_limits = ExecutionLimits {
            memory_bytes: limits.memory_bytes.unwrap_or(parent.memory_bytes),
            work_units: limits.work_units,
            batch_rows: limits.batch_rows.unwrap_or(parent.batch_rows),
            deadline,
        };
        validate(&child_limits, limits.accounting)?;
        let child = Arc::new(Shared::new(
            child_limits,
            limits.accounting,
            limits.concurrency.or(self.0.concurrency),
            Some((self.clone(), limits.memory_bytes.is_some())),
        ));
        if self.0.accounting.observes_interruption() {
            // Registered and checked under the lock `cancel` collects children
            // under, after it has published its flag: either `cancel` finds
            // this child, or this finds the flag.
            let mut state = self
                .0
                .state
                .lock()
                .map_err(|_| ProcedureError::ResourceStatePoisoned)?;
            if self.0.cancelled.load(Ordering::Acquire) {
                child.cancelled.store(true, Ordering::Release);
            } else {
                state.children.push(Arc::downgrade(&child));
            }
        }
        Ok(ExecutionContext(child))
    }

    /// The execution this one is a child of, or `None` for a root.
    pub fn parent(&self) -> Option<&ExecutionContext> {
        self.0.parent.as_ref()
    }

    /// Whether this is `ancestor` itself, a handle to it, or one of its
    /// descendants. Handles are compared by identity: two executions built
    /// with equal limits are still two executions.
    ///
    /// Such an execution admits every byte against `ancestor`'s budget as well
    /// as its own, is cancelled when `ancestor` is, and never outlives
    /// `ancestor`'s deadline.
    pub fn is_within(&self, ancestor: &ExecutionContext) -> bool {
        let mut current = Some(self);
        while let Some(context) = current {
            if Arc::ptr_eq(&context.0, &ancestor.0) {
                return true;
            }
            current = context.parent();
        }
        false
    }
}

impl Drop for Shared {
    /// A child returns to its parent what it still holds when its last handle
    /// drops. Every reservation and account holds a handle, so by now they
    /// have all released theirs, and what remains is the child's cumulative
    /// charges, which lasted as long as the child did.
    fn drop(&mut self) {
        let Some(parent) = self.parent.take() else {
            return;
        };
        parent.release_memory(*self.live_bytes.get_mut());
        if parent.0.accounting.observes_interruption() {
            // This child's own entry no longer upgrades; drop it, and any other
            // child's that has gone the same way.
            let mut state = parent
                .0
                .state
                .lock()
                .unwrap_or_else(|poison| poison.into_inner());
            state.children.retain(|child| child.strong_count() > 0);
        }
    }
}
