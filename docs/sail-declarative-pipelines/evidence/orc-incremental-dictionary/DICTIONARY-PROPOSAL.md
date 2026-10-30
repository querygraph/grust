Recorded: 2026-10-30T00:41:35.318383+00:00

# Native dictionary initialization proposal

Read-only proposal. Native base `9f23442e7f9e019c0ec3b0a2d6491929967d41e3`; the separately frozen skip draft is present but untouched. No cargo, builds, gates or repository edits.

## Current dependency order and intrinsic limits

Immutable base anchors: `src/array_decoder/string.rs:66-82` initializes the full dictionary via `next_byte_batch(dictionary_size, None)` before constructing the index decoder; `string.rs:117-149` preflights/allocates full i64 LENGTH scratch, decodes all LENGTH, validates lengths, reads DICTIONARY_DATA, then validates the Arrow string array. Row PRESENT is only decoded later by `mod.rs:101-118`; retrieving its stream during factory construction does not decode it. `src/column.rs:40-45` defaults absent unsigned dictionary_size to zero; leave its public API/default semantics unchanged.

The required final dictionary is a StringArray with i32 byte offsets and usize entry count. Therefore preflight checked `(entries + 1) * size_of::<i32>()` against usize/isize addressability, and enforce nonnegative lengths, checked i64 total and final `total <= i32::MAX`. Do not cap dictionary entry count at i32::MAX: arbitrarily many empty strings can have zero payload. Do not retain the obsolete full-count i64 scratch addressability check once scratch is fixed-size.

Local Arrow 58.4.0 source corroborates these boundaries: arrow-array `src/array/byte_array.rs:128-153` derives entry count from offsets.len()-1 and validates slices; `dictionary_array.rs:289-314` checks valid keys against values.len() and permits all-null keys; arrow-buffer `src/buffer/offset.rs:67-83` requires a nonempty monotone nonnegative offset buffer, not an i32 entry-count ceiling. These are source findings, not new runtime observations.

## Proposed minimal files

- `src/array_decoder/string.rs`: replace only dictionary initialization with private `read_dictionary` helper; keep direct string/binary, dictionary index decoding, casting, and skip behavior unchanged. A small private byte-payload read helper may be extracted if needed to avoid duplicating the current allocation/read code, with unchanged semantics and no policy expansion.
- `src/array_decoder/length.rs`: expose existing `check_offset_buffer_size` at pub(super) visibility for the actual final dictionary offsets. Avoid repurposing `check_length_buffer_size` (which also preflights a now-unneeded full-count i64 buffer), `new_length_buffer` (which allocates one), or `skip_lengths` (which has different limits/error precedence).
- `src/array_decoder/string/dictionary_tests.rs`: new focused child test module, declared from string.rs, so dictionary fixtures do not further crowd existing materialization/skip tests. Existing real unsigned RLE fixture helpers may be reused; no need to change their behavior.

## Incremental LENGTH algorithm

1. Check final offset-buffer addressability with no full-count allocation. Start offsets with one zero and fixed i64 scratch of a modest internal chunk size (e.g. 1,024). This chunk size is an implementation buffer size, not a format/count limit.
2. Decode min(remaining, chunk_size) LENGTH values using the existing actual RLE decoder. Only a successful decoded chunk proves those entries exist. Retain validated cumulative offsets with fallible amortized Vec growth (`try_reserve`, preserving TryReserveError through native I/O OutOfMemory); never reserve/zero from the whole declared entry count. Offset growth must remain addressable and never exceed the preflighted final number of offsets.
3. Preserve current semantic error precedence precisely: current code decodes *all* LENGTH before it validates any value, and checks the i32 offset bound only after nonnegative/checked-i64-sum validation. Track running checked i64 total and the first negative/sum-overflow error. Stop retaining offsets once invalidity or an i32 overflow makes a successful final array impossible, but continue bounded LENGTH decoding. A later LENGTH decoding error still wins. On successful completion of LENGTH, return the first negative/sum error, otherwise enforce the final i32 offset ceiling using the full total and declared dictionary size. An early i32 overflow must not mask a later negative/sum error. This continuation preserves existing logical error order; it is not a rollback guarantee or a work quota.
4. If all lengths validate, build the monotone i32 OffsetBuffer and read DICTIONARY_DATA using the existing total-sized fallible reserve, limited read, and Arrow validation behavior. No data read occurs until LENGTH validation succeeds. Retain current payload truncation/UTF-8 error categories; the skip unit's new successful-short-copy EOF rule does not need to change materialized dictionary errors.
5. Return a non-null StringArray dictionary, and leave row PRESENT/index decoding and DictionaryArray casting unchanged.

The proposal removes count-controlled i64 scratch, not the required final offsets or dictionary payload. Existing payload reservation follows validated LENGTH totals and remains potentially large. A separate payload-allocation policy change would need its own scope; this is not a universal OOM or heap-accounting guarantee. New incremental reserve failures have resource causes; exact historical allocation-failure timing cannot be preserved when eliminating the historical up-front allocation.

## Empty dictionaries and PRESENT

- Absent dictionary_size and explicit zero both still produce the empty dictionary. Do not inspect unused LENGTH/DICTIONARY_DATA bytes for zero entries.
- Empty dictionary with all-null row keys remains valid; an actual non-null index into the empty dictionary still fails existing Arrow key validation.
- Dictionary initialization remains eager before row PRESENT. All-null rows or malformed row PRESENT must not hide malformed nonempty dictionary LENGTH/DATA.
- Dictionary entries themselves do not receive row PRESENT; only the index array does. Empty-string entries use repeated equal offsets and are not null entries.

## Focused test plan

1. Declared u32::MAX with empty LENGTH and with one tiny entry then EOF: real decoder fails promptly, bounded decode request wrapper confirms chunk size, DICTIONARY_DATA remains unread. No huge buffers or real giant data are needed.
2. Existing RLEv1 and RLEv2 direct/short-repeat negative-length fixtures: reject as native OutOfSpec before DICTIONARY_DATA. Tiny `[i32::MAX, 1]` and `[i64::MAX, 1]` fixtures check offset versus sum overflow without payload allocation.
3. Explicit ordering controls: early negative plus later malformed/truncated LENGTH must return the later decoder error; early i32 overflow followed by negative must return negative; same arrangements across a chunk boundary. No dependent payload read. These distinguish preserving current precedence from merely failing.
4. Factory-level minimal dictionary ORCs with bad dictionary LENGTH/DATA and bad or all-null row PRESENT confirm dictionary initialization precedes row PRESENT/index work.
5. Absent/zero dictionary size with all-null rows and deliberately unused malformed LENGTH/DATA still succeeds; a non-null zero index into an empty dictionary still fails bounds checking.
6. Valid dictionary with empty, repeated, and nonempty strings plus nullable/nested-parent row indices preserves exact values. A >chunk-sized dictionary of mostly empty strings with a final nonempty entry verifies offset continuity and selection of the last entry.
7. Truncated dictionary payload and invalid UTF-8 retain the existing Arrow error path; a decompressor failure retains its native I/O cause. Parent owns runtime qualification.

Do not combine this unit with RLEv2 delta fixes, primitive allocation redesign, a new value/count cap, lazy dictionary elision for all-null rows, or payload accounting policy.
