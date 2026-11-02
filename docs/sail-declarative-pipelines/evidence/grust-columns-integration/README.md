# Minimal Grust column kernel integration

Sail `02d39b5fead46b694725c97de1b2341793100ca2` vendors grust-columns from
Grust `727baa3e983a6a8b1d6055f8c3b0ccdb85bd78b3`, using the exact Fable tree
at Sail `71e4a94d910c7afa978eaf1cc98beccb5df92051`.
The four upstream files (Cargo manifest, MIT license, implementation, tests) match
both SOURCE.json SHA256s and immutable Grust blobs. Existing vendor verification
also passes for Grust topology and ORC.

The exact detached candidate passes formatting, strict all-target/all-feature
Clippy and all **16 kernel library tests**. Tests exercise resolver-driven
include/exclude, duplicate/unresolved requests, invalid resolver indices, required
keys and reserved prefixes. Case folding/lookup policy remains the caller's.
This kernel does not introduce a runtime or third-party dependencies.

Workspace membership and the kernel's own lock stanza are added together. The
qualification script asserts that every other locked package is unchanged and
that no consumer lock entry refers to grust-columns yet. The consumer manifest
and lock edge must arrive together in a later independently buildable unit; this
avoids the original offered vendor-before-consumer edge defect.

[Independent C4 review](../fable-c4-independent-review/README.md) covers the earlier
kernel/lookup oracle. This new gate qualifies only the kernel's integration into
the current coordinator tree, not a CDC caller, streaming execution, public CLI,
or the full original Spark SDP suite. No concurrency ownership behavior changed.

The source-extraction and qualification scripts preserve their original absolute
coordinator paths and fresh /tmp output expectations. Inspect before reproduction;
do not rerun the import on an already integrated tree or overwrite historical logs.
