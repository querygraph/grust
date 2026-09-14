use super::context;
use std::{
    future::Future,
    pin::Pin,
    sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
    },
    task::{Context, Poll, Wake, Waker},
};

#[derive(Default)]
struct Counter(AtomicUsize);
impl Wake for Counter {
    fn wake(self: Arc<Self>) {
        self.0.fetch_add(1, Ordering::Relaxed);
    }
}

#[test]
fn cancellation_wakes_every_live_waiter_and_unregisters_dropped_waiters() {
    let execution = context(100);
    let first = Arc::new(Counter::default());
    let second = Arc::new(Counter::default());
    let dropped = Arc::new(Counter::default());
    let mut a = execution.cancelled();
    let mut b = execution.cancelled();
    let mut c = execution.cancelled();
    for (future, counter) in [(&mut a, &first), (&mut b, &second), (&mut c, &dropped)] {
        let waker = Waker::from(counter.clone());
        assert!(
            Pin::new(future)
                .poll(&mut Context::from_waker(&waker))
                .is_pending()
        );
    }
    drop(c);
    execution.cancel().unwrap();
    execution.cancel().unwrap();
    assert_eq!(first.0.load(Ordering::Relaxed), 1);
    assert_eq!(second.0.load(Ordering::Relaxed), 1);
    assert_eq!(dropped.0.load(Ordering::Relaxed), 0);
    assert!(matches!(
        Pin::new(&mut a).poll(&mut Context::from_waker(Waker::noop())),
        Poll::Ready(Ok(()))
    ));
    assert!(matches!(
        Pin::new(&mut execution.cancelled()).poll(&mut Context::from_waker(Waker::noop())),
        Poll::Ready(Ok(()))
    ));
}

#[test]
fn repoll_replaces_the_waiter_waker() {
    let execution = context(100);
    let old = Arc::new(Counter::default());
    let new = Arc::new(Counter::default());
    let mut wait = execution.cancelled();
    for counter in [&old, &new] {
        assert!(
            Pin::new(&mut wait)
                .poll(&mut Context::from_waker(&Waker::from(counter.clone())))
                .is_pending()
        );
    }
    execution.cancel().unwrap();
    assert_eq!(old.0.load(Ordering::Relaxed), 0);
    assert_eq!(new.0.load(Ordering::Relaxed), 1);
}
