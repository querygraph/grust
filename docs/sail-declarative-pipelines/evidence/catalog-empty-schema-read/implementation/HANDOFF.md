# Named-table empty catalog schema compatibility

Frozen one-file Sail change: empty stored catalog schemas become absent source schemas at named-table resolution, allowing ordinary runtime inference. Nonempty fields and their existing metadata, constraints, location, source options, and catalog execution context are unchanged. Direct data source reads retain `Some(empty)` and their existing meaning.

This follows pinned Spark `FindDataSourceTable.readDataSourceTable`, whose explicit compatibility rule infers empty stored schemas at runtime. Delta already normalizes empty schemas downstream; Iceberg ignores this carrier for data and metadata reads. No lake-specific branch is needed.

No new resolver harness was added: parent explicitly selected the existing real public regression and explicit-empty controls rather than approximately 200 lines of session/catalog/mock setup. The original public gate failed 295 passed / 1 failed before this change; this handoff does not claim a rerun or successful public qualification. Same-binary ORC/Parquet/JSON controls remain `/tmp/sail-sdp-orc-catalog-control.{py,json}`.

CREATE-time schema inference/persistence and arbitrary catalog metadata are separate shared catalog work. This fallback does not populate DESCRIBE metadata or claim that improvement. E registration/tests are untouched.

Formatting and diff whitespace checks passed. No cargo build/test, gate, commit, or push was run by the agent. Root owns detached verification and the unchanged public regression. Exact source identities and planned checks are in `source-audit.json`; `change.patch` is the complete production change.

Finalization: root advanced exact candidate `75ac384c4c042a9b81793f41c0df944b5217a91a` after formatting, strict Clippy and 37 plan-library tests passed. Root prepared the candidate before the final comment shortening; the advance helper refused that comment-only mismatch before branch mutation. Root restored the exact gated comment, with no functional change or Rust failure. The preceding handoff and both comment variants remain retained. Public runtime retry is separate and is not qualified by this library result.
