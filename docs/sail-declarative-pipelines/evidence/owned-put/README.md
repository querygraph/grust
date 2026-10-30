# Retained PUT result ownership

Sail `590fc2f9d3cbd489d430d04af0cce0255a5b2da0` adds TaskResourceScope.run
and the small owned_put.put helper. The existing spawn/admission/join machinery
owns the future; the result receiver is only an observer. Returned factory errors
share the same typed DataFusion cause between caller and scope drainage. Lost
observers do not abort the supervisor. The API is for completed result values;
it must not return raw multipart handles requiring later async disposal.

The PUT helper invokes the provider only after scope admission and retains its
actual future through caller loss and scope cancellation. A held forwarding store
writes real InMemory storage after release. The test cancels/joins its caller,
requests cancellation, proves drainage is held and the object absent, releases
the PUT, joins clean drainage, then deletes the published object. Other tests
check the same typed PermissionDenied/PutFailure cause (including Arc identity)
with live and abandoned observers, sealed admission without provider invocation,
and an unpolled call admitting no work. These use channels, not elapsed time as
ordering evidence; deadlines only bound broken fixtures.

All **107 common-datafusion library tests pass**, with formatting and strict
all-target/all-feature Clippy. The **4 focused tests pass optimized under ten
owned busy processes**; every worker was terminated and joined. The exact detached
commit stayed unchanged during gates, and the optimized binary hash was checked
before branch advancement. No dependency or lockfile changes. No production
pipeline calls the new helper yet, so the public selection was not repeated.

The first candidate516105dbb passed its gate, then was superseded by a stronger
observer-type assertion and more precise interruption documentation. Both source
objects, its passing logs and the refinement diff are retained. It was not a
failed gate. No unchanged-production regression control applies to a new API
absent from the old source; the separate late-publication baseline remains valid.

This component is not the full effect adapter or session barrier. Provider error
visibility/replay classification, nested runtime-wrapper qualification, whole
multipart creation/parts/complete/abort ownership, context/registry routing,
Parquet child tasks and actual checkpoint/ORC integration remain required work.
The execution owner must retain/drain the scope; runtime loss can report failure,
not clean completion. No memory-bound, public writer, streaming/CDC durability or
original Spark suite verdict follows from these component tests.

Raw receipts/logs/source patches and historical harnesses are retained.
provenance.json hashes every other packet file; harnesses use the recorded
absolute worktree paths and fresh output directories.
