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
use std::{
    collections::VecDeque,
    sync::{Arc, Mutex},
};

enum Turn<T> {
    /// Another leader committed this caller's rows, with this outcome.
    Done(std::result::Result<(), String>),
    /// This caller leads the next commit; its own rows come back with it.
    Lead { rows: Vec<T>, ownership: Lead<T> },
}

struct State<T> {
    pending: VecDeque<(Vec<T>, oneshot::Sender<Turn<T>>)>,
    leading: bool,
}

pub(super) struct WriteQueue<T> {
    state: Arc<Mutex<State<T>>>,
}

impl<T> Default for WriteQueue<T> {
    fn default() -> Self {
        Self {
            state: Arc::new(Mutex::new(State {
                pending: VecDeque::new(),
                leading: false,
            })),
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
                state.pending.push_back((rows, reply));
                Err(turn)
            } else {
                state.leading = true;
                Ok((
                    rows,
                    Lead {
                        state: Some(Arc::clone(&self.state)),
                    },
                ))
            }
        };
        let (own, lead) = match turn {
            Ok(lead) => lead,
            Err(turn) => match turn.await {
                Ok(Turn::Done(result)) => return result.map_err(GrustError::Backend),
                Ok(Turn::Lead { rows, ownership }) => (rows, ownership),
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
        let queued = std::mem::take(&mut self.lock().pending);
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
struct Lead<T> {
    // The message owns leadership even before its receiving future is polled.
    // Failed delivery disarms this token before continuing the iterative handoff.
    state: Option<Arc<Mutex<State<T>>>>,
}

impl<T> Drop for Lead<T> {
    fn drop(&mut self) {
        let Some(shared) = self.state.take() else {
            return;
        };
        loop {
            let next = {
                let mut state = shared.lock().expect("LanceDB write queue lock poisoned");
                match state.pending.pop_front() {
                    Some(next) => next,
                    None => {
                        state.leading = false;
                        return;
                    }
                }
            };
            let (rows, reply) = next;
            // Sending/dropping a channel value can run wake/drop callbacks.
            // Never hold the queue lock across either operation.
            let ownership = Lead {
                state: Some(Arc::clone(&shared)),
            };
            match reply.send(Turn::Lead { rows, ownership }) {
                Ok(()) => return,
                Err(mut undelivered) => {
                    if let Turn::Lead { ownership, .. } = &mut undelivered {
                        ownership.state = None;
                    }
                    // The cancelled caller's uncommitted rows are discarded.
                    // Disarming avoids recursive Drop for a long cancelled queue.
                    drop(undelivered);
                }
            }
        }
    }
}

/// Keep the last row per key, in queue order of those last rows.
fn last_per_key<T>(rows: Vec<T>, key: impl Fn(&T) -> Result<String>) -> Result<Vec<T>> {
    if rows.len() < 2 {
        if let Some(row) = rows.first() {
            key(row)?;
        }
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
#[path = "write_queue/cancellation_tests.rs"]
mod cancellation_tests;
