# Actual Sail clock resolution and combined public regression gate

Sail `09d2f0cb89cbb92f186f5096ba04ade7a665282c`, parent `ae26db132`,
imports Fable `56ae39abd` test changes; all three blobs match. Tests resolve
Spark-spec function calls through actual Sail PlanResolver inside lower: independent
current_timestamp, now and current_date cases remain admitted/non-replayable with
stable-function evidence; resolved abs control stays replayable. No sail-function
dependency added. Existing test-only SQL resolution_context and its module gain
pub(crate) visibility for reuse; production source behavior is unchanged.

Exact detached combined fmt/strict all-target/all-feature Clippy and 134 common-
datafusion + 55 plan + 135 Connect library tests pass (324 total). The final source
also passes a fresh CLI build,300 fixed public tests +67 upstream Python executions,
Spark4.2.1, owned server exit0/no listeners. Source/selection/receipt/log/binary hashes
and unchanged detached state were qualified before conditional advancement. These
are regression selections, not full original Scala SDP suite execution; inventory
counts are unchanged. The 67 executions retain inherited repeated-case boundaries.

This qualifies the resolved-function→admission seam so premature clock folding
would fail. It does not activate a public lowerer, own async source work, capture
complete replay identity, select C0 representation, or enable broker/target/CDC
operations. Remaining provider factories, analyzer/capture/transfer/cluster/session,
ORC writer and full Spark acceptance remain open. Original negative clock fixtures,
correction replay, inline UDTF guard review and lowerer controls stay in their
separate packets. SHA256.json covers all files except itself; historical paths are
not replay destinations. Use the durable frozen public harness with fresh outputs.
