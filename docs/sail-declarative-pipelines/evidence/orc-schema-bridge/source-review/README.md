# ORC schema/array review handoff

The source audit records pinned Spark source blobs and Sail schema candidate 7ac8e1fe8; array files are explicitly hashed draft snapshots. No repository files were changed, and no build or Spark runtime probe was performed by this reviewer.

The container annotation discrepancy was corrected in the candidate. Unannotated TIMESTAMP_INSTANT inference is supported by ORC 2.3.0 bytecode and the pinned Spark parser. Primitive annotation failures remain conservative Sail input limits, not a broad Spark-parity claim.

No further schema/array correctness blocker was found. Small reviewable sequence: (1) inferred schema plus dependencies and synthetic contract tests, (2) physical-to-logical positional array bridge and focused array tests, (3) real Spark decoder/bridge fixture qualification. Qualified timezone profiles and native-reader/bridge schema coordination remain a separate integration unit. Public file source activation must additionally implement requested-schema validation/projection, bounded pinned metadata acquisition, range ownership and residual predicate behavior.

See source-audit.json for exact hashes, ranges and remaining activation requirements.
