//! Child executions: memory drawn from the parent's budget, admitted at every
//! level in one decision; work, cancellation and deadline kept per child.
//!
//! The stress tests take their round count from `GRUST_CHILD_STRESS_ROUNDS`,
//! so a saturated-host run can repeat them far past the default.

use std::sync::Barrier;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::time::{Duration, Instant};

use super::*;

fn root(memory_bytes: usize) -> ExecutionContext {
    ExecutionContext::new(ExecutionLimits {
        memory_bytes,
        work_units: usize::MAX,
        batch_rows: 8,
        deadline: None,
    })
    .expect("valid limits")
}

fn rounds(default: usize) -> usize {
    std::env::var("GRUST_CHILD_STRESS_ROUNDS")
        .ok()
        .and_then(|rounds| rounds.parse().ok())
        .unwrap_or(default)
}

fn sub_limit(bytes: usize) -> ChildLimits {
    ChildLimits {
        memory_bytes: Some(bytes),
        ..ChildLimits::default()
    }
}

fn memory(context: &ExecutionContext) -> (usize, usize) {
    let usage = context.usage().expect("usage");
    (usage.live_bytes, usage.peak_bytes)
}

fn refused_at(result: Result<MemoryReservation>, limit: usize) -> bool {
    matches!(
        result,
        Err(ProcedureError::BudgetExceeded { resource: "memory", limit: at }) if at == limit
    )
}

#[test]
fn a_childs_memory_counts_against_its_parent_and_returns_when_released() {
    let parent = root(1000);
    let own = parent.reserve(100).expect("the parent's own");
    let child = parent.child(ChildLimits::default()).expect("child");
    assert_eq!(child.limits().memory_bytes, 1000, "the parent's budget");
    let reservation = child.reserve(300).expect("fits");
    let mut account = child.memory_account();
    account.charge(200).expect("fits");
    child.charge_cumulative_memory(50).expect("fits");
    assert_eq!(memory(&child), (550, 550));
    assert_eq!(memory(&parent), (650, 650));
    // The parent's remaining 350 is all the child can have.
    assert!(refused_at(child.reserve(351), 1000));
    assert_eq!(
        memory(&child),
        (550, 550),
        "a refused charge counts nowhere"
    );
    drop(reservation);
    drop(account);
    assert_eq!(memory(&child), (50, 550));
    assert_eq!(memory(&parent), (150, 650));
    // Cumulative charges last as long as the child, and no longer.
    drop(child);
    assert_eq!(memory(&parent), (100, 650));
    drop(own);
    assert_eq!(memory(&parent).0, 0);
}

#[test]
fn siblings_cannot_jointly_exceed_their_parent() {
    let parent = root(100);
    let first = parent.child(ChildLimits::default()).expect("child");
    let second = parent.child(ChildLimits::default()).expect("child");
    let held = first.reserve(60).expect("fits");
    assert!(refused_at(second.reserve(41), 100));
    let other = second.reserve(40).expect("exactly fits");
    assert_eq!(memory(&parent).0, 100);
    assert_eq!((memory(&first).0, memory(&second).0), (60, 40));
    drop(held);
    assert_eq!(memory(&parent).0, 40);
    drop(other);
    assert_eq!(memory(&parent).0, 0);
}

