# ORC read adapter: implementation and remaining decisions

Recorded: 2026-10-29T22:54:05.197855+00:00. Read-only audit of Sail `db8844172d2b6b70095796987bcff613f2ad62aa`, Spark
`617618396087429b5627a86ce933bb0f5d6645cb`, DataFusion 55.2.0 and the
vendored native ORC APIs. No builds, runtime experiments or repository edits were
performed for this audit. The timestamp fixture candidate was being gated during
the audit; this handoff does not independently attest that gate.

The next useful outcome is a registered shared ORC **read** path, exercised through
SQL, DataFrame and reconstructed worker scans. The existing object reader,
logical bridge, Java profile/config and controlled builder are sufficient
foundations for that adapter. There are two remaining policy decisions to settle
at the announced checkpoint: resource admission/defaults, and the precise
requested-schema compatibility surface. Object identity transport is a concrete
shared codec defect to fix, not a reason to invent an ORC execution engine.
Writer, streaming and CDC objectives remain unchanged and separate.

## Existing paths to reuse

| Responsibility | Source evidence and implication |
| --- | --- |
| Shared source entry | `sail-data-source/src/listing/source.rs:36–95`: `FormatFactory` and `ReadFormat` own option resolution, compression/schema inference, file metadata and `FileScanConfig`. `ListingDataSource` supplies SQL/DataFrame/catalog reuse. |
| Scan construction | `formats/avro/read.rs:60+`, `formats/json/read.rs:115+`, `formats/parquet/read.rs:255–293` preserve groups, constraints, statistics, projection, limit, output ordering/partitioning and preserve-order. Copy this structure, not another SessionContext. |
| Custom source/opener | `formats/csv/source.rs:162–240` and `formats/binary/source.rs:45–116` demonstrate `FileSource`, metrics, batch size and expression traversal. `FileOpenFuture` returns a stream; ORC can use its existing async object reader and native async builder. |
| Output projection | DataFusion `projection.rs:33–101,153–286`: `SplitProjection` separates unique file columns from remaining expressions/partition values; `ProjectionOpener` applies the latter. Its input is the requested logical file schema, not each individual file's physical schema. |
| Per-file logical conversion | `formats/orc/metadata.rs:44–109`: `try_new_reader` validates all raw logical types, takes immutable-file metadata, pins microseconds/Truncate/reader rules, applies a sorted unique physical projection and derives schema from that same configured builder. Keep factory and build adjacent. |
| Range identity | `formats/orc/reader.rs:11–124`: every nonempty range requires version or usable ETag; all reads validate response identity and exact bounds. Reuse this reader for inference and execution. |
| Schema evolution machinery | `sail-common-datafusion/src/schema_evolution.rs:205–276,280+,554–603,641–684,1056–1101` already supplies missing/default fields and recursive name-based casts. Reuse after ORC physical-to-logical adaptation, subject to ORC-specific compatibility validation; generic casts are not a Spark ORC compatibility specification. |
| Registration | `sail-session/src/formats.rs:29–46` registers normal `ListingDataSource` providers. `formats/binary/write.rs:11–20` shows a read-only listing format with explicit unsupported writing; ORC can use the same temporary boundary while its real writer remains outstanding. |

## Concrete shared gaps

### Inference is currently sampled, not complete

`listing/utils.rs:160–182` takes only ten nonempty objects per URL.
`ReadFormat::infer_schema` receives those samples. An ORC implementation must not
call all-sample merging and claim `mergeSchema=true` covers every file.
`list_all_files` at `listing/utils.rs:269–306` already owns hidden-path filtering,
glob filtering, prefix/file selection and listing-cache behavior.

