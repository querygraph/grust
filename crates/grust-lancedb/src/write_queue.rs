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
mod tests {
    use super::*;

    #[test]
    fn last_row_per_key_wins_in_queue_order() {
        let rows = vec![("a", 1), ("b", 1), ("a", 2), ("c", 1), ("b", 2)];
        let kept = last_per_key(rows, |row| Ok(row.0.to_string())).unwrap();
        assert_eq!(kept, vec![("a", 2), ("c", 1), ("b", 2)]);
    }

    async fn store(dir: &std::path::Path) -> crate::LanceDbGraphStore {
        let store = crate::LanceDbGraphStore::connect(crate::LanceDbConfig {
            uri: dir.display().to_string(),
            table_prefix: "queue".to_string(),
            batch_size: 500,
            bulk_batch_size: 50_000,
        })
        .await
        .unwrap();
        store.bootstrap().await.unwrap();
        store
    }

    /// A4's pattern: writers on clones of one store attach new nodes and
    /// edges to one hub at once. Every accepted write is durable exactly
    /// once, seen by this store and by another connection, with and without
    /// a merge-key index, and across the periodic compactions.
    #[tokio::test(flavor = "multi_thread", worker_threads = 4)]
    async fn concurrent_writers_on_clones_commit_every_row_once() {
        for indexed in [false, true] {
            let dir = tempfile::tempdir().unwrap();
            let store = store(dir.path()).await;
            if indexed {
                let mut graph = Graph::default();
                graph.nodes.push(Node::new("V", "hub", Props::new()));
                for i in 0..50 {
                    graph
                        .nodes
                        .push(Node::new("V", format!("v{i}"), Props::new()));
                    graph
                        .edges
                        .push(Edge::new("E", "hub", format!("v{i}"), Props::new()));
                }
                store.put_graph(&graph).await.unwrap();
            }
            let initial = if indexed { 50 } else { 0 };
            let writers = (0..8)
                .map(|w| {
                    let store = store.clone();
                    tokio::spawn(async move {
                        for i in 0..20 {
                            let id = format!("hot-{w}-{i}");
                            store
                                .put_node(&Node::new("V", id.clone(), Props::new()))
                                .await
                                .unwrap();
                            store
                                .put_edge(&Edge::new("E", "hub", id, Props::new()))
                                .await
                                .unwrap();
                        }
                    })
                })
                .collect::<Vec<_>>();
            for writer in writers {
                writer.await.unwrap();
            }
            let hub_edges = EdgeQuery {
                from: Some(NodeId::new("hub")),
                ..Default::default()
            };
            let other = crate::LanceDbGraphStore::connect(store.config().clone())
                .await
                .unwrap()
                .with_read_snapshot(false);
            for reader in [&store, &other] {
                let edges = reader.get_edges(hub_edges.clone()).await.unwrap();
                assert_eq!(edges.len(), initial + 160, "indexed: {indexed}");
                let targets = edges
                    .iter()
                    .map(|edge| edge.to.as_str().to_owned())
                    .collect::<std::collections::HashSet<_>>();
                assert_eq!(targets.len(), edges.len(), "indexed: {indexed}");
                for w in 0..8 {
                    for i in 0..20 {
                        let id = NodeId::new(format!("hot-{w}-{i}"));
                        assert!(reader.get_node(&id).await.unwrap().is_some());
                    }
                }
            }
        }
    }

    /// Writers that upsert the same node at once leave one row holding one
    /// of the values written, as sequential upserts would.
    #[tokio::test(flavor = "multi_thread", worker_threads = 4)]
    async fn concurrent_upserts_of_one_key_leave_one_row() {
        let dir = tempfile::tempdir().unwrap();
        let store = store(dir.path()).await;
        let writers = (0..8i64)
            .map(|w| {
                let store = store.clone();
                tokio::spawn(async move {
                    for i in 0..10i64 {
                        let mut node = Node::new("V", "same", Props::new());
                        node.props.insert("by".into(), Value::Int(w * 100 + i));
                        store.put_node(&node).await.unwrap();
                        store
                            .put_edge(&Edge::new("E", "same", "same", Props::new()))
                            .await
                            .unwrap();
                    }
                })
            })
            .collect::<Vec<_>>();
        for writer in writers {
            writer.await.unwrap();
        }
        let direct = store.clone().with_read_snapshot(false);
        let nodes = direct
            .traverse(Traversal {
                start: Start::NodesByLabel(Label::new("V")),
                steps: Vec::new(),
                limit: None,
            })
            .await
            .unwrap();
        assert_eq!(nodes.len(), 1);
        assert!(matches!(nodes[0].props.get("by"), Some(Value::Int(_))));
        assert_eq!(
            direct.get_edges(EdgeQuery::default()).await.unwrap().len(),
            1
        );
    }
}
