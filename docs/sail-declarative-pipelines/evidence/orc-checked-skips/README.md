# Bounded ORC skip decoding and exact consumption

Native `e9690a1eaefa35963554f44d45b8a54fd0ab0196` replaces request-sized PRESENT and LENGTH scratch
with fixed chunks. It checks signed lengths and usize conversion before dependent
work and splits requests before aggregate usize overflow. Skips may span more
than the i32/i64/usize materialized limits in aggregate. List/map child requests
preserve order; string/binary skips require every promised byte. Short successful
copies become UnexpectedEof, while original I/O/decompressor errors are retained.

Eighteen new tests execute on this 64-bit host. They use real malformed/truncated
RLE and PRESENT streams, child decoders, byte payloads, null parents and valid
cross-chunk continuation. Counted children verify large skip arithmetic without
claiming actual giant-stream execution. Two independent source reviews found no
blocker. Formatting, strict Clippy, 349 native tests (eight ignored) and 228
no-default-feature tests pass. No failed gate attempts occurred.

Sail `5cfe24e4f0bd46394efd9af30def9a22504f38e5` vendors the exact gated package with fifteen patch
revisions, source/hash/license checks and unchanged runtime lock. Formatting,
strict Clippy and 192 data-source tests pass. This vendor gate does not rebuild
the public CLI or rerun the execution crate; the preceding codec commit has its
own exact execution receipt.

[The frozen handoff](HANDOFF.md) records scope and source identities.
[Incremental dictionary preparation](DICTIONARY-PROPOSAL.md) is a read-only design
for the next unit, not part of this verdict. Dictionary initialization, RLE delta
arithmetic and remaining allocation paths stay separate. No total-heap guarantee,
public ORC registration or SDP runtime acceptance is asserted.
