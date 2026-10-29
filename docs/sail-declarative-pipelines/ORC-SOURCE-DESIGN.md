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

Use the patched native metadata API: read once with
`read_metadata_async_with_options`, retain validated `FileMetadata::column_types()`
and construct readers with `ArrowReaderBuilder::new_with_metadata`. Sail's
`OrcMetadata` wrapper should retain the physical metadata, pinned object identity
and validation policy; no second protobuf footer parser is needed. The
[bounded-API receipt](evidence/orc-metadata-options/provenance.json) qualifies
checked tail ranges, iterative type-tree validation, aggregate encoded/decoded
metadata budgets and schema-depth limits in both reader modes.

The initial tail read remains at most16KiB; the encoded limit is checked before
any second read. Footer and metadata share one decoded budget, passed into
internal block allocations. These are byte/depth bounds, not a total heap bound:
protobuf objects, codec history, allocator capacity, retained metadata and stripes
still need Sail resource accounting. Cache reuse must verify object-store and
version/ETag identity plus the applicable validation policy; size/mtime alone is
insufficient. Existing unrestricted constructors remain compatible, so Sail must
choose the bounded entry points. The probe's4MiB/depth64 settings are evidence
parameters, not adopted production limits. No bounded remote reader is implemented
yet; production resource exhaustion must be reported explicitly.

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


## Dependency implementation update

The [source-bound receipts](evidence/orc-dependency-hardening/provenance.json)
record three local commits in `orc-rust-sdp`, based on upstream v0.9.0:

| Commit | Review scope | Default test result |
| --- | --- | --- |
| `d12c9608c6` | Align Arrow test dependencies with library 59 | 253 passed; 8 upstream ignored |
| `b6bede0ef4` | Frame checks, typed Read failures, all five codec output bounds | 261 passed; 8 upstream ignored |
| `8338ce9062` | Shared checked sync/async footer ranges and exact read lengths | 266 passed; 8 upstream ignored |

Formatting and strict all-target/all-feature Clippy pass for the two code units.
No-default-feature library runs pass 159/163 tests. Three external PyORC writer
checks, ignored by default, were explicitly executed and passed at the final
head; the five other pre-existing ignored integration cases remain unqualified.
The retained malformed compression-block input now returns a typed error in both
reader modes. Eight reads of Spark files and three Spark reads of new Rust writer
outputs pass. Range/projection replay remains green. These are library results;
Sail's production source registry and four recorded ORC failures are unchanged.

The LZO decoder now uses the bounded pure-Rust `lzokay` 2.0.1 slice API. Its
predecessor's expected-size argument was only a capacity hint. The change also
changes the source type in the public BuildLzoDecoder error variant. No lower
Rust-version/MSRV or cross-platform claim follows from the Rust 1.98.1 macOS gate.

The metadata contract listed at this checkpoint is implemented in the following
three commits. Historical raw logs and the earlier source audit remain retained.

## Bounded metadata APIs and portable Sail dependency

The [new receipt](evidence/orc-metadata-options/provenance.json) records:

| Commit | Scope | Default / no-default library tests |
| --- | --- | --- |
| `9cc3c85595` | Total decoded budget across blocks, including empty and uncompressed input | 271 /168 passed |
| `4e8e80c842` | Iterative kind/arity/ownership/reachability/depth validation before recursive schema construction | 281 /178 passed |
| `91910faa90` | Encoded and combined decoded tail limits, raw attributes and metadata-reusing sync/async builders | 286 /182 passed |

All three pass formatting and strict Clippy. Default runs still contain eight
upstream ignored cases; no fresh external PyORC runs are claimed. New regressions
cover exact/over/zero budgets, all five block codecs, a10000-level raw tree,
malformed trees, combined footer/metadata accounting, depth limits, attribute
preservation and avoiding a second metadata read. Eight bounded reads of the
retained Spark files reproduce their exact native rows; both malformed-fixture
reads return errors. This does not yet adapt native physical types to Spark types.

Sail `4c5d5861d8` vendors the gated package with its license, source
hashes and all six local dependency revisions. It excludes the vendor crate from
workspace membership and declares an unused workspace dependency with defaults
disabled and async support enabled. Cargo.lock and the linked runtime are unchanged.
The vendor gate compares source bytes and package contents, verifies manifests and
preserves upstream README whitespace verbatim; its initial formatting failure is
retained. This resolves portability without claiming published upstream patches.

Next: consume that dependency in a separate metadata/schema bridge, then add the
object-store reader, FileSource/worker codec/registration and writer units. The
four current Sail ORC baseline failures and all SDP acceptance counts remain open.
TIME precision needs special care: Spark4.2.1 accepts0–6 and stores microseconds;
Sail's existing TIME parser accepts0/3/6/9. Preserve precision semantics through a
shared type improvement rather than silently reporting unsupported precisions as6.
General catalog semantics remain in Sail, with LakeCat provider coverage separate.
