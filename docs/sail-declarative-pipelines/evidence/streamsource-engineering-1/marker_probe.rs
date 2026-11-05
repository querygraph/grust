//! Narrow probes using unchanged Sail event modules and pinned dependencies.
//! The source provenance and [CREDIT] entries are in SOURCE-MANIFEST.json.
//! Expected failures are asserted and paired with valid-shape controls.

use std::sync::Arc;

use arrow::array::{Array, RecordBatch, RecordBatchOptions, StringArray};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use chrono::{DateTime, Utc};
use datafusion_common::{Result, ScalarValue};
use datafusion_expr::Operator;
use datafusion_physical_expr::expressions::{BinaryExpr, CastExpr, Column, IsNotNullExpr, Literal};
use datafusion_physical_expr::PhysicalExpr;
use datafusion_physical_plan::filter::batch_filter;
use datafusion_physical_plan::stream::RecordBatchStreamAdapter;
use futures::TryStreamExt;
use serde_json::{Value, json};
use streamsource_marker_probe::array::placeholder::placeholder_array;
use streamsource_marker_probe::streaming::event::FlowEvent;
use streamsource_marker_probe::streaming::event::encoding::{DecodedFlowEventStream, EncodedFlowEventStream};
use streamsource_marker_probe::streaming::event::marker::FlowMarker;
use streamsource_marker_probe::streaming::event::schema::to_flow_event_schema;
use streamsource_marker_probe::streaming::event::stream::FlowEventStreamAdapter;

fn encode(schema: SchemaRef, event: FlowEvent) -> Result<RecordBatch> {
    let input = FlowEventStreamAdapter::new(schema, futures::stream::empty());
    EncodedFlowEventStream::new(Box::pin(input)).encode(event)
}

fn decode(batch: RecordBatch) -> Result<Vec<FlowEvent>> {
    let input = RecordBatchStreamAdapter::new(batch.schema(), futures::stream::iter(vec![Ok(batch)]));
    futures::executor::block_on(DecodedFlowEventStream::try_new(Box::pin(input))?.try_collect())
}

fn expect_error<T>(name: &str, result: Result<T>, observations: &mut Vec<Value>) {
    let error = match result {
        Err(error) => error.to_string(),
        Ok(_) => panic!("Expected source defect did not reproduce: {name}"),
    };
    observations.push(json!({"case": name, "outcome": "expected failure reproduced", "error": error}));
}

fn markers() -> Vec<FlowMarker> {
    let timestamp = DateTime::<Utc>::from_timestamp(1_700_000_000, 0).unwrap();
    vec![
        FlowMarker::LatencyTracker { source: "probe".into(), id: 7, timestamp },
        FlowMarker::Watermark { source: "probe".into(), timestamp },
        FlowMarker::Checkpoint { id: 7 },
        FlowMarker::EndOfData,
    ]
}