#[test]
fn a_sub_limit_binds_beside_the_parent_and_cannot_exceed_it() {
    let parent = root(1000);
    assert!(matches!(
        parent.child(sub_limit(1001)),
        Err(ProcedureError::InvalidArguments(_))
    ));
    let child = parent.child(sub_limit(300)).expect("child");
    assert_eq!(child.limits().memory_bytes, 300);
    let held = child.reserve(200).expect("fits");
    assert!(refused_at(child.reserve(101), 300), "the child's own limit");
    assert!(child.check_memory_available(100).is_ok());
    assert!(child.check_memory_available(101).is_err());
    // The parent binds when it has less room than the child's limit leaves.
    let others = parent.reserve(750).expect("fits");
    assert!(refused_at(child.reserve(51), 1000), "the parent's limit");
    assert!(child.check_memory_available(51).is_err());
    let last = child.reserve(50).expect("exactly fits both");
    assert_eq!(memory(&parent).0, 1000);
    assert_eq!(memory(&child), (250, 250));
    drop((held, last, others));
    assert_eq!(memory(&parent).0, 0);
    assert_eq!(memory(&child).0, 0);
    // A grandchild answers to every level above it.
    let grandchild = child.child(sub_limit(100)).expect("grandchild");
    assert!(matches!(
        child.child(sub_limit(301)),
        Err(ProcedureError::InvalidArguments(_))
    ));
    let deep = grandchild.reserve(100).expect("fits");
    assert_eq!(
        (memory(&grandchild).0, memory(&child).0, memory(&parent).0),
        (100, 100, 100)
    );
    let beside = child.reserve(200).expect("fits the child");
    assert!(refused_at(child.reserve(1), 300));
    drop((deep, beside));
    assert_eq!(memory(&parent).0, 0);
}

/// Refusals seen by [`press`], by the level that refused.
struct Pressure {
    admitted: usize,
    by_parent: usize,
    by_child: usize,
}

/// Admit and release on `threads_per_child` threads per child, checking every
/// level after each admission and from a monitor throughout.
///
/// Every thread keeps what it holds until all have finished charging. On a
/// starved host a thread can finish all its charges inside one time slice, so
/// threads that merely run at the same time may never overlap; holding on
/// makes later threads charge against everything earlier ones still hold, so
/// the pressure on a level comes from the fixture, not from the scheduler.
fn press(
    parent: &ExecutionContext,
    children: &[(ExecutionContext, Option<usize>)],
    threads_per_child: usize,
    charges: usize,
    round: usize,
) -> Pressure {
    /// Counts a worker as finished when it drops, unwinding included, so a
    /// failed worker never leaves the others waiting for it.
    struct Finished<'a>(&'a AtomicUsize);
    impl Drop for Finished<'_> {
        fn drop(&mut self) {
            self.0.fetch_add(1, Ordering::Release);
        }
    }

    let parent_limit = parent.limits().memory_bytes;
    let workers = children.len() * threads_per_child;
    let done = AtomicBool::new(false);
    let finished = AtomicUsize::new(0);
    let admitted = AtomicUsize::new(0);
    let by_parent = AtomicUsize::new(0);
    let by_child = AtomicUsize::new(0);
    let start = Barrier::new(workers + 1);
    std::thread::scope(|scope| {
        let mut handles = Vec::new();
        for (index, (child, limit)) in children.iter().enumerate() {
            assert_ne!(*limit, Some(parent_limit), "refusals must name their level");
            for thread in 0..threads_per_child {
                let (start, finished, admitted) = (&start, &finished, &admitted);
                let (by_parent, by_child) = (&by_parent, &by_child);
                handles.push(scope.spawn(move || {
                    let mut seed = (round * 7919 + index * 31 + thread) as u64 | 1;
                    let mut next = move || {
                        seed ^= seed << 13;
                        seed ^= seed >> 7;
                        seed ^= seed << 17;
                        seed as usize
                    };
                    let done = Finished(finished);
                    let mut held = Vec::new();
                    start.wait();
                    for _ in 0..charges {
                        let bytes = 1 + next() % 900;
                        let charged = if next() % 4 == 0 {
                            let mut account = child.memory_account();
                            account.charge(bytes).map(|()| held.push(Err(account)))
                        } else {
                            child.reserve(bytes).map(|token| held.push(Ok(token)))
                        };
                        match charged {
                            Ok(()) => {
                                admitted.fetch_add(1, Ordering::Relaxed);
                                let live = memory(parent).0;
                                assert!(live <= parent_limit, "parent at {live} of {parent_limit}");
                                if let Some(limit) = limit {
                                    let live = memory(child).0;
                                    assert!(live <= *limit, "child at {live} of {limit}");
                                }
                            }
                            Err(ProcedureError::BudgetExceeded {
                                resource: "memory",
                                limit: at,
                            }) if at == parent_limit => {
                                by_parent.fetch_add(1, Ordering::Relaxed);
                            }
                            Err(ProcedureError::BudgetExceeded {
                                resource: "memory",
                                limit: at,
                            }) if Some(at) == *limit => {
                                by_child.fetch_add(1, Ordering::Relaxed);
                            }
                            Err(other) => panic!("unexpected failure: {other}"),
                        }
                        // Release a random share, so each level keeps moving
                        // both ways around its limit.
                        while held.len() > next() % 6 {
                            let at = next() % held.len();
                            drop(held.swap_remove(at));
                        }
                    }
                    // Hold on until every worker is done charging.
                    drop(done);
                    while finished.load(Ordering::Acquire) < workers {
                        std::thread::yield_now();
                    }
                    drop(held);
                }));
            }
        }
        let (done, start) = (&done, &start);
        scope.spawn(move || {
            start.wait();
            while !done.load(Ordering::Acquire) {
                let live = memory(parent).0;
                assert!(
                    live <= parent_limit,
                    "monitor: parent at {live} of {parent_limit}"
                );
                for (child, limit) in children {
                    if let Some(limit) = limit {
                        let live = memory(child).0;
                        assert!(live <= *limit, "monitor: child at {live} of {limit}");
                    }
                }
            }
        });
        // The monitor stops once every worker has finished, or failed.
        let outcomes: Vec<_> = handles.into_iter().map(|handle| handle.join()).collect();
        done.store(true, Ordering::Release);
        for outcome in outcomes {
            if let Err(panic) = outcome {
                std::panic::resume_unwind(panic);
            }
        }
    });
    // The peaks record the largest total any admission produced, so an
    // overrun between two of the monitor's reads is still seen here.
    assert!(
        memory(parent).1 <= parent_limit,
        "round {round}: parent peaked at {}",
        memory(parent).1
    );
    for (child, limit) in children {
        let (live, peak) = memory(child);
        assert_eq!(live, 0, "every release came back");
        assert!(
            peak <= limit.unwrap_or(parent_limit),
            "round {round}: child peak {peak}"
        );
    }
    Pressure {
        admitted: admitted.into_inner(),
        by_parent: by_parent.into_inner(),
        by_child: by_child.into_inner(),
    }
}

