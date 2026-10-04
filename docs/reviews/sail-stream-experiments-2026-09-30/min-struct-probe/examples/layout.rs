//! Retained allocation sizes of one unchanged copy_array_data -> StructArray.
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicIsize, Ordering};
use arrow::array::{Array, ArrayRef, Float64Array, Int64Array, MutableArrayData, StructArray};
use arrow::datatypes::{DataType, Field};
use datafusion_common::scalar::copy_array_data;

struct Counter;
static TRACK: AtomicBool = AtomicBool::new(false);
static NET: [AtomicIsize; 8193] = [const { AtomicIsize::new(0) }; 8193];
fn track(size: usize, delta: isize) {
    if TRACK.load(Ordering::Relaxed) {
        NET[size.min(8192)].fetch_add(delta, Ordering::Relaxed);
    }
}
unsafe impl GlobalAlloc for Counter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(l) }; if !p.is_null() { track(l.size(), 1); } p
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc_zeroed(l) }; if !p.is_null() { track(l.size(), 1); } p
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        track(l.size(), -1); unsafe { System.dealloc(p, l) };
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let result = unsafe { System.realloc(p, l, n) };
        if !result.is_null() { track(l.size(), -1); track(n, 1); } result
    }
}
#[global_allocator]
static ALLOCATOR: Counter = Counter;

fn main() {
    let input = StructArray::from(vec![
        (Arc::new(Field::new("distance", DataType::Float64, false)),
         Arc::new(Float64Array::from(vec![1.0])) as ArrayRef),
        (Arc::new(Field::new("hops", DataType::Int64, false)),
         Arc::new(Int64Array::from(vec![2])) as ArrayRef),
        (Arc::new(Field::new("parent", DataType::Int64, false)),
         Arc::new(Int64Array::from(vec![-3])) as ArrayRef),
    ]);
    TRACK.store(true, Ordering::Relaxed);
    let copy = StructArray::from(copy_array_data(&input.to_data()));
    TRACK.store(false, Ordering::Relaxed);
    let net: Vec<_> = NET.iter().enumerate().filter_map(|(size, n)| {
        let count = n.load(Ordering::Relaxed); (count != 0).then_some((size, count))
    }).collect();
    let child_data = copy_array_data(&input.to_data()).into_parts().5;
    println!("{}", serde_json::json!({"retained_allocations_size_count":net,
        "requested_retained_bytes":net.iter().map(|(s,n)|*s as isize*n).sum::<isize>(),
        "arrow_reported_array_size":copy.get_array_memory_size(),
        "sizeof_struct_array":size_of::<StructArray>(),
        "sizeof_mutable_array_data":size_of::<MutableArrayData>(),
        "copied_child_array_data_len":child_data.len(),
        "copied_child_array_data_capacity":child_data.capacity(),
        "boundary":"single owned copy, excluding input and stack StructArray; System allocator requested sizes"}));
    assert_eq!(copy,input);
}
