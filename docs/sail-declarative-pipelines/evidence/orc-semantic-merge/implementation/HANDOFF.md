# Frozen Spark file-schema merger implementation

Only `sail-common-datafusion/src/{lib.rs,schema_merge.rs,schema_merge_tests.rs}` changed for this task. The first is a one-line export; production and tests are new. Existing pipeline merger, listing, ReadFormat, options and ORC modules are unchanged by this agent. Other agents/root own concurrent worktree changes. Source copies and exact hashes are retained here.

Public API: `sail_common_datafusion::schema_merge::merge_spark_file_schemas(left: &arrow_schema::Schema, right: &arrow_schema::Schema, root_case_sensitive: bool) -> datafusion_common::Result<Schema>`.

The implementation validates both complete schema trees before any merge, including equal and unmatched fields. TIME precision comes from validated field metadata; intervals use the existing shared typed metadata and `wider` operation. Same-family interval unions replace only their semantic key when necessary. Field names/order/user metadata and schema-level provenance remain left-biased; matching nullability ORs; unmatched nullability does not change. Decimal precision can increase only with a fixed scale; ordinary integers/floats/Null do not promote. Nested STRUCT merges reset to case sensitive after root matching. Map role fields merge positionally and retain left names/metadata, with explicit shape/key-nullability checks.

UDT metadata, Arrow extensions (including Geo/Variant), and marked Variant storage are explicitly unsupported. Noncanonical Arrow types also fail explicitly. No generic Arrow-to-spec conversion or data-source-to-Connect dependency was introduced. Inputs use the existing ORC bridge's canonical types; unannotated YearMonth and Duration(Microsecond) mean full default interval qualifiers. Timestamp inputs must already use microseconds and a common captured display timezone.

Duplicate-name validation deliberately remains independent. ORC inference should call existing `sail_common_datafusion::column_change::validate_field_names(schema.fields(), captured_case_sensitive)` on the final inferred schema, also when merge=false or only one schema was selected. Schema merge itself does not reject duplicate names. Architecture agent received this interface and owns ReadFormat integration.

Case-insensitive normalization uses the existing Rust lowercase convention. Equal Unicode names remain accepted; no guessed blanket guard was introduced. ASCII case behavior is qualified by the retained Spark reference, while general Unicode/Java default-locale parity remains unqualified. This helper does not choose file enumeration order or assert exact Spark error-class equivalence.

Ten focused tests (all source-only until parent gates):

1. `preserves_left_order_metadata_and_unmatched_nullability`
2. `root_case_policy_does_not_reject_equal_unicode_names`
3. `nested_case_merge_and_recursive_duplicate_validation_are_separate`
4. `time_precision_is_semantic_at_root_and_in_containers` (also complete LIST element metadata/name/nullability preservation)
5. `interval_union_retains_left_user_metadata_and_supports_default_qualifiers`
6. `decimal_precision_is_the_only_numeric_merge_promotion`
7. `invalid_semantic_metadata_is_checked_in_equal_nested_and_unmatched_fields`
8. `extensions_cannot_merge_as_equal_ordinary_storage`
9. `map_roles_preserve_left_fields_and_merge_semantics_positionally`
10. `malformed_map_shape_fails_even_when_unmatched`

Formatting and whitespace checks passed. No Cargo commands, compilation, tests, services, commits or gates were run by this agent. Root completed a source review before freeze. Independent Fable review was requested and may arrive separately; it is not represented as completed here.

Pinned source rationale, exact excerpts and verified Spark reference packet details are in `/tmp/sail-sdp-orc-semantic-merge-proposal/`. That read-only proposal predates this implementation; it must not be represented as a runtime gate receipt.
