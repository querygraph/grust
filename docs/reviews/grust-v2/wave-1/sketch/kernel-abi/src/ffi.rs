//! The C ABI. A host in another language, or another Rust build, calls
//! [`grust_kernel_run`] with an exported CSR and a [`GrustHostV1`], and receives
//! an exported record batch.
//!
//! Ownership, in Arrow C data interface terms:
//!
//! | Struct | Producer | Consumer | `release` called by |
//! |---|---|---|---|
//! | input `ArrowArray` (the CSR) | host | kernel | kernel, exactly once, before `grust_kernel_run` returns |
//! | input `ArrowSchema` | host | kernel, borrowed | host |
//! | output `ArrowArray` (the batch) | kernel | host | host, exactly once, whenever it is done |
//! | output `ArrowSchema` | kernel | host | host |
//! | error string | kernel | host | host, with [`grust_error_free`] |
//!
//! The kernel moves the input struct out of the host's memory and marks the
//! host's copy released (`release == NULL`), as the C data interface asks of a
//! consumer that takes ownership. The host must not call `release` on it again.

use std::ffi::{c_char, c_void, CStr, CString};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::Arc;

use arrow_array::ffi::{from_ffi, to_ffi, FFI_ArrowArray, FFI_ArrowSchema};
use arrow_array::{Array, LargeListArray, StructArray};

use crate::kernels::{OutDegree, Wcc};
use crate::{BudgetExceeded, Csr, Host, Kernel, KernelError};

/// The host, as C sees it. Version 1. All callbacks are thread-safe and stay
/// valid until every output batch received from the kernel has been released.
#[repr(C)]
pub struct GrustHostV1 {
    pub ctx: *mut c_void,
    /// 0 admits `bytes`; anything else refuses.
    pub reserve: extern "C" fn(ctx: *mut c_void, bytes: u64) -> i32,
    pub release: extern "C" fn(ctx: *mut c_void, bytes: u64),
    /// Non-zero asks the kernel to stop.
    pub cancelled: extern "C" fn(ctx: *mut c_void) -> i32,
    pub max_threads: u32,
}

/// The C host behind the Rust [`Host`] trait. It holds a copy of the struct,
/// so the C side may free its struct after the call; `ctx` must live on (rule 4).
struct CHost(GrustHostV1);

// SAFETY: the C contract requires the callbacks and `ctx` to be thread-safe.
unsafe impl Send for CHost {}
unsafe impl Sync for CHost {}

impl Host for CHost {
    fn reserve(&self, bytes: u64) -> Result<(), BudgetExceeded> {
        match (self.0.reserve)(self.0.ctx, bytes) {
            0 => Ok(()),
            _ => Err(BudgetExceeded { requested: bytes }),
        }
    }
    fn release(&self, bytes: u64) {
        (self.0.release)(self.0.ctx, bytes)
    }
    fn is_cancelled(&self) -> bool {
        (self.0.cancelled)(self.0.ctx) != 0
    }
    fn max_threads(&self) -> usize {
        self.0.max_threads.max(1) as usize
    }
}

pub const GRUST_OK: i32 = 0;
pub const GRUST_INVALID_INPUT: i32 = 1;
pub const GRUST_BUDGET_EXCEEDED: i32 = 2;
pub const GRUST_CANCELLED: i32 = 3;
pub const GRUST_PANICKED: i32 = 4;
pub const GRUST_UNKNOWN_KERNEL: i32 = 5;

fn kernel_named(name: &str) -> Option<Box<dyn Kernel>> {
    match name {
        "out_degree" => Some(Box::new(OutDegree)),
        "wcc" => Some(Box::new(Wcc)),
        _ => None,
    }
}

fn fail(error: *mut *mut c_char, code: i32, message: String) -> i32 {
    if !error.is_null() {
        let text = CString::new(message.replace('\0', " ")).unwrap_or_default();
        // SAFETY: the caller passed a writable pointer for the error string.
        unsafe { *error = text.into_raw() };
    }
    code
}

/// Run kernel `name` on the CSR in `input`.
///
/// On success, writes the result batch to `output` and `output_schema` and
/// returns [`GRUST_OK`]. On failure, returns a code and, if `error` is not
/// null, a message the host frees with [`grust_error_free`]. Either way, the
/// input has been released by the time this returns.
///
/// # Safety
/// `input` is a valid, unreleased `ArrowArray` of type `LargeList<UInt32>`
/// described by `input_schema`; `host` is valid; `output` and `output_schema`
/// point to writable, uninitialised structs; `name` is a NUL-terminated string.
#[no_mangle]
pub unsafe extern "C" fn grust_kernel_run(
    name: *const c_char,
    input: *mut FFI_ArrowArray,
    input_schema: *const FFI_ArrowSchema,
    host: *const GrustHostV1,
    output: *mut FFI_ArrowArray,
    output_schema: *mut FFI_ArrowSchema,
    error: *mut *mut c_char,
) -> i32 {
    // Rule 1: take ownership of the input now, so that every return path below
    // releases it exactly once (by dropping `data`).
    let input = FFI_ArrowArray::from_raw(input);
    let host: Arc<dyn Host> = Arc::new(CHost(std::ptr::read(host)));
    let name = CStr::from_ptr(name).to_string_lossy().into_owned();
    let result = catch_unwind(AssertUnwindSafe(
        || -> Result<StructArray, (i32, String)> {
            let kernel =
                kernel_named(&name).ok_or((GRUST_UNKNOWN_KERNEL, format!("no kernel {name}")))?;
            let data = from_ffi(input, &*input_schema)
                .map_err(|e| (GRUST_INVALID_INPUT, e.to_string()))?;
            let list = LargeListArray::from(data);
            let csr = Csr::from_list(&list).map_err(|e| (GRUST_INVALID_INPUT, format!("{e:?}")))?;
            let batch = kernel.run(csr, &host).map_err(|e| match e {
                KernelError::Budget(b) => (
                    GRUST_BUDGET_EXCEEDED,
                    format!("budget refused {} bytes", b.requested),
                ),
                KernelError::Cancelled => (GRUST_CANCELLED, "cancelled".into()),
                KernelError::InvalidInput(m) => (GRUST_INVALID_INPUT, m),
                KernelError::Panicked(m) => (GRUST_PANICKED, m),
            })?;
            Ok(StructArray::from(batch))
            // `list` drops here: the host's release callback for the input runs.
        },
    ));
    match result {
        Ok(Ok(batch)) => match to_ffi(&batch.to_data()) {
            Ok((array, schema)) => {
                // Rule 2: the host now owns the batch and releases it.
                std::ptr::write(output, array);
                std::ptr::write(output_schema, schema);
                GRUST_OK
            }
            Err(e) => fail(error, GRUST_INVALID_INPUT, e.to_string()),
        },
        Ok(Err((code, message))) => fail(error, code, message),
        Err(panic) => {
            let message = panic
                .downcast_ref::<String>()
                .cloned()
                .or_else(|| panic.downcast_ref::<&str>().map(|s| s.to_string()))
                .unwrap_or_else(|| "kernel panicked".into());
            fail(error, GRUST_PANICKED, message)
        }
    }
}

/// Free an error string returned by [`grust_kernel_run`].
///
/// # Safety
/// `error` is null or a string returned by this library, freed at most once.
#[no_mangle]
pub unsafe extern "C" fn grust_error_free(error: *mut c_char) {
    if !error.is_null() {
        drop(CString::from_raw(error));
    }
}