/// The joint-overrun test. Eight children, half with sub-limits, on three
/// threads each, against a parent that also holds a share of its own and
/// whose remaining budget is far smaller than their joint demand. No level is
/// ever seen over its limit, by any thread, the monitor or the peaks, and the
/// parent refused often, so the race at its limit was real.
#[test]
fn concurrent_children_never_jointly_overrun_their_parent() {
    const PARENT: usize = 10_000;
    const BASE: usize = 4_000;
    for round in 0..rounds(20) {
        let parent = root(PARENT);
        let base = parent.reserve(BASE).expect("the parent's own share");
        let children: Vec<(ExecutionContext, Option<usize>)> = (0..8)
            .map(|index| {
                let limit = (index % 2 == 0).then_some(1_500);
                let limits = ChildLimits {
                    memory_bytes: limit,
                    ..ChildLimits::default()
                };
                (parent.child(limits).expect("child"), limit)
            })
            .collect();
        let pressure = press(&parent, &children, 3, 3_000, round);
        if round == 0 {
            println!(
                "{} admitted, {} refused by the parent, {} by a child",
                pressure.admitted, pressure.by_parent, pressure.by_child
            );
        }
        assert!(
            pressure.admitted > 1000 && pressure.by_parent > 100,
            "round {round}: {} admitted, {} refused by the parent",
            pressure.admitted,
            pressure.by_parent
        );
        assert_eq!(memory(&parent).0, BASE, "every child's release came back");
        drop(base);
        assert_eq!(memory(&parent).0, 0);
    }
}

