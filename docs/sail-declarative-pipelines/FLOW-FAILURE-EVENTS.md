# Flow failure events for unresolved pipelines (proposal)

Status: implemented as Sail `2456618dd` (renderer) and `13e0d4f96` (emission
and tests), under the scope Codex amended in CF-0112: the analysis call was
**not** moved out of the cancellation select; the events are yielded after
the select from a borrowed `Err(UnresolvedPipeline)` outcome, and the
renderer mirrors the Status message policy through `CommonErrorCause`. The
WARN level and source-code-location origin have no fields in the Connect
proto and are disclosed as not carried. Pinned Spark `617618396`.

## What Spark does, read from source

- `PipelineExecution.resolveGraph` and `dryRunPipeline` call
  `unresolvedGraph.resolve().validate()`; on `UnresolvedPipelineException`
  they call `handleInvalidPipeline(e)` and rethrow
  (`PipelineExecution.scala:112–118`).
- `handleInvalidPipeline` (`:135–160`) emits one `FlowProgress(FAILED)` event
  per failed flow through `flowProgressEventLogger.recordFailed`: the
  **downstream** failures first, message
  `Failed to resolve flow due to upstream failure: '<displayName>'.`, then the
  **direct** failures, message `Failed to resolve flow: '<displayName>'.`,
  both at WARN, each carrying the flow's own exception
  (`FlowProgressEventLogger.scala:137–162`). `displayName` is the unquoted
  identifier (`catalog.db.flow`).
- The Connect sender always forwards terminal flow-progress events
  (`PipelineEventSender.scala:94–106`) and renders the proto message as
  `messageWithError` (`PipelineEvent.scala:43–56`): the message, a newline,
  then `Error: ` followed by the messages of the exception and its cause
  chain joined by newlines.
- A dry run then propagates the wrapper to the client directly; a real run
  catches it in `runPipeline`, records `RunProgress(FAILED)` with the
  exception, which the handler keeps back and rethrows through
  `throwRunFailure` (`PipelinesHandler.scala:533–568, 581–588`). Either way
  the client receives the per-flow events before the wrapper error.
- Order inside each group is Scala `Map` iteration order: insertion order up
  to four entries, hash order above. Sail will emit each group in sorted
  identifier order, which equals the wrapper's own list order; disclosed.

Pinned assertion: `PythonPipelineSuite` "failed flow progress event has
correct python source code location" (`:152–178`) checks a `FAILED` event at
WARN for the failed flow whose exception message names the unresolved column.

## Proposed Sail change

1. `pipelines/failures.rs` (Fable's module): `FailureReport::events(&self)
-> Vec<String>`, the client-visible messages in Spark's order and format:
   downstream flows sorted, `Failed to resolve flow due to upstream failure:
'<name>'.\nError: <cause chain>`, then direct flows sorted,
   `Failed to resolve flow: '<name>'.\nError: <cause chain>`, where the chain
   is the cause's `Display` followed by each `source()` message on its own
   line. Unit tests pin both templates, the group order and the chain.
2. `pipelines/mod.rs` (shared, the only orchestration edit): in the run
   stream, the analysis result is matched before `?`; on
   `SparkError::UnresolvedPipeline(report)` the stream yields
   `event(message)` for each of `report.events()` and then returns the error
   unchanged, so the client receives the flow events before the wrapper, as
   in Spark. Exact delta, about eight lines:

   ```rust
   let analyzed = match analysis::analyze(&ctx, &definition).await {
       Ok(analyzed) => analyzed,
       Err(SparkError::UnresolvedPipeline(report)) => {
           for message in report.events() {
               yield event(&message);
           }
           Err(SparkError::UnresolvedPipeline(report))?
       }
       Err(error) => Err(error)?,
   };
   ```

   The analysis call moves out of the inner `run` future so the stream can
   yield; the cancellation `select!` keeps covering execution. No other
   event, no `RunProgress`, no level or origin field (the proto carries only
   timestamp and message), no change to the wrapper or its Status mapping.

3. Tests: the strict `xfail` becomes a passing test asserting the two
   templates and that the direct cause's message appears in the flow's
   event; `test_file_sources.py` (pipeline context) and the moved
   `sql.feature` scenario regain their cause assertions through the events
   while keeping the wrapper assertion; a multi-flow fixture pins the group
   order (downstream before direct) and the sorted order within a group.

## Boundaries

Not in this unit: flow events for execution-time failures (Codex's
execution path), `RunProgress` events, source-code-location origins (the
Connect proto has none), and any change to how the wrapper reaches the
client.
