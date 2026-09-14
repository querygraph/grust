use super::super::ArrowGraph;
use super::*;
use crate::ByteLimitWriter;
use grust_core::{Edge, Graph, Node, Props, Value};
use std::{io, num::NonZeroUsize};

fn fixture() -> Graph {
    let mut first = Props::new();
    first.insert("bool".into(), Value::Bool(true));
    first.insert("int".into(), Value::Int(i64::MIN));
    first.insert("float".into(), Value::Float(-0.0));
    first.insert("text".into(), Value::String("雪\n\t\u{0}\"\\".into()));
    first.insert("null".into(), Value::Null);
    first.insert("k\"\\\n".into(), Value::String("quoted key".into()));
    let mut second = Props::new();
    second.insert("bool".into(), Value::Bool(false));
    second.insert("int".into(), Value::Int(i64::MAX));
    second.insert("float".into(), Value::Float(1e300));
    second.insert("text".into(), Value::String(String::new()));
    let mut edge = Edge::new("E\"", "a", "a", first.clone());
    edge.id = Some("duplicate".into());
    Graph::new(
        vec![
            Node::new("N", "a", first),
            Node::new("N", "isolate", second),
            Node::new(
                "N",
                "z",
                ["bool", "int", "float", "text"]
                    .into_iter()
                    .map(|key| (key.to_owned(), Value::Null))
                    .collect::<Props>(),
            ),
        ],
        vec![edge.clone(), edge, Edge::new("E", "a", "z", Props::new())],
    )
}

fn table(batch: &RecordBatch) -> ArrowTable {
    let projection = (0..batch.num_columns()).rev().collect::<Vec<_>>();
    let reordered = batch.project(&projection).unwrap();
    ArrowTable::try_new(
        reordered.schema(),
        vec![
            reordered.slice(0, 0),
            reordered.slice(0, 1),
            reordered.slice(1, batch.num_rows() - 1),
        ],
    )
    .unwrap()
}

#[test]
fn borrowed_serialization_matches_core_bytes_across_reordered_sliced_batches() {
    let graph = fixture();
    let native = ArrowGraph::from_graph(&graph).unwrap();
    let tables = ArrowGraphTables::try_new(table(native.nodes()), table(native.edges())).unwrap();
    let expected = serde_json::to_vec(&graph).unwrap();
    let actual = serde_json::to_vec(&tables.as_serializable_graph()).unwrap();
    assert_eq!(actual, expected);
    assert_eq!(serde_json::from_slice::<Graph>(&actual).unwrap(), graph);
    let mut count = ByteLimitWriter::new(io::sink(), NonZeroUsize::new(expected.len()).unwrap());
    serde_json::to_writer(&mut count, &tables.as_serializable_graph()).unwrap();
    assert_eq!(count.bytes_written(), expected.len());
    let mut short =
        ByteLimitWriter::new(io::sink(), NonZeroUsize::new(expected.len() - 1).unwrap());
    assert!(
        serde_json::to_writer(&mut short, &tables.as_serializable_graph())
            .unwrap_err()
            .is_io()
    );
    assert!(short.bytes_written() < expected.len());
}

#[test]
fn empty_schema_only_graph_preserves_the_core_wire_contract() {
    let graph = Graph::new(vec![], vec![]);
    let native = ArrowGraph::from_graph(&graph).unwrap();
    let tables = ArrowGraphTables::try_new(
        ArrowTable::try_new(native.nodes().schema(), vec![]).unwrap(),
        ArrowTable::try_new(native.edges().schema(), vec![]).unwrap(),
    )
    .unwrap();
    assert_eq!(
        serde_json::to_vec(&tables.as_serializable_graph()).unwrap(),
        serde_json::to_vec(&graph).unwrap()
    );
}

#[test]
fn nonfinite_native_floats_follow_core_json_encoding() {
    for value in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
        let graph = Graph::new(
            vec![Node::new(
                "N",
                "a",
                Props::from([("f".into(), Value::Float(value))]),
            )],
            vec![],
        );
        let (nodes, edges) = ArrowGraph::from_graph(&graph).unwrap().into_tables();
        let tables = ArrowGraphTables::try_new(nodes, edges).unwrap();
        assert_eq!(
            serde_json::to_vec(&tables.as_serializable_graph()).unwrap(),
            serde_json::to_vec(&graph).unwrap()
        );
    }
}
