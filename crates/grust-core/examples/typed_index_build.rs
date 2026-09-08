//! Allocation diagnostic, not a publication benchmark. Run identical inputs
//! before and after a change. Wall time on a shared host is an upper bound;
//! retain process CPU ticks and host load with the allocation measurements.
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
use std::time::Instant;

use grust_core::{Edge, Graph, Node, Props, TypedGraphIndex};

struct Allocator;
static LIVE: AtomicUsize = AtomicUsize::new(0);
static PEAK: AtomicUsize = AtomicUsize::new(0);
static REQUESTED: AtomicUsize = AtomicUsize::new(0);

fn allocated(bytes: usize) {
    let live = LIVE.fetch_add(bytes, Relaxed) + bytes;
    PEAK.fetch_max(live, Relaxed);
    REQUESTED.fetch_add(bytes, Relaxed);
}

// Counts requested bytes, not allocator overhead, RSS, or cgroup memory.
unsafe impl GlobalAlloc for Allocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc(layout) };
        if !ptr.is_null() {
            allocated(layout.size());
        }
        ptr
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) };
        LIVE.fetch_sub(layout.size(), Relaxed);
    }
    unsafe fn realloc(&self, ptr: *mut u8, old: Layout, size: usize) -> *mut u8 {
        let ptr = unsafe { System.realloc(ptr, old, size) };
        if !ptr.is_null() {
            LIVE.fetch_sub(old.size(), Relaxed);
            allocated(size);
        }
        ptr
    }
}

#[global_allocator]
static ALLOCATOR: Allocator = Allocator;

fn cpu_ticks() -> Option<u64> {
    let stat = std::fs::read_to_string("/proc/self/stat").ok()?;
    let fields: Vec<_> = stat.rsplit_once(')')?.1.split_whitespace().collect();
    Some(fields.get(11)?.parse::<u64>().ok()? + fields.get(12)?.parse::<u64>().ok()?)
}

fn main() {
    let args: Vec<_> = std::env::args().collect();
    let number = |i: usize, default| args.get(i).map(|s| s.parse().unwrap()).unwrap_or(default);
    let vertices = number(1, 100_000usize);
    let edges = number(2, 1_000_000usize);
    let types = number(3, 128usize);
    assert!(vertices > 0 && types > 0);
    let nodes: Vec<_> = (0..vertices)
        .map(|n| Node::new("Vertex", n.to_string(), Props::new()))
        .collect();
    let labels: Vec<_> = (0..types)
        .map(|n| grust_core::Label::new(format!("T{n}")))
        .collect();
    let edges: Vec<_> = (0..edges)
        .map(|n| {
            Edge::new(
                labels[n % types].clone(),
                nodes[n % vertices].id.clone(),
                nodes[(n * 7 + n / vertices) % vertices].id.clone(),
                Props::new(),
            )
        })
        .collect();
    let graph = Arc::new(Graph::new(nodes, edges));
    let load_start = std::fs::read_to_string("/proc/loadavg").ok();
    let cpu_start = cpu_ticks();
    let live_start = LIVE.load(Relaxed);
    PEAK.store(live_start, Relaxed);
    let requested_start = REQUESTED.load(Relaxed);
    let started = Instant::now();
    let index = TypedGraphIndex::new(Arc::clone(&graph)).unwrap();
    let wall_ms = started.elapsed().as_secs_f64() * 1000.0;
    let peak_extra = PEAK.load(Relaxed).saturating_sub(live_start);
    let retained_extra = LIVE.load(Relaxed).saturating_sub(live_start);
    let requested = REQUESTED.load(Relaxed) - requested_start;
    let cpu = cpu_ticks().zip(cpu_start).map(|(end, start)| end - start);
    let load_end = std::fs::read_to_string("/proc/loadavg").ok();
    // Validate every physical edge in both directions, including duplicates.
    let mut outgoing = 0;
    let mut incoming = 0;
    for vertex in 0..vertices as u32 {
        for label in &labels {
            for neighbor in index.outgoing(vertex, label.as_str()) {
                let edge = &graph.edges[neighbor.edge as usize];
                assert_eq!(edge.from, graph.nodes[vertex as usize].id);
                assert_eq!(edge.to, graph.nodes[neighbor.vertex as usize].id);
                assert_eq!(&edge.label, label);
                outgoing += 1;
            }
            for neighbor in index.incoming(vertex, label.as_str()) {
                let edge = &graph.edges[neighbor.edge as usize];
                assert_eq!(edge.to, graph.nodes[vertex as usize].id);
                assert_eq!(edge.from, graph.nodes[neighbor.vertex as usize].id);
                assert_eq!(&edge.label, label);
                incoming += 1;
            }
        }
    }
    assert_eq!(outgoing, graph.edges.len());
    assert_eq!(incoming, graph.edges.len());
    println!(
        "{}",
        serde_json::json!({
            "vertices": vertices, "edges": graph.edges.len(), "types": types,
            "build_wall_ms_upper_bound": wall_ms, "build_cpu_ticks": cpu,
            "host_loadavg_start": load_start, "host_loadavg_end": load_end,
            "build_peak_extra_requested_bytes": peak_extra,
            "index_retained_requested_bytes": retained_extra,
            "build_total_requested_bytes": requested,
            "verified_edges_per_direction": outgoing
        })
    );
}
