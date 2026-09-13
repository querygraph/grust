# Compact snapshots and multigraph persistence

Acorn also changes how the Memory backend stores and exposes graph data. Node IDs
and labels are interned as 32-bit handles. Each edge has one compact record, with
32-bit adjacency slots; optional edge IDs and properties live separately. Public
reads retain their established node-ID and edge-key order. These are storage
choices behind the same property-graph API.

`MemoryGraphStore::indexed_snapshot()` shares immutable store storage rather than
copying every node and edge into a second graph. The index owns its slot ordering
and adjacency. A write copies the store only while an external snapshot still
holds the previous storage; older snapshots remain unchanged.

`GraphSnapshotSource` provides immutable slot access for `TypedGraphIndex`.
`TypedGraphIndex::from_source` accepts a source whose answers remain stable for its
lifetime; `TypedGraphIndex::new(Arc<Graph>)` remains available. Node and edge
accessors may construct one element on demand. Calling `graph()` explicitly
materializes and caches a full Graph when the source does not already own one.

Ordinary indexed Cypher reads traverse that source in place, preserving candidate
order, result/error behavior and budget checks. Registered local-snapshot
procedures still require a Graph; CALL can therefore materialize the source.
Lean indexed MATCH execution does not imply zero-copy algorithm projection.
Callers continue to own admission of retained input snapshots and this explicit
materialization boundary.

Turso now preserves parallel edges by endpoint, label and optional edge identity.
Re-putting one identity updates that edge; an absent ID and an empty ID are distinct.
Bootstrap migrates the previous edge-key layout transactionally, retaining stored
IDs so subsequent updates address the same migrated edges. PostgreSQL keeps its
existing schema through the SQL dialect hook's default behavior.

Turso MVCC bulk loads commit groups of 20 SQL batches. Earlier committed groups
remain if a later group fails: MVCC `put_graph` is no longer an all-or-nothing load.
WAL mode retains its whole-load transaction. This changes the bulk-load boundary,
not the transaction contract of `apply_mutations` or explicit mutation scripts.