/// The same race at a child's sub-limit: sixteen threads on one limited child
/// under a parent with room for all of them, so every refusal is the child's
/// own. In the joint test above the parent
/// usually fills first, which leaves a sub-limit little to refuse.
#[test]
fn concurrent_charges_never_overrun_a_childs_sub_limit() {
    const CHILD: usize = 5_000;
    for round in 0..rounds(20) {
        let parent = root(1 << 30);
        let children = [(parent.child(sub_limit(CHILD)).expect("child"), Some(CHILD))];
        let pressure = press(&parent, &children, 16, 3_000, round);
        if round == 0 {
            println!(
                "{} admitted, {} refused by the child",
                pressure.admitted, pressure.by_child
            );
        }
        assert_eq!(pressure.by_parent, 0);
        assert!(
            pressure.admitted > 1000 && pressure.by_child > 100,
            "round {round}: {} admitted, {} refused by the child",
            pressure.admitted,
            pressure.by_child
        );
        assert_eq!(memory(&parent).0, 0);
    }
}

/// The exactness test of `memory.rs`, across children: every chunk that fits
/// the parent is admitted, and not one more, whichever children race for it.
#[test]
fn racing_children_are_admitted_exactly_what_the_parent_fits() {
    const CHUNK: usize = 1000;
    const FITS: usize = 50;
    const CHILDREN: usize = 16;
    for round in 0..rounds(50) {
        let parent = root(FITS * CHUNK + CHUNK / 2);
        let children: Vec<ExecutionContext> = (0..CHILDREN)
            .map(|index| {
                // Sub-limits that never bind, so every refusal is the parent's.
                let limits = ChildLimits {
                    memory_bytes: (index % 2 == 0).then_some(FITS * CHUNK),
                    ..ChildLimits::default()
                };
                parent.child(limits).expect("child")
            })
            .collect();
        let admitted = AtomicUsize::new(0);
        let start = Barrier::new(CHILDREN);
        let held = std::sync::Mutex::new(Vec::new());
        std::thread::scope(|scope| {
            for child in &children {
                let (admitted, start, held) = (&admitted, &start, &held);
                scope.spawn(move || {
                    start.wait();
                    for _ in 0..FITS {
                        match child.reserve(CHUNK) {
                            Ok(token) => {
                                admitted.fetch_add(1, Ordering::Relaxed);
                                held.lock().expect("held").push(token);
                            }
                            Err(ProcedureError::BudgetExceeded {
                                resource: "memory",
                                limit,
                            }) => assert_eq!(limit, FITS * CHUNK + CHUNK / 2, "the parent's"),
                            Err(other) => panic!("unexpected failure: {other}"),
                        }
                    }
                });
            }
        });
        assert_eq!(admitted.load(Ordering::Relaxed), FITS, "round {round}");
        assert_eq!(memory(&parent), (FITS * CHUNK, FITS * CHUNK));
        let children_live: usize = children.iter().map(|child| memory(child).0).sum();
        assert_eq!(children_live, FITS * CHUNK);
        drop(held);
        assert_eq!(memory(&parent).0, 0);
    }
}

