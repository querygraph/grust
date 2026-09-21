//! The accounting opt-outs: what each one gives up, and that it gives up
//! nothing else.
//!
//! Work counting and interruption are separate switches. Disabling work
//! counting must leave cancellation, the deadline and memory admission exactly
//! as they were; disabling interruption must leave memory admission and, if
//! work is still counted, the work budget. A limit a mode could not enforce is
//! refused at construction, so no context can look bounded and not be.

use std::future::Future;
use std::pin::pin;
use std::task::{Context, Poll, Waker};
use std::time::{Duration, Instant};

use super::*;

fn limits(work_units: usize, deadline: Option<Instant>) -> ExecutionLimits {
    ExecutionLimits {
        memory_bytes: 1 << 20,
        work_units,
        batch_rows: 8,
        deadline,
    }
}

fn unbounded() -> ExecutionLimits {
    limits(usize::MAX, None)
}

fn is_invalid(error: ProcedureError) -> bool {
    matches!(error, ProcedureError::InvalidArguments(_))
}

#[test]
fn the_default_counts_work_and_an_unlimited_budget_does_not_opt_out() {
    // `usize::MAX` means "no budget", not "no accounting".
    let execution = ExecutionContext::new(unbounded()).expect("valid");
    assert_eq!(execution.accounting(), Accounting::COUNTED);
    assert_eq!(Accounting::default(), Accounting::COUNTED);
    execution.charge_work(7).expect("admitted");
    let mut meter = execution.work_meter();
    meter.charge(5).expect("admitted");
    meter.finish();
    let usage = execution.usage().expect("usage");
    assert_eq!(usage.work_units, WorkCount::Counted(12));
    assert_eq!(usage.counted_work(), Some(12));
    assert_eq!(usage.accounting, Accounting::COUNTED);
}

#[test]
fn uncounted_work_reports_not_counted_rather_than_zero() {
    let execution =
        ExecutionContext::with_accounting(unbounded(), Accounting::WORK_UNCOUNTED).expect("valid");
    execution.charge_work(1_000).expect("uncounted");
    let mut meter = execution.work_meter();
    for _ in 0..10_000 {
        meter.charge(3).expect("uncounted");
    }
    meter.finish();
    let usage = execution.usage().expect("usage");
    assert_eq!(usage.work_units, WorkCount::NotCounted);
    assert_ne!(usage.work_units, WorkCount::Counted(0));
    assert_eq!(usage.counted_work(), None);
    assert_eq!(usage.accounting, Accounting::WORK_UNCOUNTED);
    assert_eq!(usage.work_units.to_string(), "not counted");
    // A counted execution that did nothing is a real zero, and says so.
    let idle = ExecutionContext::new(unbounded()).expect("valid");
    assert_eq!(
        idle.usage().expect("usage").work_units,
        WorkCount::Counted(0)
    );
    assert_eq!(WorkCount::Counted(0).to_string(), "0");
}

#[test]
fn a_work_budget_with_uncounted_work_is_refused_at_construction() {
    for work_units in [0, 1, 1_000, usize::MAX - 1] {
        for accounting in [Accounting::WORK_UNCOUNTED, Accounting::UNCHECKED] {
            let error = ExecutionContext::with_accounting(limits(work_units, None), accounting)
                .expect_err("a budget nobody counts against cannot be enforced");
            assert!(is_invalid(error), "{work_units} under {accounting}");
        }
    }
}

#[test]
fn a_deadline_with_interruption_disabled_is_refused_at_construction() {
    let deadline = Some(Instant::now() + Duration::from_secs(3600));
    let uninterruptible = Accounting {
        work: WorkAccounting::Counted,
        interruption: Interruption::Disabled,
    };
    for accounting in [Accounting::UNCHECKED, uninterruptible] {
        let error = ExecutionContext::with_accounting(limits(usize::MAX, deadline), accounting)
            .expect_err("a deadline nobody reads cannot be enforced");
        assert!(is_invalid(error), "{accounting}");
    }
    // Uncounted work still observes the deadline, so the pair is accepted.
    ExecutionContext::with_accounting(limits(usize::MAX, deadline), Accounting::WORK_UNCOUNTED)
        .expect("deadline is still enforced when only work is uncounted");
}

