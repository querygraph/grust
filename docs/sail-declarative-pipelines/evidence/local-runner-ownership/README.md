# Local job preparation, cancellation and registered cleanup

Recorded 2026-10-30T05:58:33.244769+00:00. Sail `ec8e74d57de51149a774cd4f9048d82039704d0c` is based on the
separate [preparation prerequisite](../stream-preparation/README.md).

The local runner registers preparation before tracing/schema/execute factories,
with a fresh per-job resource scope. Stop seals admission and cancels every admitted
job before awaiting completion. A returned stream can remain unpolled and retained
by its caller while stop disposes it and waits for registered supervisors. Failed
or panicking construction also waits for its admitted cleanup.

Completed history is swept on later admission/stop; interrupted scopes remain
owned until their joins are observed. There is no forwarding task or claimed
hard bound proportional to peak concurrency. Typed cleanup failures survive job
retirement, with the first failure and first nonretryable failure retained in
bounded slots. Query failure with clean cleanup does not make stop fail. Repeated
stop waiters share existing completion; abandoning a waiter does not reopen
admission or drop cleanup ownership.

JobRunner.stop now returns a result. Both implementations and the existing session
caller change in this commit. The session helper invokes checkpoint cleanup only
after successful stop and preserves the original typed stop error. This does not
fix early Deleted/RPC acknowledgement, retain a failed-deletion session context,
or prove complete checkpoint-effect quiescence. Cluster stop retains the driver's
existing acknowledgement limitations; no new remote guarantee is claimed.

## Validation

All 103 common-datafusion, 192 execution and 29 session library tests pass (324
total), with formatting and strict all-target/all-feature Clippy. Nine local
runner tests cover stopped admission, held construction plus held cleanup, fresh
scopes, constructor errors/panics, query versus cleanup failure, later nonretryable
failure after retirement, lazy sweeping, abandoned stop and interrupted-runtime
recovery. Three session-helper tests cover pending/successful/failed stop ordering
and absence of a checkpoint registry. The nine runner and three helper tests also
pass in optimized binaries under one busy process per logical CPU. Receipts record
profiles, exact binary hashes and joined load-process exits. This is a stress
check, not a performance measurement or exhaustive concurrency proof.

A fresh CLI built at the same immutable commit passes all 300 frozen public cases
and 67 upstream Python test executions (63 unique IDs due inherited tests). The
public harness verifies Spark 4.2.1, exact selected case identities, source hashes,
CLI hash and owned server teardown. Its 300 cases combine the earlier 298-case
selection with the two corrected nested-materialization cases; withdrawn graph/
flow ORC configuration assertions are excluded. No original Scala registration
is newly qualified, and the canonical 462-registration inventory is unchanged.

## Retained failed attempt

Candidate `e8c47f2d9ccd3383ce03fe0a4b33ba20707ff33b` passed formatting and Clippy, then failed
one execution test: it assumed DataFusion Collection's Display prints every
member. DataFusion55.2 deliberately displays only its first error. The corrected
fixture inspects both retained members and still requires the later unknown-commit
cause to classify as nonretryable. The production implementation is unchanged
between these candidates. The initial common library suite passed; execution was
191 passed/1 failed, so the session suite did not run in that attempt.

The invalidated candidate's release compilation was stopped before a test verdict;
its owned process IDs, reason, partial logs and receipt are retained. It is not a
failed release test or a passing gate. The exact initial patch and fixture-only
correction are in failed-first-candidate. The failed Git object is retained under
refs/sdp/failed/local-runner-ownership-first.

## Remaining boundary

Only the owned stream and registered supervisors are joined. Legacy unregistered
operator tasks, manager-wide shutdown, truthful deletion outcomes, in-flight
checkpoint effects and cluster worker/driver shutdown require separate units.
Public ORC writing, Iggy streaming, CDC execution/recovery and complete Spark SDP
acceptance remain open. See the [design](../../LOCAL-STREAM-OWNERSHIP-DESIGN.md)
and its caller audit for these obligations. Fable's offered CDC commits are not
included in this candidate.
