//! A caller that already holds a projection runs any registered kernel by name
//! and gets typed Arrow back. Nutmeg is that caller: with this it needs no
//! per-algorithm code, so a kernel is served the day it is registered.

use arrow_array::RecordBatch;
use grust_algorithm_procedures::{
    node_property_options, node_property_requests, projection_kernel_names, projection_options,
    projection_options_for, register_algorithms, run_on_projection, run_with_properties,
};
use grust_algorithms::{
    GraphProjection, NodeProperties, Orientation, ProjectionEdge, WeightSelection,
};
use grust_core::Value;
use grust_procedures::{
    ExecutionContext, ExecutionLimits, ProcedureDefinition, ProcedureError, ProcedureRegistry,
    RegistryBuilder, SnapshotIdentity, ValueType,
};
use std::collections::BTreeMap;

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

/// Run a kernel by name whichever path it needs: a kernel that reads node
/// properties is refused by `run_on_projection` and served by
/// `run_with_properties`, so an embedder that asks first can use one path for
/// every name. Property values come from the projection's own rows, which is
/// all these kernels need to produce a row.
fn run_any(
    name: &str,
    graph: &GraphProjection,
    args: &grust_procedures::ValidatedArguments,
) -> Result<grust_algorithms::ArrowResultCursor, ProcedureError> {
    let wanted = node_property_requests(name, args)?;
    if wanted.is_empty() {
        return run_on_projection(name, graph, args);
    }
    let graph_with_properties = property_graph(graph.node_count());
    let properties = NodeProperties::from_graph(&graph_with_properties, graph, &wanted)?;
    run_with_properties(name, &properties, args)
}

/// The projection's nodes, each carrying every property name the catalog asks
/// for: a community, and a coordinate pair for the kernels with heuristics.
/// Communities alternate so a partition is not trivially one community. A kernel
/// that adds a property option adds it here, and the two catalog tests below
/// fail until it does.
fn property_graph(nodes: usize) -> grust_core::Graph {
    use grust_core::{Node, Props, Value};
    grust_core::Graph::new(
        ["a", "b", "c", "isolate"][..nodes]
            .iter()
            .enumerate()
            .map(|(row, id)| {
                Node::new(
                    "N",
                    *id,
                    Props::from([
                        ("community".to_string(), Value::Int((row % 2) as i64)),
                        // Distinct, in range, and ordered so no two nodes share
                        // a point: a zero-distance heuristic would hide an
                        // ordering bug.
                        ("latitude".to_string(), Value::Float(row as f64)),
                        ("longitude".to_string(), Value::Float(row as f64 * 2.0)),
                    ]),
                )
            })
            .collect(),
        Vec::new(),
    )
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
        if let Err(ProcedureError::InvalidArguments(message)) = run_any(name, &graph, &args) {
            assert!(message.contains("undirected"), "{name}: {message}");
            graph = projection(&context, Orientation::Undirected);
        }
        let batches = drain(run_any(name, &graph, &args).unwrap());
        assert!(!batches.is_empty(), "{name} produced no batches");

        let declared: Vec<&str> = definition.outputs.iter().map(|f| f.name.as_str()).collect();
        let schema = batches[0].schema();
        let columns: Vec<&str> = schema.fields().iter().map(|f| f.name().as_str()).collect();
        assert_eq!(
            columns, declared,
            "{name}: Arrow columns differ from the registry"
        );
        assert_declared_nullability(name, definition, &batches);
        assert_declared_types(name, definition, &batches);
        assert!(
            batches.iter().all(|batch| batch.num_rows() <= 2),
            "{name} ignored the batch row bound"
        );

        // The prefixed name is the same kernel.
        let prefixed = drain(run_any(&format!("grust.algorithms.{name}"), &graph, &args).unwrap());
        assert_eq!(prefixed, batches, "{name}");
        // Case is not significant, as in the registry.
        let lowered = drain(run_any(&name.to_ascii_lowercase(), &graph, &args).unwrap());
        assert_eq!(lowered, batches, "{name}");
    }
}

