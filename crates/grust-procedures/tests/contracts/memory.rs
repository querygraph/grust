//! Memory accounting without a lock: admission stays exact under contention,
//! releases return everything, and the peak is a true high-water mark.

use std::sync::atomic::{AtomicUsize, Ordering};

use super::*;

const WORKERS: usize = 16;

fn limits(memory_bytes: usize) -> ExecutionLimits {
    ExecutionLimits {
        memory_bytes,
        work_units: usize::MAX,
        batch_rows: 8,
        deadline: None,
    }
}

#[test]
fn concurrent_reservations_never_admit_more_than_the_limit() {
    const CHUNK: usize = 1000;
    const FITS: usize = 50;
    for _ in 0..50 {
        let execution = ExecutionContext::new(limits(FITS * CHUNK + CHUNK / 2)).expect("limits");
        let admitted = AtomicUsize::new(0);
        let refused = AtomicUsize::new(0);
        let start = std::sync::Barrier::new(WORKERS);
        let held = std::sync::Mutex::new(Vec::new());
        std::thread::scope(|scope| {
            for _ in 0..WORKERS {
                scope.spawn(|| {
                    start.wait();
                    for _ in 0..FITS {
                        match execution.reserve(CHUNK) {
                            Ok(reservation) => {
                                admitted.fetch_add(1, Ordering::Relaxed);
                                held.lock().expect("held").push(reservation);
                            }
                            Err(ProcedureError::BudgetExceeded {
                                resource: "memory", ..
                            }) => {
                                refused.fetch_add(1, Ordering::Relaxed);
                            }
                            Err(other) => panic!("unexpected failure: {other}"),
                        }
                    }
                });
            }
        });
        // Every chunk that fits is admitted, not one more, whatever the race.
        assert_eq!(admitted.load(Ordering::Relaxed), FITS);
        assert_eq!(refused.load(Ordering::Relaxed), WORKERS * FITS - FITS);
        let usage = execution.usage().expect("usage");
        assert_eq!(usage.live_bytes, FITS * CHUNK);
        assert_eq!(usage.peak_bytes, FITS * CHUNK);
        drop(held);
        let usage = execution.usage().expect("usage");
        assert_eq!(usage.live_bytes, 0, "every release came back");
        assert_eq!(usage.peak_bytes, FITS * CHUNK, "the peak does not fall");
    }
}

#[test]
fn accounts_and_reservations_dropped_on_many_threads_return_to_zero() {
    let execution = ExecutionContext::new(limits(usize::MAX)).expect("limits");
    std::thread::scope(|scope| {
        for worker in 0..WORKERS {
            let execution = execution.clone();
            scope.spawn(move || {
                for round in 0..2000 {
                    let mut account = execution.memory_account();
                    account.charge(1 + (worker + round) % 97).expect("charge");
                    let reservation = execution.reserve(64).expect("reserve");
                    account.charge(3).expect("charge");
                    drop(reservation);
                }
            });
        }
    });
    let usage = execution.usage().expect("usage");
    assert_eq!(usage.live_bytes, 0);
    assert!(usage.peak_bytes >= 64 + 4 && usage.peak_bytes <= WORKERS * (64 + 97 + 3));
}

#[test]
fn the_peak_is_the_true_maximum_of_a_sequence_and_never_below_live() {
    let execution = ExecutionContext::new(limits(10_000)).expect("limits");
    let first = execution.reserve(4000).expect("first");
    let second = execution.reserve(5000).expect("second");
    assert_eq!(execution.usage().expect("usage").peak_bytes, 9000);
    drop(first);
    let usage = execution.usage().expect("usage");
    assert_eq!((usage.live_bytes, usage.peak_bytes), (5000, 9000));
    // A refused charge moves neither figure.
    assert!(execution.reserve(6000).is_err());
    assert!(execution.check_memory_available(5001).is_err());
    assert!(execution.check_memory_available(5000).is_ok());
    let usage = execution.usage().expect("usage");
    assert_eq!((usage.live_bytes, usage.peak_bytes), (5000, 9000));
    let third = execution.reserve(5000).expect("exactly fits");
    assert_eq!(execution.usage().expect("usage").peak_bytes, 10_000);
    drop((second, third));
    assert_eq!(execution.usage().expect("usage").live_bytes, 0);

    // A reader racing charges always sees a peak at or above the live figure.
    let execution = ExecutionContext::new(limits(usize::MAX)).expect("limits");
    let done = std::sync::atomic::AtomicBool::new(false);
    std::thread::scope(|scope| {
        scope.spawn(|| {
            for round in 0..200_000usize {
                let _held = execution.reserve(1 + round % 4096).expect("reserve");
            }
            done.store(true, Ordering::Release);
        });
        while !done.load(Ordering::Acquire) {
            let usage = execution.usage().expect("usage");
            assert!(usage.peak_bytes >= usage.live_bytes);
        }
    });
}

#[test]
fn overflowing_the_counter_is_a_budget_failure_not_a_wrap() {
    let execution = ExecutionContext::new(limits(usize::MAX)).expect("limits");
    let _held = execution.reserve(usize::MAX - 10).expect("fits");
    assert!(matches!(
        execution.reserve(11),
        Err(ProcedureError::BudgetExceeded {
            resource: "memory",
            ..
        })
    ));
    assert!(execution.reserve(10).is_ok());
}
