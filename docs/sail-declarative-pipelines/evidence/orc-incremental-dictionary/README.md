# Incremental ORC dictionary initialization

Native `5937e8a8f1154aff333818dc365ffc6367c84d5f` reads dictionary LENGTH entries in fixed chunks
and grows the actual offset vector only after decoding proves entries exist.
The declared count no longer allocates a count-sized i64 scratch buffer. Final
offset-buffer addressability, nonnegative lengths, checked totals and i32 payload
offsets still apply; dictionary entry count has no arbitrary i32 ceiling.

Initialization preserves LENGTH decoding errors before value-validation errors,
then dictionary DATA and Arrow validation, then row PRESENT/index handling.
Zero/absent dictionary size retains empty/all-null behavior. Payload allocation,
truncation and UTF-8 error categories are unchanged. Eight new tests include real
factory-level ORCs, maximum declarations with tiny streams, both RLE versions,
null parents, repeated/empty strings and cross-chunk offsets.

Exact formatting, strict Clippy, 357 native tests (eight ignored) and 236
no-default-feature tests pass. Independent source review passed; no failed gate
attempts occurred. Sail `43fe0dc841ec18b2a0e666f0bb05d01a95007852` vendors the exact package with sixteen
patch revisions, source/hash/license checks and unchanged runtime lock. Formatting,
strict Clippy and 192 data-source tests pass. This vendor commit has no execution
crate or public CLI runtime verdict.

[The frozen handoff](HANDOFF.md) and [approved proposal](DICTIONARY-PROPOSAL.md)
retain the sequencing contract and limits. Required final offsets/payload still
consume memory; this is not full native heap accounting. RLE delta arithmetic and
remaining primitive allocation paths stay separate. Public format integration,
writer and complete SDP acceptance remain open.
