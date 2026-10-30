use std::sync::Arc;

use datafusion::common::Result;
use sail_common_datafusion::datasource::DataSourceRegistry;
use sail_data_source::formats::arrow::ArrowDataSource;
use sail_data_source::formats::avro::AvroDataSource;
use sail_data_source::formats::binary::BinaryDataSource;
use sail_data_source::formats::console::ConsoleDataSource;
use sail_data_source::formats::csv::CsvDataSource;
use sail_data_source::formats::json::JsonDataSource;
use sail_data_source::formats::noop::NoopDataSource;
use sail_data_source::formats::orc::OrcDataSource;
use sail_data_source::formats::parquet::ParquetDataSource;
use sail_data_source::formats::python::{PythonDataSourceAdapter, discover_data_sources};
use sail_data_source::formats::rate::RateDataSource;
use sail_data_source::formats::socket::SocketDataSource;
use sail_data_source::formats::text::TextDataSource;
use sail_delta_lake::DeltaLakeSource;
use sail_iceberg::IcebergLakeSource;

pub(crate) fn create_data_source_registry() -> Result<Arc<DataSourceRegistry>> {
    let registry = Arc::new(DataSourceRegistry::new());
    register_builtin_data_sources(&registry)?;
    register_external_data_sources(&registry)?;
    Ok(registry)
}

fn register_builtin_data_sources(registry: &DataSourceRegistry) -> Result<()> {
    registry.register_data_source(Arc::new(ArrowDataSource::default()))?;
    registry.register_data_source(Arc::new(AvroDataSource::default()))?;
    registry.register_data_source(Arc::new(BinaryDataSource::default()))?;
    registry.register_data_source(Arc::new(CsvDataSource::default()))?;
    registry.register_data_source(Arc::new(JsonDataSource::default()))?;
    registry.register_data_source(Arc::new(OrcDataSource::default()))?;
    registry.register_data_source(Arc::new(ParquetDataSource::default()))?;
    registry.register_data_source(Arc::new(TextDataSource::default()))?;
    registry.register_data_source(Arc::new(SocketDataSource))?;
    registry.register_data_source(Arc::new(RateDataSource))?;
    registry.register_data_source(Arc::new(ConsoleDataSource))?;
    registry.register_data_source(Arc::new(NoopDataSource))?;
    registry.register_data_source(Arc::new(DeltaLakeSource))?;
    registry.register_data_source(Arc::new(IcebergLakeSource))?;
    Ok(())
}

fn register_external_data_sources(registry: &DataSourceRegistry) -> Result<()> {
    // Register Python data sources
    {
        discover_data_sources()?;
        PythonDataSourceAdapter::register_all(registry)?;
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use datafusion::logical_expr::LogicalPlanBuilder;
    use datafusion::prelude::SessionContext;
    use datafusion_common::DataFusionError;
    use sail_common_datafusion::datasource::{OptionLayer, SinkInfo, SinkMode};

    use super::*;

    #[test]
    fn separates_data_sources_from_lake_sources() -> Result<()> {
        let registry = DataSourceRegistry::new();
        register_builtin_data_sources(&registry)?;

        for name in ["orc", "parquet", "rate", "console"] {
            assert!(registry.get_data_source(name).is_ok());
            assert!(registry.get_lake_source(name).is_err());
        }
        for name in ["delta", "iceberg"] {
            assert!(registry.get_data_source(name).is_ok());
            assert!(registry.get_lake_source(name).is_ok());
        }
        Ok(())
    }

    #[tokio::test]
    async fn registered_orc_source_rejects_writing() -> Result<()> {
        let registry = DataSourceRegistry::new();
        register_builtin_data_sources(&registry)?;
        let directory = tempfile::tempdir()?;
        let output = directory.path().join("output");
        let context = SessionContext::new();
        let result = registry
            .get_data_source("orc")?
            .create_writer(
                &context.state(),
                SinkInfo {
                    input: LogicalPlanBuilder::empty(true).build()?,
                    mode: SinkMode::Append,
                    partition_by: vec![],
                    bucket_by: None,
                    sort_order: vec![],
                    options: vec![OptionLayer::OptionList {
                        items: vec![("path".to_string(), output.to_string_lossy().into_owned())],
                    }],
                    lakehouse_table: None,
                },
            )
            .await;
        assert!(matches!(
            result,
            Err(DataFusionError::NotImplemented(message)) if message == "ORC writing is not implemented"
        ));
        assert!(!output.exists());
        Ok(())
    }
}
