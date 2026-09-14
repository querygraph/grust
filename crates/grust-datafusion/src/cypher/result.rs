//! Native Arrow to portable Cypher result conversion.
use datafusion::{
    arrow::{
        array::{Array, BooleanArray, Int64Array, StringArray},
        datatypes::DataType,
        record_batch::RecordBatch,
    },
    common::{DataFusionError, Result},
};
use grust_core::Value;
use grust_cypher::CypherResultTable;

/// Convert one native result batch to the ordinary Cypher table representation.
/// Column order/names, row multiplicity, nulls and exact Int64 values survive.
/// Types outside the compiler's scalar domain fail before allocating result rows;
/// this never coerces floating point, unsigned integers or nested values.
///
/// Strings and row vectors become owned. The caller must admit their allocation
/// and complete serialized output size; this conversion does not implement the
/// Cypher read policy. Prefer retaining native batches for Arrow/ADBC consumers.
pub fn decode_result_batch(batch: &RecordBatch) -> Result<CypherResultTable> {
    let columns = validated_columns(batch)?;
    Ok(decode_validated(batch, &columns))
}

fn validated_columns(batch: &RecordBatch) -> Result<Vec<Values<'_>>> {
    batch
        .columns()
        .iter()
        .map(|array| {
            let invalid = || {
                DataFusionError::Execution(format!(
                    "unsupported Cypher result type {}",
                    array.data_type()
                ))
            };
            match array.data_type() {
                DataType::Null => Ok(Values::Null),
                DataType::Boolean => array
                    .as_any()
                    .downcast_ref::<BooleanArray>()
                    .map(Values::Boolean)
                    .ok_or_else(invalid),
                DataType::Int64 => array
                    .as_any()
                    .downcast_ref::<Int64Array>()
                    .map(Values::Integer)
                    .ok_or_else(invalid),
                DataType::Utf8 => array
                    .as_any()
                    .downcast_ref::<StringArray>()
                    .map(Values::String)
                    .ok_or_else(invalid),
                _ => Err(invalid()),
            }
        })
        .collect()
}

fn decode_validated(batch: &RecordBatch, columns: &[Values<'_>]) -> CypherResultTable {
    CypherResultTable {
        columns: batch
            .schema()
            .fields()
            .iter()
            .map(|field| field.name().clone())
            .collect(),
        rows: (0..batch.num_rows())
            .map(|row| columns.iter().map(|column| column.value(row)).collect())
            .collect(),
    }
}

enum Values<'a> {
    Null,
    Boolean(&'a BooleanArray),
    Integer(&'a Int64Array),
    String(&'a StringArray),
}
impl Values<'_> {
    fn value(&self, row: usize) -> Value {
        match self {
            Self::Null => Value::Null,
            Self::Boolean(values) if !values.is_null(row) => Value::Bool(values.value(row)),
            Self::Integer(values) if !values.is_null(row) => Value::Int(values.value(row)),
            Self::String(values) if !values.is_null(row) => Value::String(values.value(row).into()),
            _ => Value::Null,
        }
    }
}

/// Decode after charging cumulative logical copy bytes to the shared execution.
/// Charges column-name storage, row containers, values and non-null UTF-8 bytes
/// from this batch's slice before allocating the portable table. The small
/// column-validation descriptors, Arrow input and allocator overhead are outside
/// this logical-copy measure. Charges remain consumed after the table is dropped.
/// This is materialization admission, not complete query/operator accounting.
pub fn decode_result_batch_with_context(
    batch: &RecordBatch,
    execution: &grust_procedures::ExecutionContext,
) -> Result<CypherResultTable> {
    execution.checkpoint().map_err(execution_error)?;
    let columns = validated_columns(batch)?;
    let overflow = || DataFusionError::Execution("Cypher result copy size overflow".into());
    let add = |a: usize, b: usize| a.checked_add(b).ok_or_else(overflow);
    let row_bytes = batch
        .num_columns()
        .checked_mul(std::mem::size_of::<Value>())
        .and_then(|bytes| bytes.checked_add(std::mem::size_of::<Vec<Value>>()))
        .ok_or_else(overflow)?;
    let mut bytes = batch
        .num_rows()
        .checked_mul(row_bytes)
        .ok_or_else(overflow)?;
    for field in batch.schema().fields() {
        bytes = add(bytes, std::mem::size_of::<String>())?;
        bytes = add(bytes, field.name().len())?;
    }
    for column in &columns {
        if let Values::String(values) = column {
            for row in 0..values.len() {
                if row % 1024 == 0 {
                    execution.checkpoint().map_err(execution_error)?;
                }
                if !values.is_null(row) {
                    bytes = add(bytes, values.value(row).len())?;
                }
            }
        }
    }
    execution
        .charge_cumulative_memory(bytes)
        .map_err(execution_error)?;
    Ok(decode_validated(batch, &columns))
}

fn execution_error(error: grust_procedures::ProcedureError) -> DataFusionError {
    DataFusionError::External(Box::new(error))
}
