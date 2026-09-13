//! Cypher over a Memory store's lean snapshot answers exactly as Cypher over
//! the store's materialized graph: same rows, same order, same errors.
//!
//! `MemoryGraphStore::indexed_snapshot` no longer copies the graph; its index
//! reads the store's frozen storage and builds elements on demand, and the
//! reference pipeline walks the index's adjacency instead of scanning an edge
//! vector. These shapes exercise the orders that substitution must preserve:
//! undirected steps with and without adjacency, self-loops, parallel edges,
//! variable-length and shortest paths, OPTIONAL MATCH, whole-element values,
//! and a node whose `id` property differs from its id.

use std::sync::Arc;

use futures_executor::block_on;
use grust_core::TypedGraphIndex;
use grust_core::prelude::*;
use grust_cypher::read::{run_read_query, run_read_query_indexed};
use grust_cypher::{CypherParameters, ReadQueryPolicy, run_bounded_read_query_indexed};
use grust_memory::MemoryGraphStore;

fn props(entries: &[(&str, Value)]) -> Props {
    entries
        .iter()
        .map(|(key, value)| (key.to_string(), value.clone()))
        .collect()
}

fn fixture() -> Graph {
    let nodes = vec![
        Node::new("A", "a", Props::new()),
        Node::new("B", "b", props(&[("score", Value::Int(2))])),
        Node::new("B", "c", props(&[("score", Value::Int(1))])),
        Node::new("A", "d", props(&[("id", Value::from("other"))])),
        Node::new("C", "e", props(&[("name", Value::from("east"))])),
    ];
    let edges = vec![
        Edge::new("R", "a", "b", props(&[("w", Value::Int(1))])),
        Edge::new("R", "a", "b", props(&[("w", Value::Int(5))])).with_id("r2"),
        Edge::new("S", "b", "c", Props::new()),
        Edge::new("R", "c", "a", Props::new()),
        Edge::new("S", "a", "a", Props::new()),
        Edge::new("R", "b", "b", Props::new()).with_id("loop"),
        Edge::new("S", "c", "e", Props::new()),
        Edge::new("R", "d", "a", Props::new()),
        Edge::new("T", "e", "d", Props::new()),
    ];
    Graph::new(nodes, edges)
}

const QUERIES: &[&str] = &[
    "MATCH (n) RETURN n.id",
    "MATCH (n) RETURN n",
    "MATCH (a {id: 'a'})-[r]->(b) RETURN type(r), r.w, b.id",
    "MATCH (a {id: 'a'})-[r]-(b) RETURN type(r), b.id",
    "MATCH (a {id: 'b'})-[r]-(b) RETURN r, b",
    "MATCH (a)-[r]-(b) RETURN a.id, type(r), b.id",
    "MATCH (a {id: 'b'})<-[r:R]-(b) RETURN b.id, r.w",
    "MATCH (a {id: 'a'})-[*1..3]->(b) RETURN b.id",
    "MATCH (a:A {id: 'a'})-[*1..2]-(b) RETURN b.id",
    "MATCH (a {id: 'a'})-[rs*1..3]-(b) RETURN rs, b.id",
    "MATCH p = (a {id: 'a'})-[:R]->(b)-[:S]->(c) RETURN p",
    "MATCH (a:A)-[:R]->(b:B) RETURN count(*) AS n",
    "MATCH (a)-[:R]->(b)-[:S]->(c) RETURN count(*) AS n",
    "MATCH (n:B) WHERE n.score > 1 RETURN n.id, n.score",
    "MATCH (n {id: 'other'}) RETURN n.id, labels(n)",
    "MATCH (n {id: 'd'}) RETURN n",
    "MATCH (n:A {id: 'a'}) RETURN n",
    "MATCH p = shortestPath((a {id: 'a'})-[*]-(e {id: 'e'})) RETURN length(p), p",
    "MATCH p = allShortestPaths((a {id: 'a'})-[*]->(c {id: 'c'})) RETURN p",
    "MATCH (a {id: 'a'}) OPTIONAL MATCH (a)-[:S]->(x) RETURN a.id, x.id",
    "MATCH (a {id: 'e'}) OPTIONAL MATCH (a)-[:R]->(x) RETURN a.id, x.id",
    "MATCH ()-[r]->() RETURN r",
    "MATCH (a)-[r:R {w: 5}]->(b) RETURN a.id, b.id, r",
    "MATCH (a {id: 'missing'})-[r]-(b) RETURN b.id",
    "MATCH (a {id: 'a'})-->(b)-->(c) RETURN a.id, b.id, c.id",
    "MATCH (a)-[r]->(a) RETURN a.id, type(r)",
    "MATCH (a {id: 'a'})-[r]->(b) WITH b, count(r) AS n RETURN b.id, n ORDER BY b.id",
    "MATCH (a:A) CALL { WITH a MATCH (a)-[:R]->(b) RETURN count(b) AS out } RETURN a.id, out",
    "MATCH (a) RETURN a.nope",
    "MATCH (a {id: 1}) RETURN a",
];

