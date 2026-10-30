# ORC writer compression model

Recorded 2026-10-30T02:56:38.637466+00:00. Sail `88a8ecfcb8ca070357ef1d28bba0db08e7d95ed3` adds a typed Spark4.2.1 codec model. Selection is compression, then orc.compress, then an already-resolved session default or ZSTD. Validate only the selected value: an overridden invalid lower-priority value cannot fail selection, while an explicitly empty higher-priority value remains invalid. Operation values are lowercased without trimming. The frontend must supply SQLConf-resolved session values when snapshot wiring is implemented.

Eight source-defined names map to seven ORC kinds (none/uncompressed share NONE). LZO and Brotli are recognized but return native capability errors; unknown names retain the option key and original text in InvalidOption. Five supported native codecs create valid empty ORC files whose footer compression kinds are checked. The public ORC factory still rejects writing.

Formatting/strict Clippy and228 data-source library tests pass, including four new tests. Exact pinned Spark option/codec sources and native capability source are retained. No fresh Spark runtime was executed, and no public SDP coverage count changes. Generated option-layer loading, immutable Connect session defaults, semantic schema admission and the actual sink remain later W3/W4 work; this is W3's codec component only.

Two gate preparations stopped before compilation at the2GiB free-space precondition. Cleanup receipts retain the individually checked closed artifacts removed from isolated gate targets. The earlier uncompiled candidate remains recorded; the final test additionally checks actual stored footer codec kinds. No runtime failure or weakened assertion is claimed.
