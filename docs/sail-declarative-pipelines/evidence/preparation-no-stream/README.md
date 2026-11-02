# Preparation exits without an artificial stream or caller error conversion

Sail `f9adaaf41653a38b8dfb0f32684428ea0b0ef8de` adds StreamPreparation.finish()
and cancel(). Both consume the guard and return its existing ManagedStreamControl.
finish seals resource admission without cancellation; cancel latches cancellation
and starts independently owned cleanup. An earlier control cancellation remains
latched when finish is called later. Neither method takes or coerces the caller's
typed result, manufactures an empty stream, nor calls an upstream schema method.
The control's own cancellation result and cleanup_result remain distinct from that
caller result. The existing fail/Drop path only renames its private helper;
its typed error/abandonment behavior remains unchanged.

Three new tests exercise normal no-stream finish with admitted work held through
closure, explicit cancellation with a lost completion observer, and finish after a
previous cancel request. They check admission sealing, actual drain pending until
settlement, watcher semantics, shared immutable reports and clean cleanup separately
from the control's cancellation result. The prior121 tests also pass.

Control `a151a55b9005903b4a15c4ffc62ab270da38654f` changes only monotone
`state.canceled |= cancel` to assignment. The identical final test fails because
finish clears the previous request and its report becomes successful. Fixed exact
fmt, strict all-target/all-feature Clippy,124 library tests and124 optimized tests
under ten joined busy workers pass. Source/log/binary and control test blobs were
checked before conditional branch advancement.

No runner trait, bound preparation object, planning context or protocol is installed
by this unit. The [design](../../PRE-PLANNING-OWNERSHIP-DESIGN.md) selects the bound-
executor API shape and these guard exits, while keeping context capture timing,
actual runner admission/stop and simultaneous-error transport policy explicit next
work. Caller-side typed SparkError identity still needs real integration tests;
this component never receives that error and cannot itself qualify the RPC path.
No dependency change or widened public/Spark verdict: latest CLI gate is47c473e6b.

SHA256.json covers files except itself. Historical absolute paths and binary hashes
name advancement-time evidence; replay into fresh source-pinned outputs rather
than overwriting old receipts. The existing Apple linker unwind-size warning did
not fail builds/tests; strict Clippy passes without suppression.
