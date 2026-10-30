use std::collections::BTreeSet;

use arrow::datatypes::TimeUnit;
use sail_common::spec;

use super::*;

#[tokio::test]
async fn both_modes_find_usable_schemas_after_eleven_empty_roots_and_merge_sees_late_fields() {
    let fixture = Fixture::new();
    let empty = file(Schema::empty(), vec![], 3);
    for i in 0..11 {
        fixture.put(&format!("{i:02}.orc"), empty.clone()).await;
    }
    fixture.put("11.orc", integers("first", vec![11])).await;
    fixture.put("12.orc", integers("late", vec![12])).await;
    for merge in [false, true] {
        fixture.store.requests.lock().unwrap().clear();
        let source = fixture
            .source(
                None,
                vec![option_list(&[(
                    "mergeSchema",
                    if merge { "true" } else { "false" },
                )])],
                true,
            )
            .await
            .unwrap();
        let schema = source.schema();
        let names = schema
            .fields()
            .iter()
            .map(|f| f.name().as_str())
            .collect::<Vec<_>>();
        assert_eq!(
            names,
            if merge {
                vec!["first", "late"]
            } else {
                vec!["first"]
            }
        );
        let paths = fixture
            .store
            .requests
            .lock()
            .unwrap()
            .iter()
            .filter(|(_, options)| !options.head)
            .map(|(path, _)| path.to_string())
            .collect::<BTreeSet<_>>();
        assert_eq!(
            paths,
            (0..if merge { 13 } else { 12 })
                .map(|i| format!("data/{i:02}.orc"))
                .collect()
        );
    }
}

#[tokio::test]
async fn first_schema_stops_before_later_corruption_but_merge_retains_the_original_failure() {
    let fixture = Fixture::new();
    fixture.put("00.orc", integers("value", vec![1])).await;
    fixture
        .put("01.orc", Bytes::from_static(b"not an ORC file"))
        .await;
    assert_eq!(
        fixture
            .source(None, vec![], true)
            .await
            .unwrap()
            .schema()
            .field(0)
            .name(),
        "value"
    );
    assert!(
        fixture
            .store
            .requests
            .lock()
            .unwrap()
            .iter()
            .all(|(path, _)| path.as_ref() != "data/01.orc")
    );
    let error = fixture
        .source(None, vec![option_list(&[("mergeSchema", "true")])], true)
        .await
        .err()
        .unwrap();
    assert!(matches!(error,
        DataFusionError::Context(context, cause)
            if context.contains("data/01.orc")
                && matches!(cause.as_ref(), DataFusionError::External(_))
    ));

    let only_empty = Fixture::new();
    only_empty
        .put("empty.orc", file(Schema::empty(), vec![], 2))
        .await;
    assert!(
        only_empty
            .source(None, vec![], true)
            .await
            .err()
            .unwrap()
            .to_string()
            .contains("no nonempty physical schema")
    );
}

#[tokio::test]
async fn merge_preserves_spark_time_annotations_and_rejects_late_precision_mismatch() {
    let fixture = Fixture::new();
    let spark = Bytes::from_static(include_bytes!(
        "../../../tests/fixtures/orc/time_precisions.orc"
    ));
    // The real Spark file reaches the ordinary listing inference path, including
    // its semantic field metadata and Spark-version schema metadata.
    fixture.put("00.orc", spark.clone()).await;
    fixture.put("01.orc", spark.clone()).await;
    let options = || vec![option_list(&[("mergeSchema", "true")])];
    let schema = fixture
        .source(None, options(), true)
        .await
        .unwrap()
        .schema();
    assert_eq!(schema.metadata()["org.apache.spark.version"], "4.2.1");
    for (index, precision) in [(1, 0), (2, 3), (3, 6)] {
        let field = schema.field(index);
        assert_eq!(field.data_type(), &DataType::Time64(TimeUnit::Nanosecond));
        assert_eq!(
            spec::SparkTimeMetadata::from_json(
                &field.metadata()[spec::SAIL_SPARK_TIME_METADATA_KEY]
            )
            .unwrap()
            .precision(),
            precision
        );
    }
    // Every mismatch input exists before this context's first listing. The
    // shared listing cache may reuse earlier inventories within one context.
    let incompatible = Fixture::new();
    incompatible.put("00.orc", spark.clone()).await;
    incompatible.put("01.orc", spark).await;
    for i in 2..11 {
        incompatible
            .put(&format!("{i:02}.orc"), file(Schema::empty(), vec![], 1))
            .await;
    }
    let late = incompatible
        .put("11.orc", annotate_time(&integers("t3", vec![0]), 6))
        .await;
    let result = incompatible.source(None, options(), true).await;
    {
        let listed = incompatible.store.listed.lock().unwrap();
        assert_eq!(listed.len(), 12);
        assert!(listed.contains(&late));
    }
    assert!(
        incompatible
            .store
            .requests
            .lock()
            .unwrap()
            .iter()
            .any(|(path, request)| path == &late.location
                && !request.head
                && request.if_match == late.e_tag)
    );
    let error = result.err().unwrap();
    assert!(error.to_string().contains("data/11.orc"), "{error}");
    assert!(
        error
            .to_string()
            .contains("Cannot merge incompatible Spark file types"),
        "{error}"
    );
    // With merging disabled the late incompatible file does not alter inference.
    incompatible.store.requests.lock().unwrap().clear();
    assert_eq!(
        incompatible
            .source(None, vec![], true)
            .await
            .unwrap()
            .schema(),
        schema
    );
    assert!(
        incompatible
            .store
            .requests
            .lock()
            .unwrap()
            .iter()
            .all(|(path, _)| path != &late.location)
    );
}

