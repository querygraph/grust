# Local captured execution

Sail `7505e2ced6e51dce9d8fd43c37f5292263bdc58c` on
`16c43aa290026e8057952e3f2ae3826d4c81948b` opts local preparations into capture.
The object owns the same admission, runner borrow, ID and one ScopedSession.
Capture checks cancellation, snapshots authority once and installs the supplied
qualified registry. Errors/panics explicitly fail with a Shared typed cause,
returned to the caller and retained in the independent cleanup report. Caller
must save control before consuming capture. Local capture does not await/reap;
existing runner lifecycle handles completed admissions.

A private helper takes optional ScopedSession. Some derives its TaskContext;
None retains legacy late capture. Trace, canceled-factory refusal, managed stream
handoff and error/cleanup/reap paths stay shared. TaskContext and plan nodes own
runtime/config/extensions/functions; registered tasks own their captures. No extra
whole-state keepalive or new cleanup framework is introduced. Delta retained
store lineage remains a separate migration constraint.

Exact detached fmt, strict all-target/all-feature Clippy,136 common-datafusion+
228 execution libraries pass (364). Optimized filters captured_ and capture pass
6 and9 cases under10 load workers each, all stopped/joined. These overlap:
seven distinct local capture/default cases plus two unrelated codec cases; they
are not15 distinct capture tests. The local tests prove captured planning/execution
config7/child registry/same scope beside unchanged legacy7/child→9/parent; identical
cause Arc on canceled capture; stop/unpolled factory refusal; finish/cancel/drop
with held cleanup; and weak registry retention after raw-stream disposal while
registered task-owned I/O is held, released after completed drain.

Negative control `62fb06978f39554cea5f26184ca8c4444133020f` substitutes late authority
TaskContext only in the captured branch. Unchanged two boundary tests give1pass/
1fail: legacy passes; captured test detects9 instead of7. Retained warning about
unused Session import is a consequence of the intentional substitution; this is
a test control, not a strict-Clippy acceptance candidate.

No public caller, cluster, catalog/provider, default router, ORC writer, SDK or
CDC activation. Latest public CLI evidence is still09d2f0cb8 (300 selected+67
upstream); this local opt-in has no fresh public CLI verdict and does not establish
full original Scala SDP acceptance. The API does not brand a physical plan to
its originating snapshot. Scope-ignoring providers remain outside supervision.

SHA256.json covers packet files except itself. Historical helper paths/qualifier
identify advancement-time checks and assume the then-parent/binaries; do not rerun
blindly against a later HEAD. Replay into fresh worktrees/output paths.

Fable CF-0214 / Grust7d4bcb00 confirms construction, cancellation windows and
owned dependency/drop paths by source. Findings7.1/7.2 addressed by explicit
Rustdoc/design wording at a74c3f429: second capture consumes/cancels; registry is
a replacement, not merged.7.3 remains open: capture's panic branch has no dedicated
fixture; cancellation exercises fail, not construction panic.7.4: planning itself
is not refused after stop, only scope-registered factories/execute.
