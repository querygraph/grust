//! Native, pull-based Arrow pipelines; no graph or row materialization.
//!
//! A reader owns its current batch. Slices share its buffers and may keep the
//! entire allocation alive. The byte guard checks an incoming decoded batch,
//! before yielding any of it; it is not a sandbox for an upstream IPC decoder.
//! Consumption is synchronous and demand-driven. Dropping the reader drops
//! its source and pending batch; no background worker or prefetch is started.

use super::{array, ipc, schema};
use array::{Array, ArrayRef, RecordBatch, RecordBatchReader, StringArray};
use schema::{ArrowError, DataType, Field, Schema, SchemaRef};
use std::{
    io::{Read, Write},
    num::NonZeroUsize,
    sync::Arc,
};

/// A standard Arrow reader whose batches have bounded row counts.
///
/// This implements the reader accepted by ADBC `Statement::bind_stream`.
/// Driver and consumer must use the same Arrow major version.
pub struct BatchReader<R> {
    source: R,
    schema: SchemaRef,
    max_rows: NonZeroUsize,
    max_batch_bytes: NonZeroUsize,
    pending: Option<(RecordBatch, usize)>,
    finished: bool,
}

impl<R: RecordBatchReader> BatchReader<R> {
    /// Wrap a reader without reading it or copying its buffers.
    ///
    /// The memory bound counts Arrow's reported array memory per input batch
    /// (shared buffers may be counted more than once), not process RSS. Schema
    /// drift, oversized input batches, and source errors end the stream after
    /// yielding one error. Row slicing does not reduce backing allocations.
    pub fn new(source: R, max_rows: NonZeroUsize, max_batch_bytes: NonZeroUsize) -> Self {
        Self {
            schema: source.schema(),
            source,
            max_rows,
            max_batch_bytes,
            pending: None,
            finished: false,
        }
    }
}

impl<R: RecordBatchReader> Iterator for BatchReader<R> {
    type Item = Result<RecordBatch, ArrowError>;

    fn next(&mut self) -> Option<Self::Item> {
        if self.finished {
            return None;
        }
        loop {
            if let Some((batch, offset)) = self.pending.as_mut() {
                let len = self.max_rows.get().min(batch.num_rows() - *offset);
                let result = batch.slice(*offset, len);
                *offset += len;
                if *offset == batch.num_rows() {
                    self.pending = None;
                }
                return Some(Ok(result));
            }
            let next = match self.source.next() {
                None => {
                    self.finished = true;
                    return None;
                }
                Some(next) => next,
            };
            let checked = next.and_then(|batch| {
                if batch.schema() != self.schema {
                    return Err(ArrowError::SchemaError(
                        "Arrow pipeline schema changed".into(),
                    ));
                }
                let observed = batch.get_array_memory_size();
                if observed > self.max_batch_bytes.get() {
                    return Err(ArrowError::ExternalError(Box::new(
                        grust_core::GrustError::ResourceLimitExceeded {
                            resource: "Arrow input batch bytes",
                            limit: self.max_batch_bytes.get(),
                            observed,
                        },
                    )));
                }
                Ok(batch)
            });
            match checked {
                Err(error) => {
                    self.finished = true;
                    return Some(Err(error));
                }
                Ok(batch) if batch.num_rows() == 0 => continue,
                Ok(batch) => self.pending = Some((batch, 0)),
            }
        }
    }
}

impl<R: RecordBatchReader> RecordBatchReader for BatchReader<R> {
    fn schema(&self) -> SchemaRef {
        Arc::clone(&self.schema)
    }
}
impl<R: RecordBatchReader> std::iter::FusedIterator for BatchReader<R> {}

/// Export a reader through Arrow's standard C Stream Interface. The returned
/// object owns the reader and its release callback. No IPC or row conversion
/// occurs; upstream Arrow owns the FFI implementation. Foreign consumers must
/// obey Arrow C Stream ownership and release rules.
#[cfg(feature = "ffi")]
pub fn export_c_stream(
    reader: Box<dyn RecordBatchReader + Send>,
) -> array::ffi_stream::FFI_ArrowArrayStream {
    array::ffi_stream::FFI_ArrowArrayStream::new(reader)
}

/// Preserve typed Grust resource errors carried by a standard Arrow reader.
/// Other Arrow errors cross the graph API as serialization failures.
pub fn into_grust_error(error: ArrowError) -> grust_core::GrustError {
    match error {
        ArrowError::ExternalError(source) => match source.downcast::<grust_core::GrustError>() {
            Ok(error) => *error,
            Err(source) => grust_core::GrustError::Serialization(source.to_string()),
        },
        ArrowError::IoError(message, source) => {
            if let Some(grust_core::GrustError::ResourceLimitExceeded {
                resource,
                limit,
                observed,
            }) = source
                .get_ref()
                .and_then(|e| e.downcast_ref::<grust_core::GrustError>())
            {
                return grust_core::GrustError::ResourceLimitExceeded {
                    resource,
                    limit: *limit,
                    observed: *observed,
                };
            }
            grust_core::GrustError::Serialization(format!("{message}: {source}"))
        }
        error => grust_core::GrustError::Serialization(error.to_string()),
    }
}