#[test]
fn uncounted_work_still_observes_cancellation_at_every_charge_point() {
    let execution =
        ExecutionContext::with_accounting(unbounded(), Accounting::WORK_UNCOUNTED).expect("valid");
    let mut meter = execution.work_meter();
    meter.charge(1).expect("before cancellation");
    execution.charge_work(1).expect("before cancellation");
    execution.cancel().expect("cancellation is accepted");
    assert!(matches!(meter.charge(1), Err(ProcedureError::Cancelled)));
    assert!(matches!(
        execution.charge_work(1),
        Err(ProcedureError::Cancelled)
    ));
    assert!(matches!(
        execution.checkpoint(),
        Err(ProcedureError::Cancelled)
    ));
    assert!(matches!(
        execution.reserve(1),
        Err(ProcedureError::Cancelled)
    ));
    // A fresh meter created after cancellation sees it on its first charge.
    assert!(matches!(
        execution.work_meter().charge(1),
        Err(ProcedureError::Cancelled)
    ));
    let waiter = pin!(execution.cancelled());
    assert!(matches!(poll_once(waiter), Poll::Ready(Ok(()))));
}

#[test]
fn uncounted_work_still_observes_an_expired_deadline_on_both_charge_paths() {
    let expired = Some(Instant::now() - Duration::from_millis(1));
    let execution =
        ExecutionContext::with_accounting(limits(usize::MAX, expired), Accounting::WORK_UNCOUNTED)
            .expect("valid");
    assert!(matches!(
        execution.checkpoint(),
        Err(ProcedureError::DeadlineExceeded)
    ));
    // The context path samples the deadline once per 1024 charges, and reads it
    // on the first.
    assert!(matches!(
        execution.charge_work(1),
        Err(ProcedureError::DeadlineExceeded)
    ));
}

/// Units a fresh meter charges one at a time before it reports the deadline.
fn units_until_expiry(accounting: Accounting) -> usize {
    let expired = Some(Instant::now() - Duration::from_millis(1));
    let execution =
        ExecutionContext::with_accounting(limits(usize::MAX, expired), accounting).expect("valid");
    let mut meter = execution.work_meter();
    for charged in 0..(1 << 24) {
        match meter.charge(1) {
            Ok(()) => {}
            Err(ProcedureError::DeadlineExceeded) => return charged,
            Err(other) => panic!("unexpected failure: {other}"),
        }
    }
    panic!("{accounting}: no deadline observed in {} units", 1 << 24);
}

#[test]
fn an_uncounted_meter_samples_the_deadline_at_the_counted_cadence() {
    // A counted meter samples the deadline when it admits a block, which its
    // first charge does. An uncounted meter admits nothing, so it samples from
    // its own tally at each block's worth of units. Without that tally it would
    // never read the deadline at all; with it, it stops within one block of
    // where a counted meter would.
    let counted = units_until_expiry(Accounting::COUNTED);
    let uncounted = units_until_expiry(Accounting::WORK_UNCOUNTED);
    assert!(
        uncounted.abs_diff(counted) <= WORK_BLOCK_UNITS,
        "counted stopped after {counted} units, uncounted after {uncounted}"
    );
}

#[test]
fn an_expiring_deadline_stops_every_uncounted_worker() {
    const WORKERS: usize = 16;
    let execution = ExecutionContext::with_accounting(
        limits(usize::MAX, Some(Instant::now() + Duration::from_millis(50))),
        Accounting::WORK_UNCOUNTED,
    )
    .expect("valid");
    let expired = std::sync::atomic::AtomicUsize::new(0);
    std::thread::scope(|scope| {
        for _ in 0..WORKERS {
            let execution = execution.clone();
            let expired = &expired;
            scope.spawn(move || {
                let mut meter = execution.work_meter();
                loop {
                    match meter.charge(1) {
                        Ok(()) => continue,
                        Err(ProcedureError::DeadlineExceeded) => {
                            expired.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                            return;
                        }
                        Err(other) => panic!("unexpected failure: {other}"),
                    }
                }
            });
        }
    });
    assert_eq!(expired.into_inner(), WORKERS);
}

