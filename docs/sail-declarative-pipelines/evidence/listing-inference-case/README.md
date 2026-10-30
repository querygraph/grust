# Captured read case policy during schema inference

Sail `18b1eed311c3bc6f66758595faf4eadb131af48e` passes SourceInfo's captured case policy through ordinary
inference, legacy empty-schema fallback and both default explicit physical
inference branches. ReadFormat::infer_schema gains one required bool parameter.
All seven existing format bodies retain their behavior; this unit adds no ORC
format or schema merge policy.

One new test crosses both captured policies with both parser normalization
settings over absent and empty supplied schemas, making eight real source
creations. Two existing explicit-schema tests now assert the policy received by
required and optional physical inference, including failures. Reconciliation,
post-partition validation and scan behavior remain covered.

Formatting, strict Clippy and all 202 data-source tests pass on the exact detached
commit. The [frozen handoff](handoff/HANDOFF.md) retains source hashes and scope.
No failed gate attempts occurred. This is a library API/plumbing verdict; it
adds no public ORC, streaming/CDC or full Spark SDP acceptance claim.
