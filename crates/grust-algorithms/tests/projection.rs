use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, MissingWeight, Orientation,
    ProjectionEdge, ProjectionOptions, SnapshotIdentity, WeightSelection, dijkstra,
};
use grust_core::{Edge, Graph, Node, Props, Value};

fn context() -> ExecutionContext {
    ExecutionContext::new(ExecutionLimits {
        memory_bytes: 1 << 20,
        work_units: 1_000_000,
        batch_rows: 128,
        deadline: None,
    })
    .unwrap()
}

fn identity() -> SnapshotIdentity {
    SnapshotIdentity::new("g".into(), "r1".into(), "reader".into()).unwrap()
}

fn fixture() -> Graph {
    Graph::new(
        vec![
            Node::new("Selected", "a", Props::new()),
            Node::new("Selected", "b", Props::new()),
            Node::new("Other", "c", Props::new()),
            Node::new("Selected", "isolate", Props::new()),
        ],
        vec![
            Edge::new("R", "a", "c", Props::new()),
            Edge::new("R", "a", "b", [("cost".into(), Value::Float(2.5))]).with_id("edge"),
            Edge::new("Other", "b", "a", Props::new()),
        ],
    )
}

#[test]
fn selection_keeps_original_ordinals_and_ignores_unselected_properties() {
    let graph = fixture();
    let ctx = context();
    let node_labels = ["Selected".into()];
    let relationship_labels = ["R".into()];
    let options = ProjectionOptions {
        node_labels: Some(&node_labels),
        relationship_labels: Some(&relationship_labels),
        weight: WeightSelection::Property {
            key: "cost",
            missing: MissingWeight::Reject,
        },
        ..Default::default()
    };
    let projection = GraphProjection::from_graph(&graph, identity(), options, &ctx).unwrap();
    assert_eq!(
        projection.representation(),
        grust_algorithms::ProjectionRepresentation::PropertyGraph
    );
    let selection = projection.selection().unwrap();
    assert_eq!(
        selection.node_labels.as_deref(),
        Some(node_labels.as_slice())
    );
    assert_eq!(
        selection.relationship_labels.as_deref(),
        Some(relationship_labels.as_slice())
    );
    assert_eq!(selection.weight_property.as_deref(), Some("cost"));
    assert_eq!(selection.missing_weight, Some(MissingWeight::Reject));
    assert_eq!(
        projection
            .node_ids()
            .iter()
            .map(|id| id.as_str())
            .collect::<Vec<_>>(),
        vec!["a", "b", "isolate"]
    );
    assert_eq!(projection.edges().len(), 1);
    assert_eq!(projection.edges()[0].ordinal, 1);
    assert_eq!(projection.edges()[0].id.as_ref().unwrap().as_str(), "edge");
    assert_eq!(
        dijkstra(&projection, "a").unwrap().values(),
        &[0.0, 2.5, f64::INFINITY]
    );
    drop(projection);
    assert_eq!(ctx.usage().unwrap().live_bytes, 0);
}

#[test]
fn rejects_ambiguous_topology_and_invalid_weights_without_leaking_admission() {
    for weight in [-1.0, f64::NAN, f64::INFINITY] {
        let ctx = context();
        assert!(
            GraphProjection::from_topology(
                identity(),
                vec!["a".into()],
                vec![ProjectionEdge {
                    source: 0,
                    target: 0,
                    ordinal: 0,
                    id: None
                }],
                Some(vec![weight]),
                Orientation::Outgoing,
                &ctx
            )
            .is_err()
        );
        assert_eq!(ctx.usage().unwrap().live_bytes, 0);
    }
    let mut graph = fixture();
    graph.nodes.push(graph.nodes[0].clone());
    assert!(
        GraphProjection::from_graph(&graph, identity(), ProjectionOptions::default(), &context())
            .is_err()
    );
    graph.nodes.pop();
    graph.edges[0].to = "missing".into();
    let no_labels = [];
    assert!(
        GraphProjection::from_graph(
            &graph,
            identity(),
            ProjectionOptions {
                node_labels: Some(&no_labels),
                ..Default::default()
            },
            &context()
        )
        .is_err()
    );
}

