//! Graph-free CALL must not turn a compact indexed source into a full Graph.

use std::{
    borrow::Cow,
    sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
    },
};

use grust_core::{
    Edge, Graph, GraphSnapshotSource, Label, Node, NodeId, Props, Result, TypedGraphIndex, Value,
};
use grust_cypher::{
    CypherParameters,
    read::{run_read_query, run_read_query_indexed},
};

#[derive(Debug)]
struct WatchedSource {
    inner: TypedGraphIndex,
    materializations: AtomicUsize,
}

impl GraphSnapshotSource for WatchedSource {
    fn node_count(&self) -> usize {
        self.inner.source().node_count()
    }
    fn edge_count(&self) -> usize {
        self.inner.source().edge_count()
    }
    fn node(&self, slot: u32) -> Cow<'_, Node> {
        self.inner.source().node(slot)
    }
    fn node_id(&self, slot: u32) -> &NodeId {
        self.inner.source().node_id(slot)
    }
    fn node_label(&self, slot: u32) -> &Label {
        self.inner.source().node_label(slot)
    }
    fn node_property(&self, slot: u32, key: &str) -> Option<Cow<'_, Value>> {
        self.inner.source().node_property(slot, key)
    }
    fn edge(&self, slot: u32) -> Cow<'_, Edge> {
        self.inner.source().edge(slot)
    }
    fn edge_label(&self, slot: u32) -> &Label {
        self.inner.source().edge_label(slot)
    }
    fn edge_props(&self, slot: u32) -> &Props {
        self.inner.source().edge_props(slot)
    }
    fn edge_endpoints(&self, slot: u32) -> Result<(u32, u32)> {
        self.inner.source().edge_endpoints(slot)
    }
    fn vertex_index(&self, id: &str) -> Option<u32> {
        self.inner.source().vertex_index(id)
    }
    fn materialize(&self) -> Graph {
        // This counter observes calls; it does not publish or synchronize data.
        self.materializations.fetch_add(1, Ordering::Relaxed);
        self.inner.graph().clone()
    }
}

#[test]
fn provider_metadata_controls_materialization_in_both_pipelines() {
    let graph = Arc::new(Graph::new(vec![Node::new("N", "n", Props::new())], vec![]));
    let source = Arc::new(WatchedSource {
        inner: TypedGraphIndex::new(graph.clone()).unwrap(),
        materializations: AtomicUsize::new(0),
    });
    let index = TypedGraphIndex::from_source(source.clone()).unwrap();
    let params = CypherParameters::new();
    for query in [
        "CALL tvf.range(1, 3) YIELD value RETURN value",
        "CALL tvf.range(1, 3) YIELD value RETURN DISTINCT value ORDER BY value",
        "CALL db.procedures() YIELD name RETURN name LIMIT 1",
    ] {
        assert_eq!(
            run_read_query_indexed(&index, query, &params).unwrap(),
            run_read_query(&graph, query, &params).unwrap(),
            "{query}"
        );
        assert_eq!(
            source.materializations.load(Ordering::Relaxed),
            0,
            "{query}"
        );
    }
    for query in [
        "CALL db.labels() YIELD label RETURN label",
        "CALL db.labels() YIELD label RETURN DISTINCT label ORDER BY label",
    ] {
        assert_eq!(
            run_read_query_indexed(&index, query, &params).unwrap(),
            run_read_query(&graph, query, &params).unwrap(),
            "{query}"
        );
        assert_eq!(
            source.materializations.load(Ordering::Relaxed),
            1,
            "snapshot materialization is cached"
        );
    }
}
