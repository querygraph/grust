# Consuming captured preparation contract

Sail `16c43aa290026e8057952e3f2ae3826d4c81948b` on ece5b6aed adds an opt-in capture transition and
CapturedJobPreparation inheriting the existing ownership/control/execution API.
Default unsupported capture explicitly cancels the admitted preparation; the caller
keeps typed NotImplemented and saved control independently reports cancellation
and cleanup. No local override, public caller migration or cluster support yet.

The legacy-wrapper test uses an actual local admission but deliberately inherits
the default, so it remains valid when LocalJobPreparation later opts in. It checks
typed capability error, completed/clean resource drain, cancellation rather than
abandonment, and stopped runner with no active jobs. Exact detached fmt, strict
all-target/all-feature Clippy,136 common-datafusion +223 execution libraries pass.
One optimized case passes under10 live CPU-load workers, all stopped and joined.
This is capability/default-cleanup evidence, not captured execution qualification.

Retained attempts: cc27bad79 contract-only and361287054 cleanup-default candidates
passed their Rust gates but were not integrated. Their default dropped the guard.
c74a81116 added explicit cancellation and stronger assertions: strict Clippy failed
on prohibited expect_err() in the test; its optimized test passed. The accepted
candidate replaces expect_err with error propagation and reruns all exact gates.
No failed attempt or output is relabeled as passing.

Fable review8391b2ab and coordinator response CF-0210 are archived here. Supported
local capture construction failure must explicitly retain the typed error via
StreamPreparation::fail. Delta log-store lineage, whole-snapshot lifetime through
registered I/O, cluster worker transport and caller migration remain open. Latest
public CLI evidence remains09d2f0cb8 (300 selected+67 upstream), not this contract.
Full original Scala SDP acceptance is not claimed.

SHA256.json covers packet files except itself. Historical absolute paths identify
advancement-time evidence; replay helpers only into fresh worktrees/output paths.

Rustdoc clarification a74c3f429b092fd5cde6f65d36371760471a07f6 on7505e2ced
states that registry replacement requires complete registration/composition and a
second consuming capture uses unsupported cancellation. Detached nightly fmt and
non-Rustdoc source equivalence pass; no new library/runtime verdict claimed.
