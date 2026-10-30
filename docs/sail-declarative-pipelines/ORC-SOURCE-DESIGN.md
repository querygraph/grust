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
parameters, not adopted production limits. Sail's separately qualified
`OrcObjectReader` now supplies bounded version/ETag range reads; registered file
source integration and decoded-buffer resource accounting remain incomplete.
Production resource exhaustion must be reported explicitly.

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
Dependency hardening and the isolated object-range reader are now implemented
as recorded below. The schema/array bridge, source and worker codec, registration
and writer remain outstanding; later streaming state/fencing and CDC coordination
remain announced design checkpoints of their own.


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

The subsequent object-range reader consumes the dependency. The schema/array
bridge, FileSource/worker codec/registration and writer remain separate units.
The four current Sail ORC baseline failures and all SDP acceptance counts remain open.
Correction to the preliminary type assumption: Spark 4.2.1 TIME accepts precision
0–6 and stores **nanoseconds**, independently of declared precision. The
[logical-type reference](evidence/orc-logical-types-reference/README.md) retains
the physical values and distinguishes string casts from explicit TIME-to-TIME
casts. Sail's existing TIME parser accepts 0/3/6/9. Preserve the declared precision
through a shared type improvement; mapping it directly to an Arrow storage unit
can discard values that Spark retains.
General catalog semantics remain in Sail, with LakeCat provider coverage separate.

## Sail field metadata and object-range reader

Recorded: 2026-10-29T20:26:20.348575+00:00. The [Sail foundation receipt](evidence/orc-sail-foundation/provenance.json) records two independently gated commits:

| Commit | Scope | Library tests |
| --- | --- | --- |
| `661232601e` | Shared declared TIME precision metadata and nested Connect field output; physical storage remains nanoseconds | common 16, Connect 49 |
| `69ff1a8e31` | Pinned object version/ETag, checked byte ranges, response identity and exact payload bounds | data source 93 |

Both pass formatting and strict all-target/all-feature Clippy. The lock audit retains every existing package version and dependency edge, apart from prost version disambiguation and the new ORC dependency. Eight required packages are added; all Arrow packages stay at 59.2.0. No ORC format is registered yet. The reader requires a usable version or ETag on every nonempty request; it rejects changed identity, invalid ranges, malformed responses and truncated/excess bodies. Its buffer still needs integration with Sail resource accounting.

The [reference archive](evidence/orc-logical-types-reference/README.md) preserves 10 ORC fixtures, 11 cases and all preliminary failures, with 15 pinned source excerpts checked. TIME physical values are nanoseconds even under lower declared precision. Default Spark TIME is gated by `spark.sql.timeType.enabled`; retained year-month Python conversion failures are not passes. Native TIMESTAMP decoding currently yields writer wallclock values, whereas Spark Java ORC uses the reader JVM timezone independently of the SQL session timezone. Relabeling the native naive array as UTC is incorrect. An opt-in native reader-timezone policy must use the original instant and writer zone, preserving DST-fold distinctions; precision truncation is a separate reviewed unit.

Capture the reader timezone once on the driver through Sail's existing `get_system_timezone`, and serialize it with the scan descriptor. Workers must not rediscover a potentially different local timezone. The session timezone remains the logical/display label. Reference timezone and historical-calendar cases must qualify the conversion before it is enabled in the Sail bridge.

The TIME metadata commit is only the outbound field half. [Source inspection](evidence/orc-sail-foundation/remaining-type-boundaries.json) finds that SDP inference round-trips Arrow fields through Connect and back into `spec::Field`; the existing inbound converter rejects precisions 1/2/4/5 and maps 0/3/6 to coarser storage. A shared semantic TIME type, including nested type metadata, typed-null and cast-target handling, needs its own design/implementation unit. SQL/non-null literal parsing and formatting also require value-level qualification. Do not add a pipeline-only repair or claim complete TIME support from these field tests.

Next: finish the timestamp policy and schema/array bridge, then the FileSource and worker codec, registry and stateful writer. Original ORC SQL/DataFrame/CTAS/pipeline failures remain open until those public paths are exercised. The 462-registration inventory and last 277 selected Sail/67 upstream Python runtime receipt are unchanged.

## Checked timestamp precision and the next timezone design checkpoint

