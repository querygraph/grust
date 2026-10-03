//! The contract, checked through the C ABI with a counting host: what is
//! admitted when, and when the input's release callback runs.

use std::ffi::{c_void, CString};
use std::ptr::NonNull;
use std::sync::atomic::{AtomicBool, AtomicI32, AtomicU64, Ordering};
use std::sync::Arc;

use arrow_array::ffi::{from_ffi, to_ffi, FFI_ArrowArray, FFI_ArrowSchema};
use arrow_array::{Array, ArrayRef, LargeListArray, StructArray, UInt32Array, UInt64Array};
use arrow_buffer::{Buffer, OffsetBuffer, ScalarBuffer};
use arrow_schema::{DataType, Field};
use grust_kernel_abi::ffi::*;

/// A host that counts admitted bytes and refuses beyond a limit.
struct Counter {
    admitted: AtomicU64,
    peak: AtomicU64,
    limit: u64,
    cancel: AtomicI32,
}

extern "C" fn reserve(ctx: *mut c_void, bytes: u64) -> i32 {
    let c = unsafe { &*(ctx as *const Counter) };
    let now = c.admitted.fetch_add(bytes, Ordering::SeqCst) + bytes;
    if now > c.limit {
        c.admitted.fetch_sub(bytes, Ordering::SeqCst);
        return 1;
    }
    c.peak.fetch_max(now, Ordering::SeqCst);
    0
}
extern "C" fn release(ctx: *mut c_void, bytes: u64) {
    let c = unsafe { &*(ctx as *const Counter) };
    c.admitted.fetch_sub(bytes, Ordering::SeqCst);
}
extern "C" fn cancelled(ctx: *mut c_void) -> i32 {
    unsafe { &*(ctx as *const Counter) }
        .cancel
        .load(Ordering::SeqCst)
}

fn host(counter: &Counter) -> GrustHostV1 {
    GrustHostV1 {
        ctx: counter as *const Counter as *mut c_void,
        reserve,
        release,
        cancelled,
        max_threads: 4,
    }
}

/// The host's CSR, whose target buffer flips a flag when its last reference
/// goes: that is when the kernel's `release` of the input has run.
fn exported_csr(freed: Arc<AtomicBool>) -> (FFI_ArrowArray, FFI_ArrowSchema) {
    struct Watched(Vec<u32>, Arc<AtomicBool>);
    impl Drop for Watched {
        fn drop(&mut self) {
            self.1.store(true, Ordering::SeqCst);
        }
    }
    // Two components: {0, 1, 2} and {3, 4}; vertex 5 is alone.
    let offsets = vec![0i64, 1, 2, 2, 3, 3, 3];
    let owner = Arc::new(Watched(vec![1u32, 2, 4], freed));
    let ptr = NonNull::new(owner.0.as_ptr() as *mut u8).unwrap();
    let buffer = unsafe { Buffer::from_custom_allocation(ptr, 3 * 4, owner) };
    let targets: ArrayRef = Arc::new(UInt32Array::new(ScalarBuffer::new(buffer, 0, 3), None));
    let field = Arc::new(Field::new("target", DataType::UInt32, false));
    let list = LargeListArray::new(field, OffsetBuffer::new(offsets.into()), targets, None);
    to_ffi(&list.to_data()).unwrap()
}

fn run(
    name: &str,
    counter: &Counter,
    freed: &Arc<AtomicBool>,
) -> Result<StructArray, (i32, String)> {
    let (mut input, schema) = exported_csr(Arc::clone(freed));
    let name = CString::new(name).unwrap();
    let host = host(counter);
    let mut output = FFI_ArrowArray::empty();
    let mut output_schema = FFI_ArrowSchema::empty();
    let mut error = std::ptr::null_mut();
    let code = unsafe {
        grust_kernel_run(
            name.as_ptr(),
            &mut input,
            &schema,
            &host,
            &mut output,
            &mut output_schema,
            &mut error,
        )
    };
    // Rule 1: the kernel consumed the input; the host's copy is marked released.
    assert!(input.is_released());
    if code != GRUST_OK {
        let message = unsafe { std::ffi::CStr::from_ptr(error) }
            .to_string_lossy()
            .into_owned();
        unsafe { grust_error_free(error) };
        return Err((code, message));
    }
    Ok(StructArray::from(
        unsafe { from_ffi(output, &output_schema) }.unwrap(),
    ))
}

