//! Fallible fixed-capacity working buffers with retained admission.

use grust_procedures::{ExecutionContext, MemoryReservation, ProcedureError, Result};

pub(crate) struct Buffer<T> {
    pub(crate) values: Vec<T>,
    _reservation: MemoryReservation,
}

impl<T> Buffer<T> {
    /// Adopt caller-owned input while retaining admission through every internal
    /// transfer. Adapters pass existing Buffers instead of releasing/reacquiring.
    pub(crate) fn adopt(values: Vec<T>, context: &ExecutionContext) -> Result<Self> {
        let bytes = values.capacity().checked_mul(size_of::<T>()).ok_or(
            ProcedureError::BudgetExceeded {
                resource: "memory",
                limit: context.limits().memory_bytes,
            },
        )?;
        Ok(Self {
            values,
            _reservation: context.reserve(bytes)?,
        })
    }

    pub(crate) fn capacity(count: usize, context: &ExecutionContext) -> Result<Self> {
        let bytes = count
            .checked_mul(size_of::<T>())
            .ok_or(ProcedureError::BudgetExceeded {
                resource: "memory",
                limit: context.limits().memory_bytes,
            })?;
        let reservation = context.reserve(bytes)?;
        let mut values = Vec::new();
        values.try_reserve_exact(count)?;
        Ok(Self {
            values,
            _reservation: reservation,
        })
    }

    /// A buffer the caller will fill by index, initialized without charging
    /// work, for kernels that charge the same elements in their own pass.
    ///
    /// [`Self::filled`] charges initialization because its caller does not
    /// otherwise visit the elements. A kernel that writes every element and
    /// charges as it goes would charge twice, which would change what a work
    /// budget means for no change in the work performed.
    pub(crate) fn indexed(count: usize, value: T, context: &ExecutionContext) -> Result<Self>
    where
        T: Clone,
    {
        let mut buffer = Self::capacity(count, context)?;
        context.checkpoint()?;
        buffer.values.resize(count, value);
        Ok(buffer)
    }

    /// As [`Self::indexed`], for elements that cannot be cloned, such as the
    /// atomics a parallel kernel claims entries in.
    pub(crate) fn indexed_with(
        count: usize,
        make: impl FnMut() -> T,
        context: &ExecutionContext,
    ) -> Result<Self> {
        let mut buffer = Self::capacity(count, context)?;
        context.checkpoint()?;
        buffer.values.resize_with(count, make);
        Ok(buffer)
    }

    pub(crate) fn filled(count: usize, value: T, context: &ExecutionContext) -> Result<Self>
    where
        T: Clone,
    {
        let mut buffer = Self::capacity(count, context)?;
        // Initialization is work too; polling in chunks bounds cancellation
        // latency without a lock for every initialized scalar.
        for offset in (0..count).step_by(1024) {
            let end = offset + (count - offset).min(1024);
            context.charge_work(end - offset)?;
            buffer.values.resize(end, value.clone());
        }
        Ok(buffer)
    }
}

impl<T> std::ops::Deref for Buffer<T> {
    type Target = [T];
    fn deref(&self) -> &Self::Target {
        &self.values
    }
}
