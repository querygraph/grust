# Sail ORC Java timezone runtime-provider handoff

Status: read-only implementation outline under the existing ORC temporal checkpoint. No repository edits, builds or Rust runtime tests were performed by this reviewer. This is a proposed interface, not an implemented provider.

## Selected data and compatibility identity

The exporter-owned artifact is /tmp/sail-sdp-orc-bridge-reference/full-java-timezone-profile/java-timezone-profiles.json: 1,541,175 UTF-8 bytes, SHA-256 1f90695f80f862138bf1635b8727281eb7b0a76d838513eaf09675cb6ee7212b. It contains 631 exact names, 349 deduplicated profiles, 36 normalized cycles (from 37 Java source rule shapes), and 268 provenance alias entries. These counts and the digest were read independently. Exporter's additional independent verifier and repeatability gate were pending when this handoff was prepared.

Configuration is explicit: Oracle Java 20.0.2+9-78, tzdb 2023c, oldmapping=false, FORMAT locale en-US, GregorianCalendar, epoch text 2015-01-01 00:00:00 and UTC epoch 1420070400. Spark4.2.1 alone does not fix these JVM settings. Java ORC's constructor actually calls SimpleDateFormat(String) without an explicit locale (retained TimestampTreeReader javap lines61-64); this selected exported baseline must not be described as matching every JVM locale/calendar or arbitrary TimeZone.setDefault override. Alternative exports require their own identities and evidence.

The runtime requires no JVM, host tzdb query, Jiff/Chrono rules evaluation or new timezone engine. The driver captures its reader-zone name once with Sail's existing get_system_timezone. That host-derived baseline is an explicit Sail choice, distinct from proving every Spark JVM default selection. SQL session timezone is the Arrow/display label and must remain separate.

## Format matching the exporter

Canonical compact sorted-key JSON v1, UTF-8, one trailing newline. Profiles and cycles are keyed by SHA-256 of the canonical object without newline; the worker identity is SHA-256 of the entire exact file including its newline.

- configuration: exact settings above, plus offset_domain_millis.
- zones: exact input name -> {profile, resolved_id, available}.
- profiles: hash -> {raw_prefix_offset_millis:i32, orc_epoch_seconds:i64, transitions:[[utc_millis:i64,total_offset_millis:i32],...], future:{kind:"fixed",offset_millis:i32}|{kind:"cycle",id}}.
- cycles: hash -> {anchor_millis:i64,period_millis:12622780800000,rows:[[position_millis:i64,total_offset_millis:i32],...]}.
- java_aliases: provenance mapping; runtime need not traverse it because zones already contains every exact exported spelling and its selected profile. Re-resolving aliases could change Java resolved IDs (PST stays PST in the Java result).

Hash the exact embedded bytes during the offline generation/verification gate and pin that digest as a constant next to the asset. Future workers compare the incoming identity with this compiled identity before constructing readers. This is sufficient for a compiled-in immutable asset and keeps runtime dependencies to existing serde/serde_json/std. Do not advertise a public arbitrary-file loader or recomputation of supplied hashes with this approach. If external bundles become a requirement, add actual byte-hash verification as a separately reviewed unit; do not handwrite cryptographic hashing. serde_json has preserve_order enabled, so ordinary Rust reserialization is not itself a guarantee of this sorted-key canonical byte representation.

## Small Rust module surface

Keep this under crates/sail-data-source/src/formats/orc/timezone/, private until file-source/codec integration needs exports.

1. profile.rs: private serde DTOs, embedded data loading/validation, immutable offset tables and native TimestampTimeZone implementation.
2. resolver.rs: exact-name selection, the bounded custom-GMT parser/normalizer, native TimestampTimeZoneResolver implementation.
3. mod.rs: small descriptor/options constructor. Focused tests in adjacent test modules. Generated JSON is an asset with exporter provenance, not hand-maintained Rust code.

