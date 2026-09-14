use super::*;
use std::{
    future::{Future, pending, ready},
    pin::Pin,
    task::{Context, Poll, Waker},
};

fn poll<F: Future>(future: Pin<&mut F>) -> Poll<F::Output> {
    future.poll(&mut Context::from_waker(Waker::noop()))
}
fn key(row: &u8) -> Result<String> {
    Ok(row.to_string())
}

#[test]
fn cancelling_handoff_before_receiver_poll_releases_leadership() {
    let queue = WriteQueue::default();
    let mut a = Box::pin(queue.submit(vec![1], key, |_| pending::<Result<()>>()));
    let mut b = Box::pin(queue.submit(vec![2], key, |_| ready(Ok(()))));
    assert!(poll(a.as_mut()).is_pending());
    assert!(poll(b.as_mut()).is_pending());
    drop(a);
    drop(b); // B owns an unread leadership message, not an active submit frame.
    let mut c = Box::pin(queue.submit(vec![3], key, |rows| {
        assert_eq!(rows, [3]);
        ready(Ok(()))
    }));
    assert!(matches!(poll(c.as_mut()), Poll::Ready(Ok(()))));
}

#[test]
fn cancelling_handoff_promotes_an_already_waiting_writer() {
    let queue = WriteQueue::default();
    let mut a = Box::pin(queue.submit(vec![1], key, |_| pending::<Result<()>>()));
    let mut b = Box::pin(queue.submit(vec![2], key, |_| ready(Ok(()))));
    let mut c = Box::pin(queue.submit(vec![3], key, |rows| {
        assert_eq!(rows, [3]);
        ready(Ok(()))
    }));
    assert!(poll(a.as_mut()).is_pending());
    assert!(poll(b.as_mut()).is_pending());
    assert!(poll(c.as_mut()).is_pending());
    drop(a);
    drop(b);
    assert!(matches!(poll(c.as_mut()), Poll::Ready(Ok(()))));
}

#[test]
fn cancelling_an_inflight_batch_reports_uncertain_durability_to_its_followers() {
    let queue = WriteQueue::default();
    let mut a = Box::pin(queue.submit(vec![1], key, |_| pending::<Result<()>>()));
    let mut b = Box::pin(queue.submit(vec![2], key, |rows| {
        assert_eq!(rows, [2, 3]);
        pending::<Result<()>>()
    }));
    let mut c = Box::pin(queue.submit(vec![3], key, |_| ready(Ok(()))));
    assert!(poll(a.as_mut()).is_pending());
    assert!(poll(b.as_mut()).is_pending());
    assert!(poll(c.as_mut()).is_pending());
    drop(a);
    assert!(poll(b.as_mut()).is_pending());
    drop(b);
    let Poll::Ready(Err(error)) = poll(c.as_mut()) else {
        panic!("uncertain batch outcome");
    };
    assert!(error.to_string().contains("may or may not be durable"));
    let mut d = Box::pin(queue.submit(vec![4], key, |_| ready(Ok(()))));
    assert!(matches!(poll(d.as_mut()), Poll::Ready(Ok(()))));
}

#[test]
fn apply_failure_reaches_every_batch_caller_and_does_not_strand_the_queue() {
    let queue = WriteQueue::default();
    let mut a = Box::pin(queue.submit(vec![1], key, |_| pending::<Result<()>>()));
    let mut b = Box::pin(queue.submit(vec![2], key, |_| {
        ready(Err(GrustError::Backend("apply failed".into())))
    }));
    let mut c = Box::pin(queue.submit(vec![3], key, |_| ready(Ok(()))));
    assert!(poll(a.as_mut()).is_pending());
    assert!(poll(b.as_mut()).is_pending());
    assert!(poll(c.as_mut()).is_pending());
    drop(a);
    for result in [poll(b.as_mut()), poll(c.as_mut())] {
        let Poll::Ready(Err(error)) = result else {
            panic!("failed batch outcome");
        };
        assert!(error.to_string().contains("apply failed"));
    }
    let mut d = Box::pin(queue.submit(vec![4], key, |_| ready(Ok(()))));
    assert!(matches!(poll(d.as_mut()), Poll::Ready(Ok(()))));
}

#[test]
fn one_row_still_validates_its_key_and_releases_leadership_on_failure() {
    let queue = WriteQueue::default();
    let mut bad = Box::pin(queue.submit(
        vec![1],
        |_| Err(GrustError::Backend("bad key".into())),
        |_| -> std::future::Ready<Result<()>> { panic!("invalid rows cannot be applied") },
    ));
    assert!(matches!(poll(bad.as_mut()), Poll::Ready(Err(_))));
    let mut good = Box::pin(queue.submit(vec![2], key, |_| ready(Ok(()))));
    assert!(matches!(poll(good.as_mut()), Poll::Ready(Ok(()))));
}

#[test]
fn cancelled_waiters_are_skipped_without_recursive_handoff() {
    let queue = WriteQueue::default();
    let mut leader = Box::pin(queue.submit(vec![0], key, |_| pending::<Result<()>>()));
    assert!(poll(leader.as_mut()).is_pending());
    for _ in 0..10_000 {
        let mut cancelled = Box::pin(queue.submit(vec![1], key, |_| ready(Ok(()))));
        assert!(poll(cancelled.as_mut()).is_pending());
        drop(cancelled);
    }
    drop(leader);
    let mut next = Box::pin(queue.submit(vec![2], key, |_| ready(Ok(()))));
    assert!(matches!(poll(next.as_mut()), Poll::Ready(Ok(()))));
}
