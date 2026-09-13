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
