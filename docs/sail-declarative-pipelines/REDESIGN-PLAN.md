# Delivering recoverable pipelines in reviewable increments

Build one complete durable append path before adding keyed change capture. Append
exercises source replay, checkpoint alignment, preparation, fencing and completion
without also deciding the representation of per-key versions. Preserve native
Extensions and develop the Comet scalar boundary alongside that work; their package
integration joins the same execution model.

This is the delivery reference for the proposals. The streaming proposal owns the
shared protocol; change capture and Extensions explain their additional contracts.
The overall review owns implementation status. This plan defines the first milestone,
its unresolved choices and the evidence required before replacing existing behavior.

## First milestone: one real source and one enforced target

Recommend a Delta transaction-log source feeding a separate filesystem-managed Delta
target, initially through Sail’s local job runner. Read an identified initial snapshot
or declared starting version, then tail append commits. Adapt the existing Delta
range reader into a continuous `StreamSource`; do not schedule a series of bounded
queries. Preserve the public pipeline declaration and normal table reads.

The [Delta source plan](DELTA-REPLAY-SOURCE.md) defines descriptor admission, bounded
manifest capture and the continuous reader as separate reviewable increments.
The existing reader already records table identity and version ranges. Add durable
schema and file-manifest identity, reproducible within-range progress and incremental
file consumption. Bind progress to logical files and rows rather than task splitting.
Initially reject data-changing rewrites, incompatible schema changes, lossy read options
and missing history. An exhausted range must not hide table recreation. Required files
must remain available or recovery must fail explicitly.

This is a production ingestion use case with existing Sail reader and writer seams.
Native rate sources, including the checkpoint-capable prototype, use wall-clock data
and cannot currently replay. A deterministic synthetic source would help testing but
would not qualify this milestone. An Iggy source remains useful later; it adds broker
retention, topology and client-dependency qualification to the same core integration.

Select the target acceptance mechanism through the [review agenda](REDESIGN-REVIEW-PACKET.md).
One candidate extends the existing staged Delta commit mechanism behind one
commit-authority process. That process accepts ownership-bound effects and publishes
exact accepted content. The deployment must deny workers and other clients direct
mutation of the target log and published data. Staging must not leave accepted content
mutable by an obsolete owner. A property checked only by cooperating Sail writers is
insufficient enforcement.

That staged-authority option requires a concrete storage-permission and durability
design. An existing catalog that can enforce the contract is the preferred alternative;
ordinary catalog serialization alone cannot. The bounded-runtime reference authority
adapter has been qualified for one authority process, not power loss, concurrent authority processes or
restoring an old database. Select and qualify the backend, restart policy and protection
against stale authority restoration before building its production adapter. Refuse
unsupported authority configurations explicitly.

Build target creation and enrollment through that authority. The existing fenced
writer accepts only an already existing filesystem-managed table, so attaching it
unchanged would leave a bootstrap gap. Schema changes, refresh and maintenance must
use enforced paths or receive explicit refusals. The first milestone has no unmanaged
write fallback.

## Bound the implementation and its review cost

The estimate is eight to ten implementation slices, usually 200–600 changed production
lines plus focused tests per slice. This is a planning estimate, not a measured diff
or a promise that the system is a small wiring change. The existing reader is about
800 lines; authority control and transition modules together are about 1,600. Ports
need separately reviewable comparisons, and an unexpectedly large interface change
requires revisiting the design before adding more machinery. These slices do not
prescribe the number of upstream pull requests.

| Reviewable unit | Dependency and discriminating evidence |
| --- | --- |
| Live source controls | Bind requests to the actual execution and registration. Idle reads wake, obsolete handles fail, cancellation closes pending requests, and ordinary reads retain their behavior. |
| Delta replay descriptor and reader | Use those controls to capture identified boundaries. Restart with pinned schema and manifests; detect missing data and source recreation. |
| Authority storage and acceptance | Settle deployment enforcement first. Persist owner transitions and exact effect acceptance; reconcile lost replies and reject stale authority. |
| Delta publication and enrollment | Use the authority for append, absent-table creation and recreation. Another permitted client cannot bypass it. |
| Typed configuration and prepared output | Normalize the effective computation, stream immutable output chunks under memory and disk limits, and persist a complete prepared record before effects. |
| Recovery coordinator | Compose the proven source, preparation and target interfaces in one job. Finish original pending effects before advancing progress. |
| Public lifecycle and resource qualification | Exercise bounded and continuous runs through the public API, final completion, cancellation, slow consumers and crash recovery. |

