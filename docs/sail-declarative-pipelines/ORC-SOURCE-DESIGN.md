# Shared ORC source design

Recorded: 2026-10-29T18:53:25.850561+00:00. Sail baseline `8d044db38`; Spark 4.2.1 source
`617618396`. This resolves the announced [file-source checkpoint](FILE-SOURCE-DESIGN-HANDOFF.md)
into implementation contracts. The [evidence package](evidence/orc-source-design/provenance.json)
contains source pins, compiled dependency probes, generated files and actual
failures. Production ORC support is still unimplemented.

## Required behavior and ownership

Spark `SqlPipelineSuite:434` writes `RANGE(3)` with `.format("orc").mode("overwrite")`,
loads a normal table through CTAS from that directory, then checks both a direct
batch materialized view and a streaming table over the CTAS table. Each must
contain exactly rows 0, 1 and 2. The pinned default compression is **ZSTD**; the
CTAS has no USING clause and defaults to Parquet. The source explicitly excludes
direct SQL streaming-file reads. Therefore this work needs a shared ORC reader
and writer; the fixture's final streaming-table assertion remains part of the
later generic streaming runner. Passing the batch half cannot qualify the whole
registration.

All format semantics belong in Sail's shared source path. SQL format/path reads,
DataFrame reads/writes, CTAS, catalog table scans and pipeline reads must use the
same implementation. LakeCat needs no ORC-specific API or query evaluator. No
reusable ORC implementation was found in the inspected Grust/LakeCat Rust sources.

## Dependency decision and evidence

Use `orc-rust` 0.9.0 as the integration baseline, with the dependency-hardening
gate below required before production registration. Configure `default-features = false` and explicit
`async`, integrated into Sail's existing Arrow **59.2.0**, DataFusion **55.2.0** and
object_store **0.13.2** graph. Preserve the complete locked Arrow family: pinning
only the umbrella crate allowed the first isolated build to resolve Arrow 59.3.2
subcrates. That initial lock/log is retained; behavioral evidence uses 59.2.0.