Recorded: 2026-10-29T20:31:30.032608+00:00. Native `579c04b3ae` adds opt-in checked fractional truncation while keeping strict precision as the default. The [receipt](evidence/orc-timestamp-precision/provenance.json) records 293 default passes, eight pre-existing ignored cases, 186 no-default library passes, formatting and strict Clippy. New native file reads cover the retained foreign submicrosecond fixture in sync/async modes, negative truncation and microsecond values at years 1 and 9999. The original strict read still errors on precision loss. Sail `4f7a642b71` vendors that exact qualified package; hashes/provenance and 93 data-source library tests pass with unchanged lockfile.

The timestamp timezone implementation remains pending. The [Java conversion probe and design handoff](evidence/orc-timestamp-precision/timezone-design/timestamp-timezone-design-handoff.txt) exposes two distinct compatibility gaps: Java `TimeZone` uses a raw standard offset before 1900 where chrono-tz uses historical local mean time; Java also extrapolates recurring daylight-saving rules after chrono-tz's finite Los Angeles transition table ends in 2099. The retained UTC-to-Los-Angeles examples differ by 7 minutes 2 seconds in years 1/1800, and require summer DST in years 2100/9999. Same-zone identity and a December-only case cannot qualify cross-zone behavior. These are Java utility/source observations, not new Spark file-read passes.

This is the next announced Astra design checkpoint: choose a small portable offset/rule provider with explicit Java compatibility and ruleset provenance, reuse an existing dependency where suitable, and retain early/future/DST-fold/gap reference cases. A temporary date guard has been considered but is not adopted as the completion contract. Preserve full SDP scope; do not replace the missing semantics with a narrower acceptance denominator. The separate shared TIME schema round-trip also needs the semantic-type decision described above.

The shared [TIME decision](TIME-SEMANTICS.md) now has a separately gated semantic type/field/literal unit. Connect activation waits for precision-aware casts, including nested leaves; the ORC bridge must preserve nanoseconds without interpreting declared precision as a request to truncate.

## Qualified opt-in native timezone mechanism

Recorded: 2026-10-29T21:52:18.043642+00:00. Native `ed6e9acf4f` introduces immutable timezone/resolver interfaces and reader-specific writer-zone state; `0653cb2287` adds generated sync/async integration coverage. Sail `a829c91a05` vendors that exact Cargo package with no runtime lockfile change. The [receipt](evidence/orc-timezone-options/provenance.json) retains both native gates, the exact package, source/license hashes and the Sail data-source gate. Final native results are 308 passes/eight existing ignored cases and 193 no-default library passes; Sail data-source has 93 passes. Formatting and strict Clippy pass for each code unit.

The opt-in path uses caller-supplied ORC 2015 epoch and UTC-offset rules, applies the Java two-offset adjustment in checked arithmetic, then narrows under the existing precision policy. Missing/empty writer names inherit the current reader-specific writer zone, initially the reader zone. Only actually started stripes update that state; range starts and wholly skipped stripes are covered. Default native behavior and TIMESTAMP_INSTANT remain unchanged. Arrow display labels are separate from conversion rules; Decimal128 overrides are explicitly rejected in this mode.

Native predicate row-group pruning is disabled under this opt-in path because stored timestamp bounds need not bound converted values. Manual row selection remains supported. Sail must also avoid unsafe file/stripe pruning before the native reader runs; this source integration is not yet activated.

The [portable mechanism proof](evidence/orc-timezone-options/mechanism-proof/TIMEZONE-PROVIDER-MECHANISM-PROOF.md) selects small Java-normalized profiles in the optional Sail ORC adapter, with no JVM or timezone database added to the native dependency. One Los Angeles profile passes 306,041 Java offset comparisons and 22 independently checked boundary conversions, including both microsecond endpoints and year 9999/10000. It uses explicit historical transitions, a 400-year future cycle and a stored Java-parsed 2015 epoch. Name/alias and stripe-inheritance evidence is retained. This proves the one-profile mechanism, not a complete all-zone exporter. Full profile generation/verification, Java-compatible writer-name resolution, worker profile identity and integrated Spark ORC fixture checks remain required.

## Qualified schema and physical-to-logical bridge

Recorded: 2026-10-29T22:21:47.414214+00:00. Four separate Sail units pass detached formatting, strict all-target/all-feature Clippy and complete data-source library gates:

