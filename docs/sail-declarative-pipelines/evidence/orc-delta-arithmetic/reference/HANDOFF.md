# RLEv2 delta arithmetic handoff

Base native commit: `5937e8a8f1154aff333818dc365ffc6367c84d5f`. Origin fetched before edits. Only `src/encoding/integer/rle_v2/delta.rs` and new `delta/safety_tests.rs` are in scope. No Cargo, dependency, shared NInt, writer, metadata, array allocation or other format changes.

## Selected arithmetic

A variable-delta run must declare at least two values. Reject a shorter run immediately after its second header byte, before base/delta payload reads, output pushes or scratch changes. Fixed-delta singleton runs remain accepted and consume their signed delta as before.

Add the signed first/fixed delta directly with explicit wrapping i64 arithmetic; never take its absolute value. Interpret packed 64-bit magnitude bits with wrapping add/subtract according to whether the original signed delta is negative. Zero takes the addition branch, matching Java's reader. A local conversion helper preserves the existing narrower i16/i32 representability check and error text after the 64-bit calculation. This deliberately does not make narrow-type overflow wrap, nor change shared NInt semantics.

This handles valid monotonic signed sequences whose deltas have bit63 set, including magnitude 2^64-2, and a first delta of i64::MIN. Additional wrap-boundary and zero-first-delta cases qualify the explicitly selected Java arithmetic behavior; they are not assertions that all such sequences are emitted by an ORC writer.

## Evidence and limitations

Apache ORCv1 delta specification: https://orc.apache.org/specification/ORCv1/#delta . Full HTML and the delta subsection are retained. The spec identifies the signed first delta and packed remaining magnitudes but does not specify overflow policy.

Apache ORC release2.3.0 tag resolves to commit `970565f2aea99420c7fefcfa3e5853ce3103a91c`. Pinned raw Java `RunLengthIntegerReaderV2.java:85-146` directly adds the signed first delta and uses Java long addition/subtraction; it takes the addition branch for zero. C++ `RleDecoderV2.cc:372-453` confirms the variable-length guard and illustrates that its final narrow casts differ from the retained Rust narrow-width checks. Full sources, exact line excerpts, SHA256s, LICENSE and NOTICE are retained in `source-audit.json`.

This is source-backed compatibility reasoning, not a newly executed Java/C++ oracle. No Java runtime or installed-class identity claim is made. The unit is not a universal malformed-varint, patched-base, primitive-allocation or integer-decoder safety audit. Writer policy remains unchanged.

## Tests

Eleven new focused tests use explicit raw byte fixtures rather than the native writer/header encoder. They cover all 31 nonzero encoded widths with invalid singleton length before payload/output, fixed singleton compatibility, i64::MIN first/fixed delta, valid increasing/decreasing sequences with packed magnitudes 2^63 and 2^64-2, fixed/variable signed wrap boundaries, unsigned base bit patterns, zero-first-delta direction, large valid narrow-type deltas, preserved narrow over/underflow errors, original truncated-stream I/O errors, and skip/continuation alignment through a width64 two-value run with no packed payload.

Two pre-existing varying-delta tests incorrectly shadowed their intended input arrays with empty scratch vectors before writing. The candidate renames only that scratch variable so both tests actually encode/decode their ordinary varying sequences and compare against the original arrays.

Author ran rustfmt and whitespace/source inspection only; no builds, tests, commits or pushes. Exact file hashes and formatter version are in `source-state.json`.

Suggested root-owned gates: formatting/strict Clippy, focused `cargo test --lib encoding::integer::rle_v2`, full default library suite, and full no-default-features library suite. Retain any failed candidate/log before correction as usual.
