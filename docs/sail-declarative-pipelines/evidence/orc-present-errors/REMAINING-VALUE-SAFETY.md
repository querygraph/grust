Recorded: 2026-10-29T23:50:15.256170+00:00

# Native ORC value-safety handoff

Read-only audit findings remain outstanding unless explicitly marked below.
Source repository: /Users/alexy/src/orc-rust-sdp.
All anchors refer to the immutable native baseline 2ecec391db0699019b55f731fc9eefd8971b3802, not changing draft line numbers.
No runtime qualification was performed for this audit.

## PRESENT correction (separate incoming unit)

- `src/array_decoder/mod.rs:231-251`: `derive_present_vec` suppresses `Some(Err(_))` as `None`.
- Current draft changes only propagation of this error and adds `src/array_decoder/present_tests.rs`.
- Real truncated byte-RLE PRESENT data exercises ordinary primitive and ordinary/nested string decoding. Primitive dependent DATA reads are counted and must remain zero. Complete string fixtures distinguish the original PRESENT EOF from a qualified later malformed LENGTH error. Valid null and all-valid controls are included.
- Root owns detached runtime/Clippy gates and commit. Until those pass, this is a source-reviewed draft only.

## 1. Materialized lengths and Arrow offset addressability

- `src/array_decoder/list.rs:71-80`: allocates i64 lengths, performs unchecked signed sum, casts to usize, requests child array, then constructs i32 offsets.
- `src/array_decoder/map.rs:82-97`: same unchecked sum/cast before key/value arrays and i32 offsets.
- `src/array_decoder/string.rs:119-143`: unsigned decoder produces i64 lengths; unchecked signed sum precedes only an upper i32 limit. Negative lengths pass that check; the cast can request an enormous capacity. Binary shares this implementation.
- `src/encoding/integer/mod.rs:63-71,101-114`: unsigned encoding uses the same signed integer decoder representation, returning values unchanged.
- `src/encoding/integer/util.rs:475-497`: unsigned 64-bit bit patterns can therefore become negative i64 values; length users must check nonnegative results.

Suggested smallest next unit: a private shared checked-length helper plus list/map/string callers. Validate each length, checked totals/conversions and existing i32 output-offset limits before child/payload allocation. Check count + 1 and size multiplication for the involved buffers. Keep existing normal null/value behavior and no new arbitrary value/stripe cap.
Tiny fixtures: RLEv1 all-ones unsigned varint; RLEv2 64-bit direct/short-repeat all-ones values; `[i64::MAX, 1]`; `[i32::MAX, 1]`; nested list/map equivalents. Guard child/payload work to prove rejection occurs before attacker-sized allocation. Valid `[2, 0, 1]` with nulls is a control.

## 2. Skip arithmetic and exact consumption

- `src/array_decoder/list.rs:89-103`: unchecked length sum/cast before child skip.
- `src/array_decoder/map.rs:106-121`: unchecked length sum/cast before both child skips.
- `src/array_decoder/string.rs:167-186`: unchecked length sum/cast and ignored byte count returned by `io::copy`; truncated DATA can report success.
- `src/array_decoder/mod.rs:254-285`: PRESENT counting allocates proportional to the entire requested skip, rather than fixed scratch chunks.

Require nonnegative checked lengths and exact byte/child consumption. An i32 offset ceiling applies to materialized arrays, not aggregate skip work spanning many otherwise valid batches. Use bounded scratch chunks for length/PRESENT scanning and conversions compatible with child skip APIs; do not create a lifetime decoded-data ceiling. Tiny fixtures can use negative lengths, two promised bytes with one available, missing child values, null-parent skips and selected values after skipped rows to detect misalignment. Fake counting child decoders can exercise large totals without large allocations.

## 3. Dictionary initialization and allocation arithmetic

- `src/array_decoder/string.rs:65-71`: declared dictionary size immediately becomes `next_byte_batch` size.
- `src/column.rs:42-46`: dictionary size is optional u32 converted to usize; absent size remains zero under existing behavior.
- `src/proto.rs:255-265`: confirms the encoded dictionary-size field is unsigned u32.
- `src/array_decoder/string.rs:119,135`: immediate full lengths allocation and data capacity allocation.
- `src/array_decoder/mod.rs:100-117`: primitive child allocation uses unchecked element count times element size implicitly in Vec allocation.

A u32::MAX dictionary declaration requests roughly 32 GiB of i64 lengths on 64-bit before its LENGTH stream is read. Checked addressability alone does not reject this because the request is addressable. Decode dictionary lengths in chunks and retain validated entries with fallible growth, avoiding up-front full-count zeroing; enforce existing i32 dictionary byte offsets. Include checked count/element-byte arithmetic without claiming total memory accounting or universal allocator-OOM recovery.
Tiny fixtures: u32::MAX declaration with empty/one-entry LENGTH stream; negative dictionary entry length; summed offset overflow; truncated dictionary bytes; valid small nullable/repeated dictionary.

## 4. Separate integer-decoder issue

- `src/encoding/integer/rle_v2/delta.rs:85`: `delta_base.abs()` can overflow for i64::MIN.
- `src/encoding/integer/rle_v2/delta.rs:107`: variable-delta mode subtracts two from the declared run length without checking a length of one.

These execute before array-level length validation. Handle malformed run lengths explicitly and preserve valid extreme signed deltas rather than blanket-rejecting i64::MIN. Keep this as a separate integer-decoder unit with tiny byte fixtures; do not combine it with PRESENT or container-length changes.

## Boundaries

These are concrete source findings, not a complete untrusted-input safety audit. The selected resource design still excludes a universal memory-aware allocator, process RSS guarantee, arbitrary date/value ceilings and a cumulative decoded-data cap. Root owns sequencing, gates and qualification of each logical unit.
