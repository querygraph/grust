use std::{
    ops::{Deref, DerefMut},
    sync::RwLockWriteGuard,
};

use super::*;
use snapshot_source::StoreSnapshot;

impl MemoryGraphStore {
    /// Returns a reusable typed index over an immutable snapshot of the store.
    ///
    /// The first call after a write freezes the stored graph, shares it with
    /// the index instead of copying its nodes and edges, and builds the index's
    /// slot order and adjacency. Subsequent calls, including calls through
    /// cloned stores, share that index. Previously returned snapshots remain
    /// valid and unchanged after later writes: a write while one is still held
    /// elsewhere copies the store's graph first (copy-on-write), leaving the
    /// snapshot's frozen graph untouched.
    ///
    /// Like `TypedGraphIndex::new`, this returns an error for dangling edges or
    /// graphs that exceed the index's slot capacity. Existing store reads and
    /// writes retain their semantics. A write attempt invalidates the cache even
    /// if validation subsequently fails.
    pub fn indexed_snapshot(&self) -> Result<Arc<TypedGraphIndex>> {
        // Always acquire the graph lock before the cache lock, on both reads and
        // writes. Holding the read lock through construction makes the snapshot
        // coherent; the cache lock prevents concurrent first callers rebuilding
        // the same graph and publishing different index identities.
        let inner = self.inner.read().expect("memory graph lock poisoned");
        let mut cache = self
            .index_cache
            .lock()
            .expect("memory index cache lock poisoned");
        if let Some(index) = cache.as_ref() {
            return Ok(Arc::clone(index));
        }
        let source = Arc::new(StoreSnapshot::new(Arc::clone(&inner)));
        let index = Arc::new(TypedGraphIndex::from_source(source)?);
        *cache = Some(Arc::clone(&index));
        Ok(index)
    }

    /// The single entry point for mutable access to the graph.
    ///
    /// Invalidate before exposing mutable state so early errors and mutation
    /// plans that partially apply cannot leave a stale snapshot cached.
    ///
    /// The retired index is dropped here, inline: it holds the store's graph
    /// `Arc`, and if it were still alive when the writer first mutated, that
    /// write would copy the whole graph. Dropping it frees only its
    /// permutations and adjacency arrays, a few large allocations.
    pub(super) fn write_inner(&self) -> MemoryWriteGuard<'_> {
        let inner = self.inner.write().expect("memory graph lock poisoned");
        let retired = self
            .index_cache
            .lock()
            .expect("memory index cache lock poisoned")
            .take();
        drop(retired);
        MemoryWriteGuard(inner)
    }
}

/// Write access to the store's graph. Reading is free; the first mutable
/// access copies the graph only if a snapshot handed out earlier still
/// shares it (`Arc::make_mut`).
pub(super) struct MemoryWriteGuard<'a>(RwLockWriteGuard<'a, Arc<MemoryGraph>>);

impl Deref for MemoryWriteGuard<'_> {
    type Target = MemoryGraph;

    fn deref(&self) -> &MemoryGraph {
        &self.0
    }
}

impl DerefMut for MemoryWriteGuard<'_> {
    fn deref_mut(&mut self) -> &mut MemoryGraph {
        Arc::make_mut(&mut self.0)
    }
}

#[cfg(test)]
#[path = "indexed_snapshot_tests.rs"]
mod tests;
