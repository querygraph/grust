# ORC semantic schema merge: source-only proposal

Read-only audit at Sail `5563ea165917fbcc9d59144da3f131f26428f07c` and Spark source `617618396087429b5627a86ce933bb0f5d6645cb`. No repository files changed, no Cargo commands, no Spark process or other runtime tests were run. `source-audit.json` records exact blobs, full-source hashes and retained numbered excerpts. This is a proposed implementation contract, not an implemented capability or runtime qualification.

## Recommendation

Add a small field-aware Arrow merger below both Connect and data-source, in `sail-common-datafusion/src/schema_merge.rs` with a separate focused test module. Leave the current pipeline normalization and spec merger unchanged in this ORC unit. Reuse the existing `spec::SparkTimeMetadata` parser and `spec::SparkIntervalMetadata::{try_new, wider, to_json}`; reuse existing recursive `column_change::validate_field_names` independently at the ORC inferred-schema boundary for the canonical container shapes.

The direct caller is ORC `ReadFormat` inference, which already receives canonical logical Arrow schemas from `infer_orc_schema`. It needs neither Connect nor sail-plan. Other formats continue using their current merger. This is not a replacement for Spark's general type coercion, data casting, schema evolution, or all existing pipeline schema normalization.

A suitable minimal public API is:

```rust
pub fn merge_spark_file_schemas(
    left: &arrow_schema::Schema,
    right: &arrow_schema::Schema,
    root_case_sensitive: bool,
) -> datafusion_common::Result<arrow_schema::Schema>;
```

Keep helpers for matching fields, merging semantic field types and updating their type metadata private. One Schema-level entry point avoids implying that a false case flag should propagate through an arbitrary standalone nested DataType. Document the input as already normalized Spark file schemas; the initial caller's complete emitted type set is the existing ORC bridge. Types or semantic extensions outside that contract need an explicit diagnostic or deliberate followup, not a physical-type-equality fallback that silently treats UDT/Geo/Variant storage as ordinary values.

## Why not extract the current spec merger first?

The existing `pipelines/schema_merge.rs:12–143` is approximately 130 lines of pure spec merge logic plus a pipeline-specific error constructor. It is easy to move to `sail-common` with `CommonResult` and preserve a thin Connect error wrapper. That move would be useful if another **spec-schema** caller needed it. It would not by itself make ORC a caller.

Pipeline `schema.rs:84–92` intentionally normalizes Arrow through `StructField::try_from` and then `spec::FieldRef::try_from`. The first converter interprets TIME, interval, UDT, GeoArrow and Variant field metadata; normalizes view/string/binary and container representations; and maps physical timestamps to Spark semantics (`proto/data_type_arrow.rs:72–194,206–323`). The second converter retains Spark user JSON metadata rather than all Arrow metadata (`proto/data_type.rs:48–70`). The reverse path needs `PlanResolver` and its configuration (`pipelines/schema.rs:176–183`, `sail-plan/resolver/data_type.rs:301–397`). There is no corresponding general Arrow-to-spec converter in sail-common or sail-common-datafusion in this revision.

Consequently, reusing an extracted spec merger for ORC now would require either extracting both conversions and their policy/dependency context, or introducing an ORC-only conversion pair. The former is substantially broader than mergeSchema; the latter duplicates normalization and risks dropping nested field, TIME/interval and CHAR/VARCHAR metadata. A generic trait abstracting both schema representations would also expand the public surface before a second actual caller exists.

The focused Arrow helper does contain a second short representation-specific structural traversal. This tradeoff is explicit: do not claim the pipeline merger was reused wholesale. Shared semantic metadata types already centralize TIME validation and interval union; no new JSON format or generic conversion is needed. Do not combine an optional pure-spec extraction with this critical path merely to move code. A later pipeline migration must separately preserve current view/UDT/Geo/Variant normalization and declared-schema equality behavior.

## Exact merge contract

