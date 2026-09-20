//! A caller that already holds a projection runs any registered kernel by name
//! and gets typed Arrow back. Nutmeg is that caller: with this it needs no
//! per-algorithm code, so a kernel is served the day it is registered.

use arrow_array::RecordBatch;
use grust_algorithm_procedures::{
    projection_kernel_names, projection_options, projection_options_for, register_algorithms,
    run_on_projection,
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
fn projection(context: &ExecutionContext, orientation: Orientation) -> GraphProjection {
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
        orientation,
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
        // Successive node arguments name different nodes: a flow needs two ends.
        let mut ids = ["a", "b", "c"].into_iter();
        for argument in &definition.arguments {
            args.push(match argument.field.value_type {
                ValueType::String => Value::from(ids.next().unwrap()),
                ValueType::Strings => Value::StringArray(vec!["a".into()]),
                ValueType::Map => Value::Json(serde_json::json!({})),
                ref other => panic!("{name}: unexpected argument type {other:?}"),
            });
        }
        let args = resolved.validate_arguments(args).unwrap();

        // Kernels defined on undirected graphs refuse a directed projection;
        // that refusal is theirs to state, and they then run on an undirected one.
        let context = context();
        let mut graph = projection(&context, Orientation::Outgoing);
        if let Err(ProcedureError::InvalidArguments(message)) =
            run_on_projection(name, &graph, &args)
        {
            assert!(message.contains("undirected"), "{name}: {message}");
            graph = projection(&context, Orientation::Undirected);
        }
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
        // Case is not significant, as in the registry.
        let lowered = drain(run_on_projection(&name.to_ascii_lowercase(), &graph, &args).unwrap());
        assert_eq!(lowered, batches, "{name}");
    }
}

#[test]
fn metadata_procedures_and_unknown_names_are_refused() {
    let registry = registry();
    let context = context();
    let graph = projection(&context, Orientation::Outgoing);
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

fn arguments(
    registry: &ProcedureRegistry,
    name: &str,
    options: serde_json::Value,
) -> grust_procedures::ValidatedArguments {
    let resolved = registry
        .resolve(&format!("grust.algorithms.{name}"))
        .unwrap();
    let mut ids = ["a", "b", "c"].into_iter();
    let mut args = Vec::new();
    for argument in &resolved.definition().arguments {
        args.push(match argument.field.value_type {
            ValueType::String => Value::from(ids.next().unwrap()),
            ValueType::Strings => Value::StringArray(vec![ids.next().unwrap().into()]),
            ValueType::Map => Value::Json(options.clone()),
            ref other => panic!("{name}: unexpected argument type {other:?}"),
        });
    }
    resolved.validate_arguments(args).unwrap()
}

#[test]
fn every_kernel_but_bellman_ford_refuses_a_signed_projection() {
    // A negative weight does not make Dijkstra fail; it makes it wrong. So a
    // projection built to admit negative weights must be refused by every kernel
    // that does not handle them, in every orientation, and a kernel added
    // without the guard fails here.
    let registry = registry();
    let edge = |source, target, ordinal| ProjectionEdge {
        source,
        target,
        ordinal,
        id: None,
    };
    let mut ran = 0;
    for orientation in [Orientation::Outgoing, Orientation::Undirected] {
        let context = context();
        let graph = GraphProjection::from_signed_topology(
            SnapshotIdentity::new("g".into(), "r1".into(), "reader".into()).unwrap(),
            vec!["a".into(), "b".into(), "c".into(), "isolate".into()],
            vec![edge(0, 1, 0), edge(1, 2, 1)],
            vec![2.0, -0.5],
            orientation,
            &context,
        )
        .unwrap();
        assert!(graph.is_signed());
        for name in projection_kernel_names() {
            let args = arguments(&registry, name, serde_json::json!({}));
            let outcome = run_on_projection(name, &graph, &args);
            if name == "bellmanFord" {
                assert!(outcome.is_ok(), "bellmanFord refused a signed projection");
                ran += 1;
                continue;
            }
            match outcome {
                Err(ProcedureError::InvalidArguments(message)) => assert!(
                    message.contains("signed projection"),
                    "{name} refused for another reason: {message}"
                ),
                Err(other) => panic!("{name}: {other}"),
                Ok(_) => panic!("{name} ran on a signed projection"),
            }
        }
    }
    assert_eq!(ran, 2);
}

#[test]
fn only_bellman_ford_is_offered_a_projection_that_admits_negative_weights() {
    let registry = registry();
    let options = serde_json::json!({"weightProperty": "cost"});
    for name in projection_kernel_names() {
        let args = arguments(&registry, name, options.clone());
        let signed = matches!(
            projection_options_for(name, &args).unwrap().weight,
            WeightSelection::SignedProperty { key: "cost", .. }
        );
        assert_eq!(signed, name == "bellmanFord", "{name}");
        // The kernel-blind form never asks for signed weights.
        assert!(matches!(
            projection_options(&args).unwrap().weight,
            WeightSelection::Property { key: "cost", .. }
        ));
    }
    let args = arguments(&registry, "bellmanFord", options);
    // Names match as `run_on_projection` matches them: prefixed, any case.
    let context = context();
    let graph = projection(&context, Orientation::Outgoing);
    let plain = arguments(&registry, "degree", serde_json::json!({}));
    assert!(run_on_projection("GRUST.ALGORITHMS.DEGREE", &graph, &plain).is_ok());
    assert!(matches!(
        projection_options_for("GRUST.ALGORITHMS.BELLMANFORD", &args)
            .unwrap()
            .weight,
        WeightSelection::SignedProperty { .. }
    ));
}