| Unit | Commit | Library tests passed |
| --- | --- | --- |
| orc-schema | `7ac8e1fe84` | 104 |
| orc-arrays | `c61fdec309` | 114 |
| orc-batch-schema-vendor | `28d46b8451` | 114 |
| orc-fixtures | `3eb9ea2630` | 117 |

The [evidence packet](evidence/orc-schema-bridge/provenance.json) retains exact patches, raw gates, the initial formatting failure, source review, and Spark fixture provenance. Schema inference uses the already validated native footer and existing Sail SQL parser. It preserves semantic TIME precision independently of nanosecond storage, interval qualifiers, recursive nullability, LTZ/NTZ distinctions and top-level CHAR/VARCHAR catalog metadata. Spark ignores Catalyst annotations on containers; regression tests include invalid and duplicate annotations at those positions. Missing legacy decimal/character parameters remain explicit unsupported cases. Primitive inconsistent annotations are not claimed to reproduce Spark errors.

The separately gated array bridge preserves structural positions, offsets and validity while translating native encodings. Naive timestamp-to-LTZ relabeling remains rejected until actual timezone conversion is wired. Requested-schema evolution belongs to the later file source. Four exact Spark-written ORC files exercise TIME casts, signed intervals, nested maps/structs/lists and null/empty containers through the native decoder and bridge at batch sizes 1, 2 and 16. Their source SQL, Spark read schemas and observed reference results accompany the small fixtures.

The real-file gate first failed all three new regressions: the native decoder rebuilt nonempty batch schemas from values, making nullability vary by batch and dropping metadata. The retained control prints the actual schema difference. Native `ec6baa4686` preserves the declared schema and adds sync/async tests for null patterns, metadata, projections and non-nullable override errors. Its detached gate passes 312 default tests (8 existing ignored) and 193 no-default library tests. Sail vendors the exact qualified package separately; fixture assertions were not weakened. The earlier fixture compiler failure is also retained.

These are library foundations. FileSource, worker codec, registry, writer and timezone-profile activation are still incomplete. No public ORC or additional SDP test pass is claimed.

## Complete Java profile export for the selected baseline

Recorded: 2026-10-29T22:24:15.099448+00:00. The [profile evidence](evidence/orc-timezone-profiles/README.md) now covers all 631 available names in the selected Oracle Java20.0.2/tzdb2023c baseline: 349 normalized profiles and 36 deduplicated future cycles from 37 recurring rule shapes. The 1,541,175-byte artifact is pinned by SHA-256 `1f90695f80f862138bf1635b8727281eb7b0a76d838513eaf09675cb6ee7212b`.

Exact Java transition evaluators establish the finite recurring boundary set; daily sampling is not used to establish completeness. Public Java checks cover 830,644 offsets, 35,336 actual Java ORC timezone conversions and 315,351 name-resolution cases. An independent integer-only Python evaluator reproduces all retained oracle digests, and two complete generations produce identical output artifacts. The archive gate replays the independent verifier in a temporary directory and checks recorded sources, outputs and profile identities.

The profile explicitly pins `oldmapping=false`, FORMAT locale `en-US`, Gregorian calendar and the stored ORC2015 epoch. Spark4.2.1 alone does not determine those JVM settings. Custom GMT resolution includes seconds and exact case/width rules; unknown names use Java's GMT fallback. The documented query envelope covers every offset lookup required by a representable microsecond result, including the second timezone query. Alternative JVM settings require a separately identified and qualified export.

The [runtime handoff](evidence/orc-timezone-profiles/proposed-runtime/RUNTIME-PROVIDER-HANDOFF.md) separates immutable profile lookup, name/config resolution, native builder/schema coordination and worker identity. Runtime code is being prepared but has no Rust gate or activation verdict in this evidence unit. The native reader still owns writer-name inheritance. Source registration, writer behavior, distributed transport, statistics admission and calendar rebasing remain separate requirements.

## Qualified Rust Java timezone provider

Recorded: 2026-10-29T22:33:20.008706+00:00. Sail `4a258021af` adds the immutable embedded profile loader, exact-name/custom-GMT resolver and `OrcJavaTimeZoneConfig`. The descriptor validates its semantic version and compiled profile identity before constructing native options. Reader-zone rules remain separate from the SQL display timezone; unknown-name GMT fallback is deliberate Java behavior, while identity and numeric-domain errors remain explicit failures.

