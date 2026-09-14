//! ADBC bulk ingestion with native Arrow 59 readers.
//!
//! ADBC owns the database/connection/statement lifecycle, driver capabilities,
//! transactions, cancellation and errors. Grust only configures a bulk target
//! and passes the reader through unchanged. This is not an ADBC driver and does
//! not reinterpret append as graph upsert. See the [ADBC specification].
//!
//! [ADBC specification]: https://arrow.apache.org/adbc/current/format/specification.html
pub use adbc_core::options::IngestMode;
use adbc_core::{
    Statement,
    options::{OptionStatement, OptionValue},
};
use arrow_array::RecordBatchReader;

/// Bind a reader to a caller-owned ADBC statement and execute bulk ingestion.
///
/// Use a fresh statement, with its connection and optional catalog/schema
/// already configured by the caller. No SQL is generated. Driver failures and
/// unsupported options retain their original ADBC status and details. Unknown
/// affected counts remain `None`. A failed call may have changed the statement
/// or written data; transaction rollback belongs to the caller/driver.
///
/// Input is consumed synchronously on demand by the driver. Run blocking
/// drivers on a blocking thread rather than an async executor worker. Wrap the
/// source in [`crate::BatchReader`] when batch admission/slicing is required.
/// The driver decides whether it buffers internally or supports each mode.
pub fn ingest(
    statement: &mut impl Statement,
    target: &str,
    mode: IngestMode,
    reader: impl RecordBatchReader + Send + 'static,
) -> adbc_core::error::Result<Option<i64>> {
    statement.set_option(
        OptionStatement::TargetTable,
        OptionValue::String(target.to_owned()),
    )?;
    statement.set_option(OptionStatement::IngestMode, mode.into())?;
    statement.bind_stream(Box::new(reader))?;
    statement.execute_update()
}

#[cfg(test)]
#[path = "adbc_tests.rs"]
mod tests;
