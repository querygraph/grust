//! Node properties: row alignment, every kind, every missing policy, and the
//! ways a read must fail rather than guess.

use grust_algorithms::{
    AlgorithmError, ExecutionContext, ExecutionLimits, GraphProjection, MissingProperty,
    NodeProperties, ProjectionOptions, PropertyKind, PropertyRequest, SnapshotIdentity,
};
use grust_core::{Edge, Graph, Node, Props, Value};

fn limits(memory_bytes: usize, work_units: usize) -> ExecutionLimits {
    ExecutionLimits {
        memory_bytes,
        work_units,
        batch_rows: 1024,
        deadline: None,
    }
}

fn context() -> ExecutionContext {
    ExecutionContext::new(limits(64 * 1024 * 1024, 100_000_000)).unwrap()
}

fn identity() -> SnapshotIdentity {
    SnapshotIdentity::new("g".into(), "r".into(), "reader".into()).unwrap()
}

fn node(label: &str, id: &str, props: &[(&str, Value)]) -> Node {
    let props: Props = props
        .iter()
        .map(|(key, value)| ((*key).to_string(), value.clone()))
        .collect();
    Node::new(label, id, props)
}

/// People and one place. The place sits between people in snapshot order, so a
/// label selection that drops it shifts every later row.
fn graph() -> Graph {
    Graph::new(
        vec![
            node(
                "Person",
                "ann",
                &[
                    ("age", Value::Int(31)),
                    ("score", Value::Float(0.5)),
                    ("team", Value::String("red".into())),
                    ("vec", Value::FloatArray(vec![1.0, 2.0, 3.0])),
                    ("seed", Value::Int(7)),
                    ("active", Value::Bool(true)),
                ],
            ),
            node("Place", "rome", &[("age", Value::Int(2700))]),
            node(
                "Person",
                "bob",
                &[
                    ("age", Value::Int(45)),
                    ("score", Value::Int(2)),
                    ("team", Value::String("blue".into())),
                    ("vec", Value::IntArray(vec![4, 5, 6])),
                    ("active", Value::Bool(false)),
                ],
            ),
            node(
                "Person",
                "cy",
                &[
                    ("age", Value::Int(19)),
                    ("score", Value::Float(-1.25)),
                    ("team", Value::String("red".into())),
                    ("vec", Value::FloatArray(vec![7.0, 8.0, 9.0])),
                    ("seed", Value::Null),
                    ("active", Value::Bool(true)),
                ],
            ),
        ],
        vec![Edge::new("KNOWS", "ann", "bob", Props::new())],
    )
}

fn people(graph: &Graph, context: &ExecutionContext) -> GraphProjection {
    let labels = ["Person".to_string()];
    GraphProjection::from_graph(
        graph,
        identity(),
        ProjectionOptions {
            node_labels: Some(&labels),
            ..Default::default()
        },
        context,
    )
    .unwrap()
}

fn request(key: &str, kind: PropertyKind, missing: MissingProperty) -> PropertyRequest<'_> {
    PropertyRequest { key, kind, missing }
}

#[test]
fn every_kind_is_read_in_projection_row_order_under_a_label_selection() {
    let graph = graph();
    let context = context();
    let projection = people(&graph, &context);
    assert_eq!(projection.node_count(), 3, "the place is not projected");
    let properties = NodeProperties::from_graph(
        &graph,
        &projection,
        &[
            PropertyRequest::required("age", PropertyKind::Integer),
            PropertyRequest::required("score", PropertyKind::Number),
            PropertyRequest::required("team", PropertyKind::Category),
            PropertyRequest::required("vec", PropertyKind::Vector),
            PropertyRequest::required("active", PropertyKind::Integer),
        ],
    )
    .unwrap();
    // Rome's 2700 is nowhere: rows are the projection's, not the snapshot's.
    assert_eq!(properties.integers("age").unwrap(), [31, 45, 19]);
    // An integer is a number when a number was asked for.
    assert_eq!(properties.numbers("score").unwrap(), [0.5, 2.0, -1.25]);
    // Booleans are 0 and 1.
    assert_eq!(properties.integers("active").unwrap(), [1, 0, 1]);

    let teams = properties.categories("team").unwrap();
    assert_eq!(teams.dictionary, ["red", "blue"], "first appearance by row");
    assert_eq!(teams.codes, [0, 1, 0]);
    assert_eq!(teams.code_of("blue"), Some(1));
    assert_eq!(teams.code_of("green"), None);

    let vectors = properties.vectors("vec").unwrap();
    assert_eq!(vectors.dimension, 3);
    assert_eq!(
        vectors.row(1),
        [4.0, 5.0, 6.0],
        "an integer list is a vector"
    );
    assert_eq!(vectors.row(2), [7.0, 8.0, 9.0]);

    assert_eq!(
        properties.keys().collect::<Vec<_>>(),
        ["age", "score", "team", "vec", "active"]
    );
    assert_eq!(properties.projection().node_count(), 3);
}

