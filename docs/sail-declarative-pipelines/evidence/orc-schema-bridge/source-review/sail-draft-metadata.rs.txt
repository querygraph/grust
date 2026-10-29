use std::sync::Arc;

use arrow::array::{Array, ArrayRef, ListArray, MapArray, StructArray};
use arrow::compute::{CastOptions, cast_with_options};
use arrow::datatypes::{DataType, Field, SchemaRef, TimeUnit};
use arrow::record_batch::{RecordBatch, RecordBatchOptions};
use datafusion_common::{Result, exec_datafusion_err, exec_err};
use orc_rust::reader::metadata::FileMetadata;
use orc_rust::schema::{ArrowSchemaOptions, TimestampPrecision};
use sail_common_datafusion::array::record_batch::cast_array_recursively;

use super::schema::infer_schema;

/// The native decoding schema and Spark-facing schema for one validated ORC file.
/// Native readers must decode with microsecond timestamp precision. Logical type
/// conversion happens after decoding; an integer decoder must not receive a
/// timestamp field merely because the ORC type has a Spark annotation.
///
/// This bridge does not configure timestamp timezone rules or register a file
/// source. Ordinary ORC TIMESTAMP columns remain guarded during adaptation until
/// a qualified reader-timezone provider is wired into Sail; TIMESTAMP_INSTANT
/// already carries an instant and can be relabeled with the session timezone.
#[derive(Debug, Clone)]
pub struct OrcSchemaBridge {
    physical: SchemaRef,
    logical: SchemaRef,
}

impl OrcSchemaBridge {
    pub fn try_new(metadata: &FileMetadata, session_timezone: &str) -> Result<Self> {
        // Check Spark type support before native conversion, including decimal
        // ranges that the native schema representation does not validate.
        let logical = infer_schema(metadata, session_timezone)?;
        let physical = Arc::new(metadata.root_data_type().create_arrow_schema_with_options(
            &Default::default(),
            ArrowSchemaOptions::new().with_timestamp_precision(TimestampPrecision::Microsecond),
        ));
        Ok(Self { physical, logical })
    }

    pub fn physical_schema(&self) -> &SchemaRef {
        &self.physical
    }

    pub fn schema(&self) -> &SchemaRef {
        &self.logical
    }

    /// Project both schemas in the same order. A native ORC projection is a set
    /// in file order; callers must pass that order here before any final output
    /// projection restores reordered or repeated requested columns.
    pub fn project(&self, indices: &[usize]) -> Result<Self> {
        Ok(Self {
            physical: Arc::new(self.physical.project(indices)?),
            logical: Arc::new(self.logical.project(indices)?),
        })
    }

    pub fn adapt_batch(&self, batch: RecordBatch) -> Result<RecordBatch> {
        if batch.schema().fields() != self.physical.fields() {
            return exec_err!("ORC decoded batch does not match the physical schema");
        }
        let columns = batch
            .columns()
            .iter()
            .zip(self.logical.fields())
            .map(|(array, field)| adapt_array(array, field))
            .collect::<Result<Vec<_>>>()?;
        Ok(RecordBatch::try_new_with_options(
            self.logical.clone(),
            columns,
            &RecordBatchOptions::new().with_row_count(Some(batch.num_rows())),
        )?)
    }
}

fn adapt_array(array: &ArrayRef, target: &Field) -> Result<ArrayRef> {
    if array.data_type() == target.data_type() {
        return Ok(array.clone());
    }
    // Preserve structural positions, including duplicate field names, offsets
    // and parent validity. Schema evolution by name belongs to the file source
    // after this physical-to-logical conversion.
    match (array.data_type(), target.data_type()) {
        (DataType::Struct(_), DataType::Struct(fields)) => {
            let source = array
                .as_any()
                .downcast_ref::<StructArray>()
                .ok_or_else(|| {
                    exec_datafusion_err!("ORC struct has an unexpected array representation")
                })?;
            if source.num_columns() != fields.len() {
                return exec_err!("ORC struct field count changed during logical conversion");
            }
            let columns = source
                .columns()
                .iter()
                .zip(fields)
                .map(|(array, field)| adapt_array(array, field))
                .collect::<Result<Vec<_>>>()?;
            Ok(Arc::new(StructArray::try_new_with_length(
                fields.clone(),
                columns,
                source.nulls().cloned(),
                source.len(),
            )?))
        }
        (DataType::List(_), DataType::List(field)) => {
            let source = array.as_any().downcast_ref::<ListArray>().ok_or_else(|| {
                exec_datafusion_err!("ORC list has an unexpected array representation")
            })?;
            Ok(Arc::new(ListArray::try_new(
                field.clone(),
                source.offsets().clone(),
                adapt_array(source.values(), field)?,
                source.nulls().cloned(),
            )?))
        }
        (DataType::Map(_, _), DataType::Map(field, sorted)) => {
            let source = array.as_any().downcast_ref::<MapArray>().ok_or_else(|| {
                exec_datafusion_err!("ORC map has an unexpected array representation")
            })?;
            let entries = adapt_array(&(Arc::new(source.entries().clone()) as ArrayRef), field)?;
            let entries = entries
                .as_any()
                .downcast_ref::<StructArray>()
                .ok_or_else(|| {
                    exec_datafusion_err!("ORC map conversion did not produce struct entries")
                })?;
            Ok(Arc::new(MapArray::try_new(
                field.clone(),
                source.offsets().clone(),
                entries.clone(),
                source.nulls().cloned(),
                *sorted,
            )?))
        }
        (DataType::Int64, DataType::Time64(TimeUnit::Nanosecond)) => {
            // Spark stores ORC TIME as nanoseconds for every declared precision.
            // Declared precision is field metadata, not permission to round.
            let options = CastOptions {
                safe: false,
                ..Default::default()
            };
            Ok(cast_with_options(array, target.data_type(), &options)?)
        }
        (DataType::Timestamp(_, None), DataType::Timestamp(_, Some(_))) => {
            exec_err!("ORC LTZ timestamps require explicit native reader timezone decoding")
        }
        _ => {
            // In particular, reuse Sail's timestamp timezone relabeling, which
            // preserves the already-decoded instant rather than shifting it.
            cast_array_recursively(array, target.data_type())
        }
    }
}

#[cfg(test)]
#[path = "metadata_tests.rs"]
mod tests;