The [Rust receipt](evidence/orc-java-timezone-runtime/provenance.json) records detached formatting, strict Clippy and all 129 data-source library tests passing. Rust replays all 830,644 retained Java offset cases and 315,351 name cases against their original oracle digests; focused tests cover malformed tables/configuration, interval endpoints, aliases and stored epochs. SHA-256 is a test-only dependency already resolved in the workspace; production uses existing serde/serde_json/std and the native interfaces, with no JVM or new timezone engine.

This unit does not yet configure a native reader or change the bridge's guarded ordinary TIMESTAMP path. The next factory unit must construct the real native builder, apply the precision and timezone options, then use that builder's physical schema. Public source/writer registration and distributed profile-identity transport remain pending.

## Qualified native reader and timestamp bridge activation

Recorded: 2026-10-29T22:44:35.775361+00:00. Sail `07e2c2226b` configures the real native reader with microsecond Truncate and the pinned timezone provider, then pairs its computed physical schema with the validated logical schema. Physical projections are explicit unique file-order ordinals mapped to native ORC type IDs; zero-column scans retain row counts. The old constructor continues to reject unconverted ordinary TIMESTAMP. The returned builder may receive execution controls, but its semantic options must stay fixed: field equality cannot authenticate a replacement same-schema timezone policy.

Sail `db8844172d` separately qualifies three Spark-written files and one ORC-Java-written submicrosecond file. Tests retain Spark's observed negative-epoch behavior, LTZ/NTZ distinctions, floor truncation, nested null/empty containers, slices, selected reader rules, display labels and async decoding. Both units pass detached formatting/strict Clippy and respectively 134/142 complete data-source library tests. [The receipt](evidence/orc-timestamp-activation/provenance.json) preserves exact patches, fixtures and gates.

The [fresh reference reread](evidence/orc-timestamp-activation/spark-reread/README.md) explicitly observes the JVM timezone, FORMAT locale, legacy mapping, runtime and tzdb. All four unchanged files match retained values under an LA reader with both UTC and LA SQL sessions; a separate UTC-reader JVM changes the foreign file's numeric values under both sessions. All ten comparisons pass and both owned JVMs exit normally. This establishes the selected reader contexts without claiming that the older unlogged JVM's ID is retrospectively known. Spark Connect labels its Arrow LTZ output UTC in both sessions; Sail's internal session display labels remain a separate existing representation policy.

The temporal decoder/bridge foundation is now qualified for these cases. FileSource, requested-schema evolution, source registration, worker reconstruction, writer integration, statistics admission and calendar rebasing remain open. The original public ORC and full SDP acceptance requirements are unchanged.

## Shared file-scan identity transport

Recorded: 2026-10-29T22:59:42.877031+00:00. The announced source-integration checkpoint found that locked DataFusion drops ETags and versions in its shared file-scan protobuf. Sail `27ab945aaa` repairs this in the general execution codec: field 67 carries an optional format-neutral supplement, validates group/file/path associations, and restores both optional strings before source-specific settings. Metadata wrappers carry only the inner copy; checkpoint partitioning is retained. This changes no catalog or ORC decoder contract.

[The evidence](evidence/file-scan-identity/README.md) records 163 passing execution library tests, formatting and strict Clippy. All seven existing file-format branches round-trip identities; a reconstructed JSON scan executes. Missing legacy supplements retain old behavior, and old workers can ignore the new field, so this is a same-codec-revision guarantee. Transport preservation is not proof that every reader enforces conditional GET.

The source/opener checkpoint still needs the requested-schema reference behavior and memory-admission contract. Shared inference currently samples ten files per URL, and read case sensitivity does not reach per-file scan construction. Those are distinct listing contracts to address in separately reviewed units. ORC source registration, worker execution, writer and the full SDP acceptance objective remain open.

## Source checkpoint: full requested schema and resource ownership

Recorded: 2026-10-29T23:05:27.986560+00:00. The [source checkpoint](evidence/orc-source-checkpoint/README.md) preserves 29 pinned interface sources and a fresh Spark 4.2.1 reference. Twelve cases under each vectorization setting produce eight successful reads, twelve dedicated ORC timestamp-compatibility errors and four later array/map conversion overflows. Complete results and the initial pre-read harness failure are retained. No Sail runtime pass is added.

