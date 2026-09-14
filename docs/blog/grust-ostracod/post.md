# Grust Ostracod: shared admission and cancellation for Arrow graph pipelines

Grust gives Rust applications one property-graph model across memory, embedded databases, SQL systems and remote graph services. Graph identities, typed values and reusable algorithms remain backend-neutral, while adapters expose their actual capabilities. Ostracod 0.18.0 extends this architecture with shared query-lifetime control and native Arrow input admission for the existing Rust, Cypher and DataFusion surfaces.

## One execution lifetime

The shared `ExecutionContext` now offers runtime-independent cancellation notifications. Every live waiter is notified, dropped waiters unregister, and callbacks run outside the resource lock. DataFusion can apply the same context to a future or an entire Arrow result stream. SQL execution, explicit Cypher result collection and the blocking Arrow reader used for ADBC ingestion retain cancellation and the original absolute deadline through consumption.

Controlled streams pass batches through without buffer copies, queues or extra worker tasks. Completion or the first error releases the owned upstream stream; subsequent polls stay finished. Dropping one consumer does not implicitly cancel sibling work. Providers and kernels must still cooperate during synchronous computation: these controls do not preempt a long individual poll.

## Admission without a row graph

`PreparedReadRequest` centralizes bounded Cypher validation, immutable parameter admission, graph/index size checks and output checks. It owns the validated AST and policy, keeps the original deadline, and retains any application registry generation. The bounded reference executor now uses these same checks. Oversized parameters fail before graph inspection, and indexed input checks reuse the exact serialized size of their immutable snapshot.

Native Arrow 55, 58 and 59 tables now expose a borrowed serialization view matching Grust's graph representation. Property-presence markers preserve missing values separately from explicit nulls; identities, scalar tags, property ordering, escaped strings and parallel relationships survive. Serialization builds per-batch column descriptors, not graph rows, property maps or copied string values. A bounded counting writer measures exact JSON bytes without keeping a JSON buffer.

DataFusion snapshot capture can apply that input policy before creating its providers, then retain the exact measured size. Snapshots also expose constant-time row counts, original batch counts and the logical payload added for relationship ordinals. Unmeasured serialized size remains explicitly unknown, including for empty graphs. These facts are inputs for future routing; they do not guess selectivity, join size or total memory.

## What this release establishes

The changes make admission and cancellation composable across shared Arrow pipelines while preserving separate error and unsupported outcomes. They do not claim automatic Cypher-to-DataFusion selection or complete mapping of candidate-work and intermediate-allocation budgets. Backend snapshot authority, pre-existing input storage and additional ordinal allocation also remain explicit obligations. Specialized graph algorithms continue through their existing kernels and procedure registry.

Qualification retains source-pinned tests, warnings-denied Rust checks, exact serialization comparisons across all three Arrow majors, and the complete release archive/registry evidence. Existing benchmark pins remain unchanged. The earlier scan and fixed-path profiles retain their conversion costs and execution boundaries; neither those profiles nor this release establishes a universal routing threshold or a backend performance result.

Read the [repository documentation](https://github.com/querygraph/grust), [Arrow architecture](https://github.com/querygraph/grust/blob/main/docs/arrow-pipelines.md), [release evidence](https://github.com/querygraph/grust/tree/main/docs/releases/ostracod), and the [Grust book](https://firstpair.org/book/grust) for the public surface and its qualified boundaries.
