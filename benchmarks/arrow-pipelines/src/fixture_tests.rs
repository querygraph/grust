use super::*;

#[test]
fn self_loops_cannot_reuse_the_same_edge_in_a_trail() {
    assert_eq!(expected(Workload::Scan, 4, 1), (1, 3));
    assert_eq!(expected(Workload::OneHop, 4, 1), (1, 1));
    assert_eq!(expected(Workload::TwoHop, 4, 1), (0, 0));
}
#[test]
fn distinct_parallel_loops_are_separate_edges() {
    assert_eq!(expected(Workload::TwoHop, 4, 5), (23, 69));
    let graph = graph(4, 5);
    assert_eq!(graph.edges.len(), 20);
    let identities = graph
        .edges
        .iter()
        .map(|e| e.id.as_ref().unwrap())
        .collect::<std::collections::BTreeSet<_>>();
    assert_eq!(identities.len(), 20);
}
#[test]
fn isolates_are_included_in_the_node_aggregate() {
    assert_eq!(expected(Workload::Scan, 20, 1), (2, 22));
    assert_eq!(expected(Workload::OneHop, 20, 1), (1, 1));
    assert_eq!(graph(20, 1).edges.len(), 18);
}
