# ORC null-stream error propagation

Native `bc0c0cef83` fixes a swallowed PRESENT-stream decode error in
`derive_present_vec`. The old match discarded Some(Err) as though there were no
nulls. The new arm returns the original error before dependent value decoding.
Successful all-valid and parent/child null behavior remains covered separately.

Three tests use real truncated byte-RLE PRESENT encodings, a counted primitive
DATA reader, and complete flat/nested STRING files whose LENGTH stream would
produce a distinct varint error if reached. Valid null placement, absent PRESENT
and all-valid PRESENT are controls. Native formatting, strict Clippy, 323 passing
tests (eight ignored) and 202 no-default-feature library tests pass. No failed
attempts occurred in this unit.

Sail `25524aa551` vendors the exact qualified package, with thirteen
patch revisions, license, source/hash checks and unchanged runtime lock. Its
formatting, strict Clippy and complete 156-test data-source library suite pass.
This does not activate the new ordinary file-source drafts or add a public SDP
runtime result.

[Remaining value-safety audit](REMAINING-VALUE-SAFETY.md) retains source findings
about signed lengths, exact skips, dictionary allocation and RLE delta arithmetic.
Its PRESENT finding describes the prior baseline and is resolved by this packet;
the other findings remain separate pending units. No total-memory guarantee or
arbitrary value/stripe cap is introduced.

[Schema-merge reuse audit](schema-merge-reuse/HANDOFF.md) preserves three pinned
source excerpts for a later mergeSchema unit. Existing pipeline semantic merging
is relevant, but Connect dependency boundaries and the outer/nested case-policy
distinction need explicit treatment. This is source evidence, not a new probe.
