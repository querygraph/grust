//! Immutable typed graph analytics, independent of Cypher and Arrow.
//!
//! Projections own topology and identity mappings, retain memory reservations,
//! and share a query execution context with kernels and result consumers.
//! Parallel edges retain their original edge ordinal even without an edge ID.

#[cfg(feature = "arrow")]
mod arrow_input;
#[cfg(feature = "arrow")]
mod arrow_output;
#[cfg(feature = "arrow")]
pub use arrow_output::{ArrowResultBatch, ArrowResultCursor};
mod bellman_ford;
pub use bellman_ford::{BellmanFord, bellman_ford};
mod astar;
pub use astar::{AStarPath, astar, astar_haversine, haversine_requests};
mod betweenness;
pub use betweenness::{Betweenness, BetweennessOptions, betweenness};
mod biconnected;
pub use biconnected::{Biconnectivity, biconnectivity};
mod buffer;
mod closeness;
mod community_quality;
pub use closeness::{ClosenessOptions, DistanceCentrality, HarmonicOptions, closeness, harmonic};
pub use community_quality::{CommunityQuality, community_quality};
mod degree;
pub use degree::{Degrees, degree};
mod fastrp;
pub use fastrp::{FastRp, FastRpOptions, fast_rp};
mod flow;
mod graph_input;
pub use flow::{MaxFlow, max_flow};
mod kcore;
mod label_propagation;
pub use label_propagation::{LabelPropagation, LabelPropagationOptions, label_propagation};
mod leiden;
pub use leiden::{Leiden, LeidenOptions, leiden};
mod louvain;
pub use kcore::{KCore, k_core};
pub use louvain::{Louvain, LouvainOptions, louvain};
mod ordering;
mod parallel;
pub use ordering::{NodeOrder, TopologicalOrder, depth_first, topological_sort};
mod pagerank;
mod properties;
#[cfg(feature = "arrow")]
mod properties_arrow;
pub use properties::{
    Categories, MissingProperty, NodeProperties, PropertyKind, PropertyRequest, Vectors,
};
mod projection;
mod random;
mod shortest;
mod similarity;
mod statistics;
pub use similarity::{NodeSimilarity, NodeSimilarityOptions, SimilarityMetric, node_similarity};
mod spanning;
pub use spanning::{SpanningForest, SpanningObjective, SpanningTreeOptions, spanning_tree};
mod spectral;
pub use spectral::{IteratedScores, IterationOptions, KatzOptions, eigenvector, hits, katz};
mod table;
mod triangles;
pub use statistics::{CsrEstimate, ProjectionStatistics};
pub use table::{NodeTable, TableScalar, TableType, TableValue};
pub use triangles::{TriangleOptions, Triangles, triangles};
mod traversal;

pub use pagerank::{PageRank, PageRankOptions, pagerank};

pub use shortest::{PathCursor, PathView, ShortestPaths, dijkstra, shortest_paths};

pub use traversal::{
    Components, Distances, bfs, multi_source_bfs, strongly_connected_components,
    weakly_connected_components,
};

pub use graph_input::{MissingWeight, ProjectionOptions, WeightSelection};
pub use grust_procedures::{
    Accounting, ExecutionContext, ExecutionLimits, Interruption, ProcedureError as AlgorithmError,
    Result, WorkAccounting, WorkCount,
};
pub use projection::{
    GraphProjection, Orientation, ProjectionEdge, ProjectionRepresentation, ProjectionSelection,
    SnapshotIdentity,
};
