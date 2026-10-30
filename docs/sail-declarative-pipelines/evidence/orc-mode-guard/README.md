# ORC unsupported read-mode guard

Sail `c01623c184bdf8f688e9153a263283694cd39a2b` checks unsupported modes in
OrcListingReadOptions::resolve. The exact session implementation must be native;
Hive and invalid choices receive explicit errors. Effective forced positional
evolution is unsupported. A false table/read override may disable a true session
flag. Automatic legacy all-_col mapping remains unchanged.

Separate immutable mode snapshots capture exact session keys. Operation
spark.sql.orc.impl does not select the provider; only the forced flag receives
read/table overrides. Connect refreshes both defaults and modes under one state
write guard after successful or partially failing updates, retaining the original
error and prior snapshots. Physical resource options and worker wire are unchanged.
Eight new tests cover mode selection, precedence, boolean syntax, exact session
keys, creation/set/unset, snapshots and partial-update ordering.

The [pinned Spark 4.2.1 source and installed ORC bytecode audit](read-mode-reference/README.md)
qualifies default V1 option-key handling: operation keys are case-insensitive,
while session keys remain exact. V2 uses a different case-sensitive Hadoop handoff;
V2 option-case parity is not claimed. Java Boolean.parseBoolean semantics apply to
the forced flag. No fresh Spark mode runtime, broker or service probe was run.
Hadoop startup configuration and variable substitution remain outside this unit.

Exact detached formatting, strict Clippy, 210 data-source tests and 70 Connect
tests pass. The [frozen implementation handoff](implementation/HANDOFF.md) predates
those parent-run gates and is preserved unchanged. The [independent source review](source-review.md)
found no blocker. A [root preparation-wrapper error](preparation-note.json) occurred
before any candidate or Rust gate and required only a script manifest-key fix;
there was no failed B2 Rust gate or source change for that error.

This is library-level qualification of the mode guard. Hive and explicit forced
positional evolution are rejected, not implemented. Public ORC registration,
writer support and complete SDP runtime acceptance are not qualified by this
checkpoint. Candidate, gate, logs, patch, source copies and reference files are
covered by the exact [packet provenance](provenance.json).
