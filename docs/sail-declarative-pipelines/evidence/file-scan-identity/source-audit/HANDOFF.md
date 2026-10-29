# ORC worker scan/codec handoff

Read-only baseline source audit for Sail db8844172d2b6b70095796987bcff613f2ad62aa. The audit itself ran no builds/tests or repository edits and makes no runtime claims. A later explicitly authorized implementation follow-through is recorded below. Locked DataFusion is 55.2.0; Arrow is 59.2.0. This complements the source/opener audit owned by orc_metadata_bounds.

## Immediate correctness finding

Sail's existing opaque DataFusion FileScanExecConf loses object ETag and version. datafusion-datasource 55.2.0 src/proto.rs:66–92 serializes path/size/last_modified/partition values/range/statistics/Arrow schema; :99–108 explicitly reconstructs e_tag=None and version=None. Its generated PartitionedFile protobuf has no identity fields (datafusion-proto-models src/generated/prost.rs:2395–2415). Every Sail file scan uses this shared conversion. OrcObjectReader requires a usable ETag or version for each nonempty range (Sail reader.rs:56–85), so a naive Avro-shaped ORC codec cannot execute reconstructed scans.

Preserve the planned identity in a shared Sail transport unit, before public ORC activation. Worker HEAD must not silently replace that identity with a newer object. Capturing a usable identity during listing/inference is separately the source adapter's responsibility; stores' conditional-read semantics and local metadata-derived ETag limitations remain as documented by OrcObjectReader.

## Existing path and what survives

* encode.rs:34–54 wraps all DataSourceExec nodes in RemoteDataSourceExec; physical-plan/data_source.rs:11–34,82–87 explains this is codec-only, never executable.
* codec.rs:2456–2470 unwraps CheckpointDataSource and detects FileScanConfig. :2472–2491 unwraps InputFileMetadataSource into an encoded ProjectionExec, preserving aliases/metadata. :2492–2595 explicitly dispatches each file format.
* Avro encode :2587–2593 and decode :826–835 are the minimal source-node template.
* parse_protobuf_file_scan_config delegates to FileScanConfig::try_from_proto; source code in DF file_scan_config/proto.rs:55–269 is the authoritative shared conversion.
* task_runner/preparation.rs:59–89 decodes, rewrites file scans, rewrites shuffle, executes key.partition. :92–121 forces preserve_order=true for every FileScanConfig, preventing independent remote task plans from stealing all groups. This applies automatically to ORC. Only the expression-adapter fallback at :108–113 is Parquet-specific.

| Item | Observed transport |
|---|---|
| Object store URL | Preserved as string; empty decodes to local filesystem. |
| Path, size, last-modified | Preserved; timestamp uses nanosecond integer conversion. |
| ETag, version | Lost, both None on decode. Blocking for identity-pinned ORC ranges. |
| File group / within-group order | Repeated arrays preserve order and empty groups. |
| FileRange | Both signed start/end preserved verbatim; codec does not validate them. Opener must validate signed conversion, order, bounds, and its chosen stripe semantics. |
| Partition values | Scalar values preserved in order. |
| Per-file statistics, Arrow schema | Preserved. Arrow field metadata recursively survives shared proto conversion. |
| Per-file extensions, metadata_size_hint, table_reference, ordering | Not carried by this protobuf. Do not put required ORC semantics or cached FileMetadata solely in extensions. |
| Table file schema / partition fields / schema metadata | Preserved via combined schema then partition-field reconstruction. Virtual fields need a format-specific supplement (Parquet already has one); ORC need not invent virtual columns. |
| Projection expressions and aliases | Serialized from FileSource.projection. Decode calls source.try_pushdown_projection; if it returns None, DF silently uses the original source. ORC must reconstruct every projection shape it itself serializes, including zero/reordered/duplicate outputs. Native unique sorted root projection is only the read subset; final output projection remains separate. |
| Limit, constraints, ordering, batch size, declared output partitioning | Present in shared base config. Limit is currently encoded with an unchecked usize-to-u32 cast; see scoped follow-up below. |
| File compression / schema expr adapter / runtime objects | Not part of shared base config. Existing format branches restore them explicitly. ORC internal compression is native file metadata, not external FileCompressionType. |
| preserve_order | Not serialized; worker preparation deliberately sets true. |

