//! Shared DataFusion 55 execution over Grust's native Arrow 59 tables.
//!
//! This optional foundation uses upstream schemas, table providers, DataFrames
//! and result streams. It does not duplicate a SQL planner or lower graph
//! kernels into joins. Backend-specific providers retain their pushdown rules.
//! Working-memory admission and optional disk spill are explicit; registered
//! input buffers and caller-retained output remain caller-owned admission.
use datafusion::{
    catalog::{
        CatalogProvider, MemoryCatalogProvider, SchemaProvider, memory::MemorySchemaProvider,
    },
    common::{Result, TableReference},
    dataframe::DataFrame,
    datasource::{MemTable, TableProvider},
    execution::{
        context::{SQLOptions, SessionConfig, SessionContext},
        disk_manager::{DiskManagerBuilder, DiskManagerMode},
        memory_pool::GreedyMemoryPool,
        runtime_env::RuntimeEnvBuilder,
    },
    physical_plan::SendableRecordBatchStream,
};
use grust_arrow::{ArrowGraphTables, ArrowTable};
use std::{
    num::{NonZeroU64, NonZeroUsize},
    path::PathBuf,
    sync::Arc,
};

mod blocking_reader;
pub use blocking_reader::BlockingReader;
/// Re-export upstream DataFusion 55 for expression/provider extensions, without
/// creating a parallel set of traits or requiring consumers to guess versions.
pub use datafusion;

/// Explicit temporary-storage policy for operators that can spill.
#[derive(Clone, Debug)]
pub enum SpillPolicy {
    /// Fail when an operator cannot remain within its working-memory budget.
    Disabled,
    /// Spill only into this directory, subject to DataFusion's directory limit.
    Directory {
        path: PathBuf,
        max_bytes: NonZeroU64,
    },
}
/// Runtime settings shared by all queries in an engine.
#[derive(Clone, Debug)]
pub struct ExecutionOptions {
    /// DataFusion's tracked working-memory pool. Not a whole-process RSS cap:
    /// upstream does not account for every allocation, nor caller-owned tables.
    pub working_memory_bytes: NonZeroUsize,
    /// Parallelism target for plans and native table partitioning.
    pub target_partitions: NonZeroUsize,
    /// Desired output batch size; upstream operators may have their own bounds.
    pub batch_rows: NonZeroUsize,
    /// Temporary-file admission, disabled unless explicitly selected.
    pub spill: SpillPolicy,
}

/// An Arrow query engine with one shared runtime and extensible upstream context.
/// Clone the context handle when composing native DataFusion extensions. The
/// read-only query methods restrict SQL mutations but are not a security sandbox
/// for caller-registered table providers, functions or external object stores.
pub struct DataFusionEngine {
    context: SessionContext,
    partitions: NonZeroUsize,
}
impl DataFusionEngine {
    /// Construct a DataFusion 55 runtime with explicit resource settings.
    pub fn new(options: ExecutionOptions) -> Result<Self> {
        let disk = match options.spill {
            SpillPolicy::Disabled => {
                DiskManagerBuilder::default().with_mode(DiskManagerMode::Disabled)
            }
            SpillPolicy::Directory { path, max_bytes } => DiskManagerBuilder::default()
                .with_mode(DiskManagerMode::Directories(vec![path]))
                .with_max_temp_directory_size(max_bytes.get()),
        };
        let runtime = RuntimeEnvBuilder::new()
            .with_memory_pool(Arc::new(GreedyMemoryPool::new(
                options.working_memory_bytes.get(),
            )))
            .with_disk_manager_builder(disk)
            .build_arc()?;
        let config = SessionConfig::new()
            .with_target_partitions(options.target_partitions.get())
            .with_batch_size(options.batch_rows.get());
        Ok(Self {
            context: SessionContext::new_with_config_rt(config, runtime),
            partitions: options.target_partitions,
        })
    }
    /// Access the upstream extension surface for functions, catalogs, object
    /// stores and providers. Extensions retain their native DataFusion contracts.
    pub fn context(&self) -> &SessionContext {
        &self.context
    }
    /// Register immutable native Arrow batches with no buffer or IPC copy.
    /// Batches are distributed across up to `target_partitions` partitions.
    /// SQL row order remains unspecified unless explicitly ordered in the query.
    /// Existing-name behavior follows the target upstream schema provider.
    pub fn register_table(
        &self,
        name: impl Into<TableReference>,
        table: ArrowTable,
    ) -> Result<Option<Arc<dyn TableProvider>>> {
        self.register_provider(name, self.table_provider(table)?)
    }
    /// Register an upstream provider, preserving its own projection/filter
    /// pushdown and scan implementation. Providers must use DataFusion 55 types.
    pub fn register_provider(
        &self,
        name: impl Into<TableReference>,
        provider: Arc<dyn TableProvider>,
    ) -> Result<Option<Arc<dyn TableProvider>>> {
        self.context.register_table(name, provider)
    }
    /// Install a validated graph as `<catalog>.graph.nodes` and `.edges`.
    /// Both providers are built before the single catalog replacement. Returns
    /// the previous catalog when replacing one; no graph buffer is re-encoded.
    /// This is session registration, not a write to any persistent backend.
    pub fn register_graph(
        &self,
        catalog_name: &str,
        graph: ArrowGraphTables,
    ) -> Result<Option<Arc<dyn CatalogProvider>>> {
        let (nodes, edges) = graph.into_tables();
        let nodes = self.table_provider(nodes)?;
        let edges = self.table_provider(edges)?;
        let schema = Arc::new(MemorySchemaProvider::new());
        schema.register_table("nodes".into(), nodes)?;
        schema.register_table("edges".into(), edges)?;
        let catalog = Arc::new(MemoryCatalogProvider::new());
        catalog.register_schema("graph", schema)?;
        Ok(self.context.register_catalog(catalog_name, catalog))
    }
    /// Parse a read-only SQL query into an upstream DataFrame, allowing callers
    /// to compose expressions, inspect optimized plans or choose result handling.
    /// Grust Cypher has separate semantics; this method accepts SQL explicitly.
    pub async fn dataframe(&self, sql: &str) -> Result<DataFrame> {
        let options = SQLOptions::new()
            .with_allow_ddl(false)
            .with_allow_dml(false)
            .with_allow_statements(false);
        self.context.sql_with_options(sql, options).await
    }
    /// Execute read-only SQL as a demand-driven native Arrow stream.
    /// Drop the stream to release its plan/resources; no collection is implicit.
    pub async fn execute_stream(&self, sql: &str) -> Result<SendableRecordBatchStream> {
        self.dataframe(sql).await?.execute_stream().await
    }
    fn table_provider(&self, table: ArrowTable) -> Result<Arc<dyn TableProvider>> {
        let schema = table.schema();
        let batches = table.into_batches();
        let count = self.partitions.get().min(batches.len().max(1));
        let mut partitions = (0..count).map(|_| Vec::new()).collect::<Vec<_>>();
        for (i, batch) in batches.into_iter().enumerate() {
            partitions[i % count].push(batch);
        }
        Ok(Arc::new(MemTable::try_new(schema, partitions)?))
    }
}

#[cfg(test)]
mod tests;
