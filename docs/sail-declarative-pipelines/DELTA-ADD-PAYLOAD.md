# Preserve complete Delta file metadata before manifest capture

A replayable source needs a saved description of each admitted input file. An ordinary scan needs only enough metadata to read it. These contracts differ: reconstructing an Add action with `dataChange=true`, replacing missing size with zero, or dropping a null partition value changes the saved description. An Add is Delta's file-addition record.

Build a capture-specific path on Sail's existing Arrow action schema and sorted replay. Preserve every meaningful Add field under the admitted Delta protocol, and keep snapshot membership separate from original commit provenance. This plan adds one focused prerequisite at a time; durable manifest capture remains the intended result.

## Existing components and alternatives

Sail already defines the complete known Add schema, including partition values, statistics, tags, deletion vectors and row-tracking fields. Sorted replay can carry arbitrary payload columns while selecting surviving actions. The read descriptor fixes table interpretation and a starting boundary.

The ordinary metadata projection narrows those fields and its decoder defaults values for scanning. Checkpoint normalization can add missing fields, cast values and reconstruct statistics. Fixed-schema JSON decoding can discard unknown fields and overwrite duplicate known struct keys. Validation after those operations cannot recover discarded evidence.

Extending the ordinary scan decoder would mix its permissive contract with capture's strict one. A separate reconciliation engine would duplicate existing ordering and identity rules. Prefer a small strict decoder first, followed by capture projection and reader admission using existing replay. This keeps ordinary reads stable and gives each boundary a direct test.

## First implementation: strict borrowed Add decoding

Add a crate-private decoder borrowing an Arrow `StructArray`. Construct it once per batch, then decode one row at a time into an owned existing `Add`. A null action returns no Add. An invalid row index or malformed non-null action returns an error. This introduces no physical node, storage I/O or collection of the active-file set.

Accept the existing action field names and exact Arrow types. Required fields must exist and non-null action rows must supply non-null path, partition map, size, modification time and `dataChange`. Refuse negative size, wrong types for recognized optional fields, and the malformed map or deletion-vector structures specified below. Preserve row-tracking integers; validating their table-level semantics requires capture admission. Preserve false `dataChange`, all partition/tag entries, statistics, row IDs and clustering information. Missing optional fields and null optional values mean semantic absence; present empty strings and maps remain distinct.

Reject duplicate schema names and duplicate or null map keys before conversion to a Rust map. Preserve a missing partition key separately from a present null value. This decoder does not infer partition coverage from arbitrary columns; capture admission must establish its descriptor-specific requirements.

Input paths are URI-encoded action paths. Decode exactly once using Sail's existing path utility. Do not decode the resulting Add again, resolve path aliases or collapse distinct replay keys. Validate deletion-vector descriptor structure: known storage type, nonnegative size, cardinality and optional offset, with no offset for inline storage. Preserve an absent offset. This checks neither external vector bytes nor bitmap contents and advertises no reader support for active vectors. Snapshot capture will separately refuse active vectors under its initial admission contract.

The decoder never invents original commit metadata. Its Add auxiliary commit fields remain unknown. The future entry wrapper supplies explicit `SnapshotAsOf(V)` membership and independently established original provenance. A checkpoint at version 20 does not establish that a surviving file was originally added at version 20.

## What this boundary proves

Independent expected entries cover every field, false flags, empty versus absent optionals, null map values, encoded percent signs, invalid types, duplicate keys, slicing and null action rows. Controls must demonstrate the ordinary scan reconstruction cannot satisfy the complete-entry oracle. Internal Rust tests are appropriate for these directly constructed Arrow inputs; public reader controls follow with integration.

A decoder test cannot establish raw JSON uniqueness, checkpoint coverage, source identity, protocol admission or statistics normalization. Before wiring complete capture, validate action identity before reconciliation and payload before lossy normalization. Admitted protocol/features determine which unknown fields are ignorable; unknown required behavior must fail admission. Parsed statistics require numeric fidelity, including floating-point values, rather than the descriptor parser's integer-only contract.

Next increments must carry the complete struct through replay, bind resolved snapshot inputs and provenance, and qualify raw JSON/checkpoint admission. Bounded discovery, global ordering, page/index limits, publication durability, retention, tail coverage and recovery remain mandatory later contracts. No persisted manifest or continuous reader is claimed by this decoder increment.
