# File-scan object identity transport

Sail `27ab945aaa3046d05a1f4aeb1e651fddf11db927` preserves listed object ETags and versions across
worker plan serialization for all seven existing file formats. A format-neutral
optional supplement binds entries to exact file-group/file positions and paths.
Restoration precedes format-specific scan settings and checkpoint partitioning.
Input-file metadata wrappers carry the supplement only on their inner scan.

The detached gate passed formatting, strict all-target/all-feature Clippy and
163 complete sail-execution library tests. Seven new tests cover optional
empty/absent/value identities, duplicate file paths with distinct ranges, empty
groups, partition values, projections, limits, malformed associations, legacy
absence, metadata wrappers, checkpoint hash partitioning, and execution of a
reconstructed JSON scan against the registered memory store. Removing the
supplement explicitly reproduces the earlier identity loss.

This is transport qualification. Existing readers do not thereby acquire
conditional-read semantics. Older workers ignore the new optional field on
known formats; identity preservation requires matching codec revisions. No ORC
format is registered by this unit, and there is no new CLI/full SDP verdict.

The source audit was made against the preceding Sail commit and locked
DataFusion 55.2.0/Arrow 59.2.0. Its ORC source proposals remain a handoff, not
implemented features. Raw logs, exact patch, source excerpts and hashes are
retained here. The initial gate failed on test-only API imports and a deprecated
schema constructor; its patch and logs are preserved. Assertions were unchanged.