The next source must retain the **full supplied data schema separately from the required projection**. Spark checks physical/full-schema timestamp kinds by positional zip before name matching, recursing through STRUCT. The reference confirms that a supplied one-field second-NTZ schema fails while the same column selected after supplying the full schema succeeds; reordering matching mixed timestamp names also fails. Appended missing fields return nulls. This evidence does not justify a stronger all-container rejection rule: array/map cases change both directions together and fail later only on this tested fixture.

Shared listing changes must carry the existing case-sensitivity input and provide all-file enumeration for `mergeSchema=true`, while preserving other formats' current behavior. Use existing discovery/filtering rules and the existing worker codec. Resource pools can be bound locally at both source construction sites; pool handles are not transport data. Metadata defaults, stripe/decode allocation admission, reservation lifetimes and cancellation remain explicit choices at this announced checkpoint. No arbitrary production cutoff is selected by these source audits. TIME/interval/integer requested-schema behavior, case ambiguity, Hive evolution and semantic schema merging remain reference work before their implementation claims.

## Requested-schema evolution: reference decisions

Recorded: 2026-10-29T23:25:15.788249+00:00. [Two further Spark reference runs](evidence/orc-schema-evolution-reference/README.md) retain 32 observations: 25 successful evolution/inference reads and three errors, plus four successful nested-name follow-ups. Requested TIME(0)→TIME(3/6) and narrower interval qualifiers preserve stored values; SQL casts remain a distinct operation. Integer narrowing nulls out-of-range values even with ANSI enabled. The ORC adapter must preserve that distinction while reusing shared safe array conversion.

All-file semantic merging sees an eleventh-file field, rejects an eleventh-file TIME precision conflict and an interval-family conflict, and unions qualifiers within one interval family. Matching is also layered: Spark rejects top-level case-insensitive ambiguity, while the tested nested ASCII fields use last-normalized-physical-field wins, including over an earlier exact spelling. Four reordered/name-variant cases distinguish that rule from exact-case preference. Installed ORC 2.3.0 disassembly uses default-locale lowercase; no universal Unicode or loaded-class-origin claim is made. `_col*` fallback is qualified for the two retained Spark-written cases, not all historical Hive variants. Full-schema timestamp checks remain separate and precede projection.

These decisions are source-adapter requirements, not new public Sail passes. Decimal/string conversion, direction-isolated nested timestamp conversion, non-ASCII/locale edge cases, calendar rebasing, and remaining configuration/error cases still need their own reference assertions. Existing source contracts and the complete SDP objective remain unchanged.

## Selected source resource limits and listing foundations

Recorded: 2026-10-29T23:33:24.916037+00:00. [Four Sail units and one native unit](evidence/orc-source-resources/README.md)
are gated and committed. Listing retains case policy and offers opt-in all-file
inference with preserved object identities; its default ten-file selection is
unchanged. Reader-owned encoded range buffers retain local pool reservations
through their final Bytes owner. Native decoded stripe footers accept an
independent optional byte budget; the exact package is vendored in Sail.

The [selected resource contract](evidence/orc-source-resources/RESOURCE-CONTRACT.md)
sets configurable Sail defaults of 64 MiB each for encoded tail, decoded tail and
decoded stripe footer, and schema depth 64 (root STRUCT depth 0). Byte ceilings
are min(configured, finite local pool limit, isize::MAX); Unknown/Infinite pools
retain configured ceilings. Zero is a zero budget. They are operational resource
settings, not Spark schema-validity limits or total-heap guarantees. The encoded
tail limit counts footer+metadata; the initial up-to-16 KiB read can precede its
declared-size check. No lifetime decoded-column-stream or encoded-stripe cap is
introduced. Bind each source to its local execution pool, including worker decode.

Keep one active native stripe per ordinary FileSource/FileOpener stream. Dropping
pending work releases owned ranges/futures; synchronous footer/dictionary/batch
decoding is not preemptible mid-call. Checked stripe/array lengths remain native
follow-ups, and optional row-index/bloom pruning remains disabled initially.
Options, requested-schema adaptation, opener, codec, registration and writer are
subsequent units; these foundation gates add no public ORC/SDP runtime pass.