/// A claim the parent refuses sits for an instant against the child's own
/// sub-limit. A charge on the same child that fits in every order the two
/// could run must still be admitted: refusals at the sub-limit are exact. Here
/// one thread asks for 80 bytes the parent can never grant, and another asks,
/// again and again, for 30 that always fit: 30 of the child's 100, and 30 of
/// the parent's remaining 50.
///
/// The race is only a test if the two sides overlap. With every core
/// saturated, the charging thread once finished all its charges before any
/// hopeless thread had run, twice in 300 runs, which the final check caught as
/// "the race never ran". So the charger does not stop at its count alone: it
/// also keeps going until `OVERLAP` hopeless claims have been made while it
/// was charging, which makes the overlap a property of every passing run
/// rather than of the scheduler's mood.
#[test]
fn a_claim_the_parent_refuses_never_refuses_a_charge_that_fits() {
    const OVERLAP: usize = 1000;
    let charges = 20_000 * rounds(20) / 20;
    let parent = root(1000);
    let _others = parent.reserve(950).expect("fits");
    let child = parent.child(sub_limit(100)).expect("child");
    let done = AtomicBool::new(false);
    let wrongly_refused = AtomicUsize::new(0);
    let hopeless = AtomicUsize::new(0);
    let overlapped = AtomicUsize::new(0);
    std::thread::scope(|scope| {
        for _ in 0..3 {
            scope.spawn(|| {
                while !done.load(Ordering::Relaxed) {
                    assert!(child.reserve(80).is_err(), "80 bytes never fit the parent");
                    hopeless.fetch_add(1, Ordering::Relaxed);
                }
            });
        }
        scope.spawn(|| {
            let before = hopeless.load(Ordering::Relaxed);
            let mut charged = 0;
            while charged < charges || hopeless.load(Ordering::Relaxed) - before < OVERLAP {
                if child.reserve(30).is_err() {
                    wrongly_refused.fetch_add(1, Ordering::Relaxed);
                }
                charged += 1;
            }
            overlapped.store(hopeless.load(Ordering::Relaxed) - before, Ordering::Relaxed);
            done.store(true, Ordering::Relaxed);
        });
    });
    assert!(
        overlapped.load(Ordering::Relaxed) >= OVERLAP,
        "the race never ran"
    );
    assert_eq!(
        wrongly_refused.load(Ordering::Relaxed),
        0,
        "refusals of 30 bytes that fit, over {charges} charges"
    );
    assert_eq!(memory(&child), (0, 30), "no refused claim reached the peak");
    assert_eq!(memory(&parent), (950, 980));
}

#[test]
fn a_released_reservation_shrinks_through_every_level() {
    let parent = root(1000);
    let child = parent.child(sub_limit(500)).expect("child");
    let bound = child.reserve(400).expect("an upper bound");
    let clone = bound.clone();
    bound.shrink(150).expect("smaller");
    assert_eq!(
        (bound.bytes(), clone.bytes()),
        (150, 150),
        "clones share it"
    );
    assert_eq!(memory(&child), (150, 400), "the peak keeps the bound");
    assert_eq!(memory(&parent), (150, 400));
    assert!(
        child.check_memory_available(350).is_ok(),
        "the child's room is back"
    );
    assert!(matches!(
        clone.shrink(151),
        Err(ProcedureError::InvalidArguments(_))
    ));
    assert_eq!(bound.bytes(), 150, "a refused shrink changes nothing");
    clone.shrink(150).expect("no change is a shrink");
    drop(bound);
    assert_eq!(memory(&parent).0, 150, "the clone still holds it");
    clone.shrink(0).expect("to nothing");
    assert_eq!(memory(&parent).0, 0);
    drop(clone);
    assert_eq!(memory(&parent).0, 0, "nothing released twice");

    // On a root, and through racing clones: each byte is released once.
    let execution = root(usize::MAX);
    for _ in 0..rounds(20) {
        let token = execution.reserve(1 << 20).expect("fits");
        std::thread::scope(|scope| {
            for worker in 0..8 {
                let token = token.clone();
                scope.spawn(move || {
                    for step in (0..64).rev() {
                        let _ = token.shrink(step * 16_384 + worker);
                    }
                });
            }
        });
        let left = token.bytes();
        assert_eq!(memory(&execution).0, left);
        drop(token);
        assert_eq!(memory(&execution).0, 0);
    }
}

