# Grust Brine: admission follows Arrow data

Grust gives Rust applications a shared property-graph API across memory, embedded databases, SQL systems and remote graph services. Typed identities, graph algorithms and optional Arrow pipelines compose across these adapters while capabilities remain explicit. Brine 0.20.0 strengthens this foundation by keeping execution reservations attached to the data that consumes them.

## Shared ownership across Arrow pipelines

The shared Arrow layer can attach an application token to an immutable buffer using safe Bytes ownership. Buffer clones, slices and C Data exports retain that token without copying payload bytes. The same mechanism works across native Arrow 55, 58 and 59 interfaces, preserving the foundation used by Arrow and ADBC consumers.

Array ownership extends through validity buffers and nested children. Metadata is rebuilt and validated; payload bytes remain shared. Algorithm results use this mechanism so retaining a raw batch or child array also retains the original memory reservation after the result wrapper is dropped. Cloning an array does not charge the reservation again.

The boundary is explicit: previously created clones do not acquire the new owner, and arrays with no physical buffers require a wrapper when metadata lifetime must be admitted. Retained payload accounting does not measure allocator capacity or process memory. Metadata validation has a cost, which requires measurement before any throughput claim.

## Admit snapshot construction before allocation

The DataFusion bridge adds controlled snapshot capture that reserves relationship-ordinal payload and charges construction work before allocating. Reservations follow the physical buffers through providers and retained results. Cancellation and work-limit failures release incomplete capture state.

Combined input-policy capture checks exact serialized input size and preserves the prepared request's original deadline. Caller-owned input buffers, schema metadata and backend authority remain separate concerns. These controls compose with existing cancellation and portable-result admission; they do not establish complete operator-level accounting.

## Qualification and the automatic execution goal

Regression coverage includes sliced and nullable arrays, nested children, empty buffers, C Data export lifetime, raw algorithm results, exact admission boundaries and capture failure cleanup. Release qualification records workspace tests, package verification and registry evidence separately from focused tests.

Automatic Cypher-to-DataFusion routing remains active work. It requires preserved language and resource-policy contracts, qualified provider and operator behavior, and end-to-end cost evidence including preparation. Existing benchmark pins remain unchanged; correctness qualification supplies no performance comparison by itself.

See the [repository documentation](https://github.com/querygraph/grust), [Arrow architecture](https://github.com/querygraph/grust/blob/main/docs/arrow-pipelines.md), [automatic execution goal](https://github.com/querygraph/grust/blob/main/docs/goals/cypher-datafusion-execution.md), and the [Grust book](https://firstpair.org/book/grust).
