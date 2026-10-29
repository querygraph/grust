# ORC source resource and listing foundations

Four independently gated Sail commits prepare the ordinary file-source path:

| Unit | Commit | Data-source library tests |
| --- | --- | ---: |
| Preserve read case policy through listing planning | `51ec5acf0` | 143 |
| Retain encoded range reservations with final Bytes owner | `9bba3434b` | 147 |
| Opt formats into stable all-file inference selection | `edbb01214` | 150 |
| Vendor the bounded native stripe-footer decoder | `c0c156d7e` | 150 |

Each receipt includes exact candidate, patch, formatting, strict all-target/all-feature
Clippy and full affected library-test logs. Native `056c066173` separately passes
315 tests (eight ignored) and 195 no-default-feature library tests, formatting and
strict Clippy. Its portable package is retained and matches the installed vendor
snapshot, including license and eleven patch revisions. The Sail runtime lock is
unchanged by the vendor update. No failed attempts occurred in these five gates.

[Resource contract](RESOURCE-CONTRACT.md) is the selected source design and its
earlier source audit. Requested encoded range bytes are admitted before I/O;
reported assembly capacity is reconciled after allocation and retained across
clones/slices until the final owner drops. SDK chunks,
native coalescing, codec/protobuf/dictionary allocations and Arrow output are not
included in that charge. This is not a total heap limit. Native decoded stripe
footer limits are opt-in and independent of file-tail limits; defaults remain
unchanged for other native callers.

Selected Sail defaults are 64 MiB for each encoded tail, decoded tail and decoded
stripe-footer budget, and schema depth 64 with root STRUCT at depth 0. Byte limits
are clamped to a finite local pool limit and isize::MAX; Unknown/Infinite pools
retain configured limits. Zero means zero. These are operational limits, not
Spark validity rules. The selected options, source/opener integration and worker
rebinding are subsequent work; this packet does not claim they are implemented.

Listing Sample retains the existing first-ten-nonempty-per-URL behavior. All uses
the same discovery filters, preserves complete object identities and URL groups,
and sorts files within each group before schema/compression/partition inference.
It is an inference selection, not a frozen execution manifest. ORC has not yet
registered a format that uses it.

Intrinsic stripe/value arithmetic, requested-schema adaptation, source and worker
codec, registry, writer, calendar/configuration parity and public Spark assertion
ports remain open. Streaming/Iggy and CDC runtime are not qualified by these
foundation gates. The full SDP objective and assertion inventory are unchanged.