#[test]
fn cancelling_a_child_reaches_neither_its_parent_nor_its_sibling() {
    let parent = root(100);
    let first = parent.child(ChildLimits::default()).expect("child");
    let second = parent.child(ChildLimits::default()).expect("child");
    let mut meter = second.work_meter();
    first.cancel().expect("cancel");
    assert!(matches!(first.checkpoint(), Err(ProcedureError::Cancelled)));
    assert!(matches!(
        first.charge_work(1),
        Err(ProcedureError::Cancelled)
    ));
    assert!(matches!(first.reserve(1), Err(ProcedureError::Cancelled)));
    parent.checkpoint().expect("the parent runs on");
    second.checkpoint().expect("the sibling runs on");
    meter.charge(1).expect("the sibling's meter runs on");
    second.reserve(1).expect("the sibling can reserve");
    parent
        .child(ChildLimits::default())
        .expect("a new child")
        .checkpoint()
        .expect("uncancelled");
}

#[test]
fn cancelling_the_parent_reaches_every_descendant_and_wakes_their_waiters() {
    use std::future::Future;
    use std::pin::Pin;
    use std::task::{Context, Poll, Wake, Waker};

    struct Woken(AtomicUsize);
    impl Wake for Woken {
        fn wake(self: std::sync::Arc<Self>) {
            self.0.fetch_add(1, Ordering::Relaxed);
        }
    }

    let parent = root(100);
    let child = parent.child(ChildLimits::default()).expect("child");
    let grandchild = child.child(ChildLimits::default()).expect("grandchild");
    let woken = std::sync::Arc::new(Woken(AtomicUsize::new(0)));
    let waker = Waker::from(woken.clone());
    let mut waiting = grandchild.cancelled();
    assert!(
        Pin::new(&mut waiting)
            .poll(&mut Context::from_waker(&waker))
            .is_pending()
    );
    let mut meter = grandchild.work_meter();
    parent.cancel().expect("cancel");
    for execution in [&parent, &child, &grandchild] {
        assert!(matches!(
            execution.checkpoint(),
            Err(ProcedureError::Cancelled)
        ));
    }
    assert!(matches!(meter.charge(1), Err(ProcedureError::Cancelled)));
    assert_eq!(woken.0.load(Ordering::Relaxed), 1);
    assert!(matches!(
        Pin::new(&mut waiting).poll(&mut Context::from_waker(&waker)),
        Poll::Ready(Ok(()))
    ));
    // A child of a cancelled execution starts cancelled.
    let late = parent.child(ChildLimits::default()).expect("child");
    assert!(matches!(late.checkpoint(), Err(ProcedureError::Cancelled)));
    let later = late.child(ChildLimits::default()).expect("grandchild");
    assert!(matches!(later.checkpoint(), Err(ProcedureError::Cancelled)));
}

/// Children created on many threads while the parent is cancelled: whichever
/// side of the cancellation a child was created on, it ends up cancelled.
#[test]
fn a_child_created_while_its_parent_is_cancelled_is_never_missed() {
    for _ in 0..rounds(200) {
        let parent = root(100);
        let start = Barrier::new(9);
        let created = std::sync::Mutex::new(Vec::new());
        std::thread::scope(|scope| {
            for _ in 0..8 {
                scope.spawn(|| {
                    start.wait();
                    for _ in 0..20 {
                        let child = parent.child(ChildLimits::default()).expect("child");
                        created.lock().expect("created").push(child);
                    }
                });
            }
            start.wait();
            parent.cancel().expect("cancel");
        });
        for child in created.into_inner().expect("created") {
            assert!(matches!(child.checkpoint(), Err(ProcedureError::Cancelled)));
        }
    }
}

#[test]
fn each_childs_work_budget_is_its_own() {
    let parent = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 100,
        work_units: 10,
        batch_rows: 8,
        deadline: None,
    })
    .expect("valid");
    let small = parent
        .child(ChildLimits {
            work_units: 100,
            ..ChildLimits::default()
        })
        .expect("child");
    let large = parent
        .child(ChildLimits {
            work_units: 5_000,
            ..ChildLimits::default()
        })
        .expect("child");
    small.charge_work(100).expect("exactly fits");
    assert!(matches!(
        small.charge_work(1),
        Err(ProcedureError::BudgetExceeded {
            resource: "work",
            limit: 100
        })
    ));
    large
        .charge_work(5_000)
        .expect("its own budget, not the parent's");
    parent
        .charge_work(10)
        .expect("the parent's budget is untouched");
    assert_eq!(small.usage().expect("usage").counted_work(), Some(100));
    assert_eq!(large.usage().expect("usage").counted_work(), Some(5_000));
    assert_eq!(parent.usage().expect("usage").counted_work(), Some(10));
}

