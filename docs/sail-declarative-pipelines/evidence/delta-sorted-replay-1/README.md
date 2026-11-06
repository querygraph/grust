# Sorted Delta replay: release consumed payloads

**Status: local, unpushed implementation. Immutable-commit qualification passed.**

Formatting, strict workspace Clippy and Rustdoc passed on the frozen source.

Sorted Delta replay reconstructs active files from their Add and Remove actions. Previously, it retained one-row Arrow slices until it accumulated roughly 8,192 winners. A few useful rows could therefore keep many large input buffers alive. This affected ordinary Delta reads and would also undermine bounded manifest capture.

The repair emits winners from each input batch and retains only the last owned key across batches. Existing file-identity reconciliation and declared output schemas remain intact; output batch boundaries and availability can change. [Design rationale](../../DELTA-SORTED-REPLAY.md).

The resource guarantee is narrow: replay holds no private payload references across input pulls and reserves its owned key contents and top-level row-selector allocation before growth. Finite pools can reject unfunded allocations. Returned Arrow buffers can remain shared with consumers; kernel scratch, upstream sorting/decoding and downstream ownership have separate responsibilities. This is not a whole-query memory bound.

## Correctness and regression evidence

The original implementation failed the retained-allocation control: **0 passed, 1 failed, 384 filtered**. The producer and consumer released their references before the next input request, isolating replay's retention. The repaired control passes within the workspace run. Lifecycle checks cover EOF, cancellation, child errors and reservation failure; Arrow checks compare exact values, types and nested metadata under changed batch layouts, including zero-column output.

- **Workspace:** 2,182 passed; one inherited ignored type-coercion test remains unexecuted.
- **Final batch matrix:** 96/96 executions passed across parent/candidate and batch sizes 1, 7 and 8,192, including eager, Sort, Hash and deletion-vector identity controls.
- **Full comparison:** 6,759 node executions across upstream, parent and candidate—not 6,759 distinct tests. Six comparisons found no introduced correctness or functionality regression.

| Artifact | External Delta: 2,185 nodes | Native: 17 nodes | Prior public: 51 nodes |
| --- | --- | --- | --- |
| Upstream | 2,120 pass; 2 fail; 42 xfail; 21 skip | 17 pass | 40 pass; 11 fail |
| Parent | 2,120 pass; 2 fail; 42 xfail; 21 skip | 17 pass | 51 pass |
| Candidate | 2,120 pass; 2 fail; 42 xfail; 21 skip | 17 pass | 51 pass |

Each external run also retains the concurrency-module collection skip. The two failures stop at JVM-created file-layout assertions before Sail row checks. Seventeen external skips pass in the native selection; four nested-field evolution skips remain uncovered. Literal nonpassing reasons and their reviewed differences remain recorded. This is not an all-tests-pass or JVM Spark parity claim. [Comparison details](REGRESSION.md).

## Performance tradeoff

Release replay took less time in every measured paired block, while downstream development-build scans retained costs: **5.17% slower** for sparse history at batch size 256, with all three blocks slower; **3.96% slower** median for dense history at batch size 8,192. The performance review accepts these scoped costs for removing unfunded retention; no coalescer was added.

Measurements used paired runs on shared Darwin arm64 hardware with unavailable CPU-steal data. Wide-payload operator timings varied substantially. These are comparative observations, not production throughput guarantees or stable speedup estimates. [Profiles, all ratios and limitations](PERFORMANCE.md).

## Revision and remaining qualification

| Identity | Value |
| --- | --- |
| Commit | `d72803efdb3ee1660b1f002d851139649b3d68c6` |
| Tree | `5181d08ac4b48dca578ea046a0313f572507e30a` |
| Parent | `3f741daad57df4bcc22cecfb7802d458b1ad1d06` |
| Upstream comparison base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Final immutable qualification receipt/hash | [Pinned receipt and artifact hashes](qualification.json) |
| Immutable artifact status and hashes | [Pinned receipt and artifact hashes](qualification.json) |

The committed revision passed the full workspace rerun, mechanical checks and artifact rebuild. Both rebuilt artifact hashes match the bytes used in the public and performance checks. This repair supplies no complete Add manifest, durable position, continuous replay reader, target fencing or source-to-table recovery; the full SDP/Extensions replacement remains incomplete.
