# Grust Brine: admission follows Arrow data

Grust gives Rust applications a shared property-graph API across memory, embedded databases, SQL systems and remote graph services. Typed identities, graph algorithms and optional Arrow pipelines compose across these adapters while capabilities remain explicit. Brine 0.20.0 strengthens this foundation by keeping execution reservations attached to the data that consumes them.

## Shared ownership across Arrow pipelines

The shared Arrow layer can attach an application token to an immutable buffer using safe Bytes ownership. Buffer clones, slices and C Data exports retain that token without copying payload bytes. The same mechanism works across native Arrow 55, 58 and 59 interfaces, preserving the foundation used by Arrow and ADBC consumers.

Array ownership extends through validity buffers and nested children. Metadata is rebuilt and validated; payload bytes remain shared. Algorithm results use this mechanism so retaining a raw batch or child array also retains the original memory reservation after the result wrapper is dropped. Cloning an array does not charge the reservation again.

The boundary is explicit: previously created clones do not acquire the new owner, and arrays with no physical buffers require a wrapper when metadata lifetime must be admitted. Retained payload accounting does not measure allocator capacity or process memory. Metadata validation has a cost, which requires measurement before any throughput claim.

## Admit snapshot construction before allocation

The DataFusion bridge adds controlled snapshot capture that reserves relationship-ordinal payload and charges construction work before allocating. Reservations follow the physical buffers through providers and retained results. Cancellation and work-limit failures release incomplete capture state.

Combined input-policy capture checks exact serialized input size and preserves the prepared request's original deadline. Caller-owned input buffers, schema metadata and backend authority remain separate concerns. These controls compose with existing cancellation and portable-result admission; they do not establish complete operator-level accounting.

## Turso under strain

Alongside the release, the Turso adapter was rebuilt for concurrent load and measured with the adversarial-graph strain harness on SNAP graphs up to 117 million edges. This work lives on the `turso-mvcc-concurrency` branch (pull request #6) and is not part of the 0.20.0 crates; the numbers below are that branch against Turso 0.7.2, the pinned engine.

MVCC loads previously ran one transaction over the whole graph, at about 1,500 edges per second. They now run over several writer connections under `BEGIN CONCURRENT`, advancing in rounds so a checkpoint can run between rounds: four writers load GAP-road at 27,700 edges per second where one writer managed 2,900, with peak memory down from 15 GB to under 7 GB at web-Google scale. A store that must be filled fastest fills through WAL and switches to MVCC afterwards, at WAL speed, 1.5 to 3 times the parallel MVCC load depending on the engine.

Loads run with foreign keys off on every path, so WAL, single-writer and parallel loads store the same graph and accept dangling edges as the Memory reference does; incremental writes keep their strictness. That alone lifted WAL loads by about 60%. Concurrent single-statement writes can share one durable commit: sixteen writers attaching 200 edges each to one node take 3.2 seconds instead of 21, all 3,200 accepted, with `synchronous = FULL` throughout.

On one non-burstable host, the MVCC store loads com-Orkut at 16,000 edges per second against Neo4j's 16,800 and WAL's 24,700, accepts every concurrent hot-node write where WAL accepts 61 of 3,200, and traverses faster than Neo4j on every graph; Neo4j is three to five times leaner in memory. Upstream Turso `main` (the coming 0.8) loads WAL 22% faster and serves reads 4 to 24% faster, but its MVCC bulk loads are 15 to 26% slower, in the index-key comparison, which upstream pull request #8385 addresses; on 0.8 the engine's own group commit replaces the client-side one.

The book chapter "Turso under strain" carries the measurements, the methodology (alternating pairs with CPU steal recorded, because burstable hosts throttle silently), and the recommended configuration per engine version.

## Qualification and the automatic execution goal

Regression coverage includes sliced and nullable arrays, nested children, empty buffers, C Data export lifetime, raw algorithm results, exact admission boundaries and capture failure cleanup. Release qualification records workspace tests, package verification and registry evidence separately from focused tests.

Automatic Cypher-to-DataFusion routing remains active work. It requires preserved language and resource-policy contracts, qualified provider and operator behavior, and end-to-end cost evidence including preparation. Existing benchmark pins remain unchanged; correctness qualification supplies no performance comparison by itself.

See the [repository documentation](https://github.com/querygraph/grust), [Turso concurrency pull request](https://github.com/querygraph/grust/pull/6), [strain results](https://adversari.al/graph/strain/), [Arrow architecture](https://github.com/querygraph/grust/blob/main/docs/arrow-pipelines.md), [automatic execution goal](https://github.com/querygraph/grust/blob/main/docs/goals/cypher-datafusion-execution.md), and the [Grust book](https://firstpair.org/book/grust).
