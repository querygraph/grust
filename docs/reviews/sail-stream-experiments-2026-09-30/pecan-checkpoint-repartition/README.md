# B1: opt-in checkpoint repartition experiment

Recorded 2026-09-30T19:33:39.142228+00:00. Querygraph/Sail branch `work/pecan-checkpoint-repartition`,
commit `fe44428c9bfb43680affed0abae07240220df852`, parent `b569e75de625885b3d919fa4196b2e0bed14c618`.

`GraphAlgorithms(spark, repartition_checkpoints=False)` omits only the keyless
`repartition(partitions)` immediately before each owned staging write. The strict
boolean option defaults to `True`, preserving existing behavior. The common
controller applies it to input snapshots, intermediate checkpoints and final
result staging for Pecan and Grenada. This does not change result export,
algorithm choice, benchmark configuration, or any default.

The existing ownership, uncertain-write, cancellation, readback, empty-schema,
column/type, row-count and commit/cleanup logic remains in place. Omitting the
repartition declares no keyed layout, preserved distribution or output file-count
guarantee. No speed or memory improvement has been measured for this change.

## Exact source and validation

The [final patch](final.patch) is the complete parent-to-commit change. The
[final exact gate](exact-v2-gate/receipt.json) ran in a detached worktree at the
commit above and verified unchanged source/runtime hashes before and after:

- 78 unit tests passed, none failed or skipped. The whole package selection
  `-m "not integration"` deselected 83 integration tests.
- Four of those integration tests then passed against installed Sail 0.7.0:
  real SQL/Parquet round trips with repartition enabled/disabled, each for empty
  and nonempty data containing duplicates and nulls. The other 79 integration
  tests were not run in this gate.
- The SQL tests use test-only temporary ownership paths. They do not exercise
  GraphUtils, an all-algorithm run, a worker process cluster, or shared storage.
  The installed runtime is identified by bytes in the receipt; it is not
  claimed to be built from the candidate or its parent.

Unit coverage pins strict public option validation before server ping, default
behavior, actual public `_run` propagation through snapshot and body writes,
selected writer identity, schema/empty/count semantics and uncommitted failure
ownership. Existing cleanup/cancellation controls run with both settings.
The public propagation regression was added following independent review; the
production files did not change after the first candidate.

[Gate command and environment](run_gate.py), [source fingerprints](source-receipt-v2.json),
[unit output](exact-v2-gate/unit.log), [SQL output](exact-v2-gate/local-sql.log)
and [exact verdict](exact-v2-gate/verdict.txt) are retained. No Rust build or remote
workload was run for this candidate. Local gate duration is not performance evidence.

## Preserved attempts

The first candidate's tests passed, but the system Python 3.14 gate runner failed
while parsing JUnit XML because its libexpat lacked a required symbol. Its
[runner error](candidate-gate/runner-error.json), logs and original runner remain.
No commit was authorized by that failed runner. The next runner used the existing
venv and completed [75 unit + 4 SQL](candidate-gate02/receipt.json), followed by an
[exact initial commit gate](exact-gate/receipt.json). Independent review then
requested the public-controller propagation regression, giving
[78 unit + 4 SQL](candidate-v2-gate/receipt.json), followed by the final exact
commit gate above. The initial unpublished commit was amended; only `fe44428c9bfb43680affed0abae07240220df852`
is the delivery candidate, not a two-commit sequence.

The v2 precommit guard's transient stdout mislabeled the delta's base as `b569`;
its guard and JSON source receipt correctly used initial commit `1aa42ac71`.
The final patch, commit parent and final exact verdict above are authoritative.
The print-only label was corrected in [the guard](verify_candidate.py).

## Remaining qualification

Before drawing operational conclusions, use the real GraphUtils extension and
unchanged native/runtime on a small process cluster, compare default versus
opt-out on the same fixtures and resources, and retain every outcome. Include
empty/isolated vertices, duplicate edges, weighted and unweighted traversal,
WCC and PageRank fixtures plus cleanup/cancellation and failed-write ownership.
Record actual optimized/physical plans, input/output row counts and staging file
counts to establish what shuffle was removed and what the reader reconstructs.
Then measure a bounded representative workload's elapsed time, process/cgroup
memory and spill with matched order/resources. This qualification has not run;
the option remains an experiment and the default remains enabled.

## Fork delivery

At 2026-09-30T19:34:34.102313+00:00, the clean exact branch was pushed to `querygraph/sail` and
`refs/heads/work/pecan-checkpoint-repartition` independently read back as `fe44428c9bfb43680affed0abae07240220df852`.
The [delivery receipt](delivery.json) records gate and artifact hashes;
[independent review](independent-audit.json) found no blocker. No upstream
push or default promotion occurred.
