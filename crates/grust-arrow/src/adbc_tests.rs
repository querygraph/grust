use super::*;
use adbc_core::{
    Optionable, PartitionedResult,
    error::{Error, Result, Status},
};
use arrow_array::{ArrayRef, Int64Array, RecordBatch, RecordBatchIterator};
use arrow_schema::Schema;
use std::sync::Arc;

#[derive(Default)]
struct StatementProbe {
    options: Vec<(OptionStatement, OptionValue)>,
    reader: Option<Box<dyn RecordBatchReader + Send>>,
    observed: Vec<RecordBatch>,
    reject_options: bool,
}
fn unsupported<T>() -> Result<T> {
    Err(Error::with_message_and_status(
        "unsupported",
        Status::NotImplemented,
    ))
}
impl Optionable for StatementProbe {
    type Option = OptionStatement;
    fn set_option(&mut self, key: OptionStatement, value: OptionValue) -> Result<()> {
        if self.reject_options {
            return unsupported();
        }
        self.options.push((key, value));
        Ok(())
    }
    fn get_option_string(&self, _: OptionStatement) -> Result<String> {
        unsupported()
    }
    fn get_option_bytes(&self, _: OptionStatement) -> Result<Vec<u8>> {
        unsupported()
    }
    fn get_option_int(&self, _: OptionStatement) -> Result<i64> {
        unsupported()
    }
    fn get_option_double(&self, _: OptionStatement) -> Result<f64> {
        unsupported()
    }
}
impl Statement for StatementProbe {
    fn bind(&mut self, _: RecordBatch) -> Result<()> {
        unsupported()
    }
    fn bind_stream(&mut self, reader: Box<dyn RecordBatchReader + Send>) -> Result<()> {
        self.reader = Some(reader);
        Ok(())
    }
    fn execute_update(&mut self) -> Result<Option<i64>> {
        let reader = self.reader.take().expect("reader bound before execute");
        self.observed = reader
            .map(|b| {
                b.map_err(|e| Error::with_message_and_status(e.to_string(), Status::InvalidData))
            })
            .collect::<Result<Vec<_>>>()?;
        Ok(None)
    }
    fn execute(&mut self) -> Result<Box<dyn RecordBatchReader + Send>> {
        unsupported()
    }
    fn execute_schema(&mut self) -> Result<Schema> {
        unsupported()
    }
    fn execute_partitions(&mut self) -> Result<PartitionedResult> {
        unsupported()
    }
    fn get_parameter_schema(&self) -> Result<Schema> {
        unsupported()
    }
    fn prepare(&mut self) -> Result<()> {
        unsupported()
    }
    fn set_sql_query(&mut self, _: impl AsRef<str>) -> Result<()> {
        unsupported()
    }
    fn set_substrait_plan(&mut self, _: impl AsRef<[u8]>) -> Result<()> {
        unsupported()
    }
    fn cancel(&mut self) -> Result<()> {
        unsupported()
    }
}
fn source() -> (RecordBatch, impl RecordBatchReader + Send) {
    let batch =
        RecordBatch::try_from_iter([("n", Arc::new(Int64Array::from(vec![1, 2, 3])) as ArrayRef)])
            .unwrap();
    let reader =
        RecordBatchIterator::new(vec![Ok(batch.clone()), Ok(batch.clone())], batch.schema());
    (batch, reader)
}
#[test]
fn native_adbc_binding_preserves_batches_buffers_and_unknown_count() {
    let (batch, reader) = source();
    let mut statement = StatementProbe::default();
    assert_eq!(
        ingest(&mut statement, "target", IngestMode::Append, reader).unwrap(),
        None
    );
    assert_eq!(statement.observed, [batch.clone(), batch.clone()]);
    assert!(Arc::ptr_eq(
        statement.observed[0].column(0),
        batch.column(0)
    ));
    assert_eq!(statement.options.len(), 2);
    assert!(
        matches!(&statement.options[0], (OptionStatement::TargetTable, OptionValue::String(value)) if value == "target")
    );
    assert!(
        matches!(&statement.options[1], (OptionStatement::IngestMode, OptionValue::String(value)) if value == "adbc.ingest.mode.append")
    );
}
#[test]
fn driver_rejection_keeps_adbc_status_and_does_not_bind() {
    let (_, reader) = source();
    let mut statement = StatementProbe {
        reject_options: true,
        ..Default::default()
    };
    let error = ingest(&mut statement, "target", IngestMode::Create, reader).unwrap_err();
    assert_eq!(error.status, Status::NotImplemented);
    assert!(statement.reader.is_none());
    assert!(statement.observed.is_empty());
}