Spark `OrcUtils.scala:193–222` chooses the first usable schema by default and
merges when enabled; an empty root schema is skipped (`:87–91`). The design already
selects those semantics. Recommended implementation: a small generic inference
selection hook (preserve existing formats' sample behavior) or reuse the generic
listing iterator for ORC's all-file merge path. Prefer the hook if it avoids a
second complete listing and preserves the same selected object identities. Do not
write ORC-specific path discovery. Test the eleventh file, empty-root first file,
multiple URLs, hidden files and deterministic selection. Stable ordering must be
explicit rather than depending on completion order of concurrent footer reads.

### Case-sensitivity currently stops at initial top-level reconciliation

`SourceInfo.read_case_sensitive` is supplied by the planner
(`sail-plan/src/resolver/query/read.rs:246,629`) and consumed by
`listing/source.rs:173,193–208`. The reconciliation function (`:351–379`) only
renames top-level fields against one inferred schema. Neither
`ListingTableSourceConfig` (`listing/table.rs:19–29`) nor `ListingScanInput`
(`listing/source.rs:121–134`) carries this setting to per-file execution.

A directory containing different spellings, nested fields or missing fields
cannot rely on that initial reconciliation. Carry the existing semantic input to
the scan/source and worker descriptor. This belongs in Sail's shared listing
contract, with LakeCat simply using that source path. Preserve ambiguity errors;
do not silently select one of `A` and `a` in case-insensitive mode.

### Worker serialization drops object identity

The coordinated execution audit found that locked DataFusion
`datafusion-datasource/src/proto.rs:66–108` omits ETag/version and reconstructs
both as `None`. ORC's qualified object reader correctly rejects such worker reads.
The smallest fix is a Sail-owned, validated identity overlay/sidecar around the
shared file-scan serialization. Do not attach mandatory identity or metadata only
to `PartitionedFile.extensions`, which is also not transported.

Preserve the planned object identity on workers. Re-HEAD on a worker and silently
select a new version would change the plan's meaning. If a listing provider omits
identity, choose explicitly between acquiring it on the driver before pinning
that file into the scan and rejecting the unsupported identity capability.
This is a planning-boundary choice, not permission to combine one version's footer
with another version's streams. Avoid serializing native `FileMetadata`: workers
can reread bounded metadata under the transported identity.

## Requested schema: what is settled and what needs a focused oracle

Settled implementation order:

1. Read each file's bounded metadata and infer its true Spark logical schema.
2. Validate requested compatibility against that file, including columns selected
   by an explicit schema rather than just the first inferred file.
3. Map requested fields to physical file ordinals; take the sorted unique physical
   set for the native builder. Native ordinals/type IDs are already handled by
   `try_new_reader`; do not feed requested/reordered schema into a native decoder.
4. Adapt decoded batches through `OrcSchemaBridge` first. Then produce requested
   logical fields/missing nulls in the order required by `SplitProjection`.
5. Let `ProjectionOpener` restore expressions, aliases, repeated/reordered output
   and partition columns. Keep predicates residual and statistics unknown until
   specific pushed semantics are qualified.

Spark `OrcUtils.scala:232–247` explicitly rejects LTZ↔NTZ conversion. Its visible
check zips top-level field types and recurses through structs; it is not a generic
recursive name matcher. `:252–289` separately selects positional Hive evolution
(`orc.force.positional.evolution` or all `_col*` names), default name matching,
case handling and missing requested columns. These details need retained Spark
cases for reordered mixed LTZ/NTZ columns and nested list/map/struct evolution
before deciding whether an existing generic adapter alone is sufficient.

The shared adapter's compatibility predicate (`schema_evolution.rs:641–684`)
mostly delegates primitive compatibility to Arrow `can_cast_types`; its strict
mode is not an ORC-specific LTZ/NTZ rejection policy. Its name matcher is exact
(`:703+`). Its relaxed timezone mode must not be used to bypass ORC compatibility.
Add narrow ORC compatibility validation and reuse shared conversions where they
match; improve generic matching in the shared module when that is the real gap.

Do not equate SQL casts with requested-read-schema evolution. TIME storage is
nanoseconds regardless of declared precision. A request to read TIME(p) as
TIME(q) may be just schema interpretation in ORC; the newly qualified SQL
precision-cast helper is not evidence that the reader should truncate values.
Include fractional TIME(0) data with explicit different precision in the Spark
read-schema oracle, plus interval qualifiers, widening integers, missing fields,
case ambiguity and explicit nullable schemas. `mergeSchema=true` also needs
Spark-compatible semantic merging, not merely an unchecked Arrow merge: current
`listing/utils.rs:64–72` calls `Schema::try_merge`. Compare TIME precision conflicts
and interval qualifier merges before reusing it unchanged.

Tradeoff at this checkpoint: a narrow explicit compatibility validator gives a
reviewable first adapter, but every intentionally unsupported conversion/option
must error and remain an open acceptance case. A broad generic conversion matrix
implemented without Spark file-read evidence risks changing values. Recommend a
small paired Spark oracle for the above cases, then a focused matcher/validator;
this is completion of the existing read contract, not a new pipeline-only path.

## Resource policy: real remaining decision, not a batch-size knob

Observed boundaries:

- Native `MetadataReadOptions` bounds combined encoded and decoded file-tail
  metadata and raw schema depth. Tests' 64 KiB/16 limits are test inputs, not
  selected production defaults. No production limits/defaults are selected yet.
- Native `stripe.rs:225–276` reads/decompresses a stripe footer and retains all
  selected encoded stream `Bytes` before decoding. The file-tail metadata budget
  does not cover those allocations or decoded data arrays.
- Native `async_arrow_reader.rs:169+` drives decoding from stream polling; output
  batch size does not bound a stripe's retained encoded buffers or a large value.
- `OrcObjectReader` checks range/addressability but does not reserve its buffers
  in DataFusion's pool. A bounded output channel alone does not fix that.
- DataFusion `FileSource::create_file_opener` has no `TaskContext` argument;
  `FileScanConfig::open_with_args` (`file_scan_config/mod.rs:699–733`) does have it,
  but passes only store/config/partition to the source. There is no direct pool
  hook in the `FileSource` trait.

An existing attachment route resolves the last API issue: driver
`ReadFormat::scan` has `Session::runtime_env`, and worker
`RemoteExecutionCodec::try_decode` has `&TaskContext`
(`sail-execution/src/proto/codec.rs:367–373`). Attach the *local* memory pool to
`OrcSource` at those two construction sites. Serialize limits, never a pool,
reservation or other runtime handle. Existing Sail reservation examples are
`sail-python-udf/src/buffer.rs:26–38` and
`sail-delta-lake/src/physical_plan/log_replay_exec.rs:895–911`.

Choose and record:

| Decision | Alternatives and consequence | Recommendation |
| --- | --- | --- |
| Tail limits/depth defaults | Unlimited preserves native legacy behavior; finite explicit limits give deterministic rejection but may exclude unusually large valid schemas. Pool-relative limits vary with worker capacity. | Select explicit serialized finite limits through existing option/config machinery, with tests at exact/over/zero boundaries. Do not copy test limits or invent an undocumented cutoff. |
| Stripe/data admission | Encoded-byte cap plus accounting after decoding is small but cannot prove a decoded-memory cap. Admission/reservation before native allocations needs an explicit bounded decoder/observer interface. | Decide the required guarantee now; if strict preallocation bounds are required by production registration, implement the smallest native budget hook as a separate reviewed dependency unit tied to this adapter. Do not call post-allocation accounting a hard cap. |
| Reservation lifetime | Releasing at the end of `get_bytes` undercounts `Bytes` still held by the native stripe; releasing on batch yield may undercount retained arrays. | Hold charges with the owning stream/stripe/batch lifetime and verify release on EOF/error/drop. Avoid charging the same shared buffer repeatedly. |
| Decode scheduling/cancellation | Native async avoids a new runtime and follows existing stream paths; synchronous decompression inside a poll cannot stop halfway. A blocking worker plus bounded channel costs lifecycle/abort machinery. | Start from Sail/DataFusion's existing cooperative stream path, but qualify cancellation and a bounded per-poll workload under the chosen data budget; use the existing `SpawnedTask` pattern if a separate decode worker is required, rather than an ORC scheduler. |

This checkpoint need not revisit graph reuse, catalogs, Java timezone semantics,
SDP orchestration or streaming/CDC design. It must produce a concrete resource
contract that can be tested and serialized.

## Options and public shape

Use `data/options/orc.yaml`, `build.rs`'s existing
`build_data_source_options("Orc", "orc")` pattern, and an `options/mod.rs` generated
include; use `ResolveOptions`/`OptionLayer` rather than hand-parsing a second option
stack. `SourceInfo.options` documents later layers overriding earlier layers
(`sail-common-datafusion/src/datasource.rs:231–234`); Parquet's factory/options are
the nearby model. Keep case sensitivity as the existing read semantic input, not
an ORC-only alternative setting.

Initial read options need `mergeSchema`, generic path filtering and the selected
resource controls. ORC compression is internal: read `infer_compression` returns
UNCOMPRESSED for the *outer* stream, like Avro/Parquet; the native reader uses each
file's postscript codec. Do not apply gzip-style wrapping. Writer codec precedence
remains the already documented later writer contract. Semantics-changing options
such as positional evolution must be implemented or explicitly rejected.

Recommended runtime source fields: `TableSchema`, resolved ORC read options,
serialized `OrcJavaTimeZoneConfig`, independent SQL display timezone, existing
read case-sensitivity setting, local memory-pool handle, batch size, metrics and
`SplitProjection`. Expose only the getters needed by worker serialization. Capture
`get_system_timezone()` once on the driver and serialize its selected reader
profile identity; workers must never infer their local zone. The options/config
values, not native profiles or metadata structs, form the serialized descriptor.

## Smallest reviewable commit sequence

1. **Shared listing semantic inputs.** Carry case sensitivity to scan construction;
   expose appropriate inference enumeration so ORC can distinguish first usable
   from all-file merge without copying path rules. Keep existing format behavior
   unless a separately tested shared bug is fixed. Tests: eleventh file, mixed/nested
   case names, ambiguous names, missing fields and hidden/glob selection.
2. **ORC options and per-file requested-schema mapping.** Resolve options through
   the generated machinery; implement the oracle-backed compatibility/matching
   policy and map to unique physical columns. Include selected resource-policy
   values once the checkpoint is resolved. This unit can be split from the opener
   if it would otherwise obscure the logical schema review.
3. **ORC ReadFormat + FileSource/opener.** Reuse bounded metadata, immutable object
   identity and `try_new_reader`; perform logical adaptation then requested-schema
   adaptation; use `SplitProjection`/`ProjectionOpener`; preserve all scan config
   fields, unknown statistics and residual filters. Direct FileSource execution
   tests must include identity change, missing columns, nulls, expressions,
   repeated/reordered projection, partition-only/zero-column counts, limit,
   multiple files/groups and resource cleanup/error/cancellation.
4. **Shared file-scan identity transport.** Add the validated ETag/version sidecar
   and preserve it across driver/worker preparation. Qualify reconstruction under
   a store that rejects absent/wrong conditions; never rebind the worker to HEAD.
5. **ORC worker codec.** Add the ORC physical node/options/profile descriptor and
   source encode/decode. Reattach local runtime resources. Execute decoded scans
   across multiple groups/partitions, repeated/computed/empty projections,
   partition values and identity mismatch. Source reconstruction must accept all
   serialized projection shapes; DataFusion's fallback must not silently lose them.
6. **Registration and public read acceptance.** Register the normal listing ORC
   provider, then run identical Spark/Sail DataFrame/SQL/CTAS-from-ORC/catalog-backed
   read cases against immutable external fixtures. Keep writing explicitly
   unsupported until the real stateful writer unit lands. Do not mark the original
   SDP registration (which also writes ORC and later streams) fully ported.

Step 4 can run in parallel with steps 2–3; it is required before the worker read
claim. Avoid exposing a registered local-only implementation while workers lose
identity or timezone configuration.

The smallest initial range choice is **whole-file reads with
`supports_repartitioning=false`**, rejecting any unsupported partial range rather
than ignoring it. This preserves read semantics with less parallelism. It is
explicitly permitted by ORC-SOURCE-DESIGN. A subsequent small range commit uses the
already selected half-open ownership rule (stripe start belongs to [start,end))
and native range API; qualify complete/disjoint output, empty ranges, multiple
stripes, writer-zone inheritance at range starts and worker reconstruction before
switching repartitioning on. DataFusion defaults this capability to true
(`file.rs:137–179`), so omission is a correctness bug, not a harmless default.

## Required next checkpoint output

Record concrete metadata/decode limits and memory ownership, the minimal
requested-schema oracle/results and treatment of unsupported evolution modes,
and the identity transport representation. Then implementation can follow the
above units directly. The first public read milestone should report precisely
which local and worker paths passed, while leaving writer and SDP streaming
assertions open. No new streaming/Iggy/CDC decision is implied by this handoff.
