//! A caller that already holds a projection runs any registered kernel by name
//! and gets typed Arrow back. Nutmeg is that caller: with this it needs no
//! per-algorithm code, so a kernel is served the day it is registered.

use arrow_array::RecordBatch;
use grust_algorithm_procedures::{
    projection_kernel_names, projection_options, register_algorithms, run_on_projection,
};
use grust_algorithms::{GraphProjection, Orientation, ProjectionEdge, WeightSelection};
use grust_core::Value;
use grust_procedures::{
    ExecutionContext, ExecutionLimits, ProcedureError, ProcedureRegistry, RegistryBuilder,
    SnapshotIdentity, ValueType,
};

fn registry() -> ProcedureRegistry {
    let mut builder = RegistryBuilder::default();
    register_algorithms(&mut builder).unwrap();
    builder.build()
}

fn context() -> ExecutionContext {
    ExecutionContext::new(ExecutionLimits {
        memory_bytes: 1024 * 1024,
        work_units: 1_000_000,
        batch_rows: 2,
        deadline: None,
    })
    .unwrap()
}

/// a -> b -> c, plus an isolate: acyclic, so every kernel has a plain answer.
fn projection(context: &ExecutionContext) -> GraphProjection {
    let edge = |source, target, ordinal| ProjectionEdge {
        source,
        target,
        ordinal,
        id: None,
    };
    GraphProjection::from_topology(
        SnapshotIdentity::new("g".into(), "r1".into(), "reader".into()).unwrap(),
        vec!["a".into(), "b".into(), "c".into(), "isolate".into()],
        vec![edge(0, 1, 0), edge(1, 2, 1)],
        Some(vec![2.0, 0.5]),
        Orientation::Outgoing,
        context,
    )
    .unwrap()
}

fn drain(mut cursor: grust_algorithms::ArrowResultCursor) -> Vec<RecordBatch> {
    let mut batches = Vec::new();
    while let Some(batch) = cursor.next_batch().unwrap() {
        batches.push(batch.record_batch().clone());
    }
    batches
}

#[test]
fn every_registered_projection_kernel_runs_by_name_with_its_declared_columns() {
    let registry = registry();
    let names = projection_kernel_names();
    assert!(names.contains(&"pagerank") && names.contains(&"shortestPaths"));

    for name in names {
        let resolved = registry
            .resolve(&format!("grust.algorithms.{name}"))
            .unwrap_or_else(|error| panic!("{name} is in the catalog but not registered: {error}"));
        let definition = resolved.definition();
        // The configuration map is always last; a source argument, if any, precedes it.
        let mut args = Vec::new();
        for argument in &definition.arguments {
            args.push(match argument.field.value_type {
                ValueType::String => Value::from("a"),
                ValueType::Strings => Value::StringArray(vec!["a".into()]),
                ValueType::Map => Value::Json(serde_json::json!({})),
                ref other => panic!("{name}: unexpected argument type {other:?}"),
            });
        }
        let args = resolved.validate_arguments(args).unwrap();

        let context = context();
        let graph = projection(&context);
        let batches = drain(run_on_projection(name, &graph, &args).unwrap());
        assert!(!batches.is_empty(), "{name} produced no batches");

        let declared: Vec<&str> = definition.outputs.iter().map(|f| f.name.as_str()).collect();
        let schema = batches[0].schema();
        let columns: Vec<&str> = schema.fields().iter().map(|f| f.name().as_str()).collect();
        assert_eq!(
            columns, declared,
            "{name}: Arrow columns differ from the registry"
        );
        assert!(
            batches.iter().all(|batch| batch.num_rows() <= 2),
            "{name} ignored the batch row bound"
        );

        // The prefixed name is the same kernel.
        let prefixed =
            drain(run_on_projection(&format!("grust.algorithms.{name}"), &graph, &args).unwrap());
        assert_eq!(prefixed, batches, "{name}");
    }
}

#[test]
fn metadata_procedures_and_unknown_names_are_refused() {
    let registry = registry();
    let context = context();
    let graph = projection(&context);
    let args = registry
        .resolve("grust.algorithms.wcc")
        .unwrap()
        .validate_arguments(vec![Value::Json(serde_json::json!({}))])
        .unwrap();
    for name in ["projectionStats", "estimateCsr", "louvain-not-yet"] {
        assert!(
            matches!(
                run_on_projection(name, &graph, &args),
                Err(ProcedureError::Unsupported(_))
            ),
            "{name}"
        );
    }
}

#[test]
fn projection_options_read_what_the_procedure_would() {
    let registry = registry();
    let resolved = registry.resolve("grust.algorithms.degree").unwrap();
    let args = resolved
        .validate_arguments(vec![Value::Json(serde_json::json!({
            "orientation": "undirected",
            "weightProperty": "cost",
            "defaultWeight": 1.5,
            "nodeLabels": ["Person"],
        }))])
        .unwrap();
    let options = projection_options(&args).unwrap();
    assert_eq!(options.orientation, Orientation::Undirected);
    assert_eq!(options.node_labels, Some(&["Person".to_string()][..]));
    assert!(matches!(
        options.weight,
        WeightSelection::Property { key: "cost", .. }
    ));

    let defaults = resolved
        .validate_arguments(vec![Value::Json(serde_json::json!({}))])
        .unwrap();
    let options = projection_options(&defaults).unwrap();
    assert_eq!(options.orientation, Orientation::Outgoing);
    assert!(matches!(options.weight, WeightSelection::Unit));
}
