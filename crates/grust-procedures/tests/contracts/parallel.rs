//! The budget contracts at more than one thread. The single-threaded versions
//! live in `failures.rs`; these assert that batching the work counter across
//! workers keeps them: a budget that fits succeeds, a budget one unit short
//! fails, cancellation reaches every worker, and an expired deadline stops the
//! region. Each test uses plain threads, so the accounting layer stays free of
//! a runtime or a thread pool.

use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::{Duration, Instant};

use super::*;

const WORKERS: usize = 16;
const PER_WORKER: usize = 10_000;

fn limits(work_units: usize, deadline: Option<Instant>) -> ExecutionLimits {
    ExecutionLimits {
        memory_bytes: 1 << 20,
        work_units,
        batch_rows: 8,
        deadline,
    }
}

/// Charge `per_worker` units on each of `WORKERS` threads, returning how many
/// workers failed and the usage the context reports afterwards.
fn charge_everywhere(execution: &ExecutionContext, per_worker: usize) -> (usize, ResourceUsage) {
    let failures = Arc::new(AtomicUsize::new(0));
    std::thread::scope(|scope| {
        for _ in 0..WORKERS {
            let execution = execution.clone();
            let failures = Arc::clone(&failures);
            scope.spawn(move || {
                let mut meter = execution.work_meter();
                for _ in 0..per_worker {
                    if meter.charge(1).is_err() {
                        failures.fetch_add(1, Ordering::Relaxed);
                        return;
                    }
                }
            });
        }
    });
    (
        failures.load(Ordering::Relaxed),
        execution.usage().expect("usage"),
    )
}

#[test]
fn a_budget_that_exactly_fits_succeeds_and_counts_the_work_performed() {
    let total = WORKERS * PER_WORKER;
    let execution = ExecutionContext::new(limits(total, None)).expect("valid limits");
    let (failures, usage) = charge_everywhere(&execution, PER_WORKER);
    assert_eq!(failures, 0, "no worker may fail inside its budget");
    // Unspent blocks are returned when each meter drops, so the final count is
    // the work actually charged, not the blocks admitted to charge it.
    assert_eq!(usage.counted_work().expect("counted"), total);
}

#[test]
fn a_budget_one_unit_short_fails_at_one_worker() {
    let total = WORKERS * PER_WORKER;
    let execution = ExecutionContext::new(limits(total - 1, None)).expect("valid limits");
    let (failures, usage) = charge_everywhere(&execution, PER_WORKER);
    assert_eq!(failures, 1, "exactly the worker that ran out should fail");
    assert!(
        usage.counted_work().expect("counted") < total,
        "spent {} of a {} unit budget",
        usage.counted_work().expect("counted"),
        total - 1
    );
}

#[test]
fn every_worker_observes_cancellation() {
    let execution = ExecutionContext::new(limits(usize::MAX, None)).expect("valid limits");
    let started = Arc::new(AtomicUsize::new(0));
    let cancelled = Arc::new(AtomicUsize::new(0));
    std::thread::scope(|scope| {
        for _ in 0..WORKERS {
            let execution = execution.clone();
            let started = Arc::clone(&started);
            let cancelled = Arc::clone(&cancelled);
            scope.spawn(move || {
                let mut meter = execution.work_meter();
                started.fetch_add(1, Ordering::Relaxed);
                loop {
                    match meter.charge(1) {
                        Ok(()) => continue,
                        Err(ProcedureError::Cancelled) => {
                            cancelled.fetch_add(1, Ordering::Relaxed);
                            return;
                        }
                        Err(other) => panic!("unexpected failure: {other}"),
                    }
                }
            });
        }
        while started.load(Ordering::Relaxed) < WORKERS {
            std::hint::spin_loop();
        }
        execution.cancel().expect("cancel");
    });
    assert_eq!(cancelled.load(Ordering::Relaxed), WORKERS);
}

#[test]
fn an_expired_deadline_stops_every_worker() {
    let execution = ExecutionContext::new(limits(
        usize::MAX,
        Some(Instant::now() + Duration::from_millis(50)),
    ))
    .expect("valid limits");
    let expired = Arc::new(AtomicUsize::new(0));
    std::thread::scope(|scope| {
        for _ in 0..WORKERS {
            let execution = execution.clone();
            let expired = Arc::clone(&expired);
            scope.spawn(move || {
                let mut meter = execution.work_meter();
                loop {
                    match meter.charge(1) {
                        Ok(()) => continue,
                        Err(ProcedureError::DeadlineExceeded) => {
                            expired.fetch_add(1, Ordering::Relaxed);
                            return;
                        }
                        Err(other) => panic!("unexpected failure: {other}"),
                    }
                }
            });
        }
    });
    assert_eq!(expired.load(Ordering::Relaxed), WORKERS);
}

