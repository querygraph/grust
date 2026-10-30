#![expect(clippy::unwrap_used)]

use arrow::array::{ArrayRef, Int64Array};
use arrow::datatypes::{DataType, Field};
use arrow::record_batch::{RecordBatch, RecordBatchOptions};
use bytes::Bytes;
use datafusion::execution::context::{SessionConfig, SessionContext};
use datafusion::logical_expr::TableSource;
use datafusion_common::Constraints;
use datafusion_datasource::ListingTableUrl;
use object_store::memory::InMemory;
use object_store::path::Path;
use object_store::{ObjectMeta, ObjectStore, ObjectStoreExt};
use orc_rust::{ArrowWriterBuilder, proto};
use prost013::Message;
use sail_common_datafusion::datasource::{DataSource, OptionLayer, SourceInfo};
use url::Url;

use super::*;
use crate::formats::orc::OrcDataSource;
use crate::options::{ResolveOptions, option_list};

#[path = "read_inference_tests.rs"]
mod inference;
#[path = "read_listing_tests.rs"]
mod listing;
#[path = "read_resource_tests.rs"]
mod resources;
#[path = "read_test_store.rs"]
mod store;

use store::ObservedStore;

fn file(schema: Schema, columns: Vec<ArrayRef>, rows: usize) -> Bytes {
    let schema = Arc::new(schema);
    let batch = RecordBatch::try_new_with_options(
        schema.clone(),
        columns,
        &RecordBatchOptions::new().with_row_count(Some(rows)),
    )
    .unwrap();
    let mut bytes = Vec::new();
    let mut writer = ArrowWriterBuilder::new(&mut bytes, schema)
        .try_build()
        .unwrap();
    writer.write(&batch).unwrap();
    writer.close().unwrap();
    Bytes::from(bytes)
}

fn integers(name: &str, values: Vec<i64>) -> Bytes {
    let rows = values.len();
    file(
        Schema::new(vec![Field::new(name, DataType::Int64, true)]),
        vec![Arc::new(Int64Array::from(values))],
        rows,
    )
}

fn annotate_time(bytes: &Bytes, precision: i32) -> Bytes {
    // Controlled foreign ORC fixture: actual encoded LONG data, with the same
    // Catalyst type attribute used by the separately retained Spark fixtures.
    let length = usize::from(bytes[bytes.len() - 1]);
    let start = bytes.len() - 1 - length;
    let mut postscript = proto::PostScript::decode(&bytes[start..bytes.len() - 1]).unwrap();
    assert_eq!(postscript.compression(), proto::CompressionKind::None);
    let footer_start = start - usize::try_from(postscript.footer_length()).unwrap();
    let mut footer = proto::Footer::decode(&bytes[footer_start..start]).unwrap();
    assert_eq!(footer.types.len(), 2);
    footer.types[1].attributes.push(proto::StringPair {
        key: Some("spark.sql.catalyst.type".into()),
        value: Some(format!("time({precision})")),
    });
    let footer = footer.encode_to_vec();
    postscript.footer_length = Some(footer.len() as u64);
    let postscript = postscript.encode_to_vec();
    let mut result = bytes[..footer_start].to_vec();
    result.extend(footer);
    result.extend(&postscript);
    result.push(postscript.len().try_into().unwrap());
    Bytes::from(result)
}

fn format(ctx: &dyn Session, options: Vec<OptionLayer>) -> OrcReadFormat {
    OrcReadFormat {
        options: OrcReadOptions::resolve(ctx, options.clone()).unwrap(),
        listing_options: OrcListingReadOptions::resolve(ctx, options).unwrap(),
        reader_timezone: OrcJavaTimeZoneConfig::for_reader_timezone("UTC".into()).unwrap(),
        session_timezone: "UTC".into(),
    }
}

fn request(schema: Option<Schema>, options: Vec<OptionLayer>, case_sensitive: bool) -> SourceInfo {
    SourceInfo {
        paths: vec!["memory://orc-read/data/".into()],
        lakehouse_table: None,
        schema,
        constraints: Constraints::default(),
        partition_by: vec![],
        bucket_by: None,
        sort_order: vec![],
        options,
        read_case_sensitive: case_sensitive,
    }
}

struct Fixture {
    context: SessionContext,
    store: Arc<ObservedStore>,
}

impl Fixture {
    fn new() -> Self {
        let context = SessionContext::new_with_config(
            SessionConfig::new()
                .with_collect_statistics(false)
                .with_target_partitions(1),
        );
        let store = Arc::new(ObservedStore::default());
        context.register_object_store(&Url::parse("memory://orc-read").unwrap(), store.clone());
        Self { context, store }
    }

    async fn put(&self, name: &str, bytes: Bytes) -> ObjectMeta {
        let path = Path::from(format!("data/{name}"));
        self.store.inner.put(&path, bytes.into()).await.unwrap();
        self.store.inner.head(&path).await.unwrap()
    }

    async fn source(
        &self,
        schema: Option<Schema>,
        options: Vec<OptionLayer>,
        case_sensitive: bool,
    ) -> Result<Arc<dyn TableSource>> {
        OrcDataSource::default()
            .create_source(
                &self.context.state(),
                request(schema, options, case_sensitive),
            )
            .await
    }

    async fn infer(&self, format: &OrcReadFormat, objects: Vec<ObjectMeta>) -> Result<SchemaRef> {
        let url = ListingTableUrl::parse("memory://orc-read/data/").unwrap();
        format
            .infer_schema(
                &self.context.state(),
                &[ListingFileSample {
                    url: &url,
                    store: self.store.clone(),
                    objects,
                }],
                CompressionTypeVariant::UNCOMPRESSED,
                true,
            )
            .await
    }
}
