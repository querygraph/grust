//! Requested heap and admitted-memory controls across the raw-input lifetime.
#[path = "../src/adjacency_tests/allocations.rs"]
mod allocations;
#[path = "delta_support/mod.rs"]
mod support;
use grust_procedures::MemoryAccount;
use sail_argentea_core::*;
use std::sync::atomic::Ordering;

const LIMIT: usize = 256 << 20;
fn bfs_options() -> BfsOptions {
    BfsOptions {
        source: 0,
        algorithm: BfsAlgorithm::Frontier,
        max_levels: 8,
        alpha: 14,
        beta: 24,
    }
}
fn sssp_options() -> SsspOptions {
    SsspOptions {
        source: 0,
        algorithm: SsspAlgorithm::DeltaStar,
        max_rounds: 8,
        delta: 1.0,
    }
}
struct Raw {
    ids: Vec<i64>,
    bfs: Vec<(i64, i64)>,
    sssp: Vec<(i64, i64, f64)>,
    // Rust drops fields in declaration order, so the charge outlives the vectors.
    _admission: MemoryAccount,
}
impl Raw {
    fn new(n: usize, degree: usize, weighted: bool, r: &Resources) -> Self {
        let mut admission = r.execution.memory_account();
        admission
            .charge(n * 8 + n * degree * if weighted { 24 } else { 16 })
            .unwrap();
        Self {
            ids: (0..n as i64).rev().map(|i| i * 3).collect(),
            bfs: if weighted {
                vec![]
            } else {
                (0..n * degree).map(|i| ((i % n) as i64 * 3, 0)).collect()
            },
            sssp: if weighted {
                (0..n * degree)
                    .map(|i| ((i % n) as i64 * 3, 0, 0.5))
                    .collect()
            } else {
                vec![]
            },
            _admission: admission,
        }
    }
}
enum Partition {
    Bfs(BfsPartition),
    Sssp(SsspPartition),
}
fn build(op: Operation, raw: &Raw, weighted: bool, r: &Resources) -> Result<Partition> {
    if weighted {
        SsspPartition::build(op, 0, 7, &raw.ids, &raw.sssp, sssp_options(), r.clone())
            .map(Partition::Sssp)
    } else {
        BfsPartition::build(op, 0, 7, &raw.ids, &raw.bfs, bfs_options(), r.clone())
            .map(Partition::Bfs)
    }
}
impl Partition {
    fn check(&self, n: usize) {
        match self {
            Self::Bfs(p) => {
                assert_eq!(p.state_rows().count(), n);
                assert_eq!(p.reached_count(), 1);
                assert_eq!(p.frontier_count(), 1);
                assert!(
                    p.state_rows()
                        .all(|r| r.distance == (r.id == 0).then_some(0))
                );
                assert_eq!(p.completed_mode(), BfsMode::Topology);
            }
            Self::Sssp(p) => {
                assert_eq!(p.state_rows().count(), n);
                assert_eq!(p.reached_count(), 1);
                assert_eq!(p.active_count(), 1);
                assert!(
                    p.state_rows()
                        .all(|r| r.label == (r.id == 0).then_some(SsspLabel::source(0)))
                );
                assert_eq!(p.completed_mode(), SsspMode::Topology);
            }
        }
    }
}
fn cost(
    n: usize,
    degree: usize,
    weighted: bool,
    release: bool,
) -> (allocations::Counts, usize, usize) {
    let (r, usage, drops) = support::resources(LIMIT);
    let op = support::operation(3, n as u64);
    // Measure raw-vector allocation too: deallocating an unmeasured input would
    // otherwise subtract bytes that were never added to the heap counter.
    let (part, counts) = allocations::measure(|| {
        let raw = Raw::new(n, degree, weighted, &r);
        assert!(!release);
        build(op, &raw, weighted, &r).unwrap()
    });
    part.check(n);
    let used = usage.usage().unwrap();
    println!(
        "INPUT_LIFETIME_COUNTER n={n} degree={degree} weighted={weighted} release={release} allocation_calls={} allocated_bytes={} peak_requested_bytes={} retained_admitted_bytes={} peak_admitted_bytes={} work={}",
        counts.calls,
        counts.bytes,
        counts.peak,
        used.live_bytes,
        used.peak_bytes,
        used.counted_work().unwrap()
    );
    drop(part);
    assert_eq!(usage.usage().unwrap().live_bytes, 0);
    drop(r);
    assert_eq!(drops.load(Ordering::SeqCst), 1);
    (counts, used.peak_bytes, used.counted_work().unwrap())
}
#[test]
fn original_baseline_input_lifetime_counters() {
    for n in [1_024, 65_536] {
        for degree in [0, 1, 8] {
            for weighted in [false, true] { cost(n, degree, weighted, false); }
        }
    }
}
