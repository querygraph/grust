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