1. Match root fields using the captured schema-inference case policy. For the currently qualified ASCII names, case-insensitive normalization is lowercase ASCII. Preserve left field spelling and order; append right-only fields in right order. A matching field keeps the left ordinary metadata and ORs nullability. An unmatched field is cloned without making it nullable merely because it was absent from the other schema.
2. When matched root fields merge their data types, subsequent STRUCT matching is case-sensitive. ARRAY elements and MAP keys/values recurse with that current type merge behavior. Do not thread the outer case-insensitive flag through all descendants. Spark `StructType.scala:620` calls `merge(leftType, rightType)` with the default `true`.
3. Merge **Fields**, not bare Arrow DataTypes: TIME precision and interval qualifiers live on fields, including list elements and map key/value fields. Parse/check these before a physical-type equality shortcut. Different TIME precisions fail even though both storage types are `Time64(Nanosecond)`; equal precision retains the left declaration. The current canonical ORC TIME output always has valid precision metadata. Unannotated nanosecond TIME is not silently precision 9 or default 6.
4. Same-family interval types merge by the union of qualifiers (`min(start)`, `max(end)`), using `SparkIntervalMetadata::wider`. Different interval families fail. On a changed union, replace only the interval semantic metadata key while retaining all other left metadata. If supporting unannotated YearMonth/Duration(Microsecond) from other normalized callers, use the existing Connect default qualifiers explicitly; do not infer that missing metadata means equal to every annotated subtype. The ORC bridge itself emits the annotation metadata.
5. Decimal128 merges only when scales are equal, choosing maximum precision. Do not rescale. Ordinary primitive types require logical equality: no INT/BIGINT widening and no Null-to-any promotion. LTZ and NTZ remain distinct; this schema operation does not cast stored values. ORC normalizes every file to the same captured display timezone before merging, so differing display labels are not a current file-inference input.
6. Rebuild containers from left fields, preserving their metadata and role/name conventions; array element/value nullability ORs. MAP key/value types merge positionally, with canonical non-null key and entry fields, not by treating the wrapper as arbitrary user struct fields. Keep left map sortedness. Validate any structural assumptions rather than indexing malformed Map fields unchecked.
7. Preserve left schema-level metadata as an explicit Sail provenance convention; Spark StructType has no equivalent schema-level metadata map. This is not a statement that the first file's Spark version describes every merged file. The caller should initialize from the first usable schema, not an empty metadata-free Schema fold that would lose that first file's metadata.
8. Do not use `Schema::try_merge` or listing `try_merge_normalized`: the former merges user metadata and promotes Null, and the latter delegates to it after physical normalization (`listing/utils.rs:57–76`). Neither has the required semantic metadata or nested case behavior.

## Independent duplicate validation

Merge success does not imply that the resulting file relation has legal field names. Spark checks the final data schema and partition schema separately with the original session resolver (`DataSource.scala:455–463`), recursively through STRUCT, ARRAY and both MAP roles (`SchemaUtils.scala:85–101`). The validation must also run for mergeSchema=false and a single inferred file: no pair merge occurs in those paths.

Existing `sail-common-datafusion::column_change::validate_field_names(fields, case_sensitive)` recursively handles Struct/List/LargeList/Map (`column_change.rs:60–84`). It can be called without `alter_schema`, which would reject zero fields. Canonical ORC uses List, canonical map roles and no FixedSizeList, so this existing traversal covers the actual bridge output. Do not claim it is a complete general Arrow schema validator: it omits FixedSizeList and several other Arrow containers, checks artificial map wrapper field names as well, and its error text/duplicate choice is not Spark's error class/message contract. A small extraction/re-export of this existing function into a neutral schema module is optional organizational work, not a prerequisite or a reason to duplicate it.

For case-insensitive Unicode, Rust `to_lowercase` in the existing validator is not proof of Java behavior. Spark merge normalizes using `Locale.ROOT`, but duplicate validation uses Java's default-locale `toLowerCase`. Existing per-file ORC matching has yet another retained implementation boundary. The current reference establishes ASCII behavior only. Keep this distinction visible and decide any unsupported-domain guard explicitly; do not silently advertise general Unicode parity.

## Retained observations and what they establish

`/tmp/sail-sdp-orc-schema-merge-case-reference` contains 16 file-read observations (13 success, 3 schema-analysis errors) plus 8 separately labelled direct JVM merge diagnostics. This audit independently verified all 35 inventoried files and all six retained source files against the pinned Git objects; it did not rerun the probe. PyArrow wrote these files; the installed Spark jars' recorded hashes do not prove build provenance from the source pin.

- CI root `Value`/`value` coalesces and reads both rows.
- CI merge of differently cased nested STRUCT fields, list-element STRUCT fields and map-value STRUCT fields retains both names internally, then fails `COLUMN_ALREADY_EXISTS` at relation/schema analysis.
- The matching CS cases preserve both fields and read null for the absent spelling.
- CI merge=false reads one selected schema and successfully matches both files. Thus rejecting every file's possible alternative nested spelling before the final merge is not a substitute for the correct merge/validation phases.
- Direct JVM merges intentionally use uppercase left and lowercase right and confirm left spelling and nested two-field intermediate outputs. File reads happened to select the lowercase schema first. That observation does **not** establish lexicographic path ordering.

