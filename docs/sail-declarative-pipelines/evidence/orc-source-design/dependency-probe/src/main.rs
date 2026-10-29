use arrow::{
    array::{ArrayRef, BooleanArray, Int64Array, RecordBatch, StringArray},
    datatypes::{DataType, Field, Schema},
    json::{ArrayWriter, WriterBuilder},
};
use orc_rust::{
    compression::CompressionType, projection::ProjectionMask, ArrowReaderBuilder,
    ArrowWriterBuilder,
};
use serde_json::{json, Value};
use std::{
    error::Error,
    fs::{self, File},
    path::Path,
    sync::Arc,
};

type Result<T> = std::result::Result<T, Box<dyn Error>>;

fn rows(batches: &[RecordBatch]) -> Result<Value> {
    let mut writer: ArrayWriter<Vec<u8>> = WriterBuilder::new()
        .with_explicit_nulls(true)
        .build(Vec::new());
    writer.write_batches(&batches.iter().collect::<Vec<_>>())?;
    writer.finish()?;
    Ok(serde_json::from_slice(&writer.into_inner())?)
}

fn read(path: &Path) -> Result<Vec<RecordBatch>> {
    Ok(ArrowReaderBuilder::try_new(File::open(path)?)?
        .with_batch_size(2)
        .build()
        .collect::<std::result::Result<Vec<_>, _>>()?)
}

fn report(path: &Path, batches: &[RecordBatch]) -> Result<Value> {
    let builder = ArrowReaderBuilder::try_new(File::open(path)?)?;
    let fields = builder.schema().fields().iter().map(|field| json!({"name":field.name(), "type":format!("{:?}",field.data_type()), "nullable":field.is_nullable()})).collect::<Vec<_>>();
    Ok(
        json!({"path":path,"fields":fields,"stripes":builder.file_metadata().stripe_metadatas().len(),"batch_rows":batches.iter().map(|b| b.num_rows()).collect::<Vec<_>>(),"row_count":batches.iter().map(|b| b.num_rows()).sum::<usize>(),"rows":rows(batches)?}),
    )
}

fn write_file(path: &Path, batches: &[RecordBatch], schema: Arc<Schema>) -> Result<()> {
    let mut writer = ArrowWriterBuilder::new(File::create(path)?, schema)
        .with_compression(CompressionType::Zstd)
        .with_batch_size(2)
        .with_stripe_byte_size(1)
        .try_build()?;
    for batch in batches {
        writer.write(batch)?;
        writer.flush_stripe()?;
    }
    writer.close()?;
    Ok(())
}

fn write(dir: &Path) -> Result<Value> {
    fs::create_dir_all(dir)?;
    let schema = Arc::new(Schema::new(vec![Field::new("id", DataType::Int64, false)]));
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![Arc::new(Int64Array::from(vec![0, 1, 2])) as ArrayRef],
    )?;
    let path = dir.join("range.orc");
    write_file(&path, &[batch], schema.clone())?;
    let empty_path = dir.join("empty.orc");
    write_file(&empty_path, &[], schema)?;
    let schema = Arc::new(Schema::new(vec![
        Field::new("id", DataType::Int64, true),
        Field::new("label", DataType::Utf8, true),
        Field::new("flag", DataType::Boolean, true),
    ]));
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            Arc::new(Int64Array::from(vec![
                Some(0),
                None,
                Some(2),
                Some(-3),
                Some(4),
            ])),
            Arc::new(StringArray::from(vec![
                Some("a"),
                None,
                Some(""),
                Some("λ"),
                Some("five"),
            ])),
            Arc::new(BooleanArray::from(vec![
                Some(true),
                None,
                Some(false),
                Some(true),
                Some(false),
            ])),
        ],
    )?;
    let expected = rows(&[batch.clone()])?;
    let nullable_path = dir.join("nullable.orc");
    write_file(
        &nullable_path,
        &[batch.slice(0, 3), batch.slice(3, 2)],
        schema,
    )?;
    let actual = read(&nullable_path)?;
    assert_eq!(rows(&actual)?, expected);
    assert_eq!(rows(&read(&path)?)?, json!([{"id":0},{"id":1},{"id":2}]));
    assert!(read(&empty_path)?.is_empty());
    let mut reports = vec![];
    for path in [&path, &empty_path, &nullable_path] {
        reports.push(report(path, &read(path)?)?);
    }
    Ok(json!({"compression":"zstd","files":reports,"outcome":"passed"}))
}

