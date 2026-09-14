# Grust Gooseneck: graphs in Arrow pipelines

Grust gives Rust applications a backend-neutral property-graph API. The same node identities, relationships, properties and traversal contracts work with an in-memory store, embedded databases, SQL systems and remote graph services. Each adapter translates that model into its backend's native capabilities. Gooseneck, version 0.15.0, extends that approach to Arrow pipelines, ADBC and optional DataFusion execution without making them requirements for ordinary graph applications.

## Native batches across adapters

LanceDB, Sail and Ladybug already had Arrow capabilities, but their adapters maintained separate batch and IPC code. Gooseneck moves reusable operations into `grust-arrow`: native readers, schema-preserving projection, batch admission, multi-batch IPC and shared graph-storage encoding. The adapters select the Arrow major version their SDK requires. Those version modules share implementation files, so one correction applies across versions without forcing a database SDK upgrade.

A batch reader pulls on demand and slices rows while retaining the original Arrow buffers. `ArrowTable` preserves arbitrary Arrow types, metadata and batch boundaries. `ArrowGraphTables` adds graph identity and endpoint validation across multiple batches. Native graph validation no longer needs to construct property-row maps and a full adjacency index merely to check the input.

LanceDB can merge native reader input while retaining identity and property arrays. Sail stages reader batches through its Spark Connect transport and keeps SQL-specific property normalization at that boundary. Its graph IPC loader now consumes batches without constructing a whole-stream graph. Ladybug exposes native reader registration and result-batch callbacks, while its persisted bulk path continues to use Arrow-backed COPY. The optional QueryGraph Memory Sail adapter shares the IPC implementation while retaining its strict input preflight and resource budgets.

## ADBC composition

The optional ADBC helper accepts a caller-owned statement and a standard Arrow reader. It sets the upstream bulk-ingestion options, binds the reader and returns the driver's affected-row count, including an unknown count. Driver errors keep their ADBC status. Connection ownership, transactions, cancellation and driver capability discovery remain with ADBC.

The optional C Stream export uses Apache Arrow's existing implementation. It transfers reader ownership through the standard release callback without introducing Grust-owned unsafe code. ADBC and Arrow consumers can therefore connect at established interfaces instead of adopting another custom reader abstraction.

## A shared DataFusion 55 foundation

The optional `grust-datafusion` crate supplies a shared DataFusion 55 foundation over native Arrow 59 tables: upstream providers and DataFrames, streaming read-only SQL, explicit working-memory and spill settings, and a caller-driven Arrow/ADBC reader bridge. Validated graph catalogs preserve isolates and parallel edges. Cypher lowering and backend execution selection still require separate semantic and performance qualification; existing SDK engines remain on their compatible versions.

## Costs and guarantees remain visible

A native buffer can be shared only when the representations agree. Spark Connect still requires IPC encoding. Sail's SQL representation can require property normalization. Graph-schema validation and typed mirrors can require values for the current batch. Ladybug registration retains the complete registered table. These costs are explicit parts of each API.

Bulk ingestion also has mutation semantics. Stream loads validate batches and can leave earlier batches committed when a later batch fails. ADBC append does not mean graph upsert, and a byte admission limit is not a process-RSS guarantee. The documentation records these boundaries alongside the APIs.

Gooseneck includes shared conformance tests and reproducible Criterion workloads for native batching, IPC boundaries and graph validation. They measure specific operations, not a universal backend speed claim. The wider loading, algorithm-performance and compatibility work continues with source-pinned, comparable workloads and retained failure evidence.

See the [repository documentation](https://github.com/querygraph/grust), the [Arrow and ADBC architecture](https://github.com/querygraph/grust/blob/main/docs/arrow-pipelines.md), the [algorithm capability inventory](https://github.com/querygraph/grust/blob/main/docs/GENERALIZED_ALGORITHMS.md), and the [Grust book](https://firstpair.org/book/grust) for the contracts and examples.
