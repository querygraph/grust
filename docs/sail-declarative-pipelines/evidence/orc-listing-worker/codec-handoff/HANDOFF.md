# ORC worker codec implementation handoff

The six files in source-state.json are the first codec unit. Nightly rustfmt and whitespace checks were run; no build, test, gate, commit or push was run by the implementing agents. Root owns detached gates. Listing and vendored-native work were not edited.

## Wire contract

Add oneof OrcExecNode at tag 68; retain shared optional file_scan_identity at tag 67. ORC alone requires this sidecar because it has no legacy identityless wire form. Existing formats retain legacy absence behavior. The sidecar preserves optional identity strings exactly; identity usability remains the opener's pre-GET check.

OrcExecNode carries opaque base_config, OrcReadOptions, reader_timezone_json, session_timezone, read_case_sensitive and output_partitioning. The four resource/depth options use required-on-decode optional uint64 fields: omitted differs from explicit zero; values convert with checked usize/u64 conversions. They are configured values, never driver-derived effective ceilings. usize::MAX is valid where representable and the source derives local addressable/pool caps later.

The timezone JSON is the existing deny_unknown_fields OrcJavaTimeZoneConfig. OrcSource::try_new validates semantics/profile identity and uses the original captured reader name, with session display label separate. Decoder clones ctx.memory_pool(); no pool, reservation, store credentials, native metadata, cache or compiled requested-schema mapping is serialized.

Decode reconstructs full TableSchema, creates the normal OrcSource, calls the shared file-scan parser/identity restoration (including normal projection reconstruction), then reapplies optional checkpoint partitioning. Encoder rejects unsupported outer compression rather than silently dropping it from DataFusion's base protobuf.

## Tests

Four host-independent structural tests plus six executed-source tests are active on 64-bit platforms; one extra width-overflow case is cfg(target_pointer_width = "32"). They cover configured zero/max values despite a tiny driver pool, full nested TIME/interval metadata and schema, reordered/duplicate/empty/computed projections, identity occurrences/ranges/empty groups, small limits and batch size, InputFileMetadata inner identity, checkpoint partitioning, omitted options/sidecar, malformed profile JSON/hash/version, outer compression rejection, actual retained TIME/interval/submicro bytes, both captured reader identities independent from display, replaced/identityless objects, invalid signed/out-of-file ranges before GET, opposite driver/worker pool limits, and stream-drop reservation release while a returned batch remains valid.

Suggested root gate commands (use the established immutable gate checkout/environment):

- cargo +nightly fmt -p sail-execution -- --check
- cargo test -p sail-execution --lib proto::codec::orc_tests
- cargo clippy -p sail-execution --lib --tests -- -D warnings
- cargo test -p sail-execution --lib

## Deliberately separate follow-through

The next logical unit tests separately decoded worker partitions through the real TaskPreparation rewrite. Its rewrite_file_scans method reads no self state and can become a private associated function for direct tests. Current rebuilding also drops DataSourceExec's separate checkpoint partitioning override (a general existing behavior shared with Parquet); preserve that override while changing only preserve_order/adapter configuration and add a regression in that unit. This codec unit tests roundtrip preservation, not that later preparation boundary.

No ReadFormat/public registry, writer, pruning, automatic ORC repartitioning, streaming/Iggy or CDC activation is included. Existing DataFusion scan-limit serialization narrows usize to u32; only small limits are qualified here and the general large-limit transport issue remains separate. Opaque per-file extensions/metadata_size_hint and arbitrary driver-only credentials are not transported. Mixed codec versions are not an identity-safe deployment claim: older workers do not understand tag 68, while the existing tag 67 qualification remains same-revision.