The [published crate](https://docs.rs/orc-rust/0.9.0/orc_rust/) supplies native ORC
encoding/decoding and range reads. The published
[DataFusion adapter](https://docs.rs/datafusion-orc/0.10.0/datafusion_orc/) depends
on DataFusion with default features and does not supply our required writer or
Spark logical-type handling. Use the core library directly, with a small Sail
adapter; no C++/Python reader, extra SessionContext or generic storage runtime
is selected. Attribute access requires no fork. The reproduced decoder panic
requires a minimal reviewed dependency fix (upstream release or pinned fix) before
registration; unchanged 0.9.0 is not qualified for production. Record the added prost 0.13 and compression/error
support dependencies in the production lockfile; do not upgrade Sail's existing
prost 0.14 wire types to accommodate ORC's private metadata protobufs.

Executed evidence:

- Spark 4.2.1 wrote ZSTD RANGE, nullable primitive, logical-type and empty fixtures.
  The exact Arrow 59.2 probe decoded all four synchronously and asynchronously.
- The Rust writer produced ZSTD RANGE, nullable multibatch/three-stripe and empty
  files. Spark read all three with exact row equality. Unicode and nulls survived.
- Seven adjacent byte ranges reproduced all rows of the multistripe file exactly
  once in both reader modes. This is a library boundary test, not distributed
  Sail evidence or exhaustive proof of range handling.
- Empty projection preserved row counts. Reordered/duplicate projection requests
  became unique fields in file order; the adapter must restore the requested
  expression order and duplicates.
- Three malformed/truncated inputs returned errors. A fourth, deliberately
  oversized compressed-block payload, **panicked with exit 101** in `split_to`.
  The input and failure are retained; successful basic checks do not qualify
  arbitrary-corruption handling.
- A footer probe recovered `spark.sql.catalyst.type` through public protobuf and
  decompressor APIs. No fork is needed to obtain attributes discarded by the
  library's simplified schema.

The current Sail CLI still fails all four baseline operations: ORC writing,
reading a Spark ORC file, CTAS from it and direct batch pipeline materialization.
Those [failures](evidence/orc-source-design/sail-baseline.json) remain explicit.
No production capability or acceptance count is changed by library-level success.

## Metadata and Spark types

The native Arrow schema is an intermediate physical representation. The paired
logical-type fixture demonstrates why: Spark's TIMESTAMP_NTZ becomes raw Int64,
and TIMESTAMP becomes Timestamp(Nanosecond,None). Exposing either unchanged would
lose Spark's logical type or interpret it incorrectly in Sail.

Add an `OrcMetadata` helper containing native file metadata plus raw ORC type
records/attributes. Recover the raw footer using public `PostScript`/`Footer` types and a checked
compression boundary before invoking native metadata construction. The local
prototype proves attribute access, but its native-reader-first ordering does not
prove production bounds. The pinned parser performs unchecked length arithmetic
and unbounded decompression; validate offsets, integer conversions, compression
block framing, decoded-size budgets and type-tree references first, on cached
bytes from the same immutable/version-pinned object. Budget the decoder's internal
scratch allocation as well as output buffers: wrapping the outer reader in `take`
does not bound a block decoder that allocates first. Reuse/harden the library's
parser instead of adding a second ORC format implementation in Sail. The narrow
dependency patch must cover both metadata and stripe decompression callers, with
retained malformed-file regressions. No bounded remote reader is implemented yet.
The prototype's4MiB cap is only a probe limit; do not silently turn it into a
Spark compatibility limit. Production metadata allocations must participate in
Sail's resource contract and report resource exhaustion explicitly.

Derive the Spark-facing schema recursively from physical types and recognized
Spark attributes. Preserve nullability, decimals, structs, lists and maps. Normalize
ORC timestamps to Spark microseconds with explicit LTZ/NTZ handling, including
negative epochs, writer timezones and nested leaves. A LONG annotated as
`timestamp_ntz` must become timestamp-without-zone, while ordinary LONG remains
BIGINT. Unknown or inconsistent Spark logical annotations must produce a useful
unsupported/invalid-schema error rather than silently becoming an integer.
Interval/TIME annotations need their corresponding Sail logical representations
before those cases can pass. Do not use a blanket nanoseconds cast as evidence
of timezone or historical-calendar parity.

Separate the physical read schema from the output schema. Decode using supported
native types, then adapt arrays using the shared schema/expression machinery.
Do not force a physical integer decoder to construct timestamp arrays merely by
replacing an Arrow field type. Add paired tests for annotations, nested leaves,
nulls, precision and incompatible explicit schemas.

Spark default `mergeSchema=false` chooses the first usable schema; true merges.
Do not silently inherit an unconditional all-file merge. Respect names and the
shared case-sensitivity setting; positional Hive evolution is a distinct option.
Missing requested fields must become nulls where Spark permits them. Hidden file
filtering, path discovery, partition extraction and catalog resolution remain in
the existing listing layer, with any missing generic behavior fixed there.

## Reader and execution boundaries

Implement `formats/orc` under `sail-data-source` with `OrcFormatFactory`,
`OrcReadFormat`, `OrcSource` and `OrcOpener`. Register through `sail-session`'s
normal `DataSourceRegistry`. Keep the decoder dependency local to the source
crate; the execution crate uses exported adapter types and serialized options.

`ReadFormat::infer_schema` uses footer metadata; it must not download entire
remote objects. `scan` constructs the existing `FileScanConfig`, retaining file
groups, partition schema/values, projection, limit, ordering and statistics.
Use unknown statistics when unavailable; do not invent pruning guarantees.
Predicates remain residual until exact pushed semantics are tested.

The opener reads through Sail's configured object store and a bounded
`AsyncChunkReader`. Bind reads to the listed object/version when supported; detect
changes rather than combining one footer with another body's contents. Preserve
cancellation and I/O failures. File/stripe size remains distinct from output
batch size: a small batch does not bound stripe decompression memory. Use existing
memory accounting and execution controls for decoded buffers and file concurrency.

The selected range contract assigns an ORC stripe to the half-open byte range
containing its start offset. Supply the assigned range to the native reader and
verify complete/disjoint ownership in FileSource tests before enabling physical
repartitioning. If an intermediate implementation scans complete files, explicitly
disable repartitioning; never inherit the default while ignoring ranges.

Projection has two stages: select a unique physical column set, then restore the
logical output with Sail/DataFusion projection and schema adaptation. Include
partition-only and zero-column COUNT scans; duplicate/reordered fields and computed
projections must not depend on library mask ordering. Apply limits and partition
values through the existing file-stream semantics.

Add source encode/decode alongside the adapter in
`sail-execution/proto/sail/plan/physical.proto` and `proto/codec.rs`. Use existing
RemoteDataSourceExec and FileScanConfig task preparation. Codec roundtrip tests
must execute reconstructed scans, including more than one file group, to catch
worker duplication. Do not treat a local CLI query as worker-serialization proof.

## Writer and commit behavior

Implement a real `WriteFormat`/file sink using a stateful per-output-file
`ArrowWriter`, not the Avro wrapper (whose underlying writer is unsupported at
this pin) or Text's stateless batch serializer. ORC has one footer per file;
concatenating independent per-batch ORC byte buffers is invalid.

Reuse listing write planning, partition demultiplexing, object-store uploads and
Sail's overwrite/delete/barrier path. Retain an explicit abort-capable upload
handle: DataFusion 55.2's ObjectWriterBuilder discards AbortableWrite and documents
that it does not clean up failures. Its reuse alone cannot fulfill this contract. Stream bounded encoded chunks to the upload
through a worker-owned writer; do not buffer the whole final object or block an
async executor with encoding. Finalize footer and upload completion before
reporting the file committed. On error/cancellation, abort unfinished uploads and
propagate the original cause through existing JobService handling. Cancellation,
empty files, multiple batches and overwrite/append need direct tests.

The dependency's writer panics for unsupported schemas such as decimal/nested
columns. Validate its supported type tree before opening an output and return a
typed error until each missing encoder is implemented. This is an incremental
failure boundary, not a redefinition of general ORC parity. Timestamp NTZ writing
also needs Spark-compatible physical encoding and attributes; emitting an ordinary
ORC TIMESTAMP would read back as LTZ. Keep failing cross-engine cases for those
extensions. The primitive BIGINT/nullable-string/bool path is experimentally
supported; reader support does not imply equivalent writer support.

Default internal compression is ZSTD. Option precedence is `compression`, then
`orc.compress`, then session `spark.sql.orc.compression.codec`. ORC compression
must not use an outer gzip-style stream wrapper. Add generated ORC option models
through Sail's existing YAML/options build machinery. Validate codecs and options;
never silently ignore an option that changes schema or values. All writer options
and sink configuration need worker codec coverage alongside source serialization.

## Human-reviewable implementation units

1. **Dependency hardening, then metadata/type bridge in separate commits.**
   First make malformed compression blocks and invalid footer ranges return typed
   errors and bound decompression allocations; replay the retained fourth failure.
   Then add the dependency/lockfile, bounded object-store
   chunk reader, raw footer attributes and Spark schema mapping. Use paired files
   and malformed/empty controls; do not register a partially wired source yet.
2. **Read adapter and worker codec.** Wire FileSource, scan projection/schema/range
   semantics, source protobuf and registry. Enable the existing required ORC batch
   test unchanged. Add SQL/DataFrame/CTAS and reconstructed-worker assertions.
3. **Stateful writer and sink codec.** Add generated compression options,
   preflight schema checks, footer/upload lifecycle and cancellation tests. Verify
   default-ZSTD files both ways with Spark and preserve unsupported-type failures.
4. **Broader type/option parity.** Extend timestamp, decimal/nested writer and
   evolution/partition behavior against the retained general-source matrix.
5. **Complete SDP fixture.** Retain writer→CTAS→MV and streaming-table assertions.
   The final table-backed streaming step waits for the already planned generic
   streaming implementation; it requires no ORC-specific streaming scheduler.

Each unit uses immutable detached source gates and its own applicable Rust,
codec and Spark 4.2.1 checks. Do not rerun unrelated expensive suites to manufacture
coverage, and do not count dependency experiments as SDP assertion ports. The
canonical inventory remains 462 registrations, 97 audited and 59 partial ports.
The next implementation step is the dependency-hardening part of unit 1; later streaming state/fencing and CDC
coordination remain announced design checkpoints of their own.
