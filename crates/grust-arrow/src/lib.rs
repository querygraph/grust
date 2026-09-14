//! Shared Arrow graph interchange and batch pipelines.
//!
//! Version modules use the adapter's native Arrow types. They share one
//! implementation; no IPC round trip or unsafe ABI cast connects local batches.
//! Enable only the versions your application needs. Arrow 59 remains the default.

#[cfg(feature = "arrow-55")]
#[path = "version55.rs"]
pub mod v55;
#[cfg(feature = "arrow-58")]
#[path = "version58.rs"]
pub mod v58;
#[cfg(feature = "arrow-59")]
#[path = "version59.rs"]
pub mod v59;

#[cfg(feature = "arrow-59")]
pub use v59::*;

/// Optional ADBC statement integration using native Arrow 59 readers.
#[cfg(feature = "adbc")]
pub mod adbc;

mod bounded_write;
pub use bounded_write::ByteLimitWriter;
