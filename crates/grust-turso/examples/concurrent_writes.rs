//! Hot-node write contention, shaped like the adversarial-graph A4 scenario:
//! `--writers` tasks each attach `--per` new edges to one hub vertex, every
//! write a `put_node` then a `put_edge` on the writer's own store handle.
//!
//! ```text
//! cargo run --release -p grust-turso --example concurrent_writes -- \
//!     [--writers 16] [--per 200] [--mode wal|mvcc] [--handles separate|shared] \
//!     [--path /tmp/concurrent.db]
//! ```
//!
//! `separate` opens every writer with `TursoGraphStore::connect` on the same
//! path (one `turso::Database` each, as the harness does); `shared` opens
//! them with `connect_shared` (one database, one connection per writer).
//! Prints accepted writes, typed conflicts, other errors, wall time and
//! accepted writes per second, then checks the hub's final out-degree.

use grust_core::prelude::*;
use grust_turso::{TursoConfig, TursoGraphStore, TursoJournalMode, TursoSynchronous};
use std::sync::Arc;
use std::time::Instant;

const HUB: &str = "hub";

struct Args {
    writers: usize,
    per: usize,
    mode: TursoJournalMode,
    shared: bool,
    sync: Option<TursoSynchronous>,
    path: String,
}

fn parse_args() -> Args {
    let mut args = Args {
        writers: 16,
        per: 200,
        mode: TursoJournalMode::Mvcc,
        shared: false,
        sync: None,
        path: std::env::temp_dir()
            .join("grust-turso-concurrent.db")
            .display()
            .to_string(),
    };
    let mut it = std::env::args().skip(1);
    while let Some(flag) = it.next() {
        let value = it.next().unwrap_or_else(|| panic!("{flag} needs a value"));
        match flag.as_str() {
            "--writers" => args.writers = value.parse().expect("--writers"),
            "--per" => args.per = value.parse().expect("--per"),
            "--mode" => {
                args.mode = match value.as_str() {
                    "wal" => TursoJournalMode::Wal,
                    "mvcc" => TursoJournalMode::Mvcc,
                    other => panic!("unknown mode {other}"),
                }
            }
            "--handles" => {
                args.shared = match value.as_str() {
                    "shared" => true,
                    "separate" => false,
                    other => panic!("unknown handles {other}"),
                }
            }
            "--sync" => {
                args.sync = Some(match value.as_str() {
                    "full" => TursoSynchronous::Full,
                    "normal" => TursoSynchronous::Normal,
                    "off" => TursoSynchronous::Off,
                    other => panic!("unknown sync {other}"),
                })
            }
            "--path" => args.path = value,
            other => panic!("unknown flag {other}"),
        }
    }
    args
}

fn is_conflict(err: &GrustError) -> bool {
    let msg = err.to_string().to_ascii_lowercase();
    msg.contains("conflict") || msg.contains("busy") || msg.contains("locked")
}

#[tokio::main(flavor = "multi_thread")]
async fn main() -> Result<()> {
    let args = parse_args();
    for suffix in ["", "-wal", "-shm", "-log"] {
        let _ = std::fs::remove_file(format!("{}{suffix}", args.path));
    }
    let config = TursoConfig {
        path: args.path.clone(),
        table_prefix: "ag".to_string(),
        batch_size: 500,
        journal_mode: args.mode,
    };
    let base = TursoGraphStore::connect(config.clone()).await?;
    base.bootstrap().await?;
    base.put_node(&Node::new("Node", HUB, Props::new())).await?;

    let opened = Instant::now();
    let mut stores = Vec::with_capacity(args.writers);
    for _ in 0..args.writers {
        let store = if args.shared {
            base.connect_shared().await?
        } else {
            TursoGraphStore::connect(config.clone()).await?
        };
        if let Some(mode) = args.sync {
            store.set_synchronous(mode).await?;
        }
        stores.push(Arc::new(store));
    }
    let open_s = opened.elapsed().as_secs_f64();

    let barrier = Arc::new(tokio::sync::Barrier::new(args.writers));
    let started = Instant::now();
    let mut tasks = Vec::with_capacity(args.writers);
    for (w, store) in stores.into_iter().enumerate() {
        let barrier = barrier.clone();
        let per = args.per;
        tasks.push(tokio::spawn(async move {
            let (mut accepted, mut conflicts, mut other) = (0usize, 0usize, Vec::new());
            barrier.wait().await;
            for i in 0..per {
                let target = format!("hot-{w}-{i}");
                let outcome = match store
                    .put_node(&Node::new("Node", target.clone(), Props::new()))
                    .await
                {
                    Ok(_) => store
                        .put_edge(&Edge::new("EDGE", HUB, target, Props::new()))
                        .await
                        .map(|_| ()),
                    Err(e) => Err(e),
                };
                match outcome {
                    Ok(()) => accepted += 1,
                    Err(e) if is_conflict(&e) => conflicts += 1,
                    Err(e) => other.push(e.to_string()),
                }
            }
            (accepted, conflicts, other)
        }));
    }
    let (mut accepted, mut conflicts, mut other) = (0usize, 0usize, Vec::new());
    for task in tasks {
        let (a, c, o) = task.await.expect("writer task");
        accepted += a;
        conflicts += c;
        other.extend(o);
    }
    let wall = started.elapsed().as_secs_f64();
    let degree = base
        .get_edges(EdgeQuery {
            from: Some(NodeId::new(HUB)),
            to: None,
            label: None,
        })
        .await?
        .len();
    println!(
        "sync={:?} mode={:?} handles={} writers={} per={} open={:.2}s wall={:.2}s accepted={} conflicts={} other={} writes/s={:.0} hub_degree={} consistent={}",
        args.sync,
        args.mode,
        if args.shared { "shared" } else { "separate" },
        args.writers,
        args.per,
        open_s,
        wall,
        accepted,
        conflicts,
        other.len(),
        accepted as f64 / wall,
        degree,
        degree == accepted
    );
    for e in other.iter().take(3) {
        println!("  other error: {e}");
    }
    Ok(())
}