#[test]
fn a_missing_value_is_an_error_a_default_or_a_null_as_asked() {
    let graph = graph();
    let context = context();
    let projection = people(&graph, &context);
    let read = |missing| {
        NodeProperties::from_graph(
            &graph,
            &projection,
            &[request("seed", PropertyKind::Integer, missing)],
        )
    };
    // Bob has no seed and Cy's is null: both are absent, and absence is an
    // error unless the caller said what to do about it.
    match read(MissingProperty::Reject) {
        Err(AlgorithmError::InvalidArguments(message)) => {
            assert!(
                message.contains("bob") && message.contains("seed"),
                "{message}"
            )
        }
        other => panic!("{:?}", other.map(|_| ())),
    }
    assert_eq!(
        read(MissingProperty::Default(-1.0))
            .unwrap()
            .integers("seed")
            .unwrap(),
        [7, -1, -1]
    );
    let kept = read(MissingProperty::Null).unwrap();
    assert_eq!(
        kept.optional_integers("seed").unwrap(),
        (&[7, 0, 0][..], &[true, false, false][..])
    );
    // A kernel that did not ask for nulls cannot read a column that has them,
    // and one that asked cannot read a column that has none as if it had.
    assert!(kept.integers("seed").is_err());
    assert!(
        read(MissingProperty::Default(0.0))
            .unwrap()
            .optional_integers("seed")
            .is_err()
    );

    // A vector default fills rows that came before the first value too.
    let sparse = Graph::new(
        vec![
            node("Person", "a", &[]),
            node("Person", "b", &[("vec", Value::FloatArray(vec![1.0, 2.0]))]),
            node("Person", "c", &[]),
        ],
        vec![],
    );
    let projection = people(&sparse, &context);
    let properties = NodeProperties::from_graph(
        &sparse,
        &projection,
        &[request(
            "vec",
            PropertyKind::Vector,
            MissingProperty::Default(0.5),
        )],
    )
    .unwrap();
    assert_eq!(
        properties.vectors("vec").unwrap().values,
        [0.5, 0.5, 1.0, 2.0, 0.5, 0.5]
    );
}

