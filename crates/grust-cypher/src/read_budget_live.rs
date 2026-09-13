//! Lexical accounting for intermediate values consumed before a callback returns.

use super::*;
use grust_procedures::MemoryAccount;

thread_local! {
    static COPIES: RefCell<Vec<MemoryAccount>> = const { RefCell::new(Vec::new()) };
}

struct CopyGuard;
impl Drop for CopyGuard {
    fn drop(&mut self) {
        COPIES.with(|copies| {
            copies.borrow_mut().pop();
        });
    }
}

/// The closure must consume or drop all allocated intermediate values before
/// returning. Retained output must obtain a separate owning reservation.
pub(crate) fn with_live_intermediates<T>(
    execution: &ExecutionContext,
    run: impl FnOnce() -> Result<T>,
) -> Result<T> {
    COPIES.with(|copies| copies.borrow_mut().push(execution.memory_account()));
    let _guard = CopyGuard;
    run()
}

pub(super) fn charge(bytes: usize, context: &str) -> Option<Result<()>> {
    COPIES.with(|copies| {
        copies.borrow_mut().last_mut().map(|account| {
            account.charge(bytes).map_err(|error| {
                gql_execution(format!(
                    "read live intermediate bytes ({error}) while {context}"
                ))
            })
        })
    })
}

pub(super) fn available(bytes: usize, context: &str) -> Option<Result<()>> {
    COPIES.with(|copies| {
        copies.borrow().last().map(|account| {
            account
                .execution()
                .check_memory_available(bytes)
                .map_err(|error| {
                    gql_execution(format!(
                        "read live intermediate bytes ({error}) while {context}"
                    ))
                })
        })
    })
}

pub(super) fn work(units: usize, context: &str) -> Option<Result<()>> {
    COPIES.with(|copies| {
        copies.borrow().last().map(|account| {
            account.execution().charge_work(units).map_err(|error| {
                gql_execution(format!(
                    "bounded read candidate-work units ({error}) while {context}"
                ))
            })
        })
    })
}

pub(super) fn active() -> bool {
    COPIES.with(|copies| !copies.borrow().is_empty())
}