## Configured resource options and native stripe arithmetic

Recorded: 2026-10-29T23:44:30.182224+00:00. [Evidence](evidence/orc-options-and-stripe-bounds/README.md)
records native `2ecec391db` (checked stripe/stream extents and addressability),
Sail `e9e0fe382` (exact vendor package), and `2c10b2da7` (generated read options
and local resource derivation). The selected 64 MiB/depth 64 defaults now have
checked option/table-property parsing and native metadata/footer helpers.
Transport must carry configured values and rederive limits against each worker's
pool. The native change preserves padding and unselected large streams; physical
object-extent preflight remains part of the upcoming source opener.

Native gates pass 320 tests (eight ignored) and 199 no-default tests; Sail passes
150 then 156 data-source tests with formatting and strict Clippy. One retained
options attempt failed unused_mut; the next retained run passed 154 but failed
two incorrect error-word expectations in new tests. Exact native-message checks
now retain all fixture/budget cases. An operational advance retry is recorded;
all production changes and the final gate remain bound to this exact commit.
Requested-schema mapping, source/worker/registry/writer integration and original
public Spark assertions remain incomplete.

## Preserve malformed PRESENT errors before dependent decoding

Recorded: 2026-10-29T23:56:34.461756+00:00. [Native `bc0c0cef83` and Sail `25524aa551`](evidence/orc-present-errors/README.md)
preserve null-stream decode errors previously discarded by the native adapter.
Real malformed encodings prove primitive DATA remains unread and STRING LENGTH
errors do not mask the earlier PRESENT error, including nested parent validity.
Native gates pass 323 tests (eight ignored), 202 no-default tests; exact vendor
and all 156 Sail data-source tests pass with formatting/strict Clippy.

The retained value-safety handoff leaves signed materialized/skip lengths,
dictionary setup and RLE delta arithmetic as separate units. A separate pinned
merge audit distinguishes existing pipeline semantic merging, outer versus nested
case policy, and requested-reader matching. Source/opener/mapper drafts remain
outside this verdict until their own exact gates; public ORC/SDP runtime remains
unqualified by these dependency changes.

## Duplicate root names and mode-dependent map-key narrowing

Recorded: 2026-10-30T00:04:08.752583+00:00. [Four fresh Spark 4.2.1 observations](evidence/orc-duplicate-key-reference/README.md)
resolve two adapter questions before its first commit. Exact duplicate root names
select the last physical field in case-sensitive mode; case-insensitive mode
retains its duplicate-name error. The mapper must preserve that distinction.

For the retained MAP<BIGINT,STRING> fixture, requested MAP<INT,STRING> and explode
projection, vectorized mode wraps key 2147483648 to -2147483648; non-vectorized mode
fails with a retained nextMap/TreeMap NullPointerException. This does not establish
a general map conversion rule. Do not apply ordinary safe integer null-on-overflow
semantics to map keys. Narrowing keys, nested/sliced/null-parent cases and reader
mode configuration remain explicit compatibility work until a precise policy is
implemented and qualified. Both failures, full plans/configurations, two fixtures,
five Spark sources and three installed ORC class disassemblies are retained.
Owned JVM 5469 exited cleanly. No public Sail/SDP count changes.

## Requested mapper and ordinary file-source execution

Recorded: 2026-10-30T00:18:01.214574+00:00. [Sail `c3f9b77466` and `f49b3f865c`](evidence/orc-requested-source/README.md)
implement requested-schema mapping and the ordinary FileSource/FileOpener path.
Their independent exact gates pass 169 and 184 data-source tests, formatting and
strict Clippy. Full requested schema survives until timestamp checking; required
projection is separate. Existing projection/file-stream infrastructure handles
expressions, partitions, limits and scheduling. Identity-bound ranges, local
resource limits, selected-stripe object bounds, captured timezone rules and
drop-owned cancellation now run together in integration tests.

The source distinguishes empty physical schemas from zero-column projection and
rejects unsupported virtual columns before projection can index them as partitions.
Explicit ranges are tested; automatic repartitioning remains disabled pending
worker/optimizer qualification. The mapper preserves the qualified value/name
rules while reporting map-key narrowing, non-ASCII matching and unqualified
cross-type evolution as pending capabilities. These are temporary implementation
boundaries, not changes to the complete Spark SDP target.

