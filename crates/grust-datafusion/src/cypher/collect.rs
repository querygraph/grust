//! Incremental portable result collection with explicit output limits.
use super::{decode_result_batch, decode_result_batch_with_context};
use datafusion::{
    common::{DataFusionError, Result},
    dataframe::DataFrame,
};
use futures::TryStreamExt;
use grust_cypher::CypherResultTable;
use grust_procedures::ExecutionContext;
use std::io::{self, Write};

/// Collect a typed plan while enforcing cumulative result rows and serialized
/// JSON bytes (`{"columns":...,"rows":...}`, matching the Cypher read policy).
/// An over-limit batch is never appended. Row limits are checked before decoding;
/// byte counting serializes into a bounded counter without a JSON allocation.
/// Errors abort collection without returning partial results or retrying.
///
/// This bounds output, not the entire execution. One decoded batch, input buffers,
/// DataFusion working memory, candidate work and deadlines need separate admission.
/// Native Arrow/ADBC consumers need not use this owning row conversion.
pub async fn collect_result(
    frame: DataFrame,
    max_rows: usize,
    max_output_bytes: usize,
) -> Result<CypherResultTable> {
    collect(frame, max_rows, max_output_bytes, None).await
}

/// Collect with shared cancellation/deadline and cumulative portable-copy
/// admission. Operator memory/work and caller-owned Arrow input remain separate.
pub async fn collect_result_with_context(
    frame: DataFrame,
    max_rows: usize,
    max_output_bytes: usize,
    execution: &ExecutionContext,
) -> Result<CypherResultTable> {
    crate::run_cancellable(
        execution,
        collect(frame, max_rows, max_output_bytes, Some(execution)),
    )
    .await
}

async fn collect(
    frame: DataFrame,
    max_rows: usize,
    max_output_bytes: usize,
    execution: Option<&ExecutionContext>,
) -> Result<CypherResultTable> {
    if let Some(execution) = execution {
        let bytes = frame
            .schema()
            .fields()
            .iter()
            .try_fold(0usize, |bytes, field| {
                bytes
                    .checked_add(std::mem::size_of::<String>())
                    .and_then(|bytes| bytes.checked_add(field.name().len()))
                    .ok_or_else(|| {
                        DataFusionError::Execution("Cypher column copy size overflow".into())
                    })
            })?;
        execution
            .charge_cumulative_memory(bytes)
            .map_err(|error| DataFusionError::External(Box::new(error)))?;
    }
    let mut table = CypherResultTable {
        columns: frame
            .schema()
            .fields()
            .iter()
            .map(|field| field.name().clone())
            .collect(),
        rows: Vec::new(),
    };
    let mut counter = OutputCounter {
        remaining: max_output_bytes,
    };
    let error =
        |error| DataFusionError::Execution(format!("Cypher output encoding failed: {error}"));
    counter
        .write_all(b"{\"columns\":")
        .map_err(|e| error(e.to_string()))?;
    serde_json::to_writer(&mut counter, &table.columns).map_err(|e| error(e.to_string()))?;
    // Precharge the closing delimiters even when execution produces no batches.
    counter
        .write_all(b",\"rows\":[]}")
        .map_err(|e| error(e.to_string()))?;
    let mut stream = frame.execute_stream().await?;
    while let Some(batch) = stream.try_next().await? {
        if batch.num_rows() > max_rows.saturating_sub(table.rows.len()) {
            return Err(DataFusionError::Execution(format!(
                "Cypher output exceeds {max_rows} rows"
            )));
        }
        let decoded = match execution {
            Some(execution) => decode_result_batch_with_context(&batch, execution)?,
            None => decode_result_batch(&batch)?,
        };
        if decoded.columns != table.columns {
            return Err(DataFusionError::Execution(
                "Cypher output schema changed during execution".into(),
            ));
        }
        let mut has_rows = !table.rows.is_empty();
        for row in &decoded.rows {
            if has_rows {
                counter.write_all(b",").map_err(|e| error(e.to_string()))?;
            }
            serde_json::to_writer(&mut counter, row).map_err(|e| error(e.to_string()))?;
            has_rows = true;
        }
        if let Some(execution) = execution {
            let bytes = decoded
                .rows
                .len()
                .checked_mul(std::mem::size_of::<Vec<grust_core::Value>>())
                .ok_or_else(|| {
                    DataFusionError::Execution("Cypher row copy size overflow".into())
                })?;
            execution
                .charge_cumulative_memory(bytes)
                .map_err(|error| DataFusionError::External(Box::new(error)))?;
        }
        table.rows.extend(decoded.rows);
    }
    Ok(table)
}

struct OutputCounter {
    remaining: usize,
}
impl Write for OutputCounter {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        self.remaining = self
            .remaining
            .checked_sub(bytes.len())
            .ok_or_else(|| io::Error::other("serialized output limit exceeded"))?;
        Ok(bytes.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}
