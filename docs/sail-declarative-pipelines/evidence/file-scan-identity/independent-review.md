# File scan identity transport review

Reviewed Sail base `db8844172d2b6b70095796987bcff613f2ad62aa` and pinned
DataFusion 55.2.0. Root selected same-revision Sail driver/workers; this unit
makes no mixed-version enforcement promise. No builds were run by this reviewer.

## Findings and selected placement

DataFusion's `PartitionedFile` proto has no ETag/version fields
(`datafusion-proto-models-55.2.0/proto/datafusion.proto:1584`). Its conversion
explicitly creates `ObjectMeta { e_tag: None, version: None }`
(`datafusion-datasource-55.2.0/src/proto.rs:96`). The loss therefore occurs in
general file-scan transport and should be fixed in Sail's execution codec.

`encode_remote_physical_plan` wraps every `DataSourceExec` with
`RemoteDataSourceExec` (`crates/sail-execution/src/proto/encode.rs:34`). The
extension codec already handles JSON, CSV, Parquet, Arrow, Avro, text and binary
leaf sources individually (`crates/sail-execution/src/proto/codec.rs:2456` at
the reviewed base). It unwraps checkpoint sources before serializing them.

The selected optional `ExtendedPhysicalPlanNode.file_scan_identity` field
(tag 67, outside the node oneof) supplements the existing opaque DataFusion
payload. Its nested group/file vectors preserve occurrence order. Each file
entry carries exact location plus optional ETag and version strings. `None`,
`Some("")` and nonempty values must remain distinct; transport does not decide
which values qualify as usable immutable identities.

Restoring the sidecar immediately after DataFusion's common config parser and
before each format builds final properties is the smallest safe placement.
A post-plan rewrite with `DataSourceExec::with_data_source` would recompute
properties and could erase checkpoint partitioning
(`datafusion-datasource-55.2.0/src/source.rs:651`). The helper instead preserves
the existing decode order and restores only the two omitted metadata fields.

`InputFileMetadata` is a different concept: SQL file name/start/length
(`crates/sail-common-datafusion/src/input_file.rs:140`). Its codec unwraps the
file source into a recursively encoded projection + inner remote scan, then
reconstructs the wrapper (`codec.rs:2150,2472` at base). Attach identity to the
inner leaf only, and reject a sidecar on the outer wrapper. This avoids duplicate
or conflicting restoration without changing SQL metadata behavior.

## Required validation and compatibility limits

- Require exact group counts, exact per-group file counts, and exact location at
  every occurrence. Do not use a map keyed only by path: duplicate paths can have
  different ranges or object versions.
- Reject sidecars on non-file nodes and on the outer input-file metadata wrapper,
  including an otherwise empty sidecar. A zero-group sidecar on a zero-group
  leaf scan is valid. An absent sidecar preserves legacy decoding behavior.
- Keep the original object-store URL, ranges, sizes, timestamps, partition
  values, projections, statistics and execution properties unchanged.
- The sidecar is additive protobuf transport. Old workers ignore its unknown
  field and may lose identity silently; same-revision compatibility is the
  selected deployment assumption. Carrying identity does not itself enforce a
  conditional read in every existing file format.
- Positional/path checks detect structural misassociation, not authenticity of
  an ETag/version or arbitrary swapping of same-path occurrences. Immutable-read
  validation remains the actual object reader's responsibility.

## Tests authored

Only `crates/sail-execution/src/proto/codec/file_scan_identity_tests.rs` was
authored by this reviewer. It covers all seven full remote scan roundtrips;
all optional-string states; duplicate paths, groups, ranges, partitions,
projection and limit; empty groups; malformed group/file counts and location;
non-file/outer-wrapper rejection; input-file wrapper preservation; checkpoint
hash partitioning; and actual decoded JSON execution using a registered in-memory
object store. The legacy control first asserts a nonempty original ETag/version,
then removes the sidecar and demonstrates that DataFusion loses both fields.

The implementation author independently reviewed these tests and formatted the
four intended identity-unit files with the repository's nightly formatter. Root
owns registration, build gates and commits. No ORC format registration is part
of this transport unit.
