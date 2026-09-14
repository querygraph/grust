//! Immutable multi-batch Arrow tables with standard-reader composition.
use super::{array, collect_batches, into_grust_error, schema};
use array::{RecordBatch, RecordBatchIterator, RecordBatchReader};
use grust_core::{GrustError, Result};
use schema::SchemaRef;
use std::{num::NonZeroUsize, sync::Arc};

/// An immutable table that preserves batch boundaries and shares Arrow buffers.
/// Schema equality is checked once on construction, including field metadata.
/// It accepts every Arrow data type; this type has no graph-specific semantics.
#[derive(Clone, Debug)]
pub struct ArrowTable {
    schema: SchemaRef,
    batches: Vec<RecordBatch>,
    rows: usize,
}
impl ArrowTable {
    /// Validate a caller-owned collection, including an empty schema-only table.
    /// No batch payload is copied. Row-count overflow fails explicitly.
    pub fn try_new(schema: SchemaRef, batches: Vec<RecordBatch>) -> Result<Self> {
        let mut rows = 0usize;
        for batch in &batches {
            if batch.schema() != schema {
                return Err(GrustError::Schema("Arrow table schema changed".into()));
            }
            rows = rows
                .checked_add(batch.num_rows())
                .ok_or(GrustError::ResourceLimitExceeded {
                    resource: "Arrow table rows",
                    limit: usize::MAX,
                    observed: usize::MAX,
                })?;
        }
        Ok(Self {
            schema,
            batches,
            rows,
        })
    }
    /// Retain a standard reader's batches under a conservative total byte limit.
    /// Decoding is upstream; this bounds retained array memory, not decoder RSS.
    pub fn read(source: impl RecordBatchReader, max_bytes: NonZeroUsize) -> Result<Self> {
        let schema = source.schema();
        Self::try_new(
            schema,
            collect_batches(source, max_bytes).map_err(into_grust_error)?,
        )
    }
    /// The exact shared schema, including extension metadata.
    pub fn schema(&self) -> SchemaRef {
        Arc::clone(&self.schema)
    }
    /// Original batches in input order. Borrowing does not copy buffers.
    pub fn batches(&self) -> &[RecordBatch] {
        &self.batches
    }
    /// Total number of rows across all batches.
    pub fn num_rows(&self) -> usize {
        self.rows
    }
    /// Transfer the original batches to a provider that owns their lifecycle.
    /// Schema remains available through each batch; read `schema()` first for a
    /// schema-only empty table.
    pub fn into_batches(self) -> Vec<RecordBatch> {
        self.batches
    }
    /// Transfer batches into a standard Arrow reader, suitable for ADBC binding.
    /// This does not concatenate or re-encode buffers.
    pub fn into_reader(self) -> impl RecordBatchReader + Send + 'static {
        RecordBatchIterator::new(self.batches.into_iter().map(Ok), self.schema)
    }
}

impl From<RecordBatch> for ArrowTable {
    fn from(batch: RecordBatch) -> Self {
        Self {
            schema: batch.schema(),
            rows: batch.num_rows(),
            batches: vec![batch],
        }
    }
}
