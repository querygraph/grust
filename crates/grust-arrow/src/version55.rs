//! Native Arrow 55 graph tables, batch readers, and IPC pipelines.
#![allow(
    clippy::duplicate_mod,
    reason = "the same implementation is instantiated against distinct native Arrow major-version types"
)]
use arrow_array_55 as array;
use arrow_ipc_55 as ipc;
use arrow_schema_55 as schema;

#[path = "graph.rs"]
mod graph;
#[path = "pipeline.rs"]
mod pipeline;
pub use graph::ArrowGraph;
pub use pipeline::*;

#[path = "storage.rs"]
mod storage;
pub use storage::*;

#[path = "table.rs"]
mod table;
pub use table::ArrowTable;

#[path = "graph_tables.rs"]
mod graph_tables;
pub use graph_tables::ArrowGraphTables;
