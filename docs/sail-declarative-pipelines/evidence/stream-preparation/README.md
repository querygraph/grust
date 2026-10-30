# Stream preparation ownership

Recorded 2026-10-30T05:35:47.971635+00:00. Sail `30f943ef9152f42b183100733b867511e8570901` is based on
`f3d32b89597edba155805a2ce5922f83b8821d7a` and contains only the common component prerequisite.

StreamPreparation publishes a control handle before a caller invokes foreign
plan construction. Cancellation seals its resource scope immediately, and a
later handoff either installs the prepared stream or sends it directly to the
existing cleanup owner. Preparation failure and guard abandonment use that same
owner, preserving typed query and cleanup causes. No forwarding task is added.

StreamCompletion.resources_drained qualifies whether every registered supervisor
join was observed. A drained scope can still contain failed supervisors; callers
must inspect cleanup_result. Runtime interruption reports false. A nonblocking
completed snapshot lets the later runner retire only joined jobs. The resource
report's errors accessor shares original typed causes rather than strings, and
can be used when an interrupted cleanup is joined again later.

Four new tests cover cancellation before handoff, typed construction failure,
abandoned preparation/completion waiters and runtime loss before or during drain.
All 103 common-datafusion library tests, formatting and strict all-target,
all-feature Clippy pass. All 16 managed-stream tests also pass in an optimized
binary under one busy process per logical CPU (10 here); owned load
processes were terminated and joined. Receipts retain the exact commit, binary
hash, compiler/profile options and logs. This is a stress check, not a performance
measurement or exhaustive concurrency proof.

This commit does not activate LocalJobRunner, alter JobRunner.stop or change
session deletion. The [selected design](../../LOCAL-STREAM-OWNERSHIP-DESIGN.md)
and caller audit retain those separate obligations. No public SDP, original Scala,
ORC writer, Iggy or CDC execution verdict follows from these library tests.