/// Decode an IPC stream lazily into native Arrow batches.
///
/// Schema parsing happens now; batches are decoded as pulled. The caller must
/// limit untrusted encoded input and decoder allocations at its I/O boundary.
/// Wrap this in [`BatchReader`] to enforce decoded batch and output row limits.
pub fn read_ipc_stream(
    input: impl Read,
) -> Result<ipc::reader::StreamReader<impl Read>, ArrowError> {
    ipc::reader::StreamReader::try_new(input, None)
}

/// Write any standard Arrow reader as one IPC stream, preserving schema even
/// for an empty reader. Pulls one batch at a time, with no collection.
///
/// Earlier bytes remain written if the source or sink fails. A successful
/// return includes the end-of-stream marker; the caller owns sink durability.
pub fn write_ipc_stream(
    output: impl Write,
    mut source: impl RecordBatchReader,
) -> Result<(), ArrowError> {
    let schema = source.schema();
    let mut writer = ipc::writer::StreamWriter::try_new(output, &schema)?;
    for batch in &mut source {
        let batch = batch?;
        if batch.schema() != schema {
            return Err(ArrowError::SchemaError(
                "Arrow pipeline schema changed".into(),
            ));
        }
        writer.write(&batch)?;
    }
    writer.finish()
}

/// Encode one batch as a complete IPC stream. Encoding copies into the result;
/// use [`write_ipc_stream`] for a caller-owned sink or a multi-batch source.
pub fn batch_to_ipc(batch: &RecordBatch) -> Result<Vec<u8>, ArrowError> {
    let mut output = Vec::new();
    write_ipc_stream(
        &mut output,
        array::RecordBatchIterator::new(std::iter::once(Ok(batch.clone())), batch.schema()),
    )?;
    Ok(output)
}

/// Project and rename columns into a destination schema by source name.
///
/// Column buffers and nested types are retained. No cast or JSON conversion
/// occurs. Missing names, type mismatches, duplicate source names, and actual
/// nulls in a required destination column fail. Unselected columns are omitted
/// deliberately. `sources` is in destination field order.
pub fn project_batch(
    batch: &RecordBatch,
    destination: SchemaRef,
    sources: &[&str],
) -> Result<RecordBatch, ArrowError> {
    if destination.fields().len() != sources.len() {
        return Err(ArrowError::SchemaError(
            "projection field count mismatch".into(),
        ));
    }
    let input_schema = batch.schema();
    let mut columns = Vec::with_capacity(sources.len());
    for (field, name) in destination.fields().iter().zip(sources) {
        let mut matches = input_schema
            .fields()
            .iter()
            .enumerate()
            .filter(|(_, f)| f.name() == name);
        let (index, _) = matches
            .next()
            .ok_or_else(|| ArrowError::SchemaError(format!("missing column {name}")))?;
        if matches.next().is_some() {
            return Err(ArrowError::SchemaError(format!("ambiguous column {name}")));
        }
        let column = batch.column(index);
        if column.data_type() != field.data_type()
            || (!field.is_nullable() && column.null_count() != 0)
        {
            return Err(ArrowError::SchemaError(format!(
                "incompatible column {name}"
            )));
        }
        columns.push(Arc::clone(column));
    }
    let options = array::RecordBatchOptions::new().with_row_count(Some(batch.num_rows()));
    RecordBatch::try_new_with_options(destination, columns, &options)
}

/// Collect a reader only for APIs which require all batches simultaneously.
/// The inclusive bound sums reported array memory plus a RecordBatch header
/// per batch, so schema-only batches cannot accumulate without accounting.
/// Stops at the first error; no partial collection is returned. Upstream decode
/// allocations occur before this retained-memory check.
pub fn collect_batches(
    source: impl RecordBatchReader,
    max_bytes: NonZeroUsize,
) -> Result<Vec<RecordBatch>, ArrowError> {
    let schema = source.schema();
    let mut batches = Vec::new();
    let mut total = 0usize;
    for batch in source {
        let batch = batch?;
        if batch.schema() != schema {
            return Err(ArrowError::SchemaError(
                "Arrow pipeline schema changed".into(),
            ));
        }
        total = total
            .checked_add(
                batch
                    .get_array_memory_size()
                    .saturating_add(std::mem::size_of::<RecordBatch>()),
            )
            .ok_or_else(|| {
                ArrowError::ExternalError(Box::new(grust_core::GrustError::ResourceLimitExceeded {
                    resource: "Arrow retained batch bytes",
                    limit: max_bytes.get(),
                    observed: usize::MAX,
                }))
            })?;
        if total > max_bytes.get() {
            return Err(ArrowError::ExternalError(Box::new(
                grust_core::GrustError::ResourceLimitExceeded {
                    resource: "Arrow retained batch bytes",
                    limit: max_bytes.get(),
                    observed: total,
                },
            )));
        }
        batches.push(batch);
    }
    Ok(batches)
}

/// Build non-null UTF-8 columns without cloning each intermediate vector.
/// All columns must have equal lengths. Values are copied once into Arrow.
pub fn string_batch(columns: &[(&str, Vec<&str>)]) -> Result<RecordBatch, ArrowError> {
    let fields = columns
        .iter()
        .map(|(name, _)| Field::new(*name, DataType::Utf8, false))
        .collect::<Vec<_>>();
    let arrays = columns
        .iter()
        .map(|(_, values)| {
            Arc::new(StringArray::from_iter_values(values.iter().copied())) as ArrayRef
        })
        .collect();
    RecordBatch::try_new(Arc::new(Schema::new(fields)), arrays)
}

#[cfg(test)]
#[path = "pipeline_tests.rs"]
mod tests;
