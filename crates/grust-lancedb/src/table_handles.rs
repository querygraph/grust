//! Serialize cached handle creation with local table recreation.
use super::*;

#[derive(Clone)]
struct CachedTables {
    nodes: Table,
    edges: Table,
}

#[derive(Default)]
pub(super) struct TableHandles {
    tables: futures::lock::Mutex<Option<CachedTables>>,
}

pub(super) enum TableLifecycle {
    Bootstrap,
    Clear,
}

impl LanceDbGraphStore {
    pub(super) async fn open_nodes(&self) -> Result<Table> {
        Ok(self.cached_handles().await?.nodes)
    }

    pub(super) async fn open_edges(&self) -> Result<Table> {
        Ok(self.cached_handles().await?.edges)
    }

    async fn cached_handles(&self) -> Result<CachedTables> {
        let mut cached = self.handles.tables.lock().await;
        if let Some(tables) = &*cached {
            return Ok(tables.clone());
        }
        let tables = CachedTables {
            nodes: self.open_table(&self.nodes_table_name()).await?,
            edges: self.open_table(&self.edges_table_name()).await?,
        };
        *cached = Some(tables.clone());
        Ok(tables)
    }

    pub(super) async fn maintain_tables(&self, operation: TableLifecycle) -> Result<()> {
        // Keep the async gate across table I/O: a concurrent first reader must
        // not republish handles opened before a clear/recreation completed.
        let mut cached = self.handles.tables.lock().await;
        *cached = None;
        // A recreated table starts its version count again, so a snapshot
        // keyed by the old tables' versions could match the new ones.
        self.reads.invalidate();
        if matches!(operation, TableLifecycle::Clear) {
            self.drop_table_if_exists(&self.edges_table_name()).await?;
            self.drop_table_if_exists(&self.nodes_table_name()).await?;
        }
        let nodes = self.nodes_table_name();
        if !self.table_exists(&nodes).await? {
            self.db
                .create_empty_table(&nodes, nodes_schema())
                .execute()
                .await
                .map_err(|err| {
                    GrustError::Backend(format!("failed to create LanceDB table {nodes}: {err}"))
                })?;
        }
        let edges = self.edges_table_name();
        if !self.table_exists(&edges).await? {
            self.db
                .create_empty_table(&edges, edges_schema())
                .execute()
                .await
                .map_err(|err| {
                    GrustError::Backend(format!("failed to create LanceDB table {edges}: {err}"))
                })?;
        }
        Ok(())
    }
}

#[cfg(test)]
#[path = "table_handles_tests.rs"]
mod tests;
