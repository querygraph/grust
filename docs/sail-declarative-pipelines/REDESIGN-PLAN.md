# Delivering recoverable pipelines in reviewable increments

Build one complete append path before adding keyed replacements and deletions. Append
exercises input replay, saving intended output, rejecting replaced writers and finishing
writes after restart. Change capture then adds record versions to those established
contracts. Preserve native Extensions and develop the optional Comet scalar interface
alongside that work, subject to agreement on its package boundary.

This plan explains implementation dependencies and the evidence needed for each stage.
The streaming proposal owns the recovery design; change capture and Extensions explain
what they add. [HUMAN-REVIEW.md](HUMAN-REVIEW.md) records current readiness. The
[decision memo](REDESIGN-REVIEW-PACKET.md) identifies the mechanisms that need agreement
before further dependent implementation.

## Start with a real source and one protected destination

Recommend a Delta source feeding a separate filesystem-managed Delta destination through
Sail's local job runner. Delta records changes to table data files in a transaction log.
Read an identified initial snapshot or starting version, then follow new append commits
through a continuous `StreamSource`. Preserve public pipeline declarations and ordinary
table reads.

The [Delta source plan](DELTA-REPLAY-SOURCE.md) separates checking the saved source
description, capturing exact file lists, and reading continuously. Descriptions already
record table identity, schema and starting boundaries. The local append implementation
also saves exact file lists and positions within files. Progress identifies logical
files and rows, independently of a task's temporary assignment.

Initially reject data-changing rewrites, incompatible schemas, lossy read options and
missing history. Require immutable retained files and a stable storage location; checking
a table identifier cannot protect against arbitrary replacement between that check and
a read. Empty input must still detect table recreation. Missing required files must fail
recovery explicitly.

This is a practical ingestion use case with existing reader and writer integration points.
The native rate source uses wall-clock data and cannot currently replay it. A deterministic
synthetic source helps testing but does not qualify real ingestion. Iggy adds broker
retention, partition changes and client dependencies, so it is a later source option.

The local append adapter records ownership and publication in the same Delta log.
Review that mechanism and failure model before adopting it as a supported target.
Prefer a catalog
that can check current ownership and the exact write in one operation. Other options are
a required Delta writer protocol or a protected commit service that approves immutable
staged output before publication. The memo explains their different costs.

For the service option, storage permissions must prevent workers and other clients from
bypassing it. A worker that has lost ownership must also be unable to alter previously
accepted staged content. Specify service restart and restore behavior: the existing
bounded-runtime reference covers one authority process, not concurrent authorities,
power loss or restoration of an older database.

Create and register new targets through the selected mechanism. The local append adapter
creates metadata, required writer protocol and initial ownership together. Schema changes,
refresh and maintenance must use protected paths or be refused. The first milestone
includes no unchecked write fallback.

## Keep each increment small enough to inspect

The planning estimate is eight to ten implementation slices, usually 200–600 changed
production lines plus focused tests per slice. It is not a measured final diff or a
promise of trivial wiring. The existing reader is about 800 lines; the reference
commit-authority control and transition modules together are about 1,600. Review ports
separately, and revisit the design if an interface change grows beyond a manageable slice.
These units do not prescribe the number of upstream pull requests.

| Unit | Dependency and evidence |
| --- | --- |
| Controls reaching live sources | Bind requests to the actual execution. Idle readers wake; replaced handles fail; cancellation closes pending requests. |
| Delta description, file lists and reader | Use identified input boundaries. Restore the same schema and files; detect missing data and table recreation. |
| Durable ownership and write acceptance | Settle enforcement and failure scope first. Persist takeover and exact write decisions; resolve lost replies and reject stale authority. |
| Delta publication and target creation | Use that mechanism for append, creation and recreation. Show that another permitted client cannot bypass it. |
| Typed configuration and saved output | Fix computation meaning. Save immutable output under memory and disk limits before writing to the destination. |
| Recovery coordination | Join the proven interfaces. Finish original pending writes before advancing to new input. |
| Public lifecycle and resources | Test continuous and bounded runs, final completion, cancellation, slow consumers and process crashes through the public API. |

Configuration, source work and target research can proceed independently after their
relevant choices are resolved. Combining them requires stable source and computation
identities and a defined commit contract. Local recovery is the first delivery boundary.
Distributed controls and coordinated checkpoints across the actual graph remain separate
required work; local success does not demonstrate them.

## Test failures where state can disagree

For each case, read the resulting Delta table normally and compare exact rows and
multiplicities with an independently specified result.

- Restart before and after saving intended output, accepting writes, publishing them
  and recording completion. Resume the original input boundary and write identifiers.
- Lose a commit response. Look up the same request, reject changed content under its
  identifier, and stop safely while its outcome cannot be determined.
- Pause worker A, let B take over, then resume A after it reloads table metadata.
  Reject new writes from A while finishing exact output accepted before takeover.
- Recreate the source or target, remove needed history, change schema and capture an
  empty range. Reject unsupported changes without advancing progress.
- Create a target and exercise every exposed write path. Attempt direct publication
  with credentials that should lack authority.
- Test memory, disk and retained files with idle input, slow consumers and interrupted
  cleanup. A bounded run cannot succeed before its final writes finish. Unexpected
  task death must produce failure, not successful termination with an active status.

Component tests and the existing bounded runtime supply controls, not evidence that
these cases work together. Preserve correct Spark-facing behavior and test intentional
stricter behavior explicitly. Do not weaken assertions to obtain a pass.

The existing bounded-runtime corpus under `python/pysail/tests/spark/pipelines/` supplies
migration requirements. The local command's `_dev/spark/pipelines/` suite does not yet
establish preservation of that wider SDP API. Retain `test_delta_sources.py` coverage for snapshot plus later commits, empty tables,
starting versions and timestamps, initial-run-only start options, commits without data
changes, table replacement and repeated writes. Keep empty-flow completion in
`test_triggered_execution.py` and failed-run status in `test_end_to_end_cli.py`.

The bounded mode permits `ignoreChanges`, `ignoreDeletes`, `skipChangeCommits`, exclusions
and `failOnDataLoss=false`. Add separate durable-mode tests that reject these lossy
options while retaining existing-mode assertions. Define `startingVersion="latest"`
continuation explicitly. The unfinished-batch test edits checkpoint files and expects
duplicates; it is not a process-crash or exactly-once oracle. Missing-history execution
and the failure cases above need new tests. This mapping is based on source inspection,
not a new test run.

## Extend the proven path

Distributed execution routes controls through driver and task ownership and coordinates
checkpoints across real merges, shuffles and replicas. Test replacement of running tasks
and multi-worker failures. Add managed Delta and Iceberg only after each adapter enforces
the same ownership rule on every supported publication path.

Change capture evaluates and validates original events once, selects the newest per key,
and stores versions for live and deleted records. Choose a transaction covering both rows
and versions, or recovery across a separately protected version store, before implementing
merges. Test different checkpoint groupings, hidden conflicts, partial writes and ordinary
external readers.

Port native Extensions through package identity, worker loading, relation placement,
memory limits and cleanup. Preserve the existing DataFusion interface as a control when
adding explicitly selected Comet scalar exports. Standalone adapter probes do not establish
package integration. A C relation interface remains a separate decision.

Measure performance at each stage without changing event order or failure behavior.
Resolve material small-batch and startup costs. YAML, JSON and API configuration use one
validated typed model; optional authoring in the typed configuration language Dhall produces
that same input. Replace the bounded runtime
only after integrated recovery, ownership enforcement, resources and interoperability are
verified, including migration of pending writes and retained change versions.
