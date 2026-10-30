# Owned mutation supervisor interruption

Sail `9d83baa8ba77b947dcadbb8b2921309a667c8f97` adds explicit mutation
registration to TaskResourceScope and uses it for owned PUT and multipart lifetimes.
A canceled/panicked task retains its original typed JoinError alongside the existing
CommitStateUnknownError. Generic spawn/run registration, cooperative cancellation
with confirmed settlement, and normally returned factory errors keep their existing
behavior. The completed-value run_mutation preserves run's no-raw-resource contract.
No new dependencies, registry routing, session change or writer activation.

Exact detached gates pass: formatting, strict all-target/all-feature Clippy,
**111 common-datafusion tests** and **198 execution tests**. Optimized CPU-load
runs pass all111 common-datafusion tests and all6 execution multipart tests;
each run used ten owned workers, all joined. Final qualification checks the exact
source, log hashes, both release binary hashes, worker terminal status, unchanged
regression/control identity and manifest/lock equality before branch advancement.

The key regression uses the actual execution adapter/TaskResourceScope and an
InMemory-backed multipart provider. It publishes the target, signals a held response,
and the caller verifies the payload. Only then is the I/O runtime hosting the scope
supervisor shut down; the drainer survives on another runtime. It requires both the
real canceled JoinError and nonretryable unknown classification in report.errors.
The same test blob on detached574399183 (production unchanged from beebb83d0)
fails at `assertion failed: !cause.is_retryable()` (expected exit101). This is an
observed classification defect after real publication, not merely a modeled schedule.

Owned PUT has a second real publication-before-runtime-loss regression, requiring
an interrupted observer, a failed/nonretryable scope report, the original typed
canceled JoinError and preserved payload. Other tests distinguish mutation panic
from generic resource panic, verify returned factory errors are not reclassified,
and allow a cooperatively canceled supervisor to confirm clean settlement. Existing
typed-provider-error sharing and all earlier scope/stream tests remain passing.

Initial evidence is retained:

- 64d5652a7 is the initial fixture-only compile failure: the async block inferred
  a DataFusionError result and could not convert the test timeout error. The block's
  boxed test-error type was corrected; the assertion stayed unchanged.
- 574399183 is the valid failing behavioral control, not integrated.
- 04d2a08da passed the combined library gate as a multipart-only fix. It was
  superseded by the same policy covering the other known owned mutation, PUT;
  it is not labelled failed.

Runtime loss here means loss of the supervisor's runtime. A nested I/O task can
instead fail while an outer supervisor returns a normal provider error; that path
still needs its actual stage/visibility policy. No universal provider/internal-task,
read-back durability, resumed disposal, checkpoint or session barrier is proved.
[Provider/runtime design checkpoint](../../PROVIDER-RUNTIME-OWNERSHIP-DESIGN.md)
records the remaining hook alternatives and discriminating tests. Returned PUT
provider errors remain an enclosing-protocol obligation. The frozen public/Scala
suite has not been substituted by these helper/runtime tests.

The qualifier and receipts use historical absolute coordinator and /tmp paths.
Inspect/adapt them before reproduction; do not overwrite historical evidence.