/// Children's meters racing on many threads, each child's budget exactly
/// fitting its work: no child refuses work that fits, none admits more, and
/// none sees the others' blocks.
#[test]
fn children_meter_work_exactly_and_independently_under_contention() {
    const CHILDREN: usize = 4;
    const WORKERS: usize = 4;
    const PER_WORKER: usize = 4 * WORK_BLOCK_UNITS;
    for round in 0..rounds(50) {
        let parent = root(100);
        // Child `index` fits exactly `index + 1` workers' work; its other
        // workers are refused at exactly the unit the budget runs out.
        let children: Vec<ExecutionContext> = (0..CHILDREN)
            .map(|index| {
                parent
                    .child(ChildLimits {
                        work_units: (index + 1) * PER_WORKER,
                        ..ChildLimits::default()
                    })
                    .expect("child")
            })
            .collect();
        let charged: Vec<AtomicUsize> = (0..CHILDREN).map(|_| AtomicUsize::new(0)).collect();
        let start = Barrier::new(CHILDREN * WORKERS);
        std::thread::scope(|scope| {
            for (child, charged) in children.iter().zip(&charged) {
                for _ in 0..WORKERS {
                    let start = &start;
                    scope.spawn(move || {
                        let mut meter = child.work_meter();
                        start.wait();
                        for _ in 0..PER_WORKER {
                            if meter.charge(1).is_err() {
                                return;
                            }
                            charged.fetch_add(1, Ordering::Relaxed);
                        }
                    });
                }
            }
        });
        for (index, (child, charged)) in children.iter().zip(&charged).enumerate() {
            let budget = ((index + 1) * PER_WORKER).min(WORKERS * PER_WORKER);
            assert_eq!(
                charged.load(Ordering::Relaxed),
                budget,
                "round {round}, child {index}"
            );
            assert_eq!(child.usage().expect("usage").counted_work(), Some(budget));
        }
        assert_eq!(parent.usage().expect("usage").counted_work(), Some(0));
    }
}

#[test]
fn each_childs_deadline_is_its_own_and_never_later_than_its_parents() {
    let parent = root(100);
    let past = Instant::now() - Duration::from_millis(1);
    let expired = parent
        .child(ChildLimits {
            deadline: Some(past),
            ..ChildLimits::default()
        })
        .expect("child");
    let running = parent
        .child(ChildLimits {
            deadline: Some(Instant::now() + Duration::from_secs(3600)),
            ..ChildLimits::default()
        })
        .expect("child");
    assert!(matches!(
        expired.checkpoint(),
        Err(ProcedureError::DeadlineExceeded)
    ));
    assert!(matches!(
        expired.reserve(1),
        Err(ProcedureError::DeadlineExceeded)
    ));
    running.checkpoint().expect("its own deadline is later");
    parent.checkpoint().expect("the parent has none");

    let soon = Instant::now() + Duration::from_secs(60);
    let bounded = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 100,
        work_units: usize::MAX,
        batch_rows: 8,
        deadline: Some(soon),
    })
    .expect("valid");
    let later = bounded
        .child(ChildLimits {
            deadline: Some(soon + Duration::from_secs(60)),
            ..ChildLimits::default()
        })
        .expect("child");
    assert_eq!(
        later.limits().deadline,
        Some(soon),
        "clipped to the parent's"
    );
    let inherited = bounded.child(ChildLimits::default()).expect("child");
    assert_eq!(inherited.limits().deadline, Some(soon));
    let earlier = bounded
        .child(ChildLimits {
            deadline: Some(past),
            ..ChildLimits::default()
        })
        .expect("child");
    assert_eq!(earlier.limits().deadline, Some(past));
    assert!(matches!(
        earlier.checkpoint(),
        Err(ProcedureError::DeadlineExceeded)
    ));
    later.checkpoint().expect("not yet");
}