Next units connect supplied-schema preparation/physical partition names, semantic
schema inference, worker codec and public registry. Writer and remaining native
value-safety/calendar/configuration contracts remain open. This is an internal
file-source verdict; no public CLI or SDP runtime count is added.

## Supplied schema preparation and physical partition bindings

Recorded: 2026-10-30T00:30:55.449580+00:00. [Sail `b52dfd5ad6`](evidence/listing-explicit-schema/README.md)
adds the shared ReadFormat hook, preserving defaults while allowing ORC to retain
an explicit empty or named schema without eager file inference. Formatting,
strict Clippy and 189 data-source tests pass; both earlier failed attempts remain
archived with their exact patches and logs.

Ten fresh Spark schema cases and eleven filters confirm that discovery retains
omitted directory fields. Explicit empty means partition-only rows; absent means
infer file fields. A case-insensitive supplied PART binds physical part while a
case-sensitive PART remains a separate null file field. All returned fields are
nullable in the tested ORC path. These reference facts require shared preparation
and logical/physical name bindings, including partition-filter rebinding before
DataFusion parsing and prefix pruning. They are not yet implemented by this hook.
Mixed physical directory casing, inferred partition types and remaining path
semantics stay visible general listing requirements. The reference's exact source
handoff, two fixtures, configs, plans and clean owned-JVM shutdown are retained.

## Validate materialized lengths before allocation

Recorded: 2026-10-30T00:34:57.556497+00:00. [Native `9f23442e7f` and Sail `947f5123b5`](evidence/orc-materialized-lengths/README.md)
validate materialized variable-length batches before dependent allocations and
reads. Intrinsic addressability, nonnegative decoded lengths, checked totals and
existing Arrow i32 offset bounds are enforced, with fallible scratch/payload
allocation and preserved PRESENT error ordering. Eight new malformed/valid tests
join 331 passing native tests (eight ignored), 210 no-default tests and 189 Sail
data-source tests; formatting, strict Clippy and exact package checks pass.

This resolves the retained materialized-length finding. Skips, dictionary setup,
remaining primitive allocations and RLE delta arithmetic retain separate work.
No total-memory or public ORC/SDP acceptance claim is added.

## Bind directory names and transport the assembled source

Recorded: 2026-10-30T00:41:53.386484+00:00. [Sail `242134aae8` and `5efdf40db8`](evidence/orc-listing-worker/README.md)
pass 192 data-source and 173 execution tests respectively, formatting and strict
Clippy. Listing now separates physical keys from logical partition fields and
rebinds only pruning expressions. Explicit selector aliases retain the actual
observed keys; file identity and output names survive. Existing schema-selection
policy remains a separate correction, with the Spark partition reference retained.

ORC node68 uses shared identity field67, carries configured resource limits and
captured timezone/profile metadata, and binds the reader to the decoding worker's
pool. Tests execute retained logical/temporal fixtures after actual encode/decode
and exercise immutable identity, ranges, both pool directions and stream drop.
A separate task-preparation unit must still qualify independently decoded groups
and preserve checkpoint partitioning at that boundary. Public registration,
semantic schema inference, writer and broader conversion parity remain open.

## Bound skip scratch and require exact skipped payloads

Recorded: 2026-10-30T00:43:23.018521+00:00. [Native `e9690a1eae` and Sail `5cfe24e4f0`](evidence/orc-checked-skips/README.md)
use fixed PRESENT/LENGTH scratch and checked child/payload skip counts. Aggregate
work is split before usize overflow without an arbitrary total limit. Successful
short byte copies fail as UnexpectedEof; original decoder errors survive. Eighteen
new tests cover real encodings, nulls, truncation and next-value alignment. Exact
gates pass 349 native tests (eight ignored), 228 no-default and 192 data-source,
with formatting, strict Clippy and portable package checks.

This resolves the retained skip arithmetic/exact-consumption finding. The next
incremental dictionary setup keeps actual Arrow limits and LENGTH-before-DATA
error order while removing declaration-sized scratch. It is still a separate
unqualified unit. RLE delta and remaining allocation follow-ups stay visible;
there is no whole-heap or public SDP verdict.
