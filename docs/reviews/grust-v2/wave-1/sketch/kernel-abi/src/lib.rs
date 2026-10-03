//! The memory discipline contract for Grust kernels: CSR in, Arrow out.
//!
//! The contract, in five rules (the design text in `../../kernel-memory/README.md`
//! gives the reasons):
//!
//! 1. **Input is the host's.** The host allocates the CSR, exports it once as an
//!    Arrow `LargeList` array, and hands the kernel the `ArrowArray` struct.
//!    The kernel takes ownership of that struct, reads it without writing, and
//!    calls its `release` exactly once, when it no longer reads any buffer of
//!    it. The buffers live until then; who frees them is the host's affair.
//! 2. **Output is the kernel's.** The kernel allocates its result and exports it
//!    as a struct array (a record batch). The host takes ownership and calls
//!    `release` exactly once. The kernel's buffers live until then.
//! 3. **Every byte the kernel allocates is admitted first.** Before allocating
//!    scratch or output, the kernel asks the host to reserve the bytes. Scratch
//!    reservations end when the kernel returns. Output reservations end when
//!    the host releases the output, not when the kernel returns.
//! 4. **The host outlives the kernel's obligations.** The host's callbacks must
//!    stay valid until every output it received has been released, because
//!    releasing an output returns its reservation through them.
//! 5. **Nothing unwinds across the boundary.** A kernel panic becomes an error
//!    code with a message the host frees with [`ffi::grust_error_free`].
//!
//! The Rust API ([`Kernel`], [`Host`], [`Csr`]) states the same rules in types,
//! for a host that links the kernels directly. [`ffi`] is the C ABI.

use std::panic::{AssertUnwindSafe, RefUnwindSafe};
use std::ptr::NonNull;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use arrow_array::{Array, ArrayRef, LargeListArray, RecordBatch, UInt32Array};
use arrow_buffer::{Buffer, ScalarBuffer};

pub mod ffi;
pub mod kernels;