/// Every batch, empty or not, says of each column exactly what the registry
/// declares: nullable where declared nullable, and never nullable otherwise.
fn assert_declared_nullability(
    name: &str,
    definition: &ProcedureDefinition,
    batches: &[RecordBatch],
) {
    let declared: Vec<(&str, bool)> = definition
        .outputs
        .iter()
        .map(|f| (f.name.as_str(), f.nullable))
        .collect();
    for (index, batch) in batches.iter().enumerate() {
        let produced: Vec<(&str, bool)> = batch
            .schema_ref()
            .fields()
            .iter()
            .map(|f| (f.name().as_str(), f.is_nullable()))
            .collect();
        assert_eq!(
            produced,
            declared,
            "{name}: batch {index} of {} rows reports other nullability than the registry",
            batch.num_rows()
        );
    }
}

/// Every column's Arrow type is the one its declared `ValueType` names:
/// `Integer` is signed 64-bit, so an integer column is Int64 and never
/// unsigned, which Spark and most SQL engines cannot represent.
fn assert_declared_types(name: &str, definition: &ProcedureDefinition, batches: &[RecordBatch]) {
    use arrow_schema::DataType;
    let element = |data_type: &DataType| match data_type {
        DataType::LargeList(item) | DataType::List(item) | DataType::FixedSizeList(item, _) => {
            Some(item.data_type().clone())
        }
        _ => None,
    };
    for batch in batches {
        for (field, output) in batch.schema_ref().fields().iter().zip(&definition.outputs) {
            let data_type = field.data_type();
            let agrees = match output.value_type {
                ValueType::Integer => *data_type == DataType::Int64,
                ValueType::Number => *data_type == DataType::Float64,
                ValueType::Boolean => *data_type == DataType::Boolean,
                ValueType::String => *data_type == DataType::Utf8,
                ValueType::Integers => element(data_type) == Some(DataType::Int64),
                ValueType::Strings => element(data_type) == Some(DataType::Utf8),
                // fastRP's embedding is a fixed-width Float32 vector.
                ValueType::Numbers => matches!(
                    element(data_type),
                    Some(DataType::Float64 | DataType::Float32)
                ),
                ref other => panic!("{name}: undeclarable output type {other:?}"),
            };
            assert!(
                agrees,
                "{name}.{}: declared {:?}, Arrow {data_type}",
                output.name, output.value_type
            );
        }
    }
}

/// Four nodes, `a`, `b`, `c` and `isolate`, with these edges, weighted 1.0
/// each or unweighted. No edges means no nodes either: the empty graph.
fn fixture(
    context: &ExecutionContext,
    orientation: Orientation,
    edges: &[(usize, usize)],
    weighted: bool,
) -> GraphProjection {
    let nodes: Vec<_> = if edges.is_empty() {
        Vec::new()
    } else {
        vec!["a".into(), "b".into(), "c".into(), "isolate".into()]
    };
    GraphProjection::from_topology(
        SnapshotIdentity::new("g".into(), "r1".into(), "reader".into()).unwrap(),
        nodes,
        edges
            .iter()
            .enumerate()
            .map(|(ordinal, &(source, target))| ProjectionEdge {
                source,
                target,
                ordinal,
                id: None,
            })
            .collect(),
        weighted.then(|| vec![1.0; edges.len()]),
        orientation,
        context,
    )
    .unwrap()
}

/// Run `name` on a fixture with the generic arguments the catalog test uses,
/// on an undirected projection if the kernel refuses a directed one.
fn run_on_fixture(
    registry: &ProcedureRegistry,
    name: &str,
    edges: &[(usize, usize)],
    weighted: bool,
) -> Vec<RecordBatch> {
    let args = arguments(registry, name, serde_json::json!({}));
    let context = context();
    let graph = fixture(&context, Orientation::Outgoing, edges, weighted);
    match run_any(name, &graph, &args) {
        Err(ProcedureError::InvalidArguments(message)) if message.contains("undirected") => {
            let graph = fixture(&context, Orientation::Undirected, edges, weighted);
            drain(run_any(name, &graph, &args).unwrap_or_else(|e| panic!("{name}: {e}")))
        }
        outcome => drain(outcome.unwrap_or_else(|e| panic!("{name}: {e}"))),
    }
}

type Edges<'a> = &'a [(usize, usize)];
/// The fixtures where a column held a null, and those where it held none.
type Coverage<'a> = (Vec<&'a str>, Vec<&'a str>);

