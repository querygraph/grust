//! Bulk-load throughput for `TursoGraphStore::put_graph`, fed the way the
//! adversarial-graph strain harness feeds it: every vertex first, then the
//! edges in CSR order (sources in string order, each source's targets in
//! string order), in `put_graph` calls of at most `--chunk` edges.
//!
//! ```text
//! cargo run --release -p grust-turso --example bulk_load -- \
//!     --edges 10000000 [--nodes N] [--chunk 5000000] [--mode wal|mvcc] \
//!     [--path /tmp/bulk.db] [--snap cit-Patents.txt]
//! ```
//!
//! Prints the rate of every chunk and the running rate, so a rate that falls
//! as the tables grow is visible, then times the first reads after the load
//! (anchored edge lookups and a two-hop traversal) and prints the indexes and
//! the query plans of those reads.

use grust_core::prelude::*;
use grust_turso::{TursoConfig, TursoGraphStore, TursoJournalMode};
use std::time::Instant;

const NODE_LABEL: &str = "Node";
const EDGE_LABEL: &str = "EDGE";

struct Args {
    edges: usize,
    nodes: Option<usize>,
    chunk: usize,
    mode: TursoJournalMode,
    path: String,
    snap: Option<String>,
}

fn parse_args() -> Args {
    let mut args = Args {
        edges: 1_000_000,
        nodes: None,
        chunk: 5_000_000,
        mode: TursoJournalMode::Wal,
        path: std::env::temp_dir()
            .join("grust-turso-bulk.db")
            .display()
            .to_string(),
        snap: None,
    };
    let mut it = std::env::args().skip(1);
    while let Some(flag) = it.next() {
        let value = it.next().unwrap_or_else(|| panic!("{flag} needs a value"));
        match flag.as_str() {
            "--edges" => args.edges = value.parse().expect("--edges"),
            "--nodes" => args.nodes = Some(value.parse().expect("--nodes")),
            "--chunk" => args.chunk = value.parse().expect("--chunk"),
            "--mode" => {
                args.mode = match value.as_str() {
                    "wal" => TursoJournalMode::Wal,
                    "mvcc" => TursoJournalMode::Mvcc,
                    other => panic!("unknown mode {other}"),
                }
            }
            "--path" => args.path = value,
            "--snap" => args.snap = Some(value),
            other => panic!("unknown flag {other}"),
        }
    }
    args
}

/// A compact CSR over string-sorted vertex ids, like the harness builds.
struct Csr {
    ids: Vec<String>,
    offsets: Vec<usize>,
    targets: Vec<u32>,
}

impl Csr {
    fn from_pairs(ids: Vec<String>, mut pairs: Vec<(u32, u32)>) -> Self {
        pairs.sort_unstable();
        pairs.dedup();
        let mut offsets = vec![0usize; ids.len() + 1];
        for &(s, _) in &pairs {
            offsets[s as usize + 1] += 1;
        }
        for i in 0..ids.len() {
            offsets[i + 1] += offsets[i];
        }
        let targets = pairs.into_iter().map(|(_, t)| t).collect();
        Self {
            ids,
            offsets,
            targets,
        }
    }

