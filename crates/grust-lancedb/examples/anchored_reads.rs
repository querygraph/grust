//! Time the adversarial-graph strain benchmark's anchored-read pattern on a
//! LanceDB store: A2's hop-by-hop BFS (one `traverse_ids` per reached vertex),
//! A1's two-hop fan-out from the hub, and A12's one-hop `get_edges` degree
//! reads, with and without the resident read snapshot.
//!
//! ```text
//! # web-Google-sized synthetic graph (875,713 nodes, 5,105,039 edges)
//! cargo run --release -p grust-lancedb --example anchored_reads
//! # a SNAP edge list, uncompressed
//! GRUST_LANCE_EDGES=web-Google.txt cargo run --release -p grust-lancedb --example anchored_reads
//! ```
//!
//! `GRUST_LANCE_DIRECT_CALLS` (default 200) bounds how many BFS calls the
//! direct-scan path is timed over; its full-BFS time is extrapolated from
//! them, since it would take hours. Every direct answer timed is also
//! compared with the snapshot's.

use std::collections::HashSet;
use std::time::{Duration, Instant};

use grust_core::prelude::*;
use grust_lancedb::{LanceDbConfig, LanceDbGraphStore};

fn env_usize(key: &str, default: usize) -> usize {
    std::env::var(key)
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(default)
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

/// Deterministic, skewed out-degrees and targets, no duplicate edges.
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
        let to = if next() % 4 == 0 {
            skewed(next(), nodes)
        } else {
            (next() % nodes as u64) as usize
        };
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

async fn neighbors(store: &LanceDbGraphStore, v: &NodeId) -> Vec<NodeId> {
    store
        .traverse_ids(Traversal::from_node(v.clone()).out("E"))
        .await
        .expect("traverse_ids")
}

/// A2: BFS layer sizes from `start` to `depth`, stopping after `max_calls`.
async fn bfs(
    store: &LanceDbGraphStore,
    start: &NodeId,
    depth: usize,
    max_calls: usize,
) -> (Vec<usize>, usize, Vec<(NodeId, Vec<NodeId>)>) {
    let mut visited = HashSet::from([start.clone()]);
    let mut frontier = vec![start.clone()];
    let mut layers = Vec::new();
    let mut calls = 0;
    let mut answers = Vec::new();
    'layers: for _ in 0..depth {
        let mut next = Vec::new();
        for v in &frontier {
            if calls == max_calls {
                break 'layers;
            }
            calls += 1;
            let ids = neighbors(store, v).await;
            if answers.len() < 200 {
                answers.push((v.clone(), ids.clone()));
            }
            for id in ids {
                if visited.insert(id.clone()) {
                    next.push(id);
                }
            }
        }
        layers.push(next.len());
        if next.is_empty() {
            break;
        }
        frontier = next;
    }
    (layers, calls, answers)
}

fn secs(d: Duration) -> String {
    format!("{:.3} s", d.as_secs_f64())
}

