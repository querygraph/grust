//! Reproduce the adversarial-graph strain benchmark's A4 (hot-node write
//! contention) on a LanceDB store and sample the process's resident set.
//!
//! After a bulk load and a few anchored reads (A1/A2 build the resident
//! snapshot), A4 reads the hub's out-degree, then 16 writers sharing one
//! store each attach 200 new nodes and hub edges (`put_node` then
//! `put_edge`), concurrently; finally the hub's out-degree is read again and
//! checked against the accepted writes.
//!
//! ```text
//! GRUST_LANCE_EDGES=web-Google.txt cargo run --release -p grust-lancedb --example hot_node_writes
//! ```
//!
//! `GRUST_LANCE_WRITERS` (16) and `GRUST_LANCE_PER_WRITER` (200) size A4;
//! without `GRUST_LANCE_EDGES` a web-Google-sized synthetic graph is used.

use std::collections::{HashMap, HashSet};
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::{Duration, Instant};

use grust_core::prelude::*;
use grust_lancedb::{LanceDbConfig, LanceDbGraphStore};

fn env_usize(key: &str, default: usize) -> usize {
    std::env::var(key)
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(default)
}

/// `(VmRSS, VmHWM)` in MiB.
fn rss_mib() -> (u64, u64) {
    let status = std::fs::read_to_string("/proc/self/status").unwrap_or_default();
    let field = |name: &str| {
        status
            .lines()
            .find(|line| line.starts_with(name))
            .and_then(|line| line.split_whitespace().nth(1))
            .and_then(|kb| kb.parse::<u64>().ok())
            .unwrap_or(0)
            / 1024
    };
    (field("VmRSS:"), field("VmHWM:"))
}

fn report(stage: &str, start: Instant) {
    let (rss, hwm) = rss_mib();
    println!(
        "[{:>8.1} s] {stage}: rss {rss} MiB, peak {hwm} MiB",
        start.elapsed().as_secs_f64()
    );
}

/// A SNAP edge list: `from<TAB>to` lines, `#` comments.
fn snap_graph(path: &str) -> Graph {
    let text = std::fs::read_to_string(path).expect("read SNAP edge list");
    let mut nodes = Vec::new();
    let mut seen = HashSet::new();
    let mut edges = Vec::new();
    for line in text.lines() {
        if line.starts_with('#') || line.trim().is_empty() {
            continue;
        }
        let mut parts = line.split_whitespace();
        let (Some(from), Some(to)) = (parts.next(), parts.next()) else {
            continue;
        };
        for id in [from, to] {
            if seen.insert(id.to_string()) {
                nodes.push(Node::new("V", id, Props::new()));
            }
        }
        edges.push(Edge::new("E", from, to, Props::new()));
    }
    Graph { nodes, edges }
}

/// Deterministic, skewed out-degrees, no duplicate edges.
fn synthetic_graph(nodes: usize, edges: usize) -> Graph {
    let mut state = 0x2545_f491_4f6c_dd1du64;
    let mut next = move || {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        state
    };
    let skewed = |r: u64, n: usize| {
        let u = (r >> 11) as f64 / (1u64 << 53) as f64;
        ((u * u * u) * n as f64) as usize % n
    };
    let mut keys = HashSet::with_capacity(edges);
    let mut list = Vec::with_capacity(edges);
    while list.len() < edges {
        let from = skewed(next(), nodes);
        let to = (next() % nodes as u64) as usize;
        if keys.insert((from as u32, to as u32)) {
            list.push(Edge::new(
                "E",
                from.to_string(),
                to.to_string(),
                Props::new(),
            ));
        }
    }
    Graph {
        nodes: (0..nodes)
            .map(|i| Node::new("V", i.to_string(), Props::new()))
            .collect(),
        edges: list,
    }
}

async fn out_degree(store: &LanceDbGraphStore, v: &NodeId) -> usize {
    store
        .get_edges(EdgeQuery {
            from: Some(v.clone()),
            to: None,
            label: Some(Label::new("E")),
        })
        .await
        .expect("get_edges")
        .len()
}

