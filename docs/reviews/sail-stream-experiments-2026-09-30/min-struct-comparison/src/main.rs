//! Exploratory allocation probe for the unchanged DataFusion 55.1 struct MIN.
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Instant;

use arrow::array::{Array, ArrayData, ArrayRef, Float64Array, Int64Array, StructArray};
use arrow::datatypes::{DataType, Field};
use datafusion_expr::{EmitTo, GroupsAccumulator};
use serde_json::json;

use min_struct_comparison::accumulator;

struct CountedSystem;
static LIVE: AtomicUsize = AtomicUsize::new(0);
static PEAK: AtomicUsize = AtomicUsize::new(0);
static ALLOCS: AtomicUsize = AtomicUsize::new(0);
static DEALLOCS: AtomicUsize = AtomicUsize::new(0);
static ALLOC_BYTES: AtomicUsize = AtomicUsize::new(0);

fn allocated(bytes: usize) {
    ALLOCS.fetch_add(1, Ordering::Relaxed);
    ALLOC_BYTES.fetch_add(bytes, Ordering::Relaxed);
    let live = LIVE.fetch_add(bytes, Ordering::Relaxed) + bytes;
    PEAK.fetch_max(live, Ordering::Relaxed);
}

unsafe impl GlobalAlloc for CountedSystem {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc(layout) };
        if !ptr.is_null() { allocated(layout.size()); }
        ptr
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc_zeroed(layout) };
        if !ptr.is_null() { allocated(layout.size()); }
        ptr
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        LIVE.fetch_sub(layout.size(), Ordering::Relaxed);
        DEALLOCS.fetch_add(1, Ordering::Relaxed);
        unsafe { System.dealloc(ptr, layout) };
    }
    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        let result = unsafe { System.realloc(ptr, layout, size) };
        if !result.is_null() {
            LIVE.fetch_sub(layout.size(), Ordering::Relaxed);
            DEALLOCS.fetch_add(1, Ordering::Relaxed);
            allocated(size);
        }
        result
    }
}

#[global_allocator]
static ALLOCATOR: CountedSystem = CountedSystem;

struct Phase { live: usize, started: Instant }
impl Phase {
    fn start() -> Self {
        let live = LIVE.load(Ordering::Relaxed);
        PEAK.store(live, Ordering::Relaxed);
        ALLOCS.store(0, Ordering::Relaxed);
        DEALLOCS.store(0, Ordering::Relaxed);
        ALLOC_BYTES.store(0, Ordering::Relaxed);
        Self { live, started: Instant::now() }
    }
    fn finish(self, phase: &str, groups: usize, reported: usize, output_bytes: usize) {
        // Snapshot before JSON serialization/printing introduces its own allocations.
        let seconds = self.started.elapsed().as_secs_f64();
        let live = LIVE.load(Ordering::Relaxed);
        let peak = PEAK.load(Ordering::Relaxed);
        let allocations = ALLOCS.load(Ordering::Relaxed);
        let deallocations = DEALLOCS.load(Ordering::Relaxed);
        let allocated_bytes = ALLOC_BYTES.load(Ordering::Relaxed);
        let mut usage = unsafe { std::mem::zeroed::<libc::rusage>() };
        assert_eq!(unsafe { libc::getrusage(libc::RUSAGE_SELF, &mut usage) }, 0);
        let process_lifetime_peak_rss = usage.ru_maxrss as usize
            * if cfg!(target_os = "macos") { 1 } else { 1024 };
        println!("{}", json!({"phase": phase, "groups": groups, "seconds": seconds,
            "live_requested_before": self.live, "live_requested_after": live,
            "live_requested_change": live as i64 - self.live as i64,
            "peak_requested": peak, "peak_requested_above_before": peak - self.live,
            "allocations": allocations, "deallocations": deallocations,
            "allocated_requested_bytes": allocated_bytes,
            "process_lifetime_peak_rss_bytes": process_lifetime_peak_rss,
            "accumulator_reported_size": reported, "output_array_memory_size": output_bytes}));
    }
}

fn input(groups: usize, distance: f64) -> StructArray {
    StructArray::from(vec![
        (Arc::new(Field::new("distance", DataType::Float64, false)),
         Arc::new(Float64Array::from(vec![distance; groups])) as ArrayRef),
        (Arc::new(Field::new("hops", DataType::Int64, false)),
         Arc::new(Int64Array::from(vec![2; groups])) as ArrayRef),
        (Arc::new(Field::new("parent", DataType::Int64, false)),
         Arc::new(Int64Array::from_iter_values((0..groups).map(|i| i as i64 - groups as i64 / 2))) as ArrayRef),
    ])
}

fn update(acc: &mut dyn GroupsAccumulator, array: &StructArray,
          groups: &[usize], growing: bool) {
    for begin in (0..groups.len()).step_by(8192) {
        let end = (begin + 8192).min(groups.len());
        let values = [Arc::new(array.slice(begin, end - begin)) as ArrayRef];
        acc.update_batch(&values, &groups[begin..end], None,
                         if growing { end } else { groups.len() }).unwrap();
    }
}

fn main() {
    let groups: usize = std::env::args().nth(1).unwrap().parse().unwrap();
    assert!((1..=100_000).contains(&groups));
    let compact = std::env::args().nth(2).as_deref() == Some("compact");
    println!("{}", json!({"groups": groups, "batch_rows": 8192, "implementation": if compact { "compact" } else { "original" },
        "sizeof_struct_array": size_of::<StructArray>(),
        "sizeof_option_struct_array": size_of::<Option<StructArray>>(),
        "sizeof_array_data": size_of::<ArrayData>(),
        "boundary": "single-thread exploratory allocation counts; requested System allocator bytes, not usable heap/RSS; no graph pipeline"}));
    let control = Phase::start();
    let array = input(groups, 2.0);
    control.finish("dense_arrow_input_control", groups, 0, array.get_array_memory_size());
    let indices: Vec<usize> = (0..groups).collect();
    let mut acc = accumulator(array.data_type(), compact);
    let phase = Phase::start();
    update(acc.as_mut(), &array, &indices, true);
    phase.finish("first_update", groups, acc.size(), 0);
    let phase = Phase::start();
    update(acc.as_mut(), &array, &indices, false);
    phase.finish("repeated_identical_update", groups, acc.size(), 0);
    let better = input(groups, 1.0);
    let phase = Phase::start();
    update(acc.as_mut(), &better, &indices, false);
    phase.finish("repeated_improving_update", groups, acc.size(), 0);
    let phase = Phase::start();
    let result = acc.evaluate(EmitTo::All).unwrap();
    phase.finish("evaluate_all", groups, acc.size(), result.get_array_memory_size());
    assert_eq!(result.len(), groups);
    if !compact { assert_eq!(acc.size(), 0); }
    let actual = result.as_any().downcast_ref::<StructArray>().unwrap();
    assert_eq!(actual, &better);
    // Independently expose retained-byte accounting after prefix emission.
    let mut prefix = accumulator(array.data_type(), compact);
    update(prefix.as_mut(), &array, &indices, true);
    let before = prefix.size();
    let emitted = prefix.evaluate(EmitTo::First(groups / 2)).unwrap();
    println!("{}", json!({"phase":"emit_first_accounting", "groups":groups,
        "before_reported":before,"after_reported":prefix.size(),"emitted_groups":emitted.len()}));
    let remaining = prefix.evaluate(EmitTo::All).unwrap();
    assert_eq!(remaining.len() + emitted.len(), groups);
}
