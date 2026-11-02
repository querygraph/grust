# Execution-owned multipart adapter

Sail `beebb83d0df5aff947bd1e20e0a69626c98c14bc` adds
sail-execution::owned_multipart::create and execution_error. This layer already
depends on both common-datafusion and object-store. No new manifest or lockfile
edge, fresh resource scope, runtime bridge or cached-store mutation is introduced.
The actual existing TaskResourceScope owns the entire prepared supervisor before
provider creation; TaskResourceScope.run is not used to return a raw resource.

Exact detached gates: formatting, strict all-target/all-feature Clippy and
**197 execution-library tests pass**. **Five optimized adapter tests** pass under
ten owned CPU-load workers, all joined; source/binary/log hashes were checked
before advancing the coordinator branch. The five tests exercise the real adapter,
TaskResourceScope, scope cancellation, shared drainage, and InMemory-backed uploads:

- Sealed and unpolled creation invokes no factory and registers no resource.
- Abandoned creation remains registered through a held abort after scope sealing.
- Lost commit and drain observers leave the commit owned; drainage remains pending
  until release. Publication precedes confirmed drainage; fixture deletion follows
  drainage. A sibling scope completes on the same underlying store and another path.
- A provider actually publishes and then loses its completion response. Both live
  and lost observers leave a typed Complete failure in the scope. The mapper keeps
  the original provider error Arc alongside CommitStateUnknownError, so report.errors
  and live observer mapping remain nonretryable. No blind abort or deletion occurs.
- Actual provider creation/part invocation/part polling/completion run on the
  existing scope runtime, while caller/observers use another retained runtime.

The detached control `b458be2f2a10df8754cb5aef8a78d6e28dc9fe45` changes only
the error mapper to omit its unknown-commit marker. The exact unchanged regression
fails at `assertion failed: !cause.is_retryable()` (expected exit101). Its receipt,
raw log and maker script are retained. This is a controlled classification failure,
not a failing verdict on the final candidate.

Initial fixture candidate884d51d34 failed compilation because NotImplemented was
constructed as a unit variant; object_store0.13.2 requires operation/implementer.
The fixture was corrected without changing assertions; its original source/ref,
receipt and Clippy output remain under initial/.

No production checkpoint writer invokes this adapter yet. Provider-internal tasks,
legacy RuntimeAwareMultipartUpload's timeout/Drop cleanup, runtime loss during
commit, operation-specific registry routing, memory admission and session/cluster
barriers remain unqualified. Interrupted/JoinError outcomes are not covered by the
Complete-returned-error marker test; they need a separate uncertainty/ownership
policy before activation. This packet does not claim public CLI or original Spark
SDP suite acceptance. The frozen public selection was not repeated for unused
component wiring; new actual adapter tests and full execution library gates cover
this unit.

[Lower component design](../../OWNED-MULTIPART-SUPERVISOR-DESIGN.md).
The scripts retain historical absolute coordinator paths and fresh /tmp receipts.
Inspect/adapt output paths before reproducing; never overwrite evidence or advance
another participant's branch.
