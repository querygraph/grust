//! Reader-based Arrow registration for embedded Ladybug.
use super::{LadybugGraphStore, ladybug_error};
use arrow::array::RecordBatchReader;
use grust_arrow::v55::{collect_batches, into_grust_error};
use grust_core::Result;
use std::num::NonZeroUsize;

impl LadybugGraphStore {
    /// Register native Arrow batches as a queryable node table, with no IPC
    /// encode/decode. The first column is the primary key. Arbitrary native
    /// Arrow columns are passed to the engine without row conversion.
    ///
    /// Ladybug registration requires all batches at once and can retain their
    /// buffers until the table is dropped. `max_bytes` bounds the conservative
    /// sum of decoded input array memory plus batch headers before registration.
    /// This is a query
    /// table registration, not a persisted GraphStore upsert or implicit COPY.
    pub fn register_arrow_node_reader(
        &self,
        table_name: &str,
        reader: impl RecordBatchReader,
        max_bytes: NonZeroUsize,
    ) -> Result<()> {
        let batches = collect_batches(reader, max_bytes).map_err(into_grust_error)?;
        self.with_conn(|conn| {
            conn.create_arrow_table(table_name, &batches)
                .map(drop)
                .map_err(ladybug_error)
        })
    }

    /// Register relationship batches without IPC, using `from`/`to` endpoint
    /// columns and separately registered source/destination node tables.
    /// Retention and byte admission follow [`Self::register_arrow_node_reader`].
    pub fn register_arrow_rel_reader(
        &self,
        table_name: &str,
        reader: impl RecordBatchReader,
        src_table_name: &str,
        dst_table_name: &str,
        max_bytes: NonZeroUsize,
    ) -> Result<()> {
        let batches = collect_batches(reader, max_bytes).map_err(into_grust_error)?;
        self.with_conn(|conn| {
            conn.create_arrow_rel_table(table_name, &batches, src_table_name, dst_table_name)
                .map(drop)
                .map_err(ladybug_error)
        })
    }

    /// Consume native Arrow query batches as they arrive, without IPC or
    /// collecting the full result. Returning an error from `consume` stops the
    /// query iteration. The connection remains borrowed for this synchronous
    /// callback; do not reenter this store from the callback.
    pub fn visit_arrow_batches(
        &self,
        query: &str,
        chunk_size: NonZeroUsize,
        mut consume: impl FnMut(arrow::array::RecordBatch) -> Result<()>,
    ) -> Result<()> {
        self.with_conn(|conn| {
            let mut result = conn
                .query_as_arrow(query, chunk_size.get())
                .map_err(ladybug_error)?;
            for batch in result.iter_arrow(chunk_size.get()).map_err(ladybug_error)? {
                consume(batch)?;
            }
            Ok(())
        })
    }
}
