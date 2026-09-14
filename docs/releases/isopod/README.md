# Isopod 0.17.0 release preparation

Status: preparing qualification; not yet published or delivered.

This lockstep release packages explicit Arrow/DataFusion Cypher execution and
exact portable Int64 ordering. Automatic routing and the broader engineering goal
remain active. The pending `lancedb-write-memory` branch is deliberately excluded:
its cancellation defect is reproduced in the retained review, and no corrected
handoff has arrived. Existing strain benchmark pins remain unchanged.

Pre-release evidence includes the 6c2bc0b workspace gate (1,597 passed, zero
failed, 49 ignored, workspace Clippy passed), subsequent focused compiler/facade
checks, and pinned scan/path profiles. These are not substitutes for qualification
of the final 0.17.0 source and crate archives.

Remaining release gates: final-source workspace build/tests/Clippy/rustdoc,
workspace packaging and attribution, appropriate integration checks, rebuilt
book and provenance-stamped TextPack, dependency-ordered publication, registry
verification, release tag and FirstPair delivery. DataFusion now has an optional
Cypher dependency, so publish `grust-cypher` before `grust-datafusion`.
