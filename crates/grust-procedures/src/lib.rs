//! Parser-independent procedure registration and execution contracts.
//!
//! A registry owns immutable definitions and providers together. An invocation
//! validates arguments before opening its provider and validates each output
//! batch. Providers must reserve memory before allocation and poll the shared
//! execution context during computation. Untrusted native plugins are outside
//! this cooperative contract.

mod builtins;
mod cache;
mod catalog;
pub use cache::{CachedPreparation, InvocationCache};
mod error;
mod registry;
mod resources;
mod signature;
mod snapshot;
pub use snapshot::{LocalSnapshot, SnapshotIdentity};

pub use builtins::register_builtins;
pub use error::{ProcedureError, Result};
pub use registry::{
    Invocation, ProcedureBatch, ProcedureCursor, ProcedureProvider, ProcedureRegistry,
    RegistryBuilder, ResolvedProcedure, ValidatedArguments,
};
pub use resources::{
    Accounting, Cancellation, ChildLimits, ExecutionContext, ExecutionLimits, Interruption,
    MemoryAccount, MemoryReservation, ResourceUsage, WORK_BLOCK_UNITS, WorkAccounting, WorkCount,
    WorkMeter,
};
pub use signature::{
    Argument, Correlation, Determinism, Field, GraphRequirement, OptionField, ProcedureDefinition,
    ProcedureMode, Streaming, ValueType,
};
