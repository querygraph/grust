//! Runtime-independent notification. Registration and cancellation share one
//! lock, preventing missed wakeups. Each future owns one reusable waiter slot;
//! dropping it unregisters. Wake/drop callbacks run after releasing the lock.
use super::ExecutionContext;
use crate::{ProcedureError, Result};
use std::{
    future::Future,
    pin::Pin,
    task::{Context, Poll},
};

/// Wait for explicit cancellation of an execution, without charging resources.
/// This notification does not install a deadline timer. Runtime adapters must
/// race the context's absolute deadline separately and continue checkpointing.
pub struct Cancellation {
    execution: ExecutionContext,
    slot: Option<usize>,
}

impl ExecutionContext {
    /// Subscribe to explicit cancellation. Multiple tasks can wait independently;
    /// a previously cancelled context completes immediately on the first poll.
    pub fn cancelled(&self) -> Cancellation {
        Cancellation {
            execution: self.clone(),
            slot: None,
        }
    }
}

impl Future for Cancellation {
    type Output = Result<()>;

    fn poll(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Self::Output> {
        let this = self.get_mut();
        let replacement = cx.waker().clone();
        let mut state = match this.execution.0.state.lock() {
            Ok(state) => state,
            Err(_) => return Poll::Ready(Err(ProcedureError::ResourceStatePoisoned)),
        };
        if this.execution.0.cancelled.load(std::sync::atomic::Ordering::Acquire) {
            return Poll::Ready(Ok(()));
        }
        let slot = *this.slot.get_or_insert_with(|| {
            if let Some(slot) = state.waiters.iter().position(Option::is_none) {
                slot
            } else {
                state.waiters.push(None);
                state.waiters.len() - 1
            }
        });
        let previous = state.waiters[slot].replace(replacement);
        drop(state);
        drop(previous);
        Poll::Pending
    }
}

impl Drop for Cancellation {
    fn drop(&mut self) {
        let Some(slot) = self.slot else { return };
        let mut state = self
            .execution
            .0
            .state
            .lock()
            .unwrap_or_else(|poison| poison.into_inner());
        let previous = state.waiters.get_mut(slot).and_then(Option::take);
        while state.waiters.last().is_some_and(Option::is_none) {
            state.waiters.pop();
        }
        drop(state);
        drop(previous);
    }
}