/// A column's nullability is the registration's, not the rows': a nullable
/// column reports nullable when it is full, a non-nullable one never does, and
/// an empty batch reports the same as a full one. Each of the fixtures is
/// chosen so that every declared-nullable column is seen holding a null on one
/// and holding none on another; the test fails if a fixture change loses one of
/// those, or if a kernel declares a nullable column the fixtures do not cover.
#[test]
fn every_batch_reports_the_declared_nullability_whether_or_not_it_holds_nulls() {
    let registry = registry();
    // A path a -> b -> c and an isolate: the isolate is unreachable, and a, c
    // and the isolate have fewer than two neighbours.
    let path: &[(usize, usize)] = &[(0, 1), (1, 2)];
    // A triangle a, b, c, with the isolate joined to c and a: every node is
    // reachable from a and has two or more neighbours, and there is a cycle.
    let covered: &[(usize, usize)] = &[(0, 1), (1, 2), (2, 0), (2, 3), (3, 0)];
    // Only a - c: the community {b, isolate} (the property graph alternates
    // communities) has no edge, so its conductance is undefined.
    let lonely: &[(usize, usize)] = &[(0, 2)];
    let fixtures: [(&str, Edges, bool); 4] = [
        ("weighted path", path, true),
        ("unweighted path", path, false),
        ("covered", covered, true),
        ("lonely community", lonely, true),
    ];

    // (kernel, declared-nullable column) -> (fixtures where it held a null,
    // fixtures where it held none).
    let mut seen: BTreeMap<(String, String), Coverage> = BTreeMap::new();
    let mut empty_checked = Vec::new();
    for name in projection_kernel_names() {
        let definition = registry
            .resolve(&format!("grust.algorithms.{name}"))
            .unwrap()
            .definition()
            .clone();
        for (fixture_name, edges, weighted) in fixtures {
            let batches = run_on_fixture(&registry, name, edges, weighted);
            assert_declared_nullability(name, &definition, &batches);
            for (column, output) in definition.outputs.iter().enumerate() {
                if !output.nullable {
                    continue;
                }
                let nulls: usize = batches.iter().map(|b| b.column(column).null_count()).sum();
                let rows: usize = batches.iter().map(RecordBatch::num_rows).sum();
                let entry = seen
                    .entry((name.to_string(), output.name.clone()))
                    .or_default();
                if nulls > 0 {
                    entry.0.push(fixture_name);
                } else if rows > 0 {
                    entry.1.push(fixture_name);
                }
            }
        }
        // No nodes at all. A kernel that takes a node argument cannot be
        // called; a table kernel emits one empty batch, which must still carry
        // the declared schema.
        let takes_node = definition
            .arguments
            .iter()
            .any(|a| matches!(a.field.value_type, ValueType::String | ValueType::Strings));
        if !takes_node {
            let batches = run_on_fixture(&registry, name, &[], false);
            assert_declared_nullability(name, &definition, &batches);
            if batches.iter().any(|b| b.num_rows() == 0) {
                empty_checked.push(name);
            }
        }
    }

    let expected = [
        ("bellmanFord", "distance"),
        ("bfs", "distance"),
        ("degree", "strength"),
        ("dijkstra", "distance"),
        ("localClusteringCoefficient", "coefficient"),
        ("longestPath", "distance"),
        ("modularity", "conductance"),
        ("multiSourceBfs", "distance"),
    ];
    let declared: Vec<(&str, &str)> = seen
        .keys()
        .map(|(kernel, column)| (kernel.as_str(), column.as_str()))
        .collect();
    assert_eq!(
        declared, expected,
        "the kernels that declare a nullable output"
    );
    for ((kernel, column), (with_nulls, without)) in &seen {
        assert!(
            !with_nulls.is_empty() && !without.is_empty(),
            "{kernel}.{column}: held a null on {with_nulls:?}, none on {without:?}; \
             the fixtures must show it both ways"
        );
    }
    for kernel in ["longestPath", "localClusteringCoefficient", "modularity"] {
        assert!(
            empty_checked.contains(&kernel),
            "{kernel} emitted no empty batch on the empty graph; checked {empty_checked:?}"
        );
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
            let outcome = run_any(name, &graph, &args);
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

/// A kernel declares the options through which it names node properties, and
/// the declaration is readable before any call is built. Validation fills an
/// absent option from its default, so the requests for a call always name some
/// column; the declaration is how a caller that builds its own graph learns
/// which columns to stage, and of what kind, before building that call.
#[test]
fn a_kernel_declares_the_options_that_name_its_node_properties() {
    // Every registered kernel answers, and a topology kernel answers "none".
    for name in projection_kernel_names() {
        let declared =
            node_property_options(name).unwrap_or_else(|error| panic!("{name}: {error}"));
        for option in declared {
            assert!(
                !option.option.is_empty(),
                "{name} declared a property option with no name"
            );
        }
    }

    assert!(
        node_property_options("pagerank")
            .expect("pagerank")
            .is_empty(),
        "a topology kernel declares no property options"
    );

    // A*'s two coordinates, in declaration order, both required.
    let coordinates: Vec<&str> = node_property_options("astar")
        .expect("astar")
        .iter()
        .map(|option| option.option)
        .collect();
    assert_eq!(coordinates, ["latitudeProperty", "longitudeProperty"]);

    // The prefixed spelling resolves to the same kernel.
    assert_eq!(
        node_property_options("grust.algorithms.astar")
            .expect("prefixed")
            .len(),
        2
    );

    assert!(node_property_options("nosuchkernel").is_err());

    // Validation fills each declared option from its default, so a call that
    // names nothing still requests a column per declared option, in order.
    let registry = registry();
    let resolved = registry.resolve("grust.algorithms.astar").expect("astar");
    let defaults = resolved
        .validate_arguments(vec![
            Value::from("a"),
            Value::from("b"),
            Value::Json(serde_json::json!({})),
        ])
        .expect("astar with defaults");
    let requested: Vec<&str> = node_property_requests("astar", &defaults)
        .expect("requests from defaults")
        .iter()
        .map(|request| request.key)
        .collect();
    assert_eq!(requested, ["latitude", "longitude"]);

    // Naming a column per declared option yields exactly those columns.
    let named = resolved
        .validate_arguments(vec![
            Value::from("a"),
            Value::from("b"),
            Value::Json(serde_json::json!({
                "latitudeProperty": "lat",
                "longitudeProperty": "lon",
            })),
        ])
        .expect("astar with named columns");
    let requested: Vec<&str> = node_property_requests("astar", &named)
        .expect("requests from named columns")
        .iter()
        .map(|request| request.key)
        .collect();
    assert_eq!(requested, ["lat", "lon"]);

    // A declaration can be conditional: linkPrediction declares its community
    // for every call, and reads it only under `sameCommunity`.
    let link = node_property_options("linkPrediction").expect("linkPrediction");
    assert_eq!(link.len(), 1);
    assert_eq!(link[0].option, "communityProperty");
    for (metric, needed) in [("sameCommunity", true), ("adamicAdar", false)] {
        let args = arguments(
            &registry,
            "linkPrediction",
            serde_json::json!({"metric": metric}),
        );
        assert_eq!(link[0].needed(&args).expect(metric), needed, "{metric}");
    }
}

/// Rows of a two-string, one-number result.
fn scored_pairs(batches: &[RecordBatch]) -> Vec<(String, String, f64)> {
    use arrow_array::{Array, Float64Array, StringArray};
    let mut rows = Vec::new();
    for batch in batches {
        let text = |index: usize| {
            batch
                .column(index)
                .as_any()
                .downcast_ref::<StringArray>()
                .unwrap()
                .clone()
        };
        let (first, second) = (text(0), text(1));
        let score = batch
            .column(2)
            .as_any()
            .downcast_ref::<Float64Array>()
            .unwrap();
        for row in 0..batch.num_rows() {
            rows.push((
                first.value(row).to_string(),
                second.value(row).to_string(),
                score.value(row),
            ));
        }
    }
    rows
}

#[test]
fn link_prediction_runs_every_metric_and_asks_for_the_community_only_when_it_scores_by_it() {
    let registry = registry();
    let context = context();
    // a - b - c undirected, plus an isolate: (a, c) is the one pair at
    // distance two, sharing b, whose neighbours are a and c. The property graph
    // puts a and c in community 0.
    let graph = projection(&context, Orientation::Undirected);
    let expected = [
        ("commonNeighbors", 1.0),
        ("adamicAdar", 1.0 / 2f64.ln()),
        ("resourceAllocation", 0.5),
        ("preferentialAttachment", 1.0),
        ("totalNeighbors", 1.0),
        ("sameCommunity", 1.0),
    ];
    for (metric, score) in expected {
        let args = arguments(
            &registry,
            "linkPrediction",
            serde_json::json!({"orientation": "undirected", "metric": metric}),
        );
        let wanted = node_property_requests("linkPrediction", &args).unwrap();
        if metric == "sameCommunity" {
            assert_eq!(wanted.len(), 1);
            assert_eq!(wanted[0].key, "community");
            assert_eq!(wanted[0].kind, grust_algorithms::PropertyKind::Integer);
            // Without its property it cannot run on the projection alone.
            assert!(matches!(
                run_on_projection("linkPrediction", &graph, &args),
                Err(ProcedureError::Unsupported(_))
            ));
        } else {
            assert!(wanted.is_empty(), "{metric} asked for {}", wanted.len());
            // Reading no property, it runs on the projection alone too.
            let plain = scored_pairs(&drain(
                run_on_projection("linkPrediction", &graph, &args).unwrap(),
            ));
            assert_eq!(plain, [("a".into(), "c".into(), score)], "{metric}");
        }
        // Every metric runs through the property path Nutmeg serves.
        let properties =
            NodeProperties::from_graph(&property_graph(graph.node_count()), &graph, &wanted)
                .unwrap();
        let rows = scored_pairs(&drain(
            run_with_properties("linkPrediction", &properties, &args).unwrap(),
        ));
        assert_eq!(rows, [("a".into(), "c".into(), score)], "{metric}");
    }

    // A named community property is the one requested, for sameCommunity only.
    let named = arguments(
        &registry,
        "linkPrediction",
        serde_json::json!({"metric": "sameCommunity", "communityProperty": "c"}),
    );
    assert_eq!(
        node_property_requests("linkPrediction", &named).unwrap()[0].key,
        "c"
    );
    let ignored = arguments(
        &registry,
        "linkPrediction",
        serde_json::json!({"metric": "adamicAdar", "communityProperty": "c"}),
    );
    assert!(
        node_property_requests("linkPrediction", &ignored)
            .unwrap()
            .is_empty()
    );

    // Explicit candidates are scored as given, in order, adjacent or not: the
    // adjacent a and b are each in the other's neighbours, so N(a) ∪ N(b) is
    // {a, b, c}.
    let explicit = arguments(
        &registry,
        "linkPrediction",
        serde_json::json!({
            "orientation": "undirected",
            "metric": "totalNeighbors",
            "node1": ["c", "a", "isolate"],
            "node2": ["a", "b", "isolate"],
        }),
    );
    let rows = scored_pairs(&drain(
        run_on_projection("linkPrediction", &graph, &explicit).unwrap(),
    ));
    assert_eq!(
        rows,
        [
            ("c".into(), "a".into(), 1.0),
            ("a".into(), "b".into(), 3.0),
            ("isolate".into(), "isolate".into(), 0.0),
        ]
    );

    for (options, fragment) in [
        (
            serde_json::json!({"orientation": "undirected", "node1": ["a"]}),
            "together",
        ),
        (
            serde_json::json!({"orientation": "undirected", "node1": ["a"], "node2": ["b", "c"]}),
            "length",
        ),
        (
            serde_json::json!({"orientation": "undirected", "node1": ["a"], "node2": ["nobody"]}),
            "nobody",
        ),
        (serde_json::json!({"metric": "jaccard"}), "metric must be"),
        (serde_json::json!({}), "undirected"),
    ] {
        let args = arguments(&registry, "linkPrediction", options.clone());
        let graph = if options["orientation"] == "undirected" {
            projection(&context, Orientation::Undirected)
        } else {
            projection(&context, Orientation::Outgoing)
        };
        match run_on_projection("linkPrediction", &graph, &args) {
            Err(ProcedureError::InvalidArguments(message)) => {
                assert!(message.contains(fragment), "{options}: {message}")
            }
            Err(other) => panic!("{options}: {other}"),
            Ok(_) => panic!("{options} ran"),
        }
    }
    // The community property has a default and cannot be null.
    let resolved = registry.resolve("grust.algorithms.linkPrediction").unwrap();
    assert!(
        resolved
            .validate_arguments(vec![Value::Json(
                serde_json::json!({"communityProperty": null})
            )])
            .is_err()
    );
}