#[test]
fn a_read_fails_rather_than_guesses() {
    let graph = graph();
    let context = context();
    let projection = people(&graph, &context);
    let held = context.usage().unwrap().live_bytes;
    let fails = |wanted: &[PropertyRequest<'_>], needle: &str| match NodeProperties::from_graph(
        &graph,
        &projection,
        wanted,
    ) {
        Err(AlgorithmError::InvalidArguments(message)) => {
            assert!(message.contains(needle), "{message:?} lacks {needle:?}")
        }
        other => panic!("{needle}: {:?}", other.map(|_| ())),
    };
    // The wrong kind, each way round.
    fails(
        &[PropertyRequest::required("team", PropertyKind::Number)],
        "not a finite number",
    );
    fails(
        &[PropertyRequest::required("score", PropertyKind::Integer)],
        "not an integer",
    );
    fails(
        &[PropertyRequest::required("age", PropertyKind::Vector)],
        "not a numeric list",
    );
    fails(
        &[PropertyRequest::required("age", PropertyKind::Category)],
        "not a string",
    );
    // Requests that mean nothing.
    fails(
        &[PropertyRequest::required("", PropertyKind::Number)],
        "nonempty",
    );
    fails(
        &[
            PropertyRequest::required("age", PropertyKind::Integer),
            PropertyRequest::required("age", PropertyKind::Number),
        ],
        "twice",
    );
    fails(
        &[request(
            "team",
            PropertyKind::Category,
            MissingProperty::Default(0.0),
        )],
        "no default",
    );
    fails(
        &[request("vec", PropertyKind::Vector, MissingProperty::Null)],
        "cannot keep nulls",
    );
    fails(
        &[request(
            "age",
            PropertyKind::Integer,
            MissingProperty::Default(1.5),
        )],
        "whole number",
    );
    fails(
        &[request(
            "score",
            PropertyKind::Number,
            MissingProperty::Default(f64::NAN),
        )],
        "finite",
    );
    assert_eq!(
        context.usage().unwrap().live_bytes,
        held,
        "failed reads leak nothing"
    );

    let bad = |props: Vec<(&str, Value)>, kind, needle: &str| {
        let graph = Graph::new(
            vec![
                node(
                    "Person",
                    "ok",
                    &[
                        ("p", Value::FloatArray(vec![1.0, 2.0])),
                        ("n", Value::Float(1.0)),
                    ],
                ),
                node("Person", "bad", &props),
            ],
            vec![],
        );
        let projection = people(&graph, &context);
        match NodeProperties::from_graph(
            &graph,
            &projection,
            &[PropertyRequest::required(props[0].0, kind)],
        ) {
            Err(AlgorithmError::InvalidArguments(message)) => {
                assert!(
                    message.contains(needle) && message.contains("bad"),
                    "{message}"
                )
            }
            other => panic!("{needle}: {:?}", other.map(|_| ())),
        }
    };
    // Ragged, empty, not finite, and finite in f64 but not once narrowed to f32.
    bad(
        vec![("p", Value::FloatArray(vec![1.0, 2.0, 3.0]))],
        PropertyKind::Vector,
        "3 components",
    );
    bad(
        vec![("p", Value::FloatArray(vec![]))],
        PropertyKind::Vector,
        "nonempty",
    );
    bad(
        vec![("p", Value::FloatArray(vec![1.0, f64::NAN]))],
        PropertyKind::Vector,
        "single precision",
    );
    bad(
        vec![("p", Value::FloatArray(vec![1.0, 1e300]))],
        PropertyKind::Vector,
        "single precision",
    );
    bad(
        vec![("n", Value::Float(f64::INFINITY))],
        PropertyKind::Number,
        "finite",
    );
    bad(
        vec![("n", Value::Int(i64::MAX))],
        PropertyKind::Number,
        "exact f64 range",
    );

    // Properties read from a graph the projection was not built from.
    let other = Graph::new(
        vec![node("Person", "ann", &[("age", Value::Int(1))])],
        vec![],
    );
    match NodeProperties::from_graph(
        &other,
        &projection,
        &[PropertyRequest::required("age", PropertyKind::Integer)],
    ) {
        Err(AlgorithmError::InvalidArguments(message)) => {
            assert!(message.contains("1 of the projection's 3"), "{message}")
        }
        other => panic!("{:?}", other.map(|_| ())),
    }
    // A key that was never requested.
    let properties = NodeProperties::from_graph(&graph, &projection, &[]).unwrap();
    assert!(properties.numbers("age").is_err());
}

