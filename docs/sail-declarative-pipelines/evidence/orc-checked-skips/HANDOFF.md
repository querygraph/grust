Recorded: 2026-10-30T00:35:40.858196+00:00

# Native variable-length skip hardening

Base: `9f23442e7f9e019c0ec3b0a2d6491929967d41e3` in `/Users/alexy/src/orc-rust-sdp`; fetched before edits, initially clean. Seven decoder/test files are frozen, identified by SHA256 in the companion JSON. No cargo command, build, runtime gate or commit was run by this agent. Direct rustfmt 1.98.1 and git diff --check passed. Root owns detached gates and commit. Independent full-diff review remains pending; architecture policy notes were incorporated, and the metadata reviewer is currently assigned to the separate listing candidate.

The shared skip helper decodes LENGTH using fixed 1,024-i64 scratch (8 KiB) and validates each entire decoded chunk for nonnegative, usize-addressable lengths before dependent work. It combines counts with checked_add, flushing a child/payload request before usize overflow; there is no cumulative i32, i64 or usize skip-work limit. List skips invoke the child with validated requests. Map skips invoke keys and values for each request before advancing to the next request. Individual lengths must fit the child skip API's usize count.

Shared PRESENT counting now uses fixed 1,024-bool scratch (1 KiB). Parent-present and absent-present semantics are preserved, including no reads for all-null parents. PRESENT still completes before LENGTH decoding. A malformed later chunk does not roll back prior stream consumption; any error terminates this decoder operation.

String/binary skips compare successful io::copy's returned count with the exact validated request. A short successful read becomes I/O UnexpectedEof; underlying decompressor/I/O errors retain their original cause and kind. Payload skip uses no declared-payload-sized allocation. All four variable-length skip callers now use the same checked helper.

## Added test inventory

The JSON records 19 named tests: 18 active on a 64-bit target, with one alternate 32-bit addressability test (16 active on 32-bit). These counts are source inventory, not passing runtime results.

- `src/array_decoder/length/tests.rs:206` — `skip_lengths_use_bounded_chunks_and_preserve_the_next_length`
- `src/array_decoder/length/tests.rs:239` — `truncated_skip_lengths_fail_before_dependent_work_without_request_sized_scratch`
- `src/array_decoder/length/tests.rs:254` — `skip_totals_split_before_usize_overflow_without_an_arrow_offset_limit` (only 64-bit)
- `src/array_decoder/length/tests.rs:277` — `individual_skip_length_must_fit_the_child_count_type` (only 32-bit)
- `src/array_decoder/list.rs:200` — `malformed_skip_lengths_never_invoke_the_list_child`
- `src/array_decoder/list.rs:218` — `list_skips_across_length_chunks_and_parent_nulls_preserve_the_next_value`
- `src/array_decoder/list.rs:252` — `list_skip_propagates_truncated_child_values`
- `src/array_decoder/list.rs:267` — `list_skip_counts_can_exceed_materialized_offsets_and_usize_in_total` (only 64-bit)
- `src/array_decoder/map.rs:213` — `malformed_skip_lengths_never_invoke_map_keys_or_values`
- `src/array_decoder/map.rs:239` — `map_skips_across_length_chunks_and_parent_nulls_preserve_the_next_entry`
- `src/array_decoder/map.rs:272` — `map_skip_propagates_truncated_keys_and_values`
- `src/array_decoder/map.rs:290` — `map_skips_advance_keys_and_values_for_each_overflow_flush` (only 64-bit)
- `src/array_decoder/present_tests.rs:260` — `skip_present_counts_bounded_chunks_and_preserves_the_next_bit`
- `src/array_decoder/present_tests.rs:291` — `skip_present_preserves_absent_and_nested_parent_null_semantics`
- `src/array_decoder/string.rs:337` — `malformed_string_and_binary_skip_lengths_leave_payload_unread`
- `src/array_decoder/string.rs:361` — `string_and_binary_skips_require_all_promised_payload_bytes`
- `src/array_decoder/string.rs:367` — `skipped_payload_preserves_the_original_decompressor_error`
- `src/array_decoder/string.rs:411` — `string_and_binary_skips_across_chunks_and_nulls_preserve_the_next_value`
- `src/array_decoder/string.rs:423` — `skip_present_failure_precedes_lengths_and_all_null_parents_read_neither`

The fixtures use real unsigned RLEv1 and RLEv2 direct/short-repeat negative encodings (five per list/map/string/binary family), truncated LENGTH and byte-RLE PRESENT streams, real truncated list/map primitive children, short byte payloads including a promise above i32::MAX, and a malformed compressed payload retaining InvalidData and its OrcError cause. Valid controls cover fixed scratch boundaries, null parents, absent PRESENT, the next PRESENT bit, and materialization of the next list/map/string/binary value after a cross-chunk skip. Counting child decoders exercise aggregate totals above i32, i64 and usize without large allocations. A bounded wrapper around the actual LENGTH/Boolean decoders checks scratch call size.

## Explicit remaining boundaries

- Dictionary initialization still materializes its declared entry count up front; it remains a separate unit.
- RLEv2 minimum signed delta and malformed short-run arithmetic remain a separate unit.
- Other materialization/primitive allocation paths and arbitrary child-decoder implementations are not covered by a universal bounded-memory claim. The scratch guarantee here is for shared PRESENT counting and variable-length LENGTH scanning.
- Exact list/map child consumption relies on their child decoder skip contract; focused real integer-child truncation tests exercise that propagation, not every possible nested child codec.
- No whole-process memory guarantee, allocator redesign, arbitrary valid-value cap or cumulative skipped-data quota is introduced.
- The original source audit `/tmp/sail-sdp-orc-value-safety-handoff.md` remains an immutable baseline; prior PRESENT and materialized-length corrections are committed separately. No Sail/vendor or Grust files were changed.
