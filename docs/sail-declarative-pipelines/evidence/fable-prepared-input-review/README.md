# Prepared input and bounded-plan review checkpoint

[Prepared-input findings](prepared-review.md) review Sail6620ee940.
[Bounded-plan review](unit4-review.md) answers and reviews the exact
[Grust88e48c03 draft](unit4-draft.md). Neither unit is integrated.

The observed schema-digest defect was reproduced by executing the same
SHA-256(Debug(schema)) expression with Arrow59.2/sha2.11 on Rust1.98.1. Two
SchemaRefs compare equal but produce different digests because their identical
metadata HashMaps have different debug iteration orders. Sources, Cargo lock,
build output and both raw debug encodings/digests are retained. The probe searches
for an observed pair; it is not a deterministic production regression test and
is not a full execution of the prepared component. The future corrected test
should assert stable canonical digests across all equivalent representations.

The manifest identity/receipt/completion verification and case-sensitive key
lookup findings are source-derived schedules, not newly executed component
counterexamples. ArrowIPC's metadata_to_fb already sorts metadata keys; this
review does not attribute the Debug defect to IPC metadata encoding. That
existing canonical metadata path is a reuse candidate.

The unit4 draft needs read-mode-aware local/external binding, empty-intent
handling, qualified incremental join/UDF semantics and a real semantic evaluation
snapshot. It must use the existing preparation owner/context before planning I/O,
return plans without effects, and require codec qualification before distributed
admission. A pure helper/plan gate is not a full streaming/CDC runtime verdict.

`provenance.json` records source and dependency hashes and hashes every other
packet file. No Fable worktree or offered history was modified.
