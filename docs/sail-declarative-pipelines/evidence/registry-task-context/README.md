# Isolated task registry context

Sail `9579a7e8db8e4f6d08713690a88ecf30702886b5` adds
`ScopedTaskContext.with_object_store_registry`. It derives a RuntimeEnv using
DataFusion's preservation builder, installs the supplied registry only in that
new context, and keeps the existing TaskResourceScope. Invalid context/owner
pairs fail before derivation. The original `new()` still creates a fresh scope.
No dependency, resolver, session, provider wrapper or checkpoint activation change.

Tests exercise distinct stores through actual parent/sibling/derived lookup and
GET, shared configuration/extensions/IDs/all four nonempty function maps,
underlying pool/disk/cache Arcs, a real cached file-list entry and its shared
removal, cancellation sharing/isolation, and missing/mismatched owners. The
RuntimeEnv and CacheManager containers are new; underlying resources remain shared.
DataFusion's builder also preserves feature-dependent encryption registry state;
that conditional field was source-reviewed, not independently fixture-tested.
Original context tests are byte-equivalent after removing module indentation.

Exact detached fmt, all-target/all-feature strict Clippy and all115 library tests
pass. All115 optimized tests pass under ten busy workers, each stopped/joined;
the executable SHA256 was rechecked before conditional branch advancement.
SHA256.json covers copied raw logs/receipts and the qualification script.
Historical absolute /tmp paths remain in receipts; adapt fresh paths before replay.
The qualifier describes advancement-time checks; later builds can replace binaries.

[Both earlier failed candidates](../registry-context-in-progress/README.md) remain
retained: nested module lookup, then wrong URL fixture type. The successful fixture
uses DataFusion ObjectStoreUrl, preserving the original isolation assertions.
No public CLI rerun is claimed for this unused helper. Latest public gate remains
exactly a2cee8f00 (300 selected public/67 upstream). Full original Spark4.2.1 SDP
acceptance, actual checkpoint routing, planning-owner propagation, provider joins
and session/distributed cleanup remain incomplete.
