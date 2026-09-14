//! Native Arrow 58 graph tables, batch readers, and IPC pipelines.
#![allow(
    clippy::duplicate_mod,
    reason = "the same implementation is instantiated against distinct native Arrow major-version types"
)]
use arrow_array_58 as array;
use arrow_ipc_58 as ipc;
use arrow_schema_58 as schema;

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

#[path = "graph_serialization.rs"]
mod graph_serialization;

use arrow_buffer_58 as buffer;
#[path = "buffer_owner.rs"]
mod buffer_owner;
pub use buffer_owner::retain_buffer_owner;

use arrow_data_58 as data;
#[path = "array_owner.rs"]
mod array_owner;
pub use array_owner::retain_array_owner;
