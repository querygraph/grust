use grust_arrow::ArrowGraph;
use grust_core::{Edge, Graph, Node, Props, Value};
use std::io::Cursor;
fn sample() -> Graph {
    let p = Props::from([
        ("null".into(), Value::Null),
        ("integer".into(), Value::Int(i64::MAX)),
        ("float".into(), Value::Float(2.5)),
        ("bool".into(), Value::Bool(true)),
        ("string".into(), Value::String("héllo\0".into())),
    ]);
    Graph::new(
        vec![
            Node::new("N", "a", p),
            Node::new("N", "isolated", Props::new()),
        ],
        vec![Edge::new("LOOP", "a", "a", Props::new()).with_id("edge")],
    )
}
#[test]
fn native_columns_and_ipc_preserve_values() {
    let g = sample();
    let a = ArrowGraph::from_graph(&g).unwrap();
    assert_eq!(a.to_graph().unwrap(), g);
    assert_eq!(
        a.nodes()
            .column_by_name("property.integer")
            .unwrap()
            .data_type(),
        &arrow_schema::DataType::Int64
    );
    let (mut n, mut e) = (Vec::new(), Vec::new());
    a.write_ipc(&mut n, &mut e).unwrap();
    assert_eq!(
        ArrowGraph::read_ipc(Cursor::new(n), Cursor::new(e))
            .unwrap()
            .to_graph()
            .unwrap(),
        g
    );
}
#[test]
fn empty_and_parallel_edges() {
    for g in [Graph::default(), {
        let mut g = sample();
        g.edges.push(g.edges[0].clone());
        g
    }] {
        assert_eq!(ArrowGraph::from_graph(&g).unwrap().to_graph().unwrap(), g);
    }
}
#[test]
fn rejects_invalid_graphs_and_unsupported_properties() {
    let mut g = sample();
    g.edges[0].to = "missing".into();
    assert!(ArrowGraph::from_graph(&g).is_err());
    let mut g = sample();
    g.nodes.push(g.nodes[0].clone());
    assert!(ArrowGraph::from_graph(&g).is_err());
    let mut g = sample();
    g.nodes[0]
        .props
        .insert("nested".into(), Value::IntArray(vec![1]));
    assert!(ArrowGraph::from_graph(&g).is_err());
    let mut g = sample();
    g.nodes[1].props.insert("integer".into(), Value::Float(1.));
    assert!(ArrowGraph::from_graph(&g).is_err());
}
#[test]
fn rejects_invalid_schema_and_presence() {
    use arrow_array::{ArrayRef, BooleanArray, RecordBatch};
    use std::sync::Arc;
    let a = ArrowGraph::from_graph(&sample()).unwrap();
    let n = a.nodes();
    let idx = n.schema().index_of("present.integer").unwrap();
    let mut columns = n.columns().to_vec();
    columns[idx] = Arc::new(BooleanArray::from(vec![false, false])) as ArrayRef;
    assert!(
        ArrowGraph::try_new(
            RecordBatch::try_new(n.schema(), columns).unwrap(),
            a.edges().clone()
        )
        .is_err()
    );
    assert!(ArrowGraph::try_new(a.edges().clone(), a.nodes().clone()).is_err());
    assert!(ArrowGraph::read_ipc(Cursor::new(b"bad"), Cursor::new(b"bad")).is_err());
}