#[test]
fn missing_null_and_large_integer_weights_have_explicit_semantics() {
    let mut graph = Graph::new(
        vec![Node::new("N", "a", Props::new())],
        vec![Edge::new("R", "a", "a", Props::new())],
    );
    let reject = ProjectionOptions {
        weight: WeightSelection::Property {
            key: "cost",
            missing: MissingWeight::Reject,
        },
        ..Default::default()
    };
    assert!(GraphProjection::from_graph(&graph, identity(), reject, &context()).is_err());
    graph.edges[0].props.insert("cost".into(), Value::Null);
    assert!(GraphProjection::from_graph(&graph, identity(), reject, &context()).is_err());
    let defaults = ProjectionOptions {
        weight: WeightSelection::Property {
            key: "cost",
            missing: MissingWeight::Default(3.0),
        },
        ..Default::default()
    };
    assert!(GraphProjection::from_graph(&graph, identity(), defaults, &context()).is_ok());
    graph.edges[0]
        .props
        .insert("cost".into(), Value::Int(i64::MAX));
    assert!(matches!(
        GraphProjection::from_graph(&graph, identity(), reject, &context()),
        Err(AlgorithmError::InvalidArguments(_))
    ));
}

#[cfg(feature = "arrow")]
mod arrow {
    use super::*;
    use arrow_array::{ArrayRef, BooleanArray, Float64Array, RecordBatch, StringArray};
    use std::sync::Arc;

    #[test]
    fn native_batches_preserve_selection_ids_presence_and_global_edge_ordinals() {
        let node_batch = RecordBatch::try_from_iter([
            (
                "node_id",
                Arc::new(StringArray::from(vec!["a", "b", "c", "isolate"])) as ArrayRef,
            ),
            (
                "label",
                Arc::new(StringArray::from(vec![
                    "Selected", "Selected", "Other", "Selected",
                ])),
            ),
        ])
        .unwrap();
        let edge_batch = RecordBatch::try_from_iter([
            (
                "source",
                Arc::new(StringArray::from(vec!["a", "a", "b"])) as ArrayRef,
            ),
            ("target", Arc::new(StringArray::from(vec!["c", "b", "a"]))),
            (
                "label",
                Arc::new(StringArray::from(vec!["R", "R", "Other"])),
            ),
            (
                "edge_id",
                Arc::new(StringArray::from(vec![None, Some("edge"), None])),
            ),
            (
                "property.cost",
                Arc::new(Float64Array::from(vec![Some(99.0), Some(2.5), None])),
            ),
            (
                "present.cost",
                Arc::new(BooleanArray::from(vec![false, true, true])),
            ),
        ])
        .unwrap();
        let nodes = [node_batch.slice(0, 1), node_batch.slice(1, 3)];
        let edges = [edge_batch.slice(0, 1), edge_batch.slice(1, 2)];
        let node_labels = ["Selected".into()];
        let relationship_labels = ["R".into()];
        let options = ProjectionOptions {
            node_labels: Some(&node_labels),
            relationship_labels: Some(&relationship_labels),
            weight: WeightSelection::Property {
                key: "cost",
                missing: MissingWeight::Reject,
            },
            ..Default::default()
        };
        let ctx = context();
        let native =
            GraphProjection::from_arrow_batches(identity(), &nodes, &edges, options, &ctx).unwrap();
        let reference =
            GraphProjection::from_graph(&fixture(), identity(), options, &context()).unwrap();
        assert_eq!(
            native.representation(),
            grust_algorithms::ProjectionRepresentation::ArrowBatches
        );
        assert_eq!(
            native.selection().unwrap().weight_property.as_deref(),
            Some("cost")
        );
        assert_eq!(native.node_ids(), reference.node_ids());
        assert_eq!(native.edges()[0].ordinal, 1);
        assert_eq!(
            dijkstra(&native, "a").unwrap().values(),
            dijkstra(&reference, "a").unwrap().values()
        );
        drop(native);
        assert_eq!(ctx.usage().unwrap().live_bytes, 0);
        // The absent first edge must use the declared missing-value policy,
        // even though its backing numeric slot contains a nonnull 99.0.
        assert!(
            GraphProjection::from_arrow_batches(
                identity(),
                &nodes,
                &edges,
                ProjectionOptions {
                    node_labels: None,
                    relationship_labels: None,
                    ..options
                },
                &ctx
            )
            .is_err()
        );
    }
    #[test]
    fn duplicate_structural_columns_fail_and_release_preparation() {
        let nodes = RecordBatch::try_from_iter([
            (
                "node_id",
                Arc::new(StringArray::from(vec!["a"])) as ArrayRef,
            ),
            ("node_id", Arc::new(StringArray::from(vec!["b"]))),
            ("label", Arc::new(StringArray::from(vec!["N"]))),
        ])
        .unwrap();
        let ctx = context();
        assert!(
            matches!(GraphProjection::from_arrow_batches(identity(), &[nodes], &[], ProjectionOptions::default(), &ctx), Err(AlgorithmError::InvalidArguments(message)) if message.contains("duplicate Arrow column"))
        );
        assert_eq!(ctx.usage().unwrap().live_bytes, 0);
    }
}