#[test]
fn a_dropped_meter_returns_what_it_did_not_spend() {
    let execution =
        ExecutionContext::new(limits(WORK_BLOCK_UNITS * 4, None)).expect("valid limits");
    {
        let mut meter = execution.work_meter();
        meter.charge(1).expect("first charge admits a block");
        assert!(
            execution
                .usage()
                .expect("usage")
                .counted_work()
                .expect("counted")
                > 1,
            "a live meter holds more than it has spent"
        );
    }
    assert_eq!(
        execution
            .usage()
            .expect("usage")
            .counted_work()
            .expect("counted"),
        1,
        "dropping the meter leaves only the work performed"
    );
    // The whole budget remains spendable afterwards, one meter at a time.
    for _ in 0..4 {
        let mut meter = execution.work_meter();
        for _ in 0..WORK_BLOCK_UNITS / 2 {
            meter.charge(1).expect("within budget");
        }
    }
    assert_eq!(
        execution
            .usage()
            .expect("usage")
            .counted_work()
            .expect("counted"),
        1 + 4 * (WORK_BLOCK_UNITS / 2)
    );
}

#[test]
fn per_worker_scratch_is_admitted_before_the_region() {
    let execution = ExecutionContext::new(limits(64, None)).expect("valid limits");
    let scratch = execution
        .reserve_for_workers(WORKERS, 1024)
        .expect("fits the memory budget");
    assert_eq!(scratch.bytes(), WORKERS * 1024);
    assert!(
        execution.reserve_for_workers(WORKERS, usize::MAX).is_err(),
        "an overflowing total is a budget failure, not a wrap"
    );
    assert!(
        execution.reserve_for_workers(1 << 20, 1 << 20).is_err(),
        "a total beyond the memory budget is refused"
    );
}

#[test]
fn concurrency_is_one_unless_set_and_cannot_change_once_shared() {
    let execution = ExecutionContext::new(limits(8, None)).expect("valid limits");
    assert_eq!(execution.concurrency(), 1);
    let execution = execution.with_concurrency(8).expect("not yet shared");
    assert_eq!(execution.concurrency(), 8);
    assert!(execution.clone().with_concurrency(2).is_err());
    assert!(
        ExecutionContext::new(limits(8, None))
            .expect("valid limits")
            .with_concurrency(0)
            .is_err()
    );
}

// --- Review reproductions (catalog agent, 2026-09-20). Both fail at 8d7fb95. ---

/// Two meters driven from one thread, so there is no race to blame. One meter
/// charges a single unit and then sits on the rest of its block; the other must
/// still be able to spend what the budget has left. Whether work fits a budget
/// must not depend on how many meters exist.
#[test]
fn an_idle_meters_unspent_block_does_not_refuse_work_that_fits() {
    const BUDGET: usize = 1500;
    let execution = ExecutionContext::new(limits(BUDGET, None)).expect("valid limits");
    let mut idle = execution.work_meter();
    let mut busy = execution.work_meter();
    idle.charge(1).expect("first unit");
    for unit in 2..=BUDGET {
        busy.charge(1).unwrap_or_else(|error| {
            panic!(
                "refused unit {unit} of a {BUDGET}-unit budget after {} units of work: {error}",
                unit - 1
            )
        });
    }
    assert!(
        busy.charge(1).is_err(),
        "unit {} exceeds the budget",
        BUDGET + 1
    );
}

/// The same at sixteen threads with skewed work: one worker does nine tenths of
/// it while the others finish early but keep their meters alive, as workers do
/// inside a parallel region until it ends.
#[test]
fn skewed_work_that_exactly_fits_succeeds_at_sixteen_threads() {
    let light = 100;
    let heavy = 9 * (WORKERS - 1) * light;
    let total = heavy + (WORKERS - 1) * light;
    let execution = ExecutionContext::new(limits(total, None)).expect("valid limits");
    let failures = AtomicUsize::new(0);
    let finished = std::sync::Barrier::new(WORKERS);
    std::thread::scope(|scope| {
        for worker in 0..WORKERS {
            let (execution, failures, finished) = (execution.clone(), &failures, &finished);
            scope.spawn(move || {
                let mut meter = execution.work_meter();
                let units = if worker == 0 { heavy } else { light };
                for _ in 0..units {
                    if meter.charge(1).is_err() {
                        failures.fetch_add(1, Ordering::Relaxed);
                        break;
                    }
                }
                // Hold the meter until every worker is done, like a region does.
                finished.wait();
            });
        }
    });
    assert_eq!(
        failures.load(Ordering::Relaxed),
        0,
        "the work fits the budget"
    );
    assert_eq!(
        execution
            .usage()
            .expect("usage")
            .counted_work()
            .expect("counted"),
        total
    );
}

