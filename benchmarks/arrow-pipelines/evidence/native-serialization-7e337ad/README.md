# Borrowed native graph serialization qualification

Source `7e337ad`, Capitola, four nice Cargo jobs. Locked `grust-arrow`
all-feature tests passed **52 tests, zero failed, zero ignored**; warnings-denied
all-target Clippy passed. The shared implementation was instantiated and tested
against native Arrow 55, 58 and 59. Logs retain the complete command results.

Exact byte comparisons against core `Graph` serialization cover reordered and
sliced multi-batch tables, empty schema-only tables, property presence versus
null, scalar tags, escaping/Unicode, integer limits, nonfinite floats, isolates,
parallel relationships and duplicate external IDs. Inclusive byte counting uses
the existing bounded writer over `io::sink()`; one byte below the required size
fails without retaining encoded JSON. No graph rows or property maps are built
by the borrowed view; serialization holds per-batch column descriptors.

Follow-up `0e7abba` connects native input-policy capture and cached exact sizes
and is under full workspace qualification. Test-only `cda270f` additionally puts
explicit nulls into each typed scalar column; it awaits its own qualification.
These are unreleased changes, not automatic routing or a full execution-policy
claim. No performance or live-driver parity claim is inferred from these tests.
