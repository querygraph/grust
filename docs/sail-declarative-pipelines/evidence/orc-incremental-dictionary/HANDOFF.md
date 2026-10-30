Recorded: 2026-10-30T00:47:48.344106+00:00

# Native incremental dictionary initialization

Base `e9690a1eaefa35963554f44d45b8a54fd0ab0196` in `/Users/alexy/src/orc-rust-sdp`; fetched before edits, initially clean. Exactly three changed files, with SHA256/size/line counts in companion JSON. `string.rs` remains 445 lines; the new focused `string/dictionary.rs` module is 493 lines including its eight tests. No cargo command, builds, gates or commits ran here; direct rustfmt1.98.1 and git diff --check passed. Independent source review is requested and pending; root owns gates and commit.

The factory initializes dictionaries through a private helper using fixed 1,024-i64 LENGTH scratch plus 1,024-i32 offset scratch (12 KiB total). It preflights only the actual final i32 offset buffer `(count + 1)` addressability, then retains offsets incrementally after successful chunk decoding/validation with fallible amortized Vec growth. No declared-count-sized LENGTH allocation remains. Allocation failures preserve TryReserveError in native I/O OutOfMemory.

The helper preserves semantic error order: all LENGTH decoder errors precede negative/checked-i64-sum errors, which precede final i32 byte-offset admission and DICTIONARY_DATA reads. It defers the first validation error while continuing bounded LENGTH decoding, and stops retaining offsets once success becomes impossible. Entry count is not capped at i32::MAX. The final offset bound and original OffsetOverflow fields use the full accumulated total and declared dictionary count. Existing total-sized payload reserve/read/Arrow validation is intentionally unchanged; payload truncation/UTF-8 remain Arrow errors and decompressor failures retain I/O causes.

Eager dictionary initialization still precedes row PRESENT/index decoding. Absent dictionary_size continues to default to zero through unchanged Column API. Empty dictionaries do not inspect unused LENGTH/DATA; all-null keys remain valid and non-null keys into an empty dictionary still fail existing bounds checks. Dictionary entries have no null bitmap; empty-string entries have equal adjacent offsets.

## Source test inventory

Eight named tests (eight on64-bit, seven on32-bit), not yet runtime-qualified:

- `src/array_decoder/string/dictionary.rs:255` — `huge_declared_count_with_tiny_length_stream_uses_bounded_scratch` (64-bit only)
- `src/array_decoder/string/dictionary.rs:294` — `malformed_dictionary_lengths_precede_payload_reads`
- `src/array_decoder/string/dictionary.rs:305` — `all_length_decoding_precedes_negative_sum_and_offset_validation`
- `src/array_decoder/string/dictionary.rs:344` — `dictionary_factory_initializes_before_row_present_or_indexes`
- `src/array_decoder/string/dictionary.rs:372` — `absent_or_zero_dictionary_size_preserves_empty_and_all_null_behavior`
- `src/array_decoder/string/dictionary.rs:400` — `dictionary_factory_preserves_empty_repeated_and_nullable_values_in_both_rle_versions`
- `src/array_decoder/string/dictionary.rs:437` — `offsets_cross_chunks_and_dictionary_indexes_preserve_parent_nulls`
- `src/array_decoder/string/dictionary.rs:465` — `dictionary_payload_truncation_utf8_and_io_errors_keep_their_categories`

Fixtures include real RLEv1 plus RLEv2 direct/short-repeat malformed lengths; declarations above i32::MAX and at u32::MAX with empty/one-entry LENGTH; bounded decode-call checking; factory-level max-count failure; cross-chunk multi-error precedence; eager dictionary-vs-malformed/all-null PRESENT; absent/zero count with deliberately malformed unused streams; valid Dictionary/DictionaryV2 repeated/empty/null values; >chunk dictionary offsets and parent-null index alignment; and unchanged payload/UTF-8/decompressor error categories. No large data allocation is needed by these fixtures.

## Remaining boundaries

- The required final offset vector and dictionary payload can still be large for actually decoded valid entries. This is not a universal OOM/heap accounting guarantee or a count/value cap.
- Historical allocation-failure timing necessarily differs after removing upfront full-count scratch; logical stream/validation error precedence is preserved.
- RLEv2 minimum signed delta/short-run arithmetic and unrelated primitive materialization allocation remain separate units.
- No Sail/vendor, Grust, skip, Column API or direct materialization changes were made. The approved source proposal remains `/tmp/sail-sdp-orc-dictionary-proposal.md`.
