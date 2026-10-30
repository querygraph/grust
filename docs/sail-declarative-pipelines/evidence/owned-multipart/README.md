# Retained multipart component qualification

Sail `4cb9aec14cd8aa8725e79326c968a5672dc4dd0e` adds
sail-object-store::owned_multipart. [Design and exact API boundary](../../OWNED-MULTIPART-SUPERVISOR-DESIGN.md).
The supervisor owns creation, FIFO provider part calls, concurrent part futures,
and complete/abort settlement. Losing command/result observers cannot abandon those
futures. No dependency/lock changes, legacy runtime-wrapper changes or checkpoint
routing are included.

The immutable detached candidate passes **33 object-store library tests**, fmt and
strict all-target/all-feature Clippy. **16 optimized multipart tests** pass under
ten owned CPU-load workers; all workers joined and the release binary hash checked.
The final qualification script checks the source pin, gate log hashes, release
receipt/binary, worker terminal status, notification-control test identity, and
unchanged manifest/lock blobs before branch advancement.

Held one-shot gates prove pending ownership during abandoned creation, active
parts, complete and abort. Fixtures wrap a real InMemory multipart upload; the
creation/affinity test creates that real upload inside the owner factory. Other
held tests construct their fixture upload before handing it to the test factory;
they establish subsequent lifetime/settlement ordering, not prior provider creation
admission. No-provider-before-first-poll uses a counted factory separately.
Cancellation is supplied through the supervisor's actual watch API. These are
retained supervisor tests, not installed TaskResourceScope/checkpoint adapter tests.

Other cases: part observers dropped before completion, FIFO invocation with parts
held concurrently, capacity reused across100 cross-thread observations, closed data
admission, both abort/complete precedence orders, empty completion, paired original
part+abort errors, uncertain complete error without blind abort, typed creation
failure, oversized capacity refusal, owner task interruption, and execution on the
owner runtime while observers run on another runtime. Tests use held events rather
than sleeps as ordering evidence; timeouts bound test observation only.

Initial evidence is retained without reclassification:

- Initial candidate d2768fa3c failed compilation: the test fixture omitted the
  ObjectStore trait import. Its source/ref and Clippy log remain.
- 36d3b0812,42f19a86a and b30924cee passed their then-current library gates and
  were superseded by stronger lifecycle/notification/capacity handoff coverage.
  They are not labelled failed. Source review found and corrected the Closed+
  cancellation state path before its dedicated regression was added.
- Detached control7e9633846 with the new notification test and old implementation
  fails at `part notification held admission lock`. The fixed commit uses the
  identical test blob. The control's historical debug binary hash was not captured;
  its immutable candidate and raw compile/test log are retained.
- An earlier control invocation accidentally ran in the editable source checkout.
  It was interrupted (exit130) after detecting the path error; no test result or
  verdict is inferred from it. Its log is notification-control.log. The independent
  detached control is notification-detached-control.log (exit101, expected failure).

No clean-disposal claim applies to complete failures, runtime loss or unqualified
provider-internal tasks. The existing wrapper's timed part wait/Drop abort remains
unqualified. Full original Spark4.2.1 SDP acceptance, public writer activation,
checkpoint routing, session/cluster cleanup and streaming/CDC effects remain open.