/// A block is invisible for a moment, after it reaches the shared counter and
/// before it reaches its meter's balance. A meter refused in that moment must
/// not give up on work that fits, so a refusal is decided with the registry held
/// exclusively and a block is admitted with it held shared. This provokes the
/// moment: many meters, all running out at once, against a budget equal to the
/// work. With retries in place of exclusion this failed in most runs on a
/// ten-core host and in none on a sixteen-thread one, so run it where it bites.
#[test]
fn many_meters_racing_for_the_last_of_a_budget_that_exactly_fits() {
    const ROUNDS: usize = 200;
    const PER_WORKER: usize = 4 * WORK_BLOCK_UNITS;
    let mut refusals = 0;
    for _ in 0..ROUNDS {
        let total = WORKERS * PER_WORKER;
        let execution = ExecutionContext::new(limits(total, None)).expect("valid limits");
        let failures = AtomicUsize::new(0);
        let start = std::sync::Barrier::new(WORKERS);
        std::thread::scope(|scope| {
            for _ in 0..WORKERS {
                let (execution, failures, start) = (execution.clone(), &failures, &start);
                scope.spawn(move || {
                    let mut meter = execution.work_meter();
                    // Charge at the same moment, so admissions collide.
                    start.wait();
                    for _ in 0..PER_WORKER {
                        if meter.charge(1).is_err() {
                            failures.fetch_add(1, Ordering::Relaxed);
                            return;
                        }
                    }
                });
            }
        });
        let failed = failures.load(Ordering::Relaxed);
        refusals += failed;
        if failed == 0 {
            assert_eq!(
                execution
                    .usage()
                    .expect("usage")
                    .counted_work()
                    .expect("counted"),
                total,
                "usage should account for exactly the work performed"
            );
        }
    }
    assert_eq!(
        refusals, 0,
        "{refusals} refusals of work that fits, over {ROUNDS} rounds of {WORKERS} racing meters"
    );
}

/// A dropping meter hands back its unspent block. If that hand-back is not
/// covered by the registry, the block is for a moment in no balance and not yet
/// refunded, and a meter refused in that moment cannot find it. So: fifteen
/// threads create, charge and drop meters continuously while one thread spends
/// down a budget equal to all the work.
#[test]
fn a_meter_dropping_its_block_does_not_hide_it_from_a_refusal() {
    const DROPS: usize = 300;
    const BUSY: usize = 8 * WORK_BLOCK_UNITS;
    let mut refusals = 0;
    for _ in 0..40 {
        let total = BUSY + (WORKERS - 1) * DROPS;
        let execution = ExecutionContext::new(limits(total, None)).expect("valid limits");
        let failures = AtomicUsize::new(0);
        let start = std::sync::Barrier::new(WORKERS);
        std::thread::scope(|scope| {
            for worker in 0..WORKERS {
                let (execution, failures, start) = (execution.clone(), &failures, &start);
                scope.spawn(move || {
                    start.wait();
                    if worker == 0 {
                        let mut meter = execution.work_meter();
                        for _ in 0..BUSY {
                            if meter.charge(1).is_err() {
                                failures.fetch_add(1, Ordering::Relaxed);
                                return;
                            }
                        }
                    } else {
                        for _ in 0..DROPS {
                            // One unit of work, then a block goes back on drop.
                            if execution.work_meter().charge(1).is_err() {
                                failures.fetch_add(1, Ordering::Relaxed);
                                return;
                            }
                        }
                    }
                });
            }
        });
        refusals += failures.load(Ordering::Relaxed);
        if failures.load(Ordering::Relaxed) == 0 {
            assert_eq!(
                execution
                    .usage()
                    .expect("usage")
                    .counted_work()
                    .expect("counted"),
                total
            );
        }
    }
    assert_eq!(refusals, 0, "{refusals} refusals of work that fits");
}