The earlier 11-file schema-evolution reference separately establishes that mergeSchema=true must reach past the first ten sampled files, TIME(0)/TIME(3) conflicts, same-family interval qualifiers union, and cross-family intervals fail. Per-file requested-schema TIME/interval reinterpretation is a separate contract and must not be reused as merge compatibility.

## ReadFormat caller impact

Fable's integration audit agrees that ORC has the needed Arrow input, but `ReadFormat::infer_schema` currently lacks the captured `SourceInfo.read_case_sensitive` argument while explicit preparation and scans already carry it. A small default-preserving inference context/hook change must provide that value before implementing this caller. Do not independently look up an unrelated worker setting or add a Connect dependency.

- ORC inference opts into the existing All file selection and consumes its grouped ordered ObjectMeta entries; merge=false stops at the first usable nonempty physical-root schema, merge=true visits every eligible schema. Keep object identity and resource-bound footer reads unchanged.
- Fold from `Option<Schema>` (first usable schema), then call duplicate validation once on the final inferred data schema using the captured session case policy. Keep schema error context at the ReadFormat boundary so callers can identify the conflicting files/types. Exact Spark error-class translation is a separate API concern.
- Explicit schema preparation returns the supplied nullable logical schema, including Some(empty), without eager file inference/merge. It does not pass through this merger; requested-schema checks remain in the per-file adapter. Do not accidentally reintroduce inference through the default explicit-schema hook.
- Final partition fields and data fields retain their separate validation/matching policies. The shared partition preparation/binding commits must not be folded into this merge helper.
- Existing CSV/JSON/Parquet/Avro/Arrow inference and existing pipeline inference remain unchanged. Do not change every format to this policy because the helper lives in a shared crate.

## Small reviewable implementation units and acceptance cases

1. Shared Arrow semantic merger and focused unit tests, plus its module export only. No new dependencies are needed in sail-common-datafusion. Tests must compare complete Fields, including metadata, rather than only Arrow DataType equality.
2. Default-preserving inference context/case propagation, if not already landed by the ReadFormat work. A custom legacy format proves the default path is unchanged.
3. ORC ReadFormat merge option/default resolution and actual caller wiring, including independent final duplicate validation. Reader options/registration and public qualification remain their own units as planned by Fable/root.

Meaningful helper tests:

- Left order/spelling/user metadata wins on conflicts; right-only metadata is retained; matched nullability ORs and unmatched nullability is unchanged. Schema-level metadata follows the documented left convention.
- Root CS versus CI pair, then the three retained nested shapes: CI pair merge returns both nested spellings, independent final CI validation fails; final CS validation passes. Validation also rejects an already duplicated single schema, independent of pair merging.
- Equal TIME precision accepts; different precision rejects at root and in a nested element/role despite equal physical Arrow storage. Malformed semantic metadata and physical mismatch must not be hidden by equality.
- YEAR/MONTH and DAY/SECOND qualifier union with left user metadata retained; different families fail, including one nested case.
- Decimal equal-scale precision widening and unequal-scale rejection; INT/BIGINT and Null/INT incompatibility controls. Same LTZ versus NTZ storage unit is not logical equality.
- Canonical MAP role/name/metadata/nullability preservation and malformed shape diagnostic.

Meaningful integration/reference tests:

- >=11 files with the last file adding a field or introducing a TIME conflict; merge false versus true, and per-read option precedence over session default.
- Use the four retained case fixture pairs to check actual inference schema/order and the three independent nested duplicate failures. Assert values for successful relations so requested-schema mapping is exercised too.
- Explicit Some(empty) bypasses merge; no hidden file footer/type-merge request from a default hook.

Do not add an exhaustive mirrored precision/type matrix. If desired, a small Connect-side comparison test can run the existing Arrow→Connect→spec path and the new helper on a few canonical schemas, without moving that conversion into production shared code.

## Remaining boundaries

General Unicode/default-locale semantics, exact file enumeration/parallel reduction ordering, exact duplicate-name error identity, noncanonical Arrow extension types and map-key schema-merge reference cases remain unqualified. The chosen All listing order is deterministic per URL group in Sail but is not established Spark enumeration parity. The current work must expose these as limitations or followup decisions; they do not justify importing Connect into data-source or silently replacing the pipeline's declared-schema contract.