#[tokio::main(flavor = "multi_thread")]
async fn main() {
    let start = Instant::now();
    let graph = match std::env::var("GRUST_LANCE_EDGES") {
        Ok(path) => snap_graph(&path),
        Err(_) => synthetic_graph(
            env_usize("GRUST_LANCE_NODES", 875_713),
            env_usize("GRUST_LANCE_EDGE_COUNT", 5_105_039),
        ),
    };
    let writers = env_usize("GRUST_LANCE_WRITERS", 16);
    let per_writer = env_usize("GRUST_LANCE_PER_WRITER", 200);
    println!(
        "graph: {} nodes, {} edges; A4: {writers} writers x {per_writer}",
        graph.nodes.len(),
        graph.edges.len()
    );

    let dir = tempfile::tempdir_in(std::env::var("GRUST_LANCE_DIR").unwrap_or_else(|_| ".".into()))
        .expect("tempdir");
    // The strain harness's configuration.
    let store = LanceDbGraphStore::connect(LanceDbConfig {
        uri: dir.path().display().to_string(),
        table_prefix: "ag".to_string(),
        batch_size: 500,
        bulk_batch_size: 50_000,
    })
    .await
    .unwrap();
    store.bootstrap().await.unwrap();
    store.clear().await.unwrap();
    let t = Instant::now();
    store.put_graph(&graph).await.unwrap();
    println!("load: {:.1} s", t.elapsed().as_secs_f64());
    report("after load", start);

    // The hub the harness picks: max out-degree, lowest id on ties.
    let mut degree = HashMap::<&str, usize>::new();
    for e in &graph.edges {
        *degree.entry(e.from.as_str()).or_default() += 1;
    }
    let (hub, hub_degree) = degree
        .iter()
        .max_by_key(|(id, d)| (**d, std::cmp::Reverse(**id)))
        .map(|(id, d)| (NodeId::new(*id), *d))
        .unwrap();
    drop(degree);
    drop(graph);
    report("graph dropped", start);

    // A1/A2: repeated anchored reads build the resident snapshot.
    for _ in 0..3 {
        store
            .traverse_ids(Traversal::from_node(hub.clone()).out("E"))
            .await
            .unwrap();
    }
    report("reads (snapshot resident)", start);

    // A4.
    let initial = out_degree(&store, &hub).await;
    assert_eq!(initial, hub_degree);
    let sampler_done = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let done_ops = Arc::new(AtomicUsize::new(0));
    let sampler = {
        let done = sampler_done.clone();
        let ops = done_ops.clone();
        tokio::spawn(async move {
            let mut last = 0;
            while !done.load(Ordering::Relaxed) {
                tokio::time::sleep(Duration::from_millis(250)).await;
                let n = ops.load(Ordering::Relaxed);
                if n / 400 != last / 400 {
                    last = n;
                    report(&format!("A4 {n} writes"), start);
                }
            }
        })
    };
    let a4 = Instant::now();
    let barrier = Arc::new(tokio::sync::Barrier::new(writers));
    let mut handles = Vec::new();
    for w in 0..writers {
        let store = store.clone();
        let hub = hub.clone();
        let barrier = barrier.clone();
        let ops = done_ops.clone();
        handles.push(tokio::spawn(async move {
            barrier.wait().await;
            let mut accepted = 0;
            for i in 0..per_writer {
                let target = format!("hot-{w}-{i}");
                let node = Node::new("V", target.clone(), Props::new());
                let edge = Edge::new("E", hub.as_str(), target, Props::new());
                match store.put_node(&node).await {
                    Ok(_) => {
                        store.put_edge(&edge).await.expect("put_edge");
                        accepted += 1;
                    }
                    Err(err) => panic!("put_node: {err}"),
                }
                ops.fetch_add(1, Ordering::Relaxed);
            }
            accepted
        }));
    }
    let mut accepted = 0;
    for handle in handles {
        accepted += handle.await.unwrap();
    }
    let a4_time = a4.elapsed();
    sampler_done.store(true, Ordering::Relaxed);
    sampler.await.unwrap();
    report("A4 writes done", start);
    let t = Instant::now();
    let final_degree = out_degree(&store, &hub).await;
    println!(
        "A4: {accepted} accepted in {:.1} s; final out-degree {final_degree} (read {:.1} s)",
        a4_time.as_secs_f64(),
        t.elapsed().as_secs_f64()
    );
    assert_eq!(final_degree, initial + accepted, "lost or duplicate writes");
    report("A4 final read", start);
    // A12-like: re-read after the writes settle (second read builds a snapshot).
    for _ in 0..2 {
        assert_eq!(out_degree(&store, &hub).await, initial + accepted);
    }
    report("after re-reads", start);
}
