# Complete Delta Add metadata decoding

The private decoder preserves Delta's file-addition metadata for future manifest capture. It is implemented locally; immutable qualification passed. It has no production reader caller and does not yet expose a replayable source.

Ordinary scan reconstruction supplies enough metadata to open files, but can replace values with scan defaults. A retained control demonstrates that it loses `dataChange=false`. The new decoder borrows an Arrow action batch and produces one owned Add at a time. It preserves all known fields, null map values and empty optional values, decodes paths once, and rejects missing required values, wrong known types, duplicate names/map keys and malformed deletion-vector structures.

A null action is distinct from a malformed non-null action. Original commit provenance remains unknown; snapshot membership and row-tracking integers must not be relabelled as original commit evidence.

Thirteen independent decoder fixtures, all 410 Delta package tests, and 2,195 workspace tests passed. One inherited workspace test remains skipped. The first control run stopped at a fixture-column error; that run is preserved separately from the corrected semantic failure.

Fresh public checks contain 2,120 Delta passes, two failures, 42 expected failures and 21 node skips, plus a separately skipped concurrency module. Native checks passed 17 tests and streaming public checks passed 51. All 48 fresh candidate batch executions passed. Exact retained baselines supply the other comparison sides through verified artifact and test-inventory identity; literal differences remain explicit. The final runtime audit resolves every changed node and collection-location record without changing raw reasons.

This decoder introduces no query execution path or new benchmark claim. Its variable-width copies, map allocations and borrowed input lifetime require admission and memory funding before capture integration. Prior measured scan costs remain documented in the sorted-replay evidence.

Raw JSON structural uniqueness, checkpoint normalization, table-level row tracking, source identity, bounded discovery, manifest publication, target fencing and recovery remain separate requirements. Component tests do not establish those integrated guarantees. The [qualification record](qualification.json) pins the exact committed source, receipts and rebuilt artifacts. Both rebuilt artifact hashes match the bytes used in the fresh public checks. The source remains local and unpushed.

The [design plan](../../DELTA-ADD-PAYLOAD.md) preceded implementation. This evidence is optional supporting material for the [review decision memo](../../REDESIGN-REVIEW-PACKET.md).