fn loaded() -> MemoryGraphStore {
    let store = MemoryGraphStore::new();
    block_on(store.put_graph(&fixture())).unwrap();
    store
}

#[test]
fn lean_snapshot_reads_match_the_materialized_graph_row_for_row() {
    let store = loaded();
    let lean = store.indexed_snapshot().unwrap();
    let graph = store.graph();
    let owned = TypedGraphIndex::new(Arc::new(graph.clone())).unwrap();
    let params = CypherParameters::new();
    for query in QUERIES {
        let reference = format!("{:?}", run_read_query(&graph, query, &params));
        let over_owned = format!("{:?}", run_read_query_indexed(&owned, query, &params));
        let over_lean = format!("{:?}", run_read_query_indexed(&lean, query, &params));
        assert_eq!(over_lean, reference, "{query}");
        assert_eq!(over_owned, reference, "{query}");
    }
}

/// Bounded reads through the lean snapshot refuse exactly where the same
/// reads through an index over the materialized graph (what
/// `indexed_snapshot` built before) refuse, with the same message: the count
/// fast paths charge identically, and the reference pipeline's in-place walk
/// charges what the owned scan charges, in the same order.
#[test]
fn lean_snapshot_bounded_reads_match_including_refusals() {
    let store = loaded();
    let lean = store.indexed_snapshot().unwrap();
    let graph = store.graph();
    let owned = TypedGraphIndex::new(Arc::new(graph.clone())).unwrap();
    let params = CypherParameters::new();
    for policy in [
        ReadQueryPolicy::default(),
        ReadQueryPolicy {
            max_candidate_work: 40,
            ..ReadQueryPolicy::default()
        },
        ReadQueryPolicy {
            max_intermediate_bytes: 2_000,
            ..ReadQueryPolicy::default()
        },
    ] {
        for query in QUERIES {
            let bounded = format!("{query} LIMIT 50");
            let bounded = if query.contains("RETURN") && !query.contains("CALL") {
                bounded
            } else {
                query.to_string()
            };
            assert_eq!(
                format!(
                    "{:?}",
                    run_bounded_read_query_indexed(&lean, &bounded, &params, &policy)
                ),
                format!(
                    "{:?}",
                    run_bounded_read_query_indexed(&owned, &bounded, &params, &policy)
                ),
                "{bounded} under {policy:?}"
            );
        }
    }
    assert_eq!(
        lean.serialized_graph_bytes(),
        serde_json::to_vec(&graph).unwrap().len()
    );
}

#[test]
fn lean_snapshot_is_not_a_copy_and_survives_later_writes() {
    let store = loaded();
    let lean = store.indexed_snapshot().unwrap();
    assert!(lean.source().as_graph().is_none());
    let before = store.graph();
    block_on(store.put_edge(&Edge::new("R", "e", "a", Props::new()))).unwrap();
    block_on(store.delete_node(&NodeId::new("c"))).unwrap();
    let params = CypherParameters::new();
    for query in QUERIES {
        assert_eq!(
            format!("{:?}", run_read_query_indexed(&lean, query, &params)),
            format!("{:?}", run_read_query(&before, query, &params)),
            "{query}"
        );
    }
    assert_eq!(lean.graph(), &before);
    let after = store.indexed_snapshot().unwrap();
    assert_eq!(after.graph(), &store.graph());
}