#[test]
fn output_bytes_stay_admitted_until_the_host_releases_the_output() {
    let counter = Counter {
        admitted: AtomicU64::new(0),
        peak: AtomicU64::new(0),
        limit: 1 << 20,
        cancel: AtomicI32::new(0),
    };
    let freed = Arc::new(AtomicBool::new(false));
    let batch = run("wcc", &counter, &freed).unwrap();
    // The input was released before the call returned.
    assert!(freed.load(Ordering::SeqCst));
    // Scratch (4 bytes a vertex) was returned; the output (4 bytes a vertex) is still admitted.
    assert_eq!(counter.admitted.load(Ordering::SeqCst), 6 * 4);
    assert_eq!(counter.peak.load(Ordering::SeqCst), 6 * 4 + 6 * 4);
    let component = batch
        .column(0)
        .as_any()
        .downcast_ref::<UInt32Array>()
        .unwrap();
    assert_eq!(component.values().as_ref(), &[0, 0, 0, 3, 3, 5]);
    // Rule 2 and 3: releasing the output returns its reservation.
    drop(batch);
    assert_eq!(counter.admitted.load(Ordering::SeqCst), 0);
}

#[test]
fn a_refused_reservation_fails_cleanly_and_leaks_nothing() {
    // Room for the scratch, not for scratch plus output.
    let counter = Counter {
        admitted: AtomicU64::new(0),
        peak: AtomicU64::new(0),
        limit: 30,
        cancel: AtomicI32::new(0),
    };
    let freed = Arc::new(AtomicBool::new(false));
    let (code, message) = run("wcc", &counter, &freed).unwrap_err();
    assert_eq!(code, GRUST_BUDGET_EXCEEDED, "{message}");
    assert!(
        freed.load(Ordering::SeqCst),
        "the input is released on failure too"
    );
    assert_eq!(
        counter.admitted.load(Ordering::SeqCst),
        0,
        "the scratch was returned"
    );
}

#[test]
fn cancellation_and_unknown_kernels_are_errors_not_panics() {
    let counter = Counter {
        admitted: AtomicU64::new(0),
        peak: AtomicU64::new(0),
        limit: 1 << 20,
        cancel: AtomicI32::new(1),
    };
    let freed = Arc::new(AtomicBool::new(false));
    assert_eq!(run("wcc", &counter, &freed).unwrap_err().0, GRUST_CANCELLED);
    assert_eq!(
        run("no_such_kernel", &counter, &freed).unwrap_err().0,
        GRUST_UNKNOWN_KERNEL
    );
    assert_eq!(counter.admitted.load(Ordering::SeqCst), 0);
}

#[test]
fn out_degree_through_the_abi() {
    let counter = Counter {
        admitted: AtomicU64::new(0),
        peak: AtomicU64::new(0),
        limit: 1 << 20,
        cancel: AtomicI32::new(0),
    };
    let freed = Arc::new(AtomicBool::new(false));
    let batch = run("out_degree", &counter, &freed).unwrap();
    let degree = batch
        .column(0)
        .as_any()
        .downcast_ref::<UInt64Array>()
        .unwrap();
    assert_eq!(degree.values().as_ref(), &[1, 1, 0, 1, 0, 0]);
    assert_eq!(counter.admitted.load(Ordering::SeqCst), 6 * 8);
    drop(batch);
    assert_eq!(counter.admitted.load(Ordering::SeqCst), 0);
}