fn nested(name: &str) -> Bytes {
    // Native ORC writing does not yet support STRUCT. These actual foreign
    // PyArrow files retain generator, readback and hash provenance alongside.
    Bytes::from_static(match name {
        "Value" => include_bytes!("../../../tests/fixtures/orc/listing_inference/nested_upper.orc"),
        "value" => include_bytes!("../../../tests/fixtures/orc/listing_inference/nested_lower.orc"),
        _ => unreachable!(),
    })
}

#[tokio::test]
async fn authoritative_case_policy_controls_root_merge_and_final_nested_validation() {
    for nested_struct in [false, true] {
        let fixture = Fixture::new();
        for (path, name) in [("00.orc", "Value"), ("01.orc", "value")] {
            fixture
                .put(
                    path,
                    if nested_struct {
                        nested(name)
                    } else {
                        integers(name, vec![1])
                    },
                )
                .await;
        }
        for case_sensitive in [false, true] {
            // Deliberately leave DataFusion identifier normalization at its
            // default. SourceInfo's policy must govern ORC inference instead.
            let result = fixture
                .source(
                    None,
                    vec![option_list(&[("mergeSchema", "true")])],
                    case_sensitive,
                )
                .await;
            if nested_struct && !case_sensitive {
                assert!(result.err().unwrap().to_string().contains("already exists"));
            } else {
                let schema = result.unwrap().schema();
                let fields = if nested_struct {
                    let DataType::Struct(fields) = schema.field(0).data_type() else {
                        unreachable!()
                    };
                    fields
                } else {
                    schema.fields()
                };
                assert_eq!(fields.len(), if case_sensitive { 2 } else { 1 });
                assert_eq!(fields[0].name(), "Value");
            }
            // Single-file/first mode also validates recursively, but this first
            // file has only one child and is valid under either case policy.
            fixture.source(None, vec![], case_sensitive).await.unwrap();
        }
    }
}

#[tokio::test]
async fn single_file_duplicate_names_are_checked_even_without_merge() {
    for nested_struct in [false, true] {
        let fixture = Fixture::new();
        let fields: arrow::datatypes::Fields = vec![
            Field::new("Value", DataType::Int64, true),
            Field::new("value", DataType::Int64, true),
        ]
        .into();
        let columns: Vec<ArrayRef> = vec![
            Arc::new(Int64Array::from(vec![1])),
            Arc::new(Int64Array::from(vec![2])),
        ];
        let bytes = if nested_struct {
            Bytes::from_static(include_bytes!(
                "../../../tests/fixtures/orc/listing_inference/nested_duplicate.orc"
            ))
        } else {
            file(Schema::new(fields), columns, 1)
        };
        fixture.put("duplicate.orc", bytes).await;
        for merge in [false, true] {
            let options = || {
                vec![option_list(&[(
                    "mergeSchema",
                    if merge { "true" } else { "false" },
                )])]
            };
            assert!(
                fixture
                    .source(None, options(), false)
                    .await
                    .err()
                    .unwrap()
                    .to_string()
                    .contains("already exists")
            );
            let schema = fixture
                .source(None, options(), true)
                .await
                .unwrap()
                .schema();
            let actual = if nested_struct {
                let DataType::Struct(fields) = schema.field(0).data_type() else {
                    unreachable!()
                };
                fields
            } else {
                schema.fields()
            };
            assert_eq!(actual.len(), 2);
        }
    }
}