/// What a kernel needs from whoever runs it. Implemented by the host (Sail's
/// memory pool, a test counter, anything). Grust never implements it.
pub trait Host: Send + Sync {
    /// Admit `bytes` more, or refuse. Called before the kernel allocates them.
    fn reserve(&self, bytes: u64) -> Result<(), BudgetExceeded>;
    /// Return `bytes` admitted earlier.
    fn release(&self, bytes: u64);
    /// Polled by long loops; a `true` makes the kernel stop with [`KernelError::Cancelled`].
    fn is_cancelled(&self) -> bool;
    /// Threads the kernel may use. The kernel never uses more.
    fn max_threads(&self) -> usize;
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BudgetExceeded {
    pub requested: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum KernelError {
    Budget(BudgetExceeded),
    Cancelled,
    InvalidInput(String),
    Panicked(String),
}

impl From<BudgetExceeded> for KernelError {
    fn from(e: BudgetExceeded) -> Self {
        KernelError::Budget(e)
    }
}

/// Bytes admitted from a host, returned when dropped. Each reservation owns
/// its count; nothing is returned twice.
pub struct Reservation {
    host: Arc<dyn Host>,
    bytes: AtomicU64,
}

impl Reservation {
    pub fn new(host: &Arc<dyn Host>, bytes: u64) -> Result<Self, BudgetExceeded> {
        host.reserve(bytes)?;
        Ok(Self {
            host: Arc::clone(host),
            bytes: AtomicU64::new(bytes),
        })
    }
    pub fn bytes(&self) -> u64 {
        self.bytes.load(Ordering::Relaxed)
    }
}

impl Drop for Reservation {
    fn drop(&mut self) {
        let bytes = self.bytes.swap(0, Ordering::Relaxed);
        if bytes > 0 {
            self.host.release(bytes);
        }
    }
}

/// An output allocation that carries its reservation: the bytes stay admitted
/// for as long as any Arrow buffer, local or exported, still points into it.
struct Admitted<T> {
    values: Vec<T>,
    _reservation: AssertUnwindSafe<Reservation>,
}

/// Allocate an output column of `len` values, admitted first, as an Arrow
/// buffer whose reservation ends when the last reference to it is dropped,
/// which for an exported array is the consumer's call to `release`.
pub fn admitted_buffer<T>(
    host: &Arc<dyn Host>,
    len: usize,
    fill: impl FnOnce(&mut [T]) -> Result<(), KernelError>,
) -> Result<ScalarBuffer<T>, KernelError>
where
    T: arrow_buffer::ArrowNativeType + Copy + Default + Send + Sync + RefUnwindSafe + 'static,
{
    let bytes = (len * std::mem::size_of::<T>()) as u64;
    let reservation = Reservation::new(host, bytes)?;
    let mut values = vec![T::default(); len];
    fill(&mut values)?;
    let owner = Arc::new(Admitted {
        values,
        _reservation: AssertUnwindSafe(reservation),
    });
    let ptr = NonNull::new(owner.values.as_ptr() as *mut u8).unwrap_or(NonNull::dangling());
    // SAFETY: `owner` keeps the Vec alive and unmoved for the buffer's lifetime,
    // and the Vec is never written again after this point.
    let buffer = unsafe { Buffer::from_custom_allocation(ptr, bytes as usize, owner) };
    Ok(ScalarBuffer::new(buffer, 0, len))
}

/// Scratch memory for the duration of a kernel call: admitted on creation,
/// returned when dropped, which is before the kernel returns.
pub fn scratch<T: Copy + Default>(
    host: &Arc<dyn Host>,
    len: usize,
) -> Result<(Vec<T>, Reservation), KernelError> {
    let reservation = Reservation::new(host, (len * std::mem::size_of::<T>()) as u64)?;
    Ok((vec![T::default(); len], reservation))
}

/// A borrowed CSR: `n` rows, `offsets[n + 1]`, `targets[m]`, read-only. It is a
/// view of an Arrow `LargeList<UInt32>`, so it never owns or frees anything.
#[derive(Clone, Copy)]
pub struct Csr<'a> {
    pub offsets: &'a [i64],
    pub targets: &'a [u32],
}

impl<'a> Csr<'a> {
    /// View a `LargeList<UInt32>` with no nulls as a CSR.
    pub fn from_list(list: &'a LargeListArray) -> Result<Self, KernelError> {
        if list.null_count() != 0 {
            return Err(KernelError::InvalidInput("a CSR row cannot be null".into()));
        }
        let targets = list
            .values()
            .as_any()
            .downcast_ref::<UInt32Array>()
            .ok_or_else(|| KernelError::InvalidInput("CSR targets must be UInt32".into()))?;
        if targets.null_count() != 0 {
            return Err(KernelError::InvalidInput(
                "a CSR target cannot be null".into(),
            ));
        }
        let offsets = list.value_offsets();
        let csr = Csr {
            offsets,
            targets: targets.values(),
        };
        let n = csr.n() as u64;
        if csr.targets.iter().any(|&t| t as u64 >= n) {
            return Err(KernelError::InvalidInput("a target is outside 0..n".into()));
        }
        Ok(csr)
    }
    pub fn n(&self) -> usize {
        self.offsets.len() - 1
    }
    pub fn m(&self) -> usize {
        (self.offsets[self.n()] - self.offsets[0]) as usize
    }
    pub fn row(&self, v: usize) -> &'a [u32] {
        &self.targets[self.offsets[v] as usize..self.offsets[v + 1] as usize]
    }
}

/// What a kernel will admit, at most, for an input of this shape.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Estimate {
    pub scratch_bytes: u64,
    pub output_bytes: u64,
}

/// A kernel. Pure: CSR in, record batch out, every allocation admitted.
pub trait Kernel: Send + Sync {
    fn name(&self) -> &'static str;
    /// An upper bound on what [`Kernel::run`] will reserve. A host may admit this
    /// up front and refuse to start; the kernel still reserves as it goes.
    fn estimate(&self, n: usize, m: usize) -> Estimate;
    /// Row `i` of the result is dense vertex `i`. No id column.
    fn run(&self, csr: Csr<'_>, host: &Arc<dyn Host>) -> Result<RecordBatch, KernelError>;
}

/// Build a CSR as the host would: a `LargeList<UInt32>` with no nulls.
pub fn csr_list(offsets: Vec<i64>, targets: Vec<u32>) -> LargeListArray {
    use arrow_schema::{DataType, Field};
    let field = Arc::new(Field::new("target", DataType::UInt32, false));
    let values: ArrayRef = Arc::new(UInt32Array::from(targets));
    LargeListArray::new(
        field,
        arrow_buffer::OffsetBuffer::new(offsets.into()),
        values,
        None,
    )
}
