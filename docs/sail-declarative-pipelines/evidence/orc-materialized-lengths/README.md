# Materialized ORC variable-length validation

Native `9f23442e7f9e019c0ec3b0a2d6491929967d41e3` validates list/map/string/binary batch sizes and
decoded lengths before allocation or dependent child/payload reads. Offset count
and scratch byte size use checked addressability; scratch allocation follows
successful PRESENT decoding. Negative i64-held unsigned lengths, overflowing
sums and Arrow i32 offset overflow fail explicitly. Fallible scratch and byte
payload reservation failures become native I/O OutOfMemory errors. Row counts
are not arbitrarily capped at i32::MAX.

Eight new tests exercise eleven malformed real unsigned RLEv1/v2 encodings per
type family, child/payload read counters, huge-count admission, exact boundaries
and valid null/nested controls. Formatting, strict Clippy, 331 native tests
(eight ignored) and 210 no-default-feature tests pass on the exact commit.
The independently reviewed PRESENT/preflight/allocation order is preserved in
[the frozen handoff](HANDOFF.md). No failed native gate attempts occurred.

Sail `947f5123b59f71fe87578114855e2f065716ebde` vendors the exact package with fourteen patch revisions,
source/hash/license verification and unchanged runtime lock. Formatting, strict
Clippy and all 189 data-source tests pass. Native package excludes its integration
test files as upstream configured; full tests ran in the native checkout before
packaging, and included Rust bytes were compared to the exact qualified source.

Skip arithmetic/exact consumption, incremental dictionary setup, remaining
primitive allocations and RLE delta arithmetic remain separate units. This does
not establish a total-heap guarantee, public ORC registration or SDP acceptance.
