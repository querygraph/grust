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
    let columns = batch
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
        .collect::<Result<Vec<_>>>()?;
    Ok(CypherResultTable {
        columns: batch
            .schema()
            .fields()
            .iter()
            .map(|field| field.name().clone())
            .collect(),
        rows: (0..batch.num_rows())
            .map(|row| columns.iter().map(|column| column.value(row)).collect())
            .collect(),
    })
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