Proposed public-to-ORC API:

    #[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
    pub(crate) struct OrcJavaTimeZoneConfig {
        semantics_version: u32,       // Java string API + profile evaluator contract
        profile_bundle_sha256: String,
        reader_timezone: String,      // captured exact driver input, not display label
    }

    impl OrcJavaTimeZoneConfig {
        pub(crate) fn for_reader_timezone(name: String) -> Result<Self>;
        pub(crate) fn native_options(&self) -> Result<TimestampTimeZoneOptions>;
    }

for_reader_timezone sets the compiled identity and validates/resolves using that bundle. Deserialization alone does not establish validity: native_options verifies semantic version and bundle identity. No worker-side get_system_timezone call. The later physical-plan descriptor can serialize this ordinary value along with the separately existing session/display timezone and precision policy.

Use a LazyLock or equivalent existing one-time initialization for Result<Arc<ValidatedProfiles>, diagnostic string>; clone Arcs per reader, not tables. DTO maps can be BTreeMap, with typed integer pairs and tagged future policy. Convert to immutable shared Arc<Profile> and Arc<Cycle>; offset arrays can be boxed slices. Exact-name aliases can share one profile Arc. A custom fixed offset may allocate one small Arc per resolved stripe name; no unbounded mutable name cache is necessary.

Profile implements native TimestampTimeZone directly. Resolver returns Arc<dyn TimestampTimeZone>. Same-Arc identity is merely a native fast path; distinct equivalent profiles must still return equal offsets. Do not move the native writer-zone cursor into this resolver: missing/empty stripe state and range/row-selection inheritance already belong to native reader state.

## Validation and offset lookup

Before exposing loaded tables, require supported format/semantics, exact configuration/domain shape, all referenced profile/cycle IDs present, GMT present, strictly increasing transition positions, nonempty cycle rows starting at zero, every cycle row in [0,period), and the selected Gregorian 400-year period. Typed serde fields reject out-of-range integers. For zero-history profiles, exporter requires a fixed future offset equal to raw_prefix; validate that invariant. The private parser consumes only trusted embedded bytes; canonical duplicate-key and object-digest verification belong to the asset gate, not silently to BTreeMap deserialization.

Lookup semantics:
- No historical transitions: return the raw-prefix/fixed offset for every supported instant.
- Before first transition: raw_prefix_offset_millis.
- Through and including exact last transition: greatest table instant <= query.
- Strictly after last transition: use the explicit future policy. A fixed future is its own supplied offset, not an inferred last historical row.
- Cycle future: compute position = (i128(query)-i128(anchor)).rem_euclid(i128(period)); binary search greatest cycle row <= position. Never use unchecked i64 subtraction or reconstruct a calendar date.

The artifact domain is [-9223380626789368,9223380626789367] ms. It is floor(i64-microsecond endpoints / 1000), expanded by 4*2^31 ms on both sides. Each difference of two i32 offsets has magnitude <2*2^31 ms. One such difference relates original to final decoded instant; a second covers native's candidate t+w-r query. Therefore this envelope covers every offset query needed for any representable final microsecond result, including submicrosecond truncation at endpoints. It is not an arbitrary year restriction. Unsupported queries outside this explicitly qualified envelope return an OrcError; no offset substitution. Use native OutOfSpecSnafu with a precise profile/domain message rather than a successful fallback for numeric-domain errors.

Return stored orc_epoch_seconds. Do not derive a named zone's 2015 epoch from its raw prefix (Windhoek demonstrates the difference). Only newly parsed fixed custom offsets use utc_epoch_seconds - offset_seconds, which is exact for whole-second Java custom offsets.

## Java string-name behavior

Resolve names in this order:
1. Exact lookup in zones, retaining its exported resolved_id for diagnostics.
2. Exact case-sensitive ASCII custom GMT parser.
3. The exported GMT profile as the deliberate Java unknown-name fallback.

Do not trim, case-fold, run Sail's SQL timezone parser, normalize IANA aliases, or interpret bare +05:30 / UTC+05:30. Keep resolver errors for invalid bundle/configuration/domain distinct from Java's successful unknown-name GMT selection. Native never passes null/empty writer metadata to this resolver; direct empty-string Java behavior is still GMT.