#[test]
fn unchecked_execution_refuses_cancellation_instead_of_ignoring_it() {
    let execution =
        ExecutionContext::with_accounting(unbounded(), Accounting::UNCHECKED).expect("valid");
    assert!(matches!(
        execution.cancel(),
        Err(ProcedureError::Unsupported(_))
    ));
    // Nothing was signalled, so nothing reports cancellation.
    execution.checkpoint().expect("no interruption observed");
    execution.charge_work(1).expect("no interruption observed");
    execution
        .work_meter()
        .charge(1)
        .expect("no interruption observed");
    // A waiter is told at once that it would wait forever.
    let waiter = pin!(execution.cancelled());
    assert!(matches!(
        poll_once(waiter),
        Poll::Ready(Err(ProcedureError::Unsupported(_)))
    ));
    let usage = execution.usage().expect("usage");
    assert_eq!(usage.work_units, WorkCount::NotCounted);
    assert_eq!(usage.accounting.label(), "unchecked");
}

#[test]
fn memory_admission_is_enforced_in_every_mode() {
    let uninterruptible = Accounting {
        work: WorkAccounting::Counted,
        interruption: Interruption::Disabled,
    };
    for accounting in [
        Accounting::COUNTED,
        Accounting::WORK_UNCOUNTED,
        uninterruptible,
        Accounting::UNCHECKED,
    ] {
        let execution = ExecutionContext::with_accounting(unbounded(), accounting).expect("valid");
        let held = execution.reserve(1 << 19).expect("fits");
        let refused = execution.reserve((1 << 19) + 1);
        assert!(
            matches!(
                refused,
                Err(ProcedureError::BudgetExceeded {
                    resource: "memory",
                    ..
                })
            ),
            "{accounting}"
        );
        let mut account = execution.memory_account();
        account.charge(1 << 19).expect("fits exactly");
        assert!(account.charge(1).is_err(), "{accounting}");
        assert!(
            execution.charge_cumulative_memory(1).is_err(),
            "{accounting}"
        );
        let usage = execution.usage().expect("usage");
        assert_eq!(usage.live_bytes, 1 << 20, "{accounting}");
        assert_eq!(usage.peak_bytes, 1 << 20, "{accounting}");
        drop((held, account));
        assert_eq!(execution.usage().expect("usage").live_bytes, 0);
    }
}

#[test]
fn an_uninterruptible_execution_still_enforces_its_work_budget_exactly() {
    // The switches are independent: giving up interruption keeps the budget.
    let uninterruptible = Accounting {
        work: WorkAccounting::Counted,
        interruption: Interruption::Disabled,
    };
    let execution =
        ExecutionContext::with_accounting(limits(10_000, None), uninterruptible).expect("valid");
    let mut meter = execution.work_meter();
    for _ in 0..10_000 {
        meter.charge(1).expect("inside the budget");
    }
    assert!(matches!(
        meter.charge(1),
        Err(ProcedureError::BudgetExceeded {
            resource: "work",
            limit: 10_000
        })
    ));
    meter.finish();
    assert_eq!(
        execution.usage().expect("usage").work_units,
        WorkCount::Counted(10_000)
    );
    assert_eq!(uninterruptible.label(), "uninterruptible");
}

#[test]
fn every_mode_has_a_distinct_stable_label() {
    let labels = [
        Accounting::COUNTED,
        Accounting::WORK_UNCOUNTED,
        Accounting {
            work: WorkAccounting::Counted,
            interruption: Interruption::Disabled,
        },
        Accounting::UNCHECKED,
    ]
    .map(|accounting| accounting.to_string());
    assert_eq!(
        labels,
        ["counted", "work-uncounted", "uninterruptible", "unchecked"]
    );
}

fn poll_once<F: Future>(future: std::pin::Pin<&mut F>) -> Poll<F::Output> {
    future.poll(&mut Context::from_waker(Waker::noop()))
}