#[test]
fn columns_are_admitted_charged_and_released() {
    let n = 5000;
    let d = 64;
    let nodes: Vec<Node> = (0..n)
        .map(|i| {
            node(
                "Person",
                &format!("n{i}"),
                &[
                    ("vec", Value::FloatArray(vec![i as f64; d])),
                    ("team", Value::String(format!("team-{}", i % 50))),
                ],
            )
        })
        .collect();
    let graph = Graph::new(nodes, vec![]);
    let wanted = [
        PropertyRequest::required("vec", PropertyKind::Vector),
        PropertyRequest::required("team", PropertyKind::Category),
    ];

    let context = context();
    let projection = people(&graph, &context);
    let before = context.usage().unwrap();
    let properties = NodeProperties::from_graph(&graph, &projection, &wanted).unwrap();
    let after = context.usage().unwrap();
    // The vector column alone is n * d * 4 bytes, and it is on the books.
    assert!(after.live_bytes - before.live_bytes >= n * d * 4);
    // One unit per node for the row map, one per node per column, one per component.
    assert!(after.work_units - before.work_units >= n + 2 * n + n * d);
    assert_eq!(properties.categories("team").unwrap().dictionary.len(), 50);
    drop(properties);
    assert_eq!(context.usage().unwrap().live_bytes, before.live_bytes);

    // A memory limit the vectors do not fit is a refusal, before they are built.
    let build = ExecutionContext::new(limits(usize::MAX, usize::MAX)).unwrap();
    let projection_bytes = {
        let _projection = people(&graph, &build);
        build.usage().unwrap().peak_bytes
    };
    let tight = ExecutionContext::new(limits(projection_bytes + n * d * 2, usize::MAX)).unwrap();
    let projection = people(&graph, &tight);
    let held = tight.usage().unwrap().live_bytes;
    assert!(matches!(
        NodeProperties::from_graph(&graph, &projection, &wanted),
        Err(AlgorithmError::BudgetExceeded {
            resource: "memory",
            ..
        })
    ));
    assert_eq!(tight.usage().unwrap().live_bytes, held);

    // So is a work budget, and cancellation.
    let context = self::context();
    let projection = people(&graph, &context);
    context.cancel().unwrap();
    assert!(matches!(
        NodeProperties::from_graph(&graph, &projection, &wanted),
        Err(AlgorithmError::Cancelled)
    ));
}

#[cfg(feature = "arrow")]
mod arrow {
    use std::sync::Arc;

    use super::*;
    use arrow_array::{
        ArrayRef, BooleanArray, Float32Array, Float64Array, Int32Array, Int64Array,
        LargeStringArray, RecordBatch, StringArray,
        builder::{FixedSizeListBuilder, Float32Builder, Float64Builder, ListBuilder},
    };

    fn batch(columns: Vec<(&str, ArrayRef)>) -> RecordBatch {
        RecordBatch::try_from_iter(columns).unwrap()
    }

    fn fixed(rows: &[Option<[f32; 3]>]) -> ArrayRef {
        let mut builder = FixedSizeListBuilder::new(Float32Builder::new(), 3);
        for row in rows {
            match row {
                Some(values) => {
                    builder.values().append_slice(values);
                    builder.append(true);
                }
                None => {
                    builder.values().append_nulls(3);
                    builder.append(false);
                }
            }
        }
        Arc::new(builder.finish()) as ArrayRef
    }

    fn ragged(rows: &[&[f64]]) -> ArrayRef {
        let mut builder = ListBuilder::new(Float64Builder::new());
        for row in rows {
            builder.values().append_slice(row);
            builder.append(true);
        }
        Arc::new(builder.finish()) as ArrayRef
    }

    /// The same people as `graph()`, split across two batches, with the place
    /// between them and the column types varied on purpose.
    fn batches() -> Vec<RecordBatch> {
        vec![
            batch(vec![
                ("node_id", Arc::new(StringArray::from(vec!["ann", "rome"]))),
                (
                    "label",
                    Arc::new(StringArray::from(vec!["Person", "Place"])),
                ),
                ("property.age", Arc::new(Int64Array::from(vec![31, 2700]))),
                (
                    "property.score",
                    Arc::new(Float64Array::from(vec![Some(0.5), None])),
                ),
                (
                    "property.team",
                    Arc::new(StringArray::from(vec![Some("red"), None])),
                ),
                ("property.vec", fixed(&[Some([1.0, 2.0, 3.0]), None])),
                (
                    "property.seed",
                    Arc::new(Int64Array::from(vec![Some(7), None])),
                ),
                (
                    "property.active",
                    Arc::new(BooleanArray::from(vec![Some(true), None])),
                ),
            ]),
            batch(vec![
                ("node_id", Arc::new(StringArray::from(vec!["bob", "cy"]))),
                (
                    "label",
                    Arc::new(StringArray::from(vec!["Person", "Person"])),
                ),
                // Narrower and wider types than the first batch, same column.
                ("property.age", Arc::new(Int32Array::from(vec![45, 19]))),
                (
                    "property.score",
                    Arc::new(Float32Array::from(vec![2.0, -1.25])),
                ),
                (
                    "property.team",
                    Arc::new(LargeStringArray::from(vec!["blue", "red"])),
                ),
                (
                    "property.vec",
                    ragged(&[&[4.0, 5.0, 6.0], &[7.0, 8.0, 9.0]]),
                ),
                // Present says Cy has no seed although the column holds a number.
                (
                    "property.seed",
                    Arc::new(Int64Array::from(vec![None, Some(99)])),
                ),
                (
                    "present.seed",
                    Arc::new(BooleanArray::from(vec![false, false])),
                ),
                (
                    "property.active",
                    Arc::new(BooleanArray::from(vec![false, true])),
                ),
            ]),
        ]
    }

