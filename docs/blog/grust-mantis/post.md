# Grust Mantis: owned write lifetimes and admitted Arrow results

Grust gives Rust applications one property-graph API across memory, embedded databases, SQL systems and remote graph services. Shared identities, typed values and algorithm kernels let applications compose these backends while keeping each adapter's capabilities explicit. Mantis 0.19.0 strengthens that foundation with cancellation-safe write batching and admission before portable Arrow results allocate owned values.

## Durable writes with explicit ownership

The LanceDB adapter groups concurrent single-row writes through clones of one store into universal-table commits. Queued rows sharing a key retain the last value in queue order. Leadership travels in an owned handoff message, so cancelling a receiver before its next poll cannot strand the queue. Cancelled waiters are skipped iteratively, without holding the queue mutex across channel callbacks.

A caller whose leader is cancelled during a commit receives an explicit uncertain-durability error. The write may already have reached storage; Grust does not convert that uncertainty into a success or replay it silently. Universal tables and typed mirrors remain separate commits, so batching does not imply an atomic multi-table transaction.

Bulk graph and shared Arrow loads maintain merge-key indexes after compaction. Periodic maintenance combines fragments from smaller writes, and writes release retained read snapshots. Connection cache limits bound the index and metadata caches separately; they are not process-memory limits. These changes preserve the native shared Arrow ingestion path rather than introducing another storage representation.

## Admit copies before making them

The DataFusion bridge can now charge a shared execution context before converting Arrow results to portable Cypher rows. Its logical copy count uses the actual batch slice, including column names, row/value containers and non-null UTF-8 byte lengths. Unsupported types fail before row allocation. Cumulative charges remain consumed after a table is dropped, preserving the distinction between copied data and live retained memory.

Controlled result collection applies the same admission while retaining cancellation, deadlines, row limits and exact serialized-output limits. The explicit controlled Cypher entrypoint uses this collector. Native Arrow and ADBC consumers can continue retaining columnar batches and avoid portable row conversion.

## Qualification and remaining work

Deterministic queue tests cover cancellation before handoff polling, already-waiting successors, abandoned in-flight batches, apply failures, invalid keys and long cancelled queues. The original reproduced failure and corrected receipts are retained. Result-admission tests cover exact byte boundaries, slices, null and empty strings, cumulative reuse and cancellation. Full release gates and archive evidence are tracked separately from these component checks.

Mantis does not establish automatic Cypher-to-DataFusion routing or full operator-level candidate-work and intermediate-allocation accounting. Existing benchmark pins remain unchanged. Performance comparisons require disclosed datasets, execution classes, indexing and conversion costs, resource envelopes and retained failure outcomes; passing correctness tests alone supplies no throughput claim.

See the [repository documentation](https://github.com/querygraph/grust), [Arrow architecture](https://github.com/querygraph/grust/blob/main/docs/arrow-pipelines.md), [Mantis release evidence](https://github.com/querygraph/grust/tree/main/docs/releases/mantis), and the [Grust book](https://firstpair.org/book/grust) for the interfaces and qualification boundaries.
