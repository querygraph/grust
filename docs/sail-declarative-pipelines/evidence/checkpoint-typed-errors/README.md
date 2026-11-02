# Typed checkpoint and compensating-cleanup failures

Sail `34eb270d0041c2fe4b0801afbdda93ad838c51ab` preserves both typed causes
when checkpoint collection/publication and compensating cleanup fail. The result
is a DataFusion Collection containing the original commit error and the original
cleanup error wrapped with the checkpoint path. Successful cleanup still returns
the original error directly. No dependency or lockfile changes.

The tests invoke commit_checkpoint itself. The input returns CommitStateUnknown;
cleanup either succeeds on an empty InMemory prefix or fails looking up an
unregistered store. They verify nonretryable classification, original error type,
both collection members, path context and absence of a published descriptor.
The failure fixture performs no storage mutation and does not emulate partial
provider deletion or qualify effect drainage.

All **15 physical-plan library tests pass**, along with formatting and strict
all-target/all-feature Clippy. A fresh exact-commit CLI passes **300 selected
public cases and 67 upstream Python executions (63 unique IDs)** on Spark4.2.1.
The source remained detached/unchanged; the owned server stopped with no remaining
listener. The frozen public harness is the one archived in the
[local-runner packet](../local-runner-ownership/README.md), whose hash matches the
new receipt. No new original Scala registration is qualified.

Control e358384da uses unchanged base production plus only the new test module
and declaration. It fails the nonretryable-cause assertion (exit101, one failed
test). The same assertion passes with the fix. Control source hashes, exact patch,
harness and log are retained. The initial candidate failed strict Clippy because
explicit panic macros are forbidden; fixture branches now return test errors,
without weakening the assertions. That failed gate remains retained separately.

This corrects error preservation before owned-effect recovery; it does not add
an effect adapter or a session/cluster cleanup barrier. Streaming/Iggy, CDC and
complete SDP acceptance remain required work. Raw logs and compiler warnings are
unchanged. provenance.json hashes every packet file except itself; historical
harnesses use absolute paths and fresh output directories.