fn extras(path: &Path) -> Result<Value> {
    let full = read(path)?;
    let metadata = ArrowReaderBuilder::try_new(File::open(path)?)?;
    assert!(
        metadata.file_metadata().stripe_metadatas().len() > 1,
        "range test must use multiple stripes"
    );
    let size = fs::metadata(path)?.len() as usize;
    let mut bounded = vec![];
    let mut ranges = vec![];
    for i in 0..7 {
        let start = size * i / 7;
        let end = size * (i + 1) / 7;
        let batches = ArrowReaderBuilder::try_new(File::open(path)?)?
            .with_file_byte_range(start..end)
            .build()
            .collect::<std::result::Result<Vec<_>, _>>()?;
        use futures::TryStreamExt;
        let asynchronous = tokio::runtime::Builder::new_current_thread()
            .build()?
            .block_on(async {
                let file = tokio::fs::File::open(path).await?;
                let batches = ArrowReaderBuilder::try_new_async(file)
                    .await?
                    .with_file_byte_range(start..end)
                    .build_async()
                    .try_collect::<Vec<_>>()
                    .await?;
                Ok::<_, Box<dyn Error>>(batches)
            })?;
        assert_eq!(rows(&asynchronous)?, rows(&batches)?);
        ranges.push(json!({"start":start,"end":end,"rows":rows(&batches)?,"async_matches":true}));
        bounded.extend(batches);
    }
    assert_eq!(rows(&bounded)?, rows(&full)?);
    let mut projections = vec![];
    for names in [vec![], vec!["flag", "id", "id"], vec!["label"]] {
        let builder = ArrowReaderBuilder::try_new(File::open(path)?)?;
        let mask = ProjectionMask::named_roots(builder.file_metadata().root_data_type(), &names);
        let batches = builder
            .with_projection(mask)
            .build()
            .collect::<std::result::Result<Vec<_>, _>>()?;
        projections.push(json!({"requested":names,"actual_columns":batches.first().map(|b|b.schema().fields().iter().map(|f|f.name().clone()).collect::<Vec<_>>()),"row_count":batches.iter().map(|b|b.num_rows()).sum::<usize>(),"rows":rows(&batches)?}));
    }
    Ok(
        json!({"path":path,"byte_ranges_exactly_once":true,"ranges":ranges,"projection_observations":projections,"scope":"Library range behavior and projection observations; adapter must restore requested projection order/duplicates"}),
    )
}

fn main() -> Result<()> {
    let args = std::env::args().collect::<Vec<_>>();
    let path = Path::new(args.get(2).ok_or("missing path")?);
    let output = match args.get(1).map(String::as_str) {
        Some("write") => write(path)?,
        Some("read") => report(path, &read(path)?)?,
        Some("read-async") => {
            use futures::TryStreamExt;
            let batches = tokio::runtime::Builder::new_current_thread()
                .build()?
                .block_on(async {
                    let file = tokio::fs::File::open(path).await?;
                    let batches = ArrowReaderBuilder::try_new_async(file)
                        .await?
                        .with_batch_size(2)
                        .build_async()
                        .try_collect::<Vec<_>>()
                        .await?;
                    Ok::<_, Box<dyn Error>>(batches)
                })?;
            assert_eq!(rows(&batches)?, rows(&read(path)?)?);
            report(path, &batches)?
        }
        Some("extras") => extras(path)?,
        _ => return Err("usage: probe write DIR | read FILE | extras FILE".into()),
    };
    println!("{}", serde_json::to_string_pretty(&output)?);
    Ok(())
}