Custom grammar matches pinned Java20 TimeZone.parseCustomTimeZone, including seconds:
- Prefix GMT, then + or -.
- Compact one/two digits means hours; three/four digits means HHMM (e.g. GMT+0010 is +00:10).
- One colon: hour width 1..2; final minutes width exactly 2.
- Two colons: hour width 1..2, middle minutes width 1..2, final seconds width exactly 2.
- Hours <=23, minutes/seconds <=59; ASCII digits only, no whitespace/trailing data/additional colons.
- Normalize to GMT[sign]HH:MM, appending :SS only for nonzero seconds. Preserve signed zero spelling as GMT+00:00 or GMT-00:00.
- Examples requiring regression coverage: GMT+1:2 fails to GMT, but GMT+1:2:03 succeeds as GMT+01:02:03; GMT+23:59:59 is valid. GMT+00530, GMT+24:00, GMT+05:60 and non-ASCII digits fall back to GMT.

The exporter retained 315,351 name-oracle cases/digest plus representative outcomes. Mirror the actual oracle sequence in Rust tests (or retain a manageable independently generated result corpus), rather than testing only cases produced by the Rust parser itself.

## Correct bridge/reader construction

Current OrcSchemaBridge::try_new creates ordinary TIMESTAMP physical fields without a timezone. Its adaptation guard rejects naive-to-LTZ conversion. Once native timezone options are enabled, ArrowReaderBuilder::schema instead emits ordinary TIMESTAMP as UTC. Passing those native batches to the current bridge causes the physical-field equality check to fail. Removing the guard or merely relabeling old decoded arrays would be incorrect.

No new vendor API is needed. ArrowReaderBuilder<R>::new_with_metadata, its timezone/precision setters and schema() are available on impl<R>, without a ChunkReader bound. The smallest coherent integration:
1. Validate/infer the full logical schema first, preserving current decimal validation order.
2. Construct the actual full-column native builder from pinned metadata + its object reader.
3. Apply Microsecond precision, the separately chosen truncation policy, and immutable native_options.
4. Obtain its computed physical schema with builder.schema(); an internal bridge constructor pairs this with the inferred logical schema. The controlled path must not call native with_schema with a user-requested logical schema.
5. Apply the same unique file-order projection to native builder and bridge; restore requested order/repeats later.
6. Build the sync/async reader. Both use the same builder configuration type.

Prefer a private factory returning (configured builder, bridge) or a private bridge constructor called only by that factory. Avoid a public constructor accepting arbitrary requested schemas as proof of native decoding. For ordinary timestamps, native options select the numeric semantics and UTC physical label; the bridge's existing timezone relabel helper preserves those decoded instants while applying the session display label.

This step does not implement requested-schema evolution, calendar rebasing or generic file-source registration. Native pruning suppression also does not qualify Sail-side statistics pruning.

## Reviewable implementation units and gates

A. Generated profile asset/provenance, private typed loader, validation and integer lookup tests. Require exporter repeatability, all object digests and independent evaluator/oracle agreement first.
B. Exact-name/custom-GMT resolver and immutable config-to-native-options conversion; full retained name oracle, unknown/aliases, signed zero, stored epochs and malformed descriptor identity tests.
C. Controlled native builder + bridge integration, with real Spark/foreign ORC timestamp fixtures; positive/negative submicroseconds, cross-zone folds/gaps, reader/display separation, missing/empty writer inheritance, fresh range starts, TIMESTAMP_INSTANT invariance and recursive null/slice cases.
D. Later source/worker codec unit serializes profile identity and captured reader name; workers with mismatched identity reject before data output. Keep full batch file-source work separate.

Tests must assert transition -1/0/+1ms, exact final historical transition versus +1ms, zero-history fixed zones, cycle start/end and repeated 400-year blocks, domain endpoints and adjacent errors, plus native µs-overflow behavior. Use retained independent expected numbers/digests for real profiles. Handcrafted malformed tables test validation only.

No missing semantics currently require another design alternative. Implementation is contingent on the exporter gates and these explicit baseline settings; neither existing source evidence nor this handoff claims arbitrary Spark JVM configuration equivalence.