/// A projection's transpose is built by the first kernel that needs it, and
/// that kernel pays for it. `prepare_incoming` moves the build earlier without
/// changing what is built: the kernel afterwards charges exactly the transpose's
/// work less than it would have, a second prepare charges nothing, and the
/// kernel's result is bit-identical either way.
#[test]
fn preparing_the_transpose_moves_its_cost_without_changing_the_answer() {
    use grust_algorithms::{PageRankOptions, pagerank};

    // A directed ring with chords. PageRank pulls, and so reads the transpose,
    // only above a parallel floor of 1 << 14 units, (nodes + arcs) * 2; below it
    // the push path runs and never builds one. 5,000 nodes and 10,000 arcs is
    // 30,000 units, clear of it. A 2,000-node version of this fixture sat under
    // the floor and tested the push path instead, which is checked below.
    let n = 5_000usize;
    let edges: Vec<ProjectionEdge> = (0..n)
        .flat_map(|node| [(node, (node + 1) % n), (node, (node * 7 + 3) % n)])
        .enumerate()
        .map(|(ordinal, (source, target))| ProjectionEdge {
            source,
            target,
            ordinal,
            id: None,
        })
        .collect();
    let build = |context: &ExecutionContext| {
        GraphProjection::from_topology(
            identity(),
            (0..n).map(|node| format!("{node}").into()).collect(),
            edges.clone(),
            None,
            Orientation::Outgoing,
            context,
        )
        .unwrap()
    };
    // One worker selects the pull kernel, which reads the transpose.
    let pull = || {
        ExecutionContext::new(ExecutionLimits {
            memory_bytes: 1 << 26,
            work_units: usize::MAX,
            batch_rows: 128,
            deadline: None,
        })
        .unwrap()
        .with_concurrency(1)
        .unwrap()
    };
    let options = || PageRankOptions {
        damping: 0.85,
        tolerance: 1e-10,
        max_iterations: 50,
        personalization: None,
    };
    let work = |context: &ExecutionContext| context.usage().unwrap().work_units;

    // Lazily: the kernel builds the transpose itself.
    let lazy_context = pull();
    let lazy = build(&lazy_context);
    let before = work(&lazy_context);
    let lazy_scores = pagerank(&lazy, options()).unwrap();
    let lazy_kernel = work(&lazy_context) - before;
    // The fixture reached the pull kernel: it built the transpose, so a prepare
    // afterwards finds it cached and builds nothing.
    let before = work(&lazy_context);
    lazy.prepare_incoming().unwrap();
    assert_eq!(
        work(&lazy_context),
        before,
        "the lazy kernel did not build the transpose, so it did not pull"
    );

    // Eagerly: the transpose is built first, and the kernel does not build it.
    let eager_context = pull();
    let eager = build(&eager_context);
    let before = work(&eager_context);
    eager.prepare_incoming().unwrap();
    let transpose = work(&eager_context) - before;
    let before = work(&eager_context);
    eager.prepare_incoming().unwrap();
    assert_eq!(
        work(&eager_context),
        before,
        "a second prepare builds nothing"
    );
    let before = work(&eager_context);
    let eager_scores = pagerank(&eager, options()).unwrap();
    let eager_kernel = work(&eager_context) - before;

    assert!(
        transpose > 0,
        "the fixture must make the transpose real work"
    );
    assert_eq!(
        lazy_kernel,
        eager_kernel + transpose,
        "the kernel's work falls by exactly the transpose's"
    );
    let bits = |scores: &[f64]| scores.iter().map(|s| s.to_bits()).collect::<Vec<_>>();
    assert_eq!(bits(lazy_scores.values()), bits(eager_scores.values()));
}