    pub fn people(batches: &[RecordBatch], context: &ExecutionContext) -> GraphProjection {
        let labels = ["Person".to_string()];
        GraphProjection::from_arrow_batches(
            identity(),
            batches,
            &[],
            ProjectionOptions {
                node_labels: Some(&labels),
                ..Default::default()
            },
            context,
        )
        .unwrap()
    }

    #[test]
    fn arrow_batches_read_exactly_what_the_graph_reads() {
        let context = context();
        let batches = batches();
        let projection = people(&batches, &context);
        let wanted = [
            PropertyRequest::required("age", PropertyKind::Integer),
            PropertyRequest::required("score", PropertyKind::Number),
            PropertyRequest::required("team", PropertyKind::Category),
            PropertyRequest::required("vec", PropertyKind::Vector),
            PropertyRequest::required("active", PropertyKind::Integer),
            request("seed", PropertyKind::Integer, MissingProperty::Null),
        ];
        let from_arrow =
            NodeProperties::from_arrow_batches(&batches, &projection, &wanted).unwrap();

        let graph = graph();
        let graph_projection = super::people(&graph, &context);
        let from_graph = NodeProperties::from_graph(&graph, &graph_projection, &wanted).unwrap();

        assert_eq!(
            from_arrow.integers("age").unwrap(),
            from_graph.integers("age").unwrap()
        );
        assert_eq!(
            from_arrow.numbers("score").unwrap(),
            from_graph.numbers("score").unwrap()
        );
        assert_eq!(
            from_arrow.integers("active").unwrap(),
            from_graph.integers("active").unwrap()
        );
        let (arrow_teams, graph_teams) = (
            from_arrow.categories("team").unwrap(),
            from_graph.categories("team").unwrap(),
        );
        assert_eq!(arrow_teams.codes, graph_teams.codes);
        assert_eq!(arrow_teams.dictionary, graph_teams.dictionary);
        let (arrow_vectors, graph_vectors) = (
            from_arrow.vectors("vec").unwrap(),
            from_graph.vectors("vec").unwrap(),
        );
        assert_eq!(arrow_vectors.dimension, 3);
        assert_eq!(arrow_vectors.values, graph_vectors.values);
        // Null in the column and `present = false` are both absence.
        assert_eq!(
            from_arrow.optional_integers("seed").unwrap(),
            from_graph.optional_integers("seed").unwrap()
        );
    }