#[tokio::main(flavor = "multi_thread")]
async fn main() {
    let graph = match std::env::var("GRUST_LANCE_EDGES") {
        Ok(path) => snap_graph(&path),
        Err(_) => synthetic_graph(
            env_usize("GRUST_LANCE_NODES", 875_713),
            env_usize("GRUST_LANCE_EDGE_COUNT", 5_105_039),
        ),
    };
    let direct_calls = env_usize("GRUST_LANCE_DIRECT_CALLS", 200);
    println!(
        "graph: {} nodes, {} edges",
        graph.nodes.len(),
        graph.edges.len()
    );

    let dir = tempfile::tempdir_in(std::env::var("GRUST_LANCE_DIR").unwrap_or_else(|_| ".".into()))
        .expect("tempdir");
    // The strain harness's configuration.
    let config = LanceDbConfig {
        uri: dir.path().display().to_string(),
        table_prefix: "ag".to_string(),
        batch_size: 500,
        bulk_batch_size: 50_000,
    };
    let store = LanceDbGraphStore::connect(config.clone()).await.unwrap();
    store.bootstrap().await.unwrap();
    store.clear().await.unwrap();
    let t = Instant::now();
    store.put_graph(&graph).await.unwrap();
    println!("load: {}", secs(t.elapsed()));
    let direct = LanceDbGraphStore::connect(config)
        .await
        .unwrap()
        .with_read_snapshot(false);

    // The start and hub the harness picks: lowest id, max out-degree.
    let start = graph
        .nodes
        .iter()
        .map(|n| n.id.clone())
        .min_by(|a, b| a.as_str().cmp(b.as_str()))
        .unwrap();
    let mut degree = std::collections::HashMap::<&str, usize>::new();
    for e in &graph.edges {
        *degree.entry(e.from.as_str()).or_default() += 1;
    }
    let (hub, hub_degree) = degree
        .iter()
        .max_by_key(|(id, d)| (**d, std::cmp::Reverse(**id)))
        .map(|(id, d)| (NodeId::new(*id), *d))
        .unwrap();
    drop(graph);

    let depth = 50;
    let t = Instant::now();
    let (_, calls, direct_answers) = bfs(&direct, &start, depth, direct_calls).await;
    let direct_time = t.elapsed();
    let per_call = direct_time / calls.max(1) as u32;
    println!(
        "A2 direct scans: {calls} calls in {} ({} per call)",
        secs(direct_time),
        secs(per_call)
    );

    let t = Instant::now();
    neighbors(&store, &start).await;
    let first = t.elapsed();
    let t = Instant::now();
    neighbors(&store, &start).await;
    println!(
        "snapshot: first read (direct) {}, second read (builds) {}",
        secs(first),
        secs(t.elapsed())
    );
    let t = Instant::now();
    let (layers, calls, fast_answers) = bfs(&store, &start, depth, usize::MAX).await;
    let fast_time = t.elapsed();
    println!(
        "A2 snapshot: full BFS from {} to depth {depth}: {calls} calls, {} reached, {} layers, in {} ({:.1} us per call)",
        start.as_str(),
        layers.iter().sum::<usize>(),
        layers.len(),
        secs(fast_time),
        fast_time.as_secs_f64() * 1e6 / calls.max(1) as f64
    );
    println!(
        "A2 direct scans, extrapolated to the full BFS: {}",
        secs(per_call * calls as u32)
    );
    let compared = direct_answers.len().min(fast_answers.len());
    assert_eq!(
        direct_answers[..compared],
        fast_answers[..compared],
        "snapshot and direct answers differ"
    );
    println!("A2: first {compared} neighbour lists identical on both paths");

    for (name, s) in [("direct", &direct), ("snapshot", &store)] {
        let t = Instant::now();
        let mut visited = HashSet::from([hub.clone()]);
        let mut frontier = vec![hub.clone()];
        let mut layers = Vec::new();
        let mut calls = 0;
        for _ in 0..2 {
            let mut next = Vec::new();
            for v in &frontier {
                calls += 1;
                for id in neighbors(s, v).await {
                    if visited.insert(id.clone()) {
                        next.push(id);
                    }
                }
            }
            layers.push(next.len());
            frontier = next;
            if name == "direct" {
                break; // two hops over the direct path is A1's 248 s
            }
        }
        println!(
            "A1 {name}: hub {} (out-degree {hub_degree}), layers {layers:?}, {calls} calls in {}",
            hub.as_str(),
            secs(t.elapsed())
        );
    }

    let degree_of = |s: LanceDbGraphStore, v: NodeId| async move {
        s.get_edges(EdgeQuery {
            from: Some(v),
            to: None,
            label: Some(Label::new("E")),
        })
        .await
        .unwrap()
    };
    let sample = fast_answers
        .iter()
        .flat_map(|(_, ids)| ids.iter().cloned())
        .take(100)
        .collect::<Vec<_>>();
    for (name, s) in [("direct", &direct), ("snapshot", &store)] {
        let t = Instant::now();
        let n = if name == "direct" { 20 } else { sample.len() };
        for v in sample.iter().take(n) {
            degree_of(s.clone(), v.clone()).await;
        }
        println!(
            "A12 {name}: {n} one-hop get_edges in {} ({} each)",
            secs(t.elapsed()),
            secs(t.elapsed() / n.max(1) as u32)
        );
    }
    for v in sample.iter().take(20).chain([&hub]) {
        assert_eq!(
            degree_of(direct.clone(), v.clone()).await,
            degree_of(store.clone(), v.clone()).await
        );
    }
    println!("A12: edge lists identical on both paths");
}
