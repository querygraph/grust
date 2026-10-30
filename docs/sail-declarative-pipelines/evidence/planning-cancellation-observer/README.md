# Caller-owned preparation cancellation observation

Sail `97f9983d5310c8ef8c7818e3f4177fd577951312` adds
TaskResourceScope.cancelled(): a latched request observer, including cancellation
before its first poll. It does not seal admission, start drainage or certify any
provider outcome. No new dependency, runner/registry/Connect/session activation.

Tests prove observation leaves admission open, noncanceling seal does not satisfy
it, late/dropped/multiple observers work, siblings remain independent, and request
observation can finish while a mutation still prevents drainage. A held preparation
future borrows a local !Sync Cell; it stays on the caller's task. An entered barrier
precedes stop, cancellation selects the request, the future's Drop is observed,
and only then is preparation released and the stop completion report delivered.
This is a component handoff test, not actual runner pre-planning admission.

Controlf6f191c823b8cb16d6bdcef262ba9def25625af7 changes only the observer to
wait for a new change. The identical test fails because cancellation already
requested before subscription is lost. Fixed fmt, strict all-target/all-feature
Clippy and120 library tests pass; all120 optimized tests under ten joined busy
workers pass. Exact source/log/binary and control test blobs were verified before
conditional advancement. Latest public CLI gate remains47c473e6b; the new unused
observation method has no widened public or original Spark-suite verdict.

The first optimized executable also passed120/0 and all workers joined, but the
wrapper asserted that substring “0 passed;” must be absent; it also occurs in
“120 passed;”. The receipt correctly has test_exit0 but no successful wrapper
outcome. Its logs/receipt/script remain under initial-wrapper-failure. The corrected
stress.py recognizes a positive exact test summary with zero failures; separate
parser checks cover0,4,120 and a failing summary. A fresh output run passes the
corrected wrapper. No old output is overwritten or relabelled as a successful gate.

[Design](../../PRE-PLANNING-OWNERSHIP-DESIGN.md) selects explicit finite preparation
ownership and caller-polled cancellation direction; exact lease/handoff, session
authority, effect-outcome and writer memory APIs remain open. There is no detached
planning task, no eager stream forwarding and no complete session barrier here.
SHA256.json covers files except itself. Scripts/receipts retain historical absolute
paths and advancement-time binary hashes; replay with fresh source-pinned outputs.


## Registered I/O after the borrowed waiter is gone

Test-only Sail `d8e5213c6461a64874d59ef565c07eb943b8d3fb` appends the combined
CF-0127 counterexample to the original three tests; all production and existing
test bytes are unchanged. Actual factory entry on a distinct I/O runtime precedes
stop. The local borrowed waiter is dropped, then its guard is released, but the
actual scope drain stays pending while registered I/O is held. A publication
marker deliberately becomes true only after cancellation, demonstrating that
cancellation is not rollback. The registered task settles before the completion
report can qualify drainage, while the primary cancellation error stays visible.
This is an owned runtime-task model, not qualification of opaque SDK children.

All121 library and121 optimized tests pass with fmt/strict Clippy and ten joined
load workers. Source/log/binary/old-test prefix were checked before conditional
advancement. The initial03f0a92e0 model passed the same counts; it is retained,
superseded by explicit polling of the actual drain and a registered-count assertion
so a merely unscheduled cleanup notification cannot establish the intended hold.
registered-io contains both exact positive packets and the final qualification script.

The first documentation snapshot36fa799a passed its checks but was not advanced:
Fable appended CF-0126/0127 during the gate, and the tree compare correctly rejected
the stale log snapshot. Those review entries are incorporated in the refreshed
snapshot; no peer entry is discarded and no successful code verdict is widened.