    #[test]
    fn arrow_reads_fail_rather_than_guess() {
        let context = context();
        let batches = batches();
        let projection = people(&batches, &context);
        let held = context.usage().unwrap().live_bytes;
        let fails = |batches: &[RecordBatch], wanted: &[PropertyRequest<'_>], needle: &str| {
            match NodeProperties::from_arrow_batches(batches, &projection, wanted) {
                Err(AlgorithmError::InvalidArguments(message))
                | Err(AlgorithmError::Unsupported(message)) => {
                    assert!(message.contains(needle), "{message:?} lacks {needle:?}")
                }
                other => panic!("{needle}: {:?}", other.map(|_| ())),
            }
        };
        // Bob's seed is absent, and absence is an error unless asked otherwise.
        fails(
            &batches,
            &[PropertyRequest::required("seed", PropertyKind::Integer)],
            "bob",
        );
        // A column no batch has is absent everywhere.
        fails(
            &batches,
            &[PropertyRequest::required("height", PropertyKind::Number)],
            "ann",
        );
        // A string is not a number, and a list of strings is not a vector.
        fails(
            &batches,
            &[PropertyRequest::required("team", PropertyKind::Number)],
            "not a finite number",
        );
        fails(
            &batches,
            &[PropertyRequest::required("team", PropertyKind::Vector)],
            "not a numeric list",
        );
        assert_eq!(context.usage().unwrap().live_bytes, held);

        // A ragged list, a null inside a list, and batches that are not the
        // projection's.
        let with_vectors = |vectors: ArrayRef| {
            vec![batch(vec![
                (
                    "node_id",
                    Arc::new(StringArray::from(vec!["ann", "bob", "cy"])) as ArrayRef,
                ),
                ("label", Arc::new(StringArray::from(vec!["Person"; 3]))),
                ("property.vec", vectors),
            ])]
        };
        let ragged_batches = with_vectors(ragged(&[&[1.0, 2.0], &[1.0], &[1.0, 2.0]]));
        let ragged_projection = people(&ragged_batches, &context);
        match NodeProperties::from_arrow_batches(
            &ragged_batches,
            &ragged_projection,
            &[PropertyRequest::required("vec", PropertyKind::Vector)],
        ) {
            Err(AlgorithmError::InvalidArguments(message)) => {
                assert!(
                    message.contains("bob") && message.contains("1 components"),
                    "{message}"
                )
            }
            other => panic!("{:?}", other.map(|_| ())),
        }
        let mut holes = ListBuilder::new(Float64Builder::new());
        for row in [
            [Some(1.0), Some(2.0)],
            [Some(1.0), None],
            [Some(3.0), Some(4.0)],
        ] {
            for item in row {
                holes.values().append_option(item);
            }
            holes.append(true);
        }
        let hole_batches = with_vectors(Arc::new(holes.finish()));
        let hole_projection = people(&hole_batches, &context);
        match NodeProperties::from_arrow_batches(
            &hole_batches,
            &hole_projection,
            &[PropertyRequest::required("vec", PropertyKind::Vector)],
        ) {
            Err(AlgorithmError::InvalidArguments(message)) => {
                assert!(
                    message.contains("bob") && message.contains("single precision"),
                    "{message}"
                )
            }
            other => panic!("{:?}", other.map(|_| ())),
        }
        fails(
            &batches[..1],
            &[PropertyRequest::required("age", PropertyKind::Integer)],
            "1 of the projection's 3",
        );
    }
}

/// Reproductions from quegee's review of the first version of this module
/// (`review/node-properties-repros`), turned round to pin the fixed behaviour.
mod reviewed {
    use super::*;

    /// A category column read keeping nulls was reachable and then unreadable:
    /// `validate` allowed the pair, and the only accessor for its kind refused
    /// it and named a method that did not exist.
    #[test]
    fn a_category_keeping_nulls_is_readable() {
        let graph = graph();
        let context = context();
        let projection = people(&graph, &context);
        let properties = NodeProperties::from_graph(
            &graph,
            &projection,
            &[request(
                "team",
                PropertyKind::Category,
                MissingProperty::Null,
            )],
        )
        .unwrap();
        let (teams, present) = properties.optional_categories("team").unwrap();
        assert_eq!(teams.dictionary, ["red", "blue"]);
        assert_eq!(teams.codes, [0, 1, 0]);
        assert_eq!(present, [true, true, true]);
        // The kind-and-nullness rules hold both ways round, as for the others.
        assert!(properties.categories("team").is_err());
        assert!(properties.optional_integers("team").is_err());

        // A node without the property keeps its absence rather than inventing a
        // string, and code zero on that row means nothing.
        let sparse = Graph::new(
            vec![
                node("Person", "a", &[("team", Value::String("red".into()))]),
                node("Person", "b", &[]),
            ],
            vec![],
        );
        let projection = people(&sparse, &context);
        let properties = NodeProperties::from_graph(
            &sparse,
            &projection,
            &[request(
                "team",
                PropertyKind::Category,
                MissingProperty::Null,
            )],
        )
        .unwrap();
        let (teams, present) = properties.optional_categories("team").unwrap();
        assert_eq!(teams.dictionary, ["red"]);
        assert_eq!(present, [true, false]);
    }
}

