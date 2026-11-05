# Preserve streaming failure messages across Spark Connect

A failed query must expose its complete first cause when a client calls
`query.exception()`. Sail already retains the failure, but its response sends
the bare message where PySpark expects a class-prefixed exception string.
Correct that serialization without changing execution or adding error recovery.

## Existing boundary and decision

Sail's `service/plan_executor.rs` currently sends `throwable.message()` as
`exception_message` and the Java class name as `error_class`. PySpark 4.2.1
[removes the first class prefix](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/python/pyspark/sql/connect/streaming/query.py#L152)
by splitting at the first `: `. A bare message without that separator raises
an indexing error. A message containing it loses part of its cause.

Return the exception's class name, `: `, then the unchanged retained message.
Keep individual waits on the existing gRPC exception translation. The polling
response's `error_class` means an error condition, not a Java exception class.
Populate it only when Sail has a recorded condition; otherwise leave it absent.
Do not invent `STREAM_FAILED` or matching parameters that Sail has not recorded.

Spark's [server serialization](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/connect/server/src/main/scala/org/apache/spark/sql/connect/planner/SparkConnectPlanner.scala#L3733)
uses `toString()` and `getCondition`. Its
[exception implementation](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/common/utils/src/main/scala/org/apache/spark/sql/streaming/StreamingQueryException.scala#L101)
defines the class prefix. These are inspected source contracts, not an executed
parity claim. Changing PySpark is unnecessary because Sail can satisfy its
existing wire contract directly.

## Verification and scope

Pass delimiter-free, colon-containing and Unicode causes through the response
builder and actual PySpark protobuf/client decoding. Assert that decoding succeeds
and retains the complete cause. Check absent and recorded conditions separately.
Retain the live failed-query regression. This repair does not promise Spark's
debug offsets, JVM stack trace or complete structured-error metadata.
