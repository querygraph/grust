//! Merge-key indexing and periodic fragment maintenance.
use super::LanceDbGraphStore;
use grust_core::{GrustError, Result};
use lancedb::{
    Error as LanceError, Table,
    index::{Index, scalar::BTreeIndexBuilder},
    table::OptimizeAction,
};

/// Single-row commits to a table between compactions of their fragments.
const COMPACT_EVERY_COMMITS: u64 = 64;

impl LanceDbGraphStore {
    /// Give the table a B-tree on its merge key, or fold rows written since
    /// into the one it has. With it, a `merge_insert` looks its rows' keys
    /// up instead of joining them against a scan of the whole table, which
    /// held every key of the table in memory once per concurrent write and
    /// made each single-row write cost a full scan. Only fragments written
    /// after the last index update are still scanned. An empty table is left
    /// unindexed; its first bulk load indexes it.
    async fn index_merge_key(table: &Table, column: &str) -> Result<()> {
        let failed =
            |err: LanceError| GrustError::Backend(format!("LanceDB {column} index failed: {err}"));
        let indexed = table
            .list_indices()
            .await
            .map_err(failed)?
            .iter()
            .any(|index| index.columns == [column]);
        if indexed {
            table
                .optimize(OptimizeAction::Index(Default::default()))
                .await
                .map_err(failed)?;
        } else if table.count_rows(None).await.map_err(failed)? > 0 {
            table
                .create_index(&[column], Index::BTree(BTreeIndexBuilder::default()))
                .execute()
                .await
                .map_err(failed)?;
        }
        Ok(())
    }

    /// Every `COMPACT_EVERY_COMMITS` single-row commits to a table, merge the
    /// small fragments they left. Each commit adds one, and every later
    /// `merge_insert` scans all fragments its key index does not cover, so
    /// per-commit work can grow with the number of unindexed fragments.
    /// The write that triggers it has already committed, so a failed or
    /// conflicting compaction is left for the next one.
    pub(super) async fn compact_now_and_then(
        table: &Table,
        commits: &std::sync::atomic::AtomicU64,
    ) {
        let n = commits
            .fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            .wrapping_add(1);
        if n.is_multiple_of(COMPACT_EVERY_COMMITS) {
            let _ = Self::compact(table).await;
        }
    }

    /// The bulk paths' last step: merge the small files the load left, then
    /// index the merge key.
    pub(super) async fn finish_bulk_load(table: &Table, key: &str) -> Result<()> {
        Self::compact(table).await?;
        Self::index_merge_key(table, key).await
    }
}