#[cfg(feature = "arrow")]
mod reviewed_arrow {
    use std::sync::Arc;

    use super::arrow::people as arrow_people;
    use super::*;
    use arrow_array::{ArrayRef, Int64Array, RecordBatch, StringArray};

    fn rows(ids: &[&str], ages: &[i64]) -> RecordBatch {
        RecordBatch::try_from_iter(vec![
            (
                "node_id",
                Arc::new(StringArray::from(ids.to_vec())) as ArrayRef,
            ),
            (
                "label",
                Arc::new(StringArray::from(vec!["Person"; ids.len()])),
            ),
            ("property.age", Arc::new(Int64Array::from(ages.to_vec()))),
        ])
        .unwrap()
    }

    /// Batch order used to be load-bearing: vectors were appended, so a caller
    /// whose only mistake was not sorting got an internal contract error. The
    /// Arrow path is Nutmeg's, where batches come from a DataFrame ordered as
    /// the engine likes, so the order requirement is gone rather than documented.
    #[test]
    fn arrow_batches_may_arrive_in_any_order() {
        let context = context();
        let ordered = [rows(&["ann", "bob", "cy"], &[31, 45, 19])];
        let projection = arrow_people(&ordered, &context);
        let wanted = [PropertyRequest::required("age", PropertyKind::Integer)];
        let expected = [31, 45, 19];

        for batches in [
            vec![rows(&["cy", "bob", "ann"], &[19, 45, 31])],
            // A near-identity permutation: only two rows move.
            vec![rows(&["ann", "cy", "bob"], &[31, 19, 45])],
            // Split across batches, and the second batch first.
            vec![rows(&["bob", "cy"], &[45, 19]), rows(&["ann"], &[31])],
        ] {
            let properties =
                NodeProperties::from_arrow_batches(&batches, &projection, &wanted).unwrap();
            assert_eq!(properties.integers("age").unwrap(), expected);
        }
    }

    /// The same, for vectors, which is where the ordering was load-bearing:
    /// their width is not known until the first value arrives.
    #[test]
    fn vectors_survive_any_order_including_a_defaulted_first_row() {
        use arrow_array::builder::{FixedSizeListBuilder, Float32Builder};
        let context = context();
        let vectors = |present: &[Option<[f32; 2]>]| {
            let mut builder = FixedSizeListBuilder::new(Float32Builder::new(), 2);
            for row in present {
                match row {
                    Some(values) => {
                        builder.values().append_slice(values);
                        builder.append(true);
                    }
                    None => {
                        builder.values().append_nulls(2);
                        builder.append(false);
                    }
                }
            }
            Arc::new(builder.finish()) as ArrayRef
        };
        let batch = |ids: &[&str], vs: ArrayRef| {
            vec![
                RecordBatch::try_from_iter(vec![
                    (
                        "node_id",
                        Arc::new(StringArray::from(ids.to_vec())) as ArrayRef,
                    ),
                    (
                        "label",
                        Arc::new(StringArray::from(vec!["Person"; ids.len()])),
                    ),
                    ("property.v", vs),
                ])
                .unwrap(),
            ]
        };
        let projection = arrow_people(
            &batch(&["ann", "bob", "cy"], vectors(&[Some([0.0; 2]); 3])),
            &context,
        );
        let wanted = [request(
            "v",
            PropertyKind::Vector,
            MissingProperty::Default(9.0),
        )];

        // ann has no vector and arrives last, so the width is known before her
        // row is written; bob's and cy's land at their own offsets either way.
        let shuffled = batch(
            &["cy", "bob", "ann"],
            vectors(&[Some([5.0, 6.0]), Some([3.0, 4.0]), None]),
        );
        let properties =
            NodeProperties::from_arrow_batches(&shuffled, &projection, &wanted).unwrap();
        let read = properties.vectors("v").unwrap();
        assert_eq!(read.dimension, 2);
        assert_eq!(read.row(0), [9.0, 9.0], "ann is defaulted");
        assert_eq!(read.row(1), [3.0, 4.0]);
        assert_eq!(read.row(2), [5.0, 6.0]);
    }
}
