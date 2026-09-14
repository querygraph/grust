use super::*;
use grust_core::GraphIndex;

#[test]
fn conversion_topology_errors_match_index_validation() {
    let node = Node::new("N", "a", Props::new());
    for graph in [
        Graph::new(vec![node.clone(), node.clone()], vec![]),
        Graph::new(
            vec![node.clone()],
            vec![Edge::new("E", "a", "missing", Props::new())],
        ),
        Graph::new(
            vec![node],
            vec![Edge::new("E", "missing", "a", Props::new())],
        ),
    ] {
        assert_eq!(
            ArrowGraph::from_graph(&graph).unwrap_err().to_string(),
            GraphIndex::new(&graph).unwrap_err().to_string()
        );
    }
}

#[test]
fn conversion_retains_strings_presence_and_parallel_edges() {
    let graph = Graph::new(
        vec![
            Node::new(
                "N",
                "a",
                Props::from([("text".into(), Value::String("λ".repeat(1024)))]),
            ),
            Node::new("N", "b", Props::from([("text".into(), Value::Null)])),
            Node::new("N", "c", Props::new()),
            Node::new(
                "N",
                "d",
                Props::from([("text".into(), Value::String(String::new()))]),
            ),
        ],
        vec![
            Edge::new("E", "a", "a", Props::new()),
            Edge::new("E", "a", "a", Props::new()),
        ],
    );
    let converted = ArrowGraph::from_graph(&graph).unwrap();
    assert_eq!(converted.to_graph().unwrap(), graph);
    let presence = converted
        .nodes()
        .column_by_name("present.text")
        .unwrap()
        .as_any()
        .downcast_ref::<BooleanArray>()
        .unwrap();
    assert_eq!(
        presence.iter().collect::<Vec<_>>(),
        vec![Some(true), Some(true), Some(false), Some(true)]
    );
}
