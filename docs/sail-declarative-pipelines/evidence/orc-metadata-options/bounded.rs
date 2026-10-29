use arrow::json::{ArrayWriter, WriterBuilder};
use arrow::record_batch::RecordBatch;
use futures::TryStreamExt;
use orc_rust::reader::metadata::{
    read_metadata_async_with_options, read_metadata_with_options, FileMetadata, MetadataReadOptions,
};
use orc_rust::ArrowReaderBuilder;
use serde_json::{json, Value};
use std::error::Error;
use std::fs::File;
use std::sync::Arc;

type Result<T> = std::result::Result<T, Box<dyn Error>>;

fn options() -> MetadataReadOptions {
    MetadataReadOptions {
        max_encoded_metadata_bytes: Some(4 * 1024 * 1024),
        max_decoded_metadata_bytes: Some(4 * 1024 * 1024),
        max_schema_depth: Some(64),
    }
}

fn report(metadata: &FileMetadata, batches: &[RecordBatch]) -> Result<Value> {
    let mut writer: ArrayWriter<Vec<u8>> = WriterBuilder::new()
        .with_explicit_nulls(true)
        .build(Vec::new());
    writer.write_batches(&batches.iter().collect::<Vec<_>>())?;
    writer.finish()?;
    let rows: Value = serde_json::from_slice(&writer.into_inner())?;
    let types = metadata.column_types().iter().enumerate().map(|(index, ty)| {
        json!({"column_id": index, "kind": ty.kind, "children": ty.subtypes,
            "names": ty.field_names, "attributes": ty.attributes.iter().map(|attribute|
                json!({"key": attribute.key, "value": attribute.value})).collect::<Vec<_>>()})
    }).collect::<Vec<_>>();
    Ok(json!({"row_count": batches.iter().map(|batch| batch.num_rows()).sum::<usize>(),
        "rows": rows, "column_types": types, "encoded_limit": 4*1024*1024,
        "decoded_limit": 4*1024*1024, "depth_limit": 64}))
}

fn main() -> Result<()> {
    let args = std::env::args().collect::<Vec<_>>();
    let path = args.get(2).ok_or("missing path")?;
    let output = match args.get(1).map(String::as_str) {
        Some("sync") => {
            let mut reader = File::open(path)?;
            let metadata = Arc::new(read_metadata_with_options(&mut reader, options())?);
            let batches = ArrowReaderBuilder::new_with_metadata(reader, metadata.clone())
                .with_batch_size(2)
                .build()
                .collect::<std::result::Result<Vec<_>, _>>()?;
            report(&metadata, &batches)?
        }
        Some("async") => tokio::runtime::Builder::new_current_thread().build()?.block_on(async {
            let mut reader = tokio::fs::File::open(path).await?;
            let metadata = Arc::new(read_metadata_async_with_options(&mut reader, options()).await?);
            let batches = ArrowReaderBuilder::new_with_metadata(reader, metadata.clone())
                .with_batch_size(2)
                .build_async()
                .try_collect::<Vec<_>>()
                .await?;
            report(&metadata, &batches)
        })?,
        _ => return Err("usage: bounded sync|async FILE".into()),
    };
    println!("{}", serde_json::to_string_pretty(&output)?);
    Ok(())
}