#[test]
fn a_childs_accounting_mode_is_its_own_within_what_its_parent_can_stop() {
    let counted = root(100);
    assert!(
        matches!(
            counted.child(ChildLimits {
                accounting: Accounting::UNCHECKED,
                ..ChildLimits::default()
            }),
            Err(ProcedureError::InvalidArguments(_))
        ),
        "cancelling the parent could not reach an uninterruptible child"
    );
    let uncounted = counted
        .child(ChildLimits {
            accounting: Accounting::WORK_UNCOUNTED,
            ..ChildLimits::default()
        })
        .expect("child");
    uncounted.charge_work(1_000).expect("uncounted");
    assert_eq!(
        uncounted.usage().expect("usage").work_units,
        WorkCount::NotCounted
    );
    assert!(matches!(
        counted.child(ChildLimits {
            accounting: Accounting::WORK_UNCOUNTED,
            work_units: 10,
            ..ChildLimits::default()
        }),
        Err(ProcedureError::InvalidArguments(_))
    ));

    // Under a parent nothing can stop, a child may be stoppable, or not.
    let unchecked = ExecutionContext::with_accounting(
        ExecutionLimits {
            memory_bytes: 100,
            work_units: usize::MAX,
            batch_rows: 8,
            deadline: None,
        },
        Accounting::UNCHECKED,
    )
    .expect("valid");
    let stoppable = unchecked
        .child(ChildLimits {
            work_units: 10,
            ..ChildLimits::default()
        })
        .expect("a counted, interruptible child");
    assert!(unchecked.cancel().is_err());
    stoppable.checkpoint().expect("not cancelled");
    assert!(matches!(
        stoppable.charge_work(11),
        Err(ProcedureError::BudgetExceeded {
            resource: "work",
            ..
        })
    ));
    stoppable.cancel().expect("cancel the child");
    assert!(matches!(
        stoppable.checkpoint(),
        Err(ProcedureError::Cancelled)
    ));
    let quiet = unchecked
        .child(ChildLimits {
            accounting: Accounting::UNCHECKED,
            ..ChildLimits::default()
        })
        .expect("an unchecked child");
    assert!(quiet.cancel().is_err());
    // Memory is admitted in every mode, against every level.
    let _held = quiet.reserve(100).expect("fits");
    assert!(refused_at(quiet.reserve(1), 100));
}

#[test]
fn a_child_inherits_batch_rows_and_concurrency_unless_it_sets_its_own() {
    let parent = root(100).with_concurrency(4).expect("unshared");
    let inherited = parent.child(ChildLimits::default()).expect("child");
    assert_eq!(inherited.limits().batch_rows, 8);
    assert_eq!(inherited.concurrency_requested(), Some(4));
    let own = parent
        .child(ChildLimits {
            batch_rows: Some(64),
            concurrency: Some(2),
            ..ChildLimits::default()
        })
        .expect("child");
    assert_eq!((own.limits().batch_rows, own.concurrency()), (64, 2));
    assert!(own.with_concurrency(3).is_err(), "set through ChildLimits");
    for invalid in [
        ChildLimits {
            batch_rows: Some(0),
            ..ChildLimits::default()
        },
        ChildLimits {
            concurrency: Some(0),
            ..ChildLimits::default()
        },
    ] {
        assert!(matches!(
            parent.child(invalid),
            Err(ProcedureError::InvalidArguments(_))
        ));
    }
    assert!(
        root(100)
            .child(ChildLimits::default())
            .expect("child")
            .concurrency_requested()
            .is_none()
    );
    assert!(inherited.parent().is_some() && parent.parent().is_none());
}
