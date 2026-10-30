# Named-table empty catalog schema compatibility

Frozen one-file Sail change: empty stored catalog schemas become absent source schemas at named-table resolution, allowing ordinary runtime inference. Nonempty fields and their existing metadata, constraints, location, source options, and catalog execution context are unchanged. Direct data source reads retain `Some(empty)` and their existing meaning.

This follows pinned Spark `FindDataSourceTable.readDataSourceTable`, whose explicit compatibility rule infers empty stored schemas at runtime. Delta already normalizes empty schemas downstream; Iceberg ignores this carrier for data and metadata reads. No lake-specific branch is needed.

No new resolver harness was added: parent explicitly selected the existing real public regression and explicit-empty controls rather than approximately 200 lines of session/catalog/mock setup. The original public gate failed 295 passed / 1 failed before this change; this handoff does not claim a rerun or successful public qualification. Same-binary ORC/Parquet/JSON controls remain `/tmp/sail-sdp-orc-catalog-control.{py,json}`.

CREATE-time schema inference/persistence and arbitrary catalog metadata are separate shared catalog work. This fallback does not populate DESCRIBE metadata or claim that improvement. E registration/tests are untouched.

Formatting and diff whitespace checks passed. No cargo build/test, gate, commit, or push was run by the agent. Root owns detached verification and the unchanged public regression. Exact source identities and planned checks are in `source-audit.json`; `change.patch` is the complete production change.