Arrow metadata evidence: datafusion-proto-common src/to_proto/mod.rs:92–104 clones Field metadata, src/from_proto/mod.rs:360–366 restores it; nested Arrow type conversion uses those Field conversions. Existing Sail codec test codec.rs:7355–7427 covers Parquet virtual field + partition field + reordered projection, a useful template, not proof of new ORC execution.

## Shared identity transport contract selected after this audit

Keep opaque DataFusion base bytes and add optional FileScanIdentity file_scan_identity=67 to ExtendedPhysicalPlanNode outside its node_kind oneof. FileScanIdentity.groups contains FileGroupIdentity.files containing FileObjectIdentity { location, optional e_tag, optional version }. A dense group/file structure with optional ETag/version preserves None versus Some(empty). Require exact location and group/file count matches against the decoded scan. Validate malformed supplements, unexpected non-file targets, and association mismatches before execution. Absent sidecars retain legacy behavior for existing formats. Older workers silently ignore unknown field67 on known scan node kinds, so wire-additive does not mean identity-safe across mixed versions. Qualification is same-revision deployment only; negotiation is outside this unit. New ORC messages will require the new node/codec and must not quietly downgrade identity requirements.

Capture it from the final FileScanConfig after optimizer repartitioning; the same object may occur multiple times with different ranges. Each occurrence needs the same planned identity. Restore through one shared parse helper immediately after DataFusion base-config decoding and before format-specific builder/property overrides or file I/O. InputFileMetadata's recursively encoded inner scan carries identity; the outer wrapper must not carry a copy and is rejected if it does. Do not rely on FileExtensions. No DataFusion fork or new dependency is needed.

The selected shared parse helper avoids this trap: rebuilding a DataSourceExec with a replacement FileScanConfig recomputes plan properties (DF source.rs:651–655). Existing Parquet decode can set a separate checkpoint output-partitioning override (:758–768). Applying a generic post-decode supplement must preserve that override, or restoration should occur before those per-format overrides. Don't introduce a partitioning regression in a metadata-only change.

Tests for this shared unit: multiple groups including empty; repeated path with distinct ranges; None/empty/nonempty ETag/version combinations; exact last-modified/size/partition values/ranges/schema preservation; malformed counts/path binding; InputFileMetadata wrapped scans; an existing Parquet checkpoint/partitioning case if post-decode restoration is used. This repairs transport only: existing readers do not thereby become conditional readers.

## Minimal ORC node and reconstruction

Add a free oneof tag (1–66 currently used) and OrcExecNode to physical.proto. Suggested content: opaque base_config; validated immutable read/options descriptor; serialized OrcJavaTimeZoneConfig; captured SQL/session display timezone; explicit schema-adapter mode only if chosen source policy varies. Existing codec JSON helpers at :5366–5380 can serialize Sail descriptors without a new serde dependency. Expose read-only getters on OrcSource for these semantic settings; no getter/serialization for runtime pools, caches or native readers.

Decode sequence:
1. Decode descriptor and read bounds with checked validation, and OrcJavaTimeZoneConfig.native_options() so unsupported semantics/profile identity fails before object I/O.
2. Recover TableSchema from base config (all TIME/interval metadata retained).
3. Reconstruct OrcSource with captured options and timezones, plus worker-local runtime resources.
4. Reuse parse_protobuf_file_scan_config to restore groups/projection/partitioning; ensure required identity supplement is restored before opening.
5. Reinstall chosen schema expression adapter deliberately, if the source needs one. Worker preparation only supplies a Parquet fallback.
6. Return ordinary DataSourceExec. No separate ORC execution node or worker runtime factory is needed.

Do not recapture worker local timezone. OrcJavaTimeZoneConfig is serde serializable but deserialization alone does not validate: resolver.rs:15–20,48–68. It pins semantics version + compiled profile bundle hash + original reader timezone. Session display labels remain separate from numeric conversion. The existing factory metadata.rs:44–106 configures Microsecond/Truncate/profile and derives the matching physical schema; the opener must use that paired builder/bridge.

