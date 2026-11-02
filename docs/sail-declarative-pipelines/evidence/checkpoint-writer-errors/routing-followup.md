# Routing follow-up from the writer trace

Observed on Sail47c473e6b9af7b5e2e5fbe30070ab2fe407def49; this note does
not select a new runner or registry API.

- sail-physical-plan/src/remote_checkpoint.rs: RemoteCheckpointWriteExec::execute
  resolves one store, but write_checkpoint_partition constructs a ParquetSink
  which resolves its own store through the supplied TaskContext. Both lookups,
  metadata reads and cleanup need the same operation ownership/routing.
- sail-plan/src/lib.rs: resolve_and_execute_plan_with_scope resolves the named
  logical plan, invokes execute_logical_plan, optimizes/rewrites, then creates
  the physical plan before returning it. Its comment explicitly places catalog
  commands and barriers in physical planning. Starting ownership only after this
  function returns leaves planning effects outside that owner.
- sail-spark-connect/src/service/plan_executor.rs: handle_execute_plan and
  handle_execute_write_stream_operation_start prepare a physical plan before
  calling JobRunner.execute. The SQL-config branch also creates a physical plan.
- sail-spark-connect/src/pipelines/execution.rs: run_command follows the same
  prepare-then-run order using resolve_and_execute_plan_with_scope.
- sail-execution/src/job_runner/local.rs: LocalJobRunner.execute currently creates
  a fresh ScopedTaskContext and StreamPreparation and admits the job only after
  receiving the physical plan. Its stop qualification does not cover the earlier
  preparation just described. Distributed execution has separate admission and
  worker-context responsibilities; the local observation is not a cluster verdict.

The existing isolated registry context helper preserves an already-known owner;
it does not establish ownership before these planning calls. Keep actual store
routing, pre-planning admission/owner transfer, operator-child joins, provider
uncertainty and session/cluster teardown separately reviewable. Do not activate
cleanup-qualified deletion on the strength of only the error-classifier fix.