    /// `edges` pseudo-random edges over `nodes` vertices named by their
    /// decimal index (xorshift, fixed seed: every run loads the same graph).
    fn synthetic(edges: usize, nodes: usize) -> Self {
        let mut ids: Vec<String> = (0..nodes).map(|i| i.to_string()).collect();
        ids.sort_unstable();
        let mut state = 0x9E37_79B9_7F4A_7C15u64;
        let mut next = || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            state
        };
        let n = nodes as u64;
        let pairs = (0..edges)
            .map(|_| ((next() % n) as u32, (next() % n) as u32))
            .collect();
        Self::from_pairs(ids, pairs)
    }

    /// A SNAP edge list (`src<TAB>dst`, `#` comments), deduplicated. Ids are
    /// interned while streaming, as the harness does, so the file is never
    /// held whole in memory.
    fn snap(path: &str, limit: usize) -> Self {
        use std::io::BufRead;
        let file = std::io::BufReader::new(std::fs::File::open(path).expect("open SNAP file"));
        let mut intern: std::collections::HashMap<String, u32> = Default::default();
        let mut ids: Vec<String> = Vec::new();
        let mut id_of = |s: &str| -> u32 {
            if let Some(&i) = intern.get(s) {
                return i;
            }
            let i = ids.len() as u32;
            ids.push(s.to_string());
            intern.insert(s.to_string(), i);
            i
        };
        let mut pairs = Vec::new();
        for line in file.lines() {
            let line = line.expect("read SNAP line");
            if line.starts_with('#') || line.trim().is_empty() {
                continue;
            }
            let mut parts = line.split_whitespace();
            let (Some(a), Some(b)) = (parts.next(), parts.next()) else {
                continue;
            };
            pairs.push((id_of(a), id_of(b)));
            if pairs.len() >= limit {
                break;
            }
        }
        drop(intern);
        // Renumber so index order is string order, as the harness does.
        let mut order: Vec<u32> = (0..ids.len() as u32).collect();
        order.sort_unstable_by(|&a, &b| ids[a as usize].cmp(&ids[b as usize]));
        let mut rank = vec![0u32; ids.len()];
        for (r, &old) in order.iter().enumerate() {
            rank[old as usize] = r as u32;
        }
        for pair in &mut pairs {
            *pair = (rank[pair.0 as usize], rank[pair.1 as usize]);
        }
        ids.sort_unstable();
        Self::from_pairs(ids, pairs)
    }

    fn edge_count(&self) -> usize {
        self.targets.len()
    }

    fn node_chunks(&self, chunk: usize) -> impl Iterator<Item = Graph> + '_ {
        self.ids.chunks(chunk).map(|ids| {
            Graph::new(
                ids.iter()
                    .map(|id| Node::new(NODE_LABEL, id.as_str(), Props::new()))
                    .collect(),
                Vec::new(),
            )
        })
    }

    fn edge_chunk(&self, start: usize, chunk: usize) -> Graph {
        let end = (start + chunk).min(self.edge_count());
        let mut source = self.offsets.partition_point(|&o| o <= start) - 1;
        let mut edges = Vec::with_capacity(end - start);
        for pos in start..end {
            while self.offsets[source + 1] <= pos {
                source += 1;
            }
            edges.push(Edge::new(
                EDGE_LABEL,
                self.ids[source].as_str(),
                self.ids[self.targets[pos] as usize].as_str(),
                Props::new(),
            ));
        }
        Graph::new(Vec::new(), edges)
    }
}

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<()> {
    let args = parse_args();
    let started = Instant::now();
    let csr = match &args.snap {
        Some(path) => Csr::snap(path, args.edges),
        None => Csr::synthetic(args.edges, args.nodes.unwrap_or(args.edges / 20).max(1)),
    };
    println!(
        "input: {} nodes, {} edges (built in {:.1}s)",
        csr.ids.len(),
        csr.edge_count(),
        started.elapsed().as_secs_f64()
    );

    for suffix in ["", "-wal", "-shm", "-log"] {
        let _ = std::fs::remove_file(format!("{}{suffix}", args.path));
    }
    let store = TursoGraphStore::connect(TursoConfig {
        path: args.path.clone(),
        table_prefix: "ag".to_string(),
        batch_size: 500,
        journal_mode: args.mode,
    })
    .await?;
    store.bootstrap().await?;

    let load = Instant::now();
    for graph in csr.node_chunks(args.chunk.max(1)) {
        store.put_graph(&graph).await?;
    }
    let nodes_secs = load.elapsed().as_secs_f64();
    println!(
        "nodes: {} in {nodes_secs:.1}s ({:.0} nodes/s)",
        csr.ids.len(),
        csr.ids.len() as f64 / nodes_secs
    );

    let edges_started = Instant::now();
    let mut loaded = 0usize;
    while loaded < csr.edge_count() {
        let graph = csr.edge_chunk(loaded, args.chunk.max(1));
        let t = Instant::now();
        store.put_graph(&graph).await?;
        let secs = t.elapsed().as_secs_f64();
        loaded += graph.edges.len();
        println!(
            "edges: {loaded:>11} chunk {:>9} in {secs:>7.1}s ({:>8.0} edges/s)  running {:>8.0} edges/s",
            graph.edges.len(),
            graph.edges.len() as f64 / secs,
            loaded as f64 / edges_started.elapsed().as_secs_f64()
        );
    }
    let edge_secs = edges_started.elapsed().as_secs_f64();
    println!(
        "LOAD {} edges in {edge_secs:.1}s = {:.0} edges/s (nodes+edges {:.1}s)",
        loaded,
        loaded as f64 / edge_secs,
        load.elapsed().as_secs_f64()
    );

    // Recreate any index the load deferred (a no-op otherwise), timed: a
    // deferred index is paid for here, not hidden in the first read.
    let t = Instant::now();
    store.bootstrap().await?;
    println!(
        "bootstrap after load (index rebuild) {:.1}s; load+rebuild {:.1}s = {:.0} edges/s",
        t.elapsed().as_secs_f64(),
        edges_started.elapsed().as_secs_f64(),
        loaded as f64 / edges_started.elapsed().as_secs_f64()
    );

    // First reads after the load: anchored lookups both ways and a two-hop
    // traversal from a few sources, timed individually.
    let probes: Vec<&str> = (0..5)
        .map(|k| csr.ids[(k * 7919) % csr.ids.len()].as_str())
        .collect();
    for (i, id) in probes.iter().enumerate() {
        let t = Instant::now();
        let out = store
            .get_edges(EdgeQuery {
                from: Some(NodeId::new(*id)),
                ..Default::default()
            })
            .await?;
        let out_ms = t.elapsed().as_secs_f64() * 1e3;
        let t = Instant::now();
        let inc = store
            .get_edges(EdgeQuery {
                to: Some(NodeId::new(*id)),
                ..Default::default()
            })
            .await?;
        let in_ms = t.elapsed().as_secs_f64() * 1e3;
        let t = Instant::now();
        let two_hop = store
            .traverse(
                Traversal::from_node(NodeId::new(*id))
                    .out(EDGE_LABEL)
                    .out(EDGE_LABEL),
            )
            .await?;
        let hop_ms = t.elapsed().as_secs_f64() * 1e3;
        println!(
            "read {i} node {id}: out {} in {out_ms:.2}ms, in {} in {in_ms:.2}ms, 2-hop {} in {hop_ms:.2}ms",
            out.len(),
            inc.len(),
            two_hop.len()
        );
    }
    drop(store);

    // Row count, indexes and plans, from a fresh connection to the same file.
    // (A Cypher count(r) is not a pushdown shape and would materialize every
    // edge in memory.)
    let db = turso::Builder::new_local(&args.path)
        .build()
        .await
        .map_err(|e| GrustError::Backend(e.to_string()))?;
    let conn = db
        .connect()
        .map_err(|e| GrustError::Backend(e.to_string()))?;
    let t = Instant::now();
    let mut rows = conn
        .query("SELECT count(*) FROM ag_edges", ())
        .await
        .map_err(|e| GrustError::Backend(e.to_string()))?;
    if let Some(row) = rows
        .next()
        .await
        .map_err(|e| GrustError::Backend(e.to_string()))?
    {
        println!(
            "count(*) = {:?} in {:.1}s",
            row.get_value(0).ok(),
            t.elapsed().as_secs_f64()
        );
    }
    let mut rows = conn
        .query(
            "SELECT name, tbl_name FROM sqlite_schema WHERE type = 'index' ORDER BY name",
            (),
        )
        .await
        .map_err(|e| GrustError::Backend(e.to_string()))?;
    while let Some(row) = rows
        .next()
        .await
        .map_err(|e| GrustError::Backend(e.to_string()))?
    {
        println!(
            "index {:?} on {:?}",
            row.get_value(0).ok(),
            row.get_value(1).ok()
        );
    }
    let id = probes[0];
    for sql in [
        format!("SELECT * FROM ag_edges WHERE from_id = '{id}'"),
        format!("SELECT * FROM ag_edges WHERE to_id = '{id}'"),
        grust_turso::traversal_sql(
            "ag_nodes",
            "ag_edges",
            &Traversal::from_node(NodeId::new(id))
                .out(EDGE_LABEL)
                .out(EDGE_LABEL),
        )?,
    ] {
        let mut rows = conn
            .query(format!("EXPLAIN QUERY PLAN {sql}"), ())
            .await
            .map_err(|e| GrustError::Backend(e.to_string()))?;
        println!(
            "plan: {}",
            sql.split_whitespace().collect::<Vec<_>>().join(" ")
        );
        while let Some(row) = rows
            .next()
            .await
            .map_err(|e| GrustError::Backend(e.to_string()))?
        {
            println!("   {:?}", row.get_value(3).ok());
        }
    }
    let bytes: u64 = ["", "-wal"]
        .iter()
        .filter_map(|s| std::fs::metadata(format!("{}{s}", args.path)).ok())
        .map(|m| m.len())
        .sum();
    println!("database size {:.2} GB", bytes as f64 / 1e9);
    Ok(())
}