Worker memory binding is already available: PhysicalExtensionCodec::try_decode receives &TaskContext (codec.rs:367–373), and DF TaskContext::memory_pool() returns &Arc<dyn MemoryPool> (execution/src/task.rs:133–140). Attach a cloned worker pool to OrcSource at reconstruction, while the driver scan binds its own runtime pool. Serialize budgets/limits, never pools or reservations. This removes a need to alter FileSource::create_file_opener just to expose TaskContext. Actual native allocation accounting/cancellation remains the source/opener agent's resource-policy task.

Worker object stores are resolved using the existing runtime registry. Parquet's decoder already reconstructs store/cache from ctx.runtime_env at codec.rs:718–730. WorkerSessionFactory builds the same DynamicObjectStoreRegistry via RuntimeEnvFactory (:worker.rs:30–51, runtime.rs:45–69); registry.rs:98–114 creates stores from URL/runtime. This is not proof of arbitrary driver-only credentials or custom registrations transferring. ORC should follow existing worker-store deployment rules; do not serialize credentials/handles in the ORC node.

## Source/worker partition boundaries

DF FileSource::supports_repartitioning defaults true (file.rs:137–179), and default FileGroupPartitioner clones each PartitionedFile while assigning arbitrary half-open byte ranges (file_groups.rs:204–266). If the first source unit is whole-file-only, explicitly return false; otherwise the opener must implement validated stripe ownership and writer-timezone inheritance for every assigned range, tested for no duplicates/omissions. Merely ignoring ranges duplicates rows. This is a source choice already sent to the adapter author.

Worker preparation forces per-group execution; no additional scheduler path is necessary. The shared-build join planner already detects any FileScanConfig (job_graph/planner.rs:113–150), so ORC naturally participates. Qualify multi-task execution using separately reconstructed plans per partition, not just one process sharing one decoded plan; assert total rows exactly once.

## Registration and human-reviewable units

1. Shared identity preservation in sail-execution proto + codec helper + focused existing-format tests (general Sail correctness, no ORC dependency).
2. Shared ORC ReadFormat/FileSource/opener and explicit validated options (other agent's handoff); source-local schema/resource/range policy tests. Preserve fail-closed output semantics.
3. ORC codec plus sail-session formats.rs import/register at :27–41, and source registry test adding orc to data-only names. Public registration should land only with worker reconstruction qualified.
4. End-to-end public read qualification: real retained primitive/TIME/interval/timestamp fixtures; both reader-zone contexts independently from display zone; nested null/empty containers; partitions and zero/reordered/duplicate projection; corrupt option/profile rejection; object replacement fails; separately decoded worker groups return exactly once. Keep writer implementation and streaming/CDC phases separate as previously scoped.

## Other observed shared limits (not reasons to broaden the ORC unit blindly)

* DF base conf encodes limit as u32 with an unchecked cast (file_scan_config/proto.rs:120). Values over u32::MAX can change across remote transport. If relevant to activation, correct it in a small separate generic codec guard/transport unit; do not claim all limits are lossless.
* Arbitrary FileExtensions/runtime caches and per-file ordering aren't serialized. ORC must be able to reload bounded metadata from the preserved object identity. Generic extensions cannot be made portable by serializing Any.
* Driver-only session stores/credentials are not generally serialized by this file-scan path. Existing runtime deployment policy applies.
* Native profile/statistics pruning limitations remain; no evidence here qualifies ORC predicate pushdown or footer min/max statistics under transformed timestamp semantics.

No new streaming/CDC design phase is required by this audit. The actual shared design addition is the file-identity wire contract; resource admission and schema/range choices remain the already active ORC source checkpoint.

## Authorized implementation follow-through (draft, not qualified)

After root reviewed this audit, root authorized the smallest shared transport unit. Agent-owned changes are physical.proto, codec.rs, and codec/file_scan_identity.rs only. Root assigned the separate codec/file_scan_identity_tests.rs to an independent reviewer. The production draft restores identity through the shared parse helper at every existing leaf file-format decoder, validates positional shape/location, rejects outer/non-file supplements, and leaves metadata_size_hint/extensions and ORC activation unchanged. No builds or commits were run by this agent; root owns immutable gating and commit. This paragraph is not a claim that the draft has passed runtime qualification.
