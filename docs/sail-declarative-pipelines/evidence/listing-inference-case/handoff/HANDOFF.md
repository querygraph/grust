# Listing inference case-context unit A

The required `ReadFormat::infer_schema` signature now ends with `read_case_sensitive: bool`, parallel to the existing explicit-schema hook. Its documentation identifies SourceInfo as authoritative; format implementations must not infer this policy from SQL identifier normalization or another session option.

`ListingDataSource::create_source` already destructures the captured SourceInfo flag. It passes that exact value when no schema was supplied or when an explicit empty schema takes the legacy inference fallback. The default `prepare_explicit_schema` passes the same value to both required-validation inference and optional case-insensitive physical inference. Error propagation, optional failure behavior, reconciliation, compression, file selection and scan context are unchanged.

Seven existing format implementations (Arrow, Avro, binary, CSV, JSON, Parquet, text) accept an unused parameter. An automated source comparison verified each file is byte-identical to the base after removing exactly that parameter line. No format opts into new matching behavior here. The required argument is a deliberate Rust trait API change; all in-workspace implementations and ReadFormat delegation calls were updated. Distinct DataSource/LakeSource inference APIs are unchanged.

## Tests and expected behavior

- New test `inferred_schemas_use_the_source_case_policy_independently_of_sql_normalization` invokes the real ListingDataSource over a registered in-memory object store. It crosses captured false/true with parser normalization false/true, and absent versus explicit-empty schemas. Every format inference call must observe the captured flag along with the independently configured parser flag; all resulting schemas keep their existing field spelling. No scan is needed to trigger inference.
- Existing explicit-schema success test now verifies case-policy observations for both required-validation settings and both case flags, preserving its schema reconciliation and post-partition validation assertions. Case-sensitive optional preparation still makes no inference call.
- Existing optional/required inference-failure test now verifies the policy passed before failure; optional reconciliation still swallows only the previously optional failure while required validation still fails.
- The existing case-policy scan test, explicit-empty override tests and file-selection tests remain in place. Their implementing/delegating formats accept/forward the new parameter without altering selection or preparation policies.

## Scope and gates

Exact eleven-file hashes and base Git blob identities are in `source-state.json`. No ORC registration, options, schema merge, timezone, source, codec, writer or Spark session bridge implementation is included. No repository instructions were found in this worktree; origin was fetched before edits. No builds, gates, commits or pushes were run by the author.

Author checks: nightly rustfmt, git diff --check, complete in-workspace ReadFormat implementation/call search, and seven-format body identity verification.

Suggested root-owned validation: `cargo +nightly fmt -p sail-data-source -- --check`; focused `cargo test -p sail-data-source --lib listing::source`; strict Clippy for the library/tests; full sail-data-source library tests. The single new test exercises eight source creations rather than asserting only a stored setter value.
