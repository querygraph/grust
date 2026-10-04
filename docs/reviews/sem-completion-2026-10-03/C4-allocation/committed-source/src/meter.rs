//! Requested System allocator bytes; input construction and JSON are outside phases.
use serde_json::json;
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Instant;

pub struct CountedSystem;
static LIVE: AtomicUsize = AtomicUsize::new(0);
static PEAK: AtomicUsize = AtomicUsize::new(0);
static ALLOCS: AtomicUsize = AtomicUsize::new(0);
static DEALLOCS: AtomicUsize = AtomicUsize::new(0);
static BYTES: AtomicUsize = AtomicUsize::new(0);

fn allocated(bytes: usize) {
    ALLOCS.fetch_add(1, Ordering::Relaxed);
    BYTES.fetch_add(bytes, Ordering::Relaxed);
    PEAK.fetch_max(
        LIVE.fetch_add(bytes, Ordering::Relaxed) + bytes,
        Ordering::Relaxed,
    );
}

unsafe impl GlobalAlloc for CountedSystem {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let pointer = unsafe { System.alloc(layout) };
        if !pointer.is_null() {
            allocated(layout.size());
        }
        pointer
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let pointer = unsafe { System.alloc_zeroed(layout) };
        if !pointer.is_null() {
            allocated(layout.size());
        }
        pointer
    }
    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        LIVE.fetch_sub(layout.size(), Ordering::Relaxed);
        DEALLOCS.fetch_add(1, Ordering::Relaxed);
        unsafe { System.dealloc(pointer, layout) };
    }
    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        let result = unsafe { System.realloc(pointer, layout, size) };
        if !result.is_null() {
            LIVE.fetch_sub(layout.size(), Ordering::Relaxed);
            DEALLOCS.fetch_add(1, Ordering::Relaxed);
            allocated(size);
        }
        result
    }
}

pub struct Phase {
    live: usize,
    started: Instant,
}
impl Phase {
    pub fn start() -> Self {
        let live = LIVE.load(Ordering::Relaxed);
        PEAK.store(live, Ordering::Relaxed);
        ALLOCS.store(0, Ordering::Relaxed);
        DEALLOCS.store(0, Ordering::Relaxed);
        BYTES.store(0, Ordering::Relaxed);
        Self {
            live,
            started: Instant::now(),
        }
    }
    pub fn finish(
        self,
        name: &str,
        reported: usize,
        output_bytes: usize,
        metadata: serde_json::Value,
    ) {
        // Snapshot before formatting, printing or querying process RSS allocates.
        let seconds = self.started.elapsed().as_secs_f64();
        let live = LIVE.load(Ordering::Relaxed);
        let peak = PEAK.load(Ordering::Relaxed);
        let allocations = ALLOCS.load(Ordering::Relaxed);
        let deallocations = DEALLOCS.load(Ordering::Relaxed);
        let bytes = BYTES.load(Ordering::Relaxed);
        let mut usage = unsafe { std::mem::zeroed::<libc::rusage>() };
        assert_eq!(unsafe { libc::getrusage(libc::RUSAGE_SELF, &mut usage) }, 0);
        println!(
            "{}",
            json!({
                "phase":name, "seconds_exploratory_shared_host":seconds,
                "live_requested_before":self.live, "live_requested_after":live,
                "live_requested_change":live as i64-self.live as i64,
                "peak_requested_above_before":peak-self.live,
                "allocations":allocations, "deallocations":deallocations,
                "allocated_requested_bytes":bytes, "accumulator_reported_size":reported,
                "output_array_reported_bytes":output_bytes, "metadata":metadata,
                "process_lifetime_peak_rss_bytes":usage.ru_maxrss as usize * if cfg!(target_os="macos") {1} else {1024},
            })
        );
    }
}
