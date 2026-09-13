//! Resident-memory growth of `MemoryGraphStore` per stored edge.
//!
//! Loads an untyped synthetic graph (one node label, one edge label, no
//! properties beyond the node `id` that `Node::new` adds) through `put_graph`
//! in batches, the way the strain benchmark loads real graphs, and reports RSS
//! growth from `/proc/self/statm`.
//!
//! ```text
//! cargo run --release -p grust-memory --example footprint -- 10000000
//! ```
//!
//! Arguments: edge count (default 1,000,000), batch size (default 50,000).
//! Nodes are `edges / 20`; every edge is distinct, so the store holds exactly
//! `edges` edges.

use grust_core::prelude::*;
use grust_memory::MemoryGraphStore;

fn rss_bytes() -> u64 {
    let statm = std::fs::read_to_string("/proc/self/statm").expect("read /proc/self/statm");
    let resident: u64 = statm
        .split_whitespace()
        .nth(1)
        .and_then(|pages| pages.parse().ok())
        .expect("statm resident pages");
    resident * 4096
}

fn main() {
    let mut args = std::env::args().skip(1);
    let edges: usize = args
        .next()
        .map_or(1_000_000, |s| s.parse().expect("edge count"));
    let batch: usize = args
        .next()
        .map_or(50_000, |s| s.parse().expect("batch size"));
    let nodes = (edges / 20).max(2);
    // Out-neighbours of vertex f are f + 1 + k * stride (mod nodes) for the
    // k-th edge leaving f, distinct while k * stride stays below `nodes`.
    let per_node = edges.div_ceil(nodes);
    let stride = ((nodes - 1) / per_node).max(1);

    let store = MemoryGraphStore::new();
    let before = rss_bytes();
    let started = std::time::Instant::now();

    let mut next = 0;
    while next < nodes {
        let end = (next + batch).min(nodes);
        let graph = Graph::new(
            (next..end)
                .map(|i| Node::new("Node", format!("n{i}"), Props::new()))
                .collect(),
            Vec::new(),
        );
        futures_executor::block_on(store.put_graph(&graph)).expect("load nodes");
        next = end;
    }
    let after_nodes = rss_bytes();

    let mut next = 0;
    while next < edges {
        let end = (next + batch).min(edges);
        let graph = Graph::new(
            Vec::new(),
            (next..end)
                .map(|i| {
                    let from = i % nodes;
                    let k = i / nodes;
                    let to = (from + 1 + k * stride) % nodes;
                    Edge::new("LINKS", format!("n{from}"), format!("n{to}"), Props::new())
                })
                .collect(),
        );
        futures_executor::block_on(store.put_graph(&graph)).expect("load edges");
        next = end;
    }
    let after = rss_bytes();
    let elapsed = started.elapsed();

    let check = futures_executor::block_on(store.get_edges(EdgeQuery {
        from: Some(NodeId::new("n0")),
        ..EdgeQuery::default()
    }))
    .expect("read back");
    let mb = |b: u64| b as f64 / (1024.0 * 1024.0);
    println!(
        "edges={edges} nodes={nodes} batch={batch} load_secs={:.1}",
        elapsed.as_secs_f64()
    );
    println!(
        "rss_before_mib={:.1} node_growth_mib={:.1} edge_growth_mib={:.1} total_growth_mib={:.1}",
        mb(before),
        mb(after_nodes.saturating_sub(before)),
        mb(after.saturating_sub(after_nodes)),
        mb(after.saturating_sub(before)),
    );
    println!(
        "bytes_per_edge_total={:.1} bytes_per_edge_edges_only={:.1} bytes_per_node={:.1} n0_out_degree={}",
        after.saturating_sub(before) as f64 / edges as f64,
        after.saturating_sub(after_nodes) as f64 / edges as f64,
        after_nodes.saturating_sub(before) as f64 / nodes as f64,
        check.len()
    );
}
