# Stop streaming queries on execution failure

A failed streaming query must stop consuming input and expose its first
error. Console output failures must reach the query, and waiting for a failed
query must raise an error. Repair the sink and query manager without
adding another lifecycle service.

## Existing behavior and decision

Sail's console sink prints source and formatting errors as ordinary output and
ignores stdout errors. The query runner stores execution errors but keeps polling,
allowing later errors to replace the cause. Await handles report only termination.

Return console source, formatting and write errors through the execution stream.
Stop consuming on the first error. Publish stopped status and its optional cause
as one watch value after releasing the input stream. Separate notifications allow
a waiter to raise while status still reports active. One value makes that partial
state impossible without adding a lifecycle service. Individual and manager waits
must raise for retained failures. Continuing would require a separate retry or
row-rejection contract.

Failures take priority over successful termination. `resetTerminated` clears manager-wide consideration
of already stopped queries; it must not erase their individual exceptions or make
individual waits succeed. Preserve explicit-stop behavior.

Spark 4.2.1's [execution](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/core/src/main/scala/org/apache/spark/sql/execution/streaming/runtime/StreamExecution.scala#L609)
and [manager](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/core/src/main/scala/org/apache/spark/sql/classic/StreamingQueryManager.scala#L113)
source establish failure propagation and retained termination. This is source
inspection. Sail's existing snapshot of queries considered
by a pending manager wait remains unchanged; queries registered afterward and
selection among multiple failed queries are not claimed as full Spark parity.

## Verification and boundary

Inject an error followed by observable input: later input must remain unpolled.
Test atomic terminal publication, console failures, first-cause retention, failed
waits, failure priority, reset and normal completion. Exercise a failing console
query against unchanged and repaired executables.

Normal stream exhaustion is not checkpoint-qualified durable completion. Task
panics, join-failure supervision and cancellation taxonomy remain separate work.
