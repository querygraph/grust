//! Actionable failures preserved until the transport boundary.

/// A procedure operation result.
pub type Result<T> = std::result::Result<T, ProcedureError>;

/// Registry, validation, resource, and provider failures.
#[derive(Debug, thiserror::Error)]
#[non_exhaustive]
pub enum ProcedureError {
    /// No definition is registered under this name.
    #[error("unknown procedure: {0}")]
    UnknownProcedure(String),
    /// Canonical name or alias already belongs to a definition.
    #[error("duplicate procedure name or alias: {0}")]
    DuplicateName(String),
    /// Metadata cannot establish a valid signature.
    #[error("invalid procedure definition: {0}")]
    InvalidDefinition(String),
    /// Argument count, type or value is invalid.
    #[error("invalid procedure arguments: {0}")]
    InvalidArguments(String),
    /// The caller supplied a configuration key outside the declared schema.
    #[error("unknown procedure option: {0}")]
    UnknownOption(String),
    /// The requested output does not exist.
    #[error("unknown procedure output: {0}")]
    UnknownOutput(String),
    /// The requested mode, backend or representation has no implementation.
    #[error("unsupported procedure execution: {0}")]
    Unsupported(String),
    /// Invocation policy did not grant this operation.
    #[error("procedure access denied: {0}")]
    Denied(String),
    /// A snapshot or prepared plan no longer matches the execution context.
    #[error("stale procedure execution: {0}")]
    Stale(String),
    /// A resource reservation would exceed the configured envelope.
    #[error("procedure {resource} budget exceeded (limit {limit})")]
    BudgetExceeded {
        /// Resource whose admission failed.
        resource: &'static str,
        /// Configured ceiling, in bytes or work units.
        limit: usize,
    },
    /// Cooperative cancellation was requested.
    #[error("procedure execution cancelled")]
    Cancelled,
    /// The shared deadline expired.
    #[error("procedure execution timed out")]
    DeadlineExceeded,
    /// An allocation failed after budget admission.
    #[error("procedure allocation failed")]
    Allocation(#[from] std::collections::TryReserveError),
    /// Arithmetic overflow or a nonfinite numerical result occurred.
    #[error("procedure numerical failure: {0}")]
    Numerical(String),
    /// A provider violated its declared output schema or batch bound.
    #[error("procedure output contract violated: {0}")]
    OutputContract(String),
    /// A caller polled again after the cursor had already failed.
    #[error("procedure cursor previously failed; partial output is incomplete")]
    CursorFailed,
    /// Provider-specific failure, retaining its original cause.
    #[error("procedure provider failed")]
    Provider(#[source] Box<dyn std::error::Error + Send + Sync>),
    /// Internal resource state was poisoned by an unwinding thread.
    #[error("procedure resource state poisoned")]
    ResourceStatePoisoned,
}