fn main() -> Result<()> {
    let mut observations = Vec::<Value>::new();
    let empty_schema = Arc::new(Schema::empty());
    let empty_data = RecordBatch::try_new_with_options(
        empty_schema.clone(), vec![], &RecordBatchOptions::new().with_row_count(Some(3)),
    )?;
    assert_eq!(empty_data.num_rows(), 3);
    let encoded_data = encode(empty_schema.clone(), FlowEvent::append_only_data(empty_data))?;
    assert_eq!(encoded_data.num_rows(), 3);
    expect_error("zero_columns_data_3_rows_decode", decode(encoded_data), &mut observations);
    for (i, marker) in markers().into_iter().enumerate() {
        let encoded = encode(empty_schema.clone(), FlowEvent::Marker(marker))?;
        assert_eq!(encoded.num_rows(), 1);
        expect_error(&format!("zero_columns_marker_{i}_decode"), decode(encoded), &mut observations);
    }
    observations.push(json!({"case": "explicit_zero_column_row_count_control", "outcome": "pass", "rows": 3}));

    let string_schema = Arc::new(Schema::new(vec![Field::new("s", DataType::Utf8, false)]));
    let data = RecordBatch::try_new(string_schema.clone(), vec![Arc::new(StringArray::from(vec!["12"]))])?;
    let encoded_data = encode(string_schema.clone(), FlowEvent::append_only_data(data))?;
    let decoded = decode(encoded_data.clone())?;
    assert!(matches!(&decoded[..], [FlowEvent::Data { batch, .. }] if batch.num_rows() == 1));
    for marker in markers() {
        let decoded = decode(encode(string_schema.clone(), FlowEvent::Marker(marker.clone()))?)?;
        assert!(matches!(&decoded[..], [FlowEvent::Marker(actual)] if actual == &marker));
    }
    observations.push(json!({"case": "one_column_data_and_all_4_markers_roundtrip_control", "outcome": "pass"}));

    for dtype in [DataType::Decimal32(5, 2), DataType::Decimal64(10, 2), DataType::Decimal128(10, 2), DataType::Decimal256(10, 2)] {
        let placeholder = placeholder_array(&dtype, 1)?;
        assert_ne!(placeholder.data_type(), &dtype);
        observations.push(json!({"case": "decimal_placeholder_type", "requested": format!("{dtype:?}"), "actual": format!("{:?}", placeholder.data_type())}));
        let schema = Arc::new(Schema::new(vec![Field::new("d", dtype.clone(), false)]));
        for (i, marker) in markers().into_iter().enumerate() {
            expect_error(&format!("{dtype:?}_nonnullable_marker_{i}_encode"), encode(schema.clone(), FlowEvent::Marker(marker)), &mut observations);
        }
        let nullable_schema = Arc::new(Schema::new(vec![Field::new("d", dtype.clone(), true)]));
        for marker in markers() {
            let encoded = encode(nullable_schema.clone(), FlowEvent::Marker(marker.clone()))?;
            assert_eq!(encoded.column(2).data_type(), &dtype);
            let decoded = decode(encoded)?;
            assert!(matches!(&decoded[..], [FlowEvent::Marker(actual)] if actual == &marker));
        }
        let default_schema = Arc::new(Schema::new(vec![Field::new("d", placeholder.data_type().clone(), false)]));
        let encoded = encode(default_schema, FlowEvent::Marker(FlowMarker::Checkpoint { id: 7 }))?;
        assert!(matches!(&decode(encoded)?[..], [FlowEvent::Marker(FlowMarker::Checkpoint { id: 7 })]));
        observations.push(json!({"case": format!("{dtype:?}_nullable_and_default_type_controls"), "outcome": "pass"}));
    }

    let cast: Arc<dyn PhysicalExpr> = Arc::new(CastExpr::new(Arc::new(Column::new("s", 2)), DataType::Int32, None));
    let greater_than_zero: Arc<dyn PhysicalExpr> = Arc::new(BinaryExpr::new(cast.clone(), Operator::Gt, Arc::new(Literal::new(ScalarValue::Int32(Some(0))))));
    let marker_present: Arc<dyn PhysicalExpr> = Arc::new(IsNotNullExpr::new(Arc::new(Column::new("_marker", 0))));
    let predicate: Arc<dyn PhysicalExpr> = Arc::new(BinaryExpr::new(greater_than_zero.clone(), Operator::Or, marker_present.clone()));
    assert_eq!(batch_filter(&encoded_data, &predicate)?.num_rows(), 1);
    assert_eq!(cast.evaluate(&encoded_data)?.into_array(1)?.len(), 1);
    observations.push(json!({"case": "strict_cast_valid_data_control", "outcome": "pass"}));
    for (i, marker) in markers().into_iter().enumerate() {
        let encoded = encode(string_schema.clone(), FlowEvent::Marker(marker))?;
        expect_error(&format!("strict_cast_marker_{i}_projection_expression"), cast.evaluate(&encoded), &mut observations);
        expect_error(&format!("strict_cast_marker_{i}_user_predicate_or_marker"), batch_filter(&encoded, &predicate), &mut observations);
        let reordered: Arc<dyn PhysicalExpr> = Arc::new(BinaryExpr::new(marker_present.clone(), Operator::Or, greater_than_zero.clone()));
        assert_eq!(batch_filter(&encoded, &reordered)?.num_rows(), 1);
    }
    observations.push(json!({"case": "marker_first_predicate_control", "outcome": "pass for all 4 marker-only batches", "limit": "This control does not fix projections or prove general marker-safe execution"}));

    let original_metadata = std::collections::HashMap::from([("probe".to_string(), "retained".to_string())]);
    let schema = Schema::new_with_metadata(vec![Field::new("s", DataType::Utf8, false)], original_metadata.clone());
    assert_eq!(schema.metadata(), &original_metadata);
    let flow_schema = to_flow_event_schema(&schema);
    assert!(flow_schema.metadata().is_empty());
    observations.push(json!({"case": "schema_metadata_encode", "outcome": "metadata lost", "input": original_metadata, "encoded": flow_schema.metadata()}));

    println!("{}", serde_json::to_string_pretty(&json!({
        "scope": "Unchanged Sail event/placeholder modules and DataFusion expressions in an isolated harness; not an optimized SQL or distributed runtime execution",
        "sail_revision": "85c6cca01cd521dd778bc200c987a34edf141de1",
        "arrow": "59.2.0", "datafusion": "55.2.0",
        "observations": observations,
        "assertions": "All predicted failure cases failed and all named controls passed"
    })).unwrap());
    Ok(())
}
