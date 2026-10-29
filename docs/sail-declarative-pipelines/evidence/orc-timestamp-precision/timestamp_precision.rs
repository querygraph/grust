// Licensed to the Apache Software Foundation (ASF) under one
// or more contributor license agreements.  See the NOTICE file
// distributed with this work for additional information
// regarding copyright ownership.  The ASF licenses this file
// to you under the Apache License, Version 2.0 (the
// "License"); you may not use this file except in compliance
// with the License.  You may obtain a copy of the License at
//
//   http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing,
// software distributed under the License is distributed on an
// "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
// KIND, either express or implied.  See the License for the
// specific language governing permissions and limitations
// under the License.

use std::sync::Arc;

use arrow::{
    array::{Array, RecordBatch, TimestampMicrosecondArray},
    datatypes::{Field, Schema},
};
use bytes::Bytes;
use orc_rust::{
    ArrowReaderBuilder, ArrowWriterBuilder, TimestampPrecision, TimestampPrecisionLoss,
    TimestampReadOptions,
};

const FOREIGN: &[u8] = include_bytes!("integration/data/timestamp_options/foreign_submicro.orc");

fn options() -> TimestampReadOptions {
    TimestampReadOptions::new().with_precision_loss(TimestampPrecisionLoss::Truncate)
}

fn values(batches: &[RecordBatch]) -> Vec<Option<i64>> {
    batches
        .iter()
        .flat_map(|batch| {
            batch
                .column_by_name("ts")
                .unwrap()
                .as_any()
                .downcast_ref::<TimestampMicrosecondArray>()
                .unwrap()
                .iter()
                .collect::<Vec<_>>()
        })
        .collect()
}

#[test]
fn foreign_submicroseconds_are_strict_by_default_and_can_be_truncated() {
    let builder = || {
        ArrowReaderBuilder::try_new(Bytes::from_static(FOREIGN))
            .unwrap()
            .with_timestamp_precision(TimestampPrecision::Microsecond)
            .with_batch_size(2)
    };
    assert!(builder().build().collect::<Result<Vec<_>, _>>().is_err());
    let batches = builder()
        .with_timestamp_read_options(options())
        .build()
        .collect::<Result<Vec<_>, _>>()
        .unwrap();
    assert_eq!(
        values(&batches),
        vec![Some(1_577_934_245_123_456), Some(-1_876_544), Some(0), None]
    );
}

#[test]
fn microsecond_instants_retain_year_one_and_year_9999() {
    let expected = vec![
        Some(-62_135_596_800_000_000),
        Some(253_402_300_799_999_999),
        None,
    ];
    let array = TimestampMicrosecondArray::from(expected.clone()).with_timezone("UTC");
    let schema = Arc::new(Schema::new(vec![Field::new(
        "ts",
        array.data_type().clone(),
        true,
    )]));
    let batch = RecordBatch::try_new(schema.clone(), vec![Arc::new(array)]).unwrap();
    let mut encoded = Vec::new();
    let mut writer = ArrowWriterBuilder::new(&mut encoded, schema)
        .try_build()
        .unwrap();
    writer.write(&batch).unwrap();
    writer.close().unwrap();
    let batches = ArrowReaderBuilder::try_new(Bytes::from(encoded))
        .unwrap()
        .with_timestamp_precision(TimestampPrecision::Microsecond)
        .with_timestamp_read_options(options())
        .build()
        .collect::<Result<Vec<_>, _>>()
        .unwrap();
    assert_eq!(values(&batches), expected);
}

#[cfg(feature = "async")]
#[tokio::test]
async fn async_reader_propagates_precision_options() {
    use futures::TryStreamExt;
    let batches = ArrowReaderBuilder::try_new_async(std::io::Cursor::new(FOREIGN))
        .await
        .unwrap()
        .with_batch_size(2)
        .with_timestamp_precision(TimestampPrecision::Microsecond)
        .with_timestamp_read_options(options())
        .build_async()
        .try_collect::<Vec<_>>()
        .await
        .unwrap();
    assert_eq!(
        values(&batches),
        vec![Some(1_577_934_245_123_456), Some(-1_876_544), Some(0), None]
    );
}
