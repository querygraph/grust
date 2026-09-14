mod queue {
//! Group commit for single-row writes to one table.
//!
//! Every `put_node` or `put_edge` is a `merge_insert`, and every
//! `merge_insert` is a new table version with a new fragment. When many
//! callers write through clones of one store at once, each commit also
//! conflicts with the others and retries. A queue per table lets one caller
//! at a time — the leader — commit the rows every waiting caller has queued,
//! as one `merge_insert`. Callers still return only after their rows are
//! durable, and a failed commit fails every caller whose rows it carried.
//! When the leader is done it hands the lead, with the rows queued in the
//! meantime, to the first caller still waiting.

use futures::channel::oneshot;
use grust_core::prelude::*;

enum Turn<T> {
    /// Another leader committed this caller's rows, with this outcome.
    Done(std::result::Result<(), String>),
    /// This caller leads the next commit; its own rows come back with it.
    Lead(Vec<T>),
}

struct State<T> {
    pending: Vec<(Vec<T>, oneshot::Sender<Turn<T>>)>,
    leading: bool,
}

pub(super) struct WriteQueue<T> {
    state: std::sync::Mutex<State<T>>,
}

impl<T> Default for WriteQueue<T> {
    fn default() -> Self {
        Self {
            state: std::sync::Mutex::new(State {
                pending: Vec::new(),
                leading: false,
            }),
        }
    }
}

impl<T> WriteQueue<T> {
    /// Queue `rows`, then either wait for a leader to commit them or lead:
    /// commit everything queued so far with `apply`. `key` identifies a row:
    /// when several queued rows share one, only the last queued is written,
    /// as if the writes had been applied one after another.
    pub(super) async fn submit<K, F, Fut>(&self, rows: Vec<T>, key: K, apply: F) -> Result<()>
    where
        K: Fn(&T) -> Result<String>,
        F: FnOnce(Vec<T>) -> Fut,
        Fut: std::future::Future<Output = Result<()>>,
    {
        // Decide under the lock; wait, if at all, after releasing it.
        let turn = {
            let mut state = self.lock();
            if state.leading {
                let (reply, turn) = oneshot::channel();
                state.pending.push((rows, reply));
                Err(turn)
            } else {
                state.leading = true;
                Ok(rows)
            }
        };
        let own = match turn {
            Ok(rows) => rows,
            Err(turn) => match turn.await {
                Ok(Turn::Done(result)) => return result.map_err(GrustError::Backend),
                Ok(Turn::Lead(rows)) => rows,
                Err(oneshot::Canceled) => {
                    return Err(GrustError::Backend(
                        "LanceDB write abandoned: the caller committing it was cancelled, \
                         so it may or may not be durable"
                            .into(),
                    ));
                }
            },
        };
        // This caller leads until `lead` is dropped, which hands the lead on.
        let lead = Lead { queue: self };
        let queued = std::mem::take(&mut lead.queue.lock().pending);
        let mut rows = own;
        let mut replies = Vec::with_capacity(queued.len());
        for (batch, reply) in queued {
            rows.extend(batch);
            replies.push(reply);
        }
        let result = match last_per_key(rows, &key) {
            Ok(rows) => apply(rows).await,
            Err(err) => Err(err),
        };
        let shared = result.as_ref().map(|_| ()).map_err(ToString::to_string);
        for reply in replies {
            // A caller that stopped waiting has nobody to tell.
            let _ = reply.send(Turn::Done(shared.clone()));
        }
        drop(lead);
        result
    }

    fn lock(&self) -> std::sync::MutexGuard<'_, State<T>> {
        self.state
            .lock()
            .expect("LanceDB write queue lock poisoned")
    }
}

/// The lead, handed on when dropped — after a commit, or when the leading
/// caller is cancelled mid-commit (its batch's callers then see `Canceled`).
struct Lead<'a, T> {
    queue: &'a WriteQueue<T>,
}

impl<T> Drop for Lead<'_, T> {
    fn drop(&mut self) {
        let mut state = self.queue.lock();
        while !state.pending.is_empty() {
            let (rows, reply) = state.pending.remove(0);
            if reply.send(Turn::Lead(rows)).is_ok() {
                return;
            }
            // That caller stopped waiting before its rows were written;
            // they are dropped with it, as if never submitted.
        }
        state.leading = false;
    }
}

/// Keep the last row per key, in queue order of those last rows.
fn last_per_key<T>(rows: Vec<T>, key: impl Fn(&T) -> Result<String>) -> Result<Vec<T>> {
    if rows.len() < 2 {
        return Ok(rows);
    }
    let mut seen = std::collections::HashSet::with_capacity(rows.len());
    let mut kept = Vec::with_capacity(rows.len());
    for row in rows.into_iter().rev() {
        if seen.insert(key(&row)?) {
            kept.push(row);
        }
    }
    kept.reverse();
    Ok(kept)
}


#[cfg(test)]
mod cancellation_review {
    use super::*;
    use std::{future::Future, task::{Context, Poll}};
    #[test]
    fn cancellation_after_handoff_must_release_leadership() {
        let queue = WriteQueue::<u64>::default();
        let key = |row: &u64| Ok(row.to_string());
        let mut a = Box::pin(queue.submit(vec![1], key, |_| std::future::pending::<Result<()>>()));
        let mut b = Box::pin(queue.submit(vec![2], key, |_| async { Ok(()) }));
        let mut context = Context::from_waker(futures::task::noop_waker_ref());
        assert!(a.as_mut().poll(&mut context).is_pending());
        assert!(b.as_mut().poll(&mut context).is_pending());
        drop(a);
        // B owns the delivered handoff but has never resumed to build its guard.
        drop(b);
        let mut c = Box::pin(queue.submit(vec![3], key, |_| async { Ok(()) }));
        assert!(matches!(c.as_mut().poll(&mut context), Poll::Ready(Ok(()))),
            "new writer remains pending after all previous callers were dropped");
    }
}

}