Source controls, configuration and authority research can proceed independently.
Prepared-work integration depends on stable source and computation identities and
the target acceptance contract. Local recovery is the first delivery boundary;
distributed routing and graph-wide alignment remain required subsequent work, not
capabilities inferred from passing the local path.

## Acceptance uses actual process failures

For each case below, inspect the resulting Delta table through its ordinary reader
and compare exact rows and multiplicities with an independently specified result.

- Restart before preparation, after preparation, after acceptance, after publication
  and before completion recording. Resume the original boundary and effect identity.
- Lose the acceptance response. Reconcile the same request, reject changed content
  under its identifier, and fail closed while the authority is unavailable.
- Pause owner A, let B take over, then resume A after it reloads current metadata.
  Reject new A effects while allowing completion of previously accepted exact content.
- Recreate source or target, remove required input history, change schema and capture
  an empty range. Refuse unsupported changes without advancing progress.
- Create and enroll a new target; exercise every exposed mutation entry point and
  attempt direct publication from a client without authority credentials.
- Bound memory, spill and retained artifacts with idle input, slow consumers and
  interrupted cleanup. A completed stream must not report success before its final
  durable effects finish.

Existing component and bounded-runtime tests provide controls, not proof of these
integrated cases. Retain correct Spark-facing behavior and add explicit expectations
for stricter source admission. Do not weaken assertions merely to obtain a pass.

The current public tests under `python/pysail/tests/spark/pipelines/` provide a
concrete starting corpus. In `test_delta_sources.py`, retain
`test_a_snapshot_then_the_new_commits`, `test_an_empty_table_is_a_start`,
`test_starting_version`, `test_a_starting_version_applies_only_to_a_first_run`,
`test_a_starting_timestamp_before_the_table`,
`test_commits_without_data_changes_add_nothing`,
`test_a_replaced_table_is_a_different_table` and `test_a_delta_target_runs_twice`.
Retain empty-flow completion in `test_triggered_execution.py` and failed-run exit
status in `test_end_to_end_cli.py`.

The bounded mode permits options such as `ignoreChanges`, `ignoreDeletes`,
`skipChangeCommits`, exclusions and `failOnDataLoss=false`. The durable path must
test their explicit refusal under its stricter admission contract. Keep the existing
mode's assertions and introduce separate durable-mode expectations. Define
`startingVersion="latest"` continuation explicitly. The current unfinished-batch
replay test edits checkpoint files and expects duplicates; it is not a crash test
or an exactly-once oracle. Missing-history execution and the failure cases above
need new tests. This corpus mapping comes from source inspection, not a new run.

## Extend the proven path without changing its guarantees

Distributed execution next routes controls through driver and task ownership and
aligns boundaries across real fan-in, shuffle and replicas. It needs task-attempt
replacement and multi-worker failure tests. Add managed Delta and Iceberg only after
their adapters enforce the same ownership contract at every admitted publication path.

Change capture then adds once-evaluated normalization, original-row validation, interval
reduction and durable versions for live and deleted keys. Choose atomic target-associated
state or fenced sidecar recovery before its merge implementation. Verify checkpoint
regrouping, conflicts hidden by later winners, partial effects and ordinary table access.

Port the existing extension host through package identity, worker resolution, relation
placement, memory admission and cleanup. Preserve its DataFusion interface as a control
when adding explicitly selected Comet scalar exports. Package and worker qualification,
not standalone adapter probes, establishes integration. A C relation interface remains
an independent capability decision.

Performance work accompanies each stage. Resolve material mixed-marker fragmentation
and startup costs without changing event ordering or failure behavior. Typed YAML,
JSON and API configuration share one authoritative model; optional Dhall produces the
same validated input. Migration of the existing runtime follows integrated recovery,
fencing, resource and interoperability evidence, including pending work and retained
change-capture versions. The full replacement remains the completion criterion.
