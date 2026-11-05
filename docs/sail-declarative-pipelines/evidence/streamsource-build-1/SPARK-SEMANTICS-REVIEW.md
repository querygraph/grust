# Spark semantics for event fidelity and data-only expressions

## Scope, references and verdict

Source inspection supports the two design notes. A projection must preserve
input row multiplicity even when its output has no columns. A filter retains
only rows whose predicate is true. Errors in expressions that actually evaluate
real data must remain errors under the selected expression mode. Sail control
markers are not data rows and must not invoke those expressions.

No conformance-driven compromise is needed. Spark does not specify Sail's marker
encoding, retraction handling, asynchronous evaluator integration or Arrow type
coverage. Those obligations follow Sail's own contracts. No new Spark/Sail test,
build, benchmark or runtime execution was performed in this review.

| Subject | Inspected reference |
| --- | --- |
| Spark source | `/Users/alexy/src/spark-sdp-4.2.1`, `617618396087429b5627a86ce933bb0f5d6645cb`, Spark 4.2.1 |
| Sail baseline | `/Users/alexy/src/sail/tmp/streamsource-build-20261105-b52144955`, `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Event-fidelity design | `STREAMSOURCE-EVENT-FIDELITY.md`, documentation commit `4e2c40e737207745d05cd454df5b39488829cfdc` |
| Expression-isolation design | `STREAMSOURCE-DATA-ONLY-EXPRESSIONS.md`, documentation commit `207e715e71b58bcccf78ad09247dd48de64fdfa6` |

The Sail worktree contained developing tests when inspected. This is semantic
grounding for the increments, not a cumulative implementation verdict. Source
paths and line numbers below refer to the pinned commits, not changing files.

## Projection preserves data rows, including zero-column rows

Spark's `sql/core/src/main/scala/org/apache/spark/sql/execution/basicPhysicalOperators.scala:47`
defines `ProjectExec`. Its output attributes come from the project list at :54;
execution preserves partition sizes at :99–111.
`ProjectEvaluatorFactory.scala:36–38` creates the projection, initializes it once
per partition, and maps it over every input row. There is no empty-project-list
branch that drops input rows.

The interpreted implementation makes the distinction explicit:
`sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/expressions/InterpretedUnsafeProjection.scala:43–53`
allocates an output row using the expression count. At :76–91 it evaluates that
many fields and returns a row. Zero fields do not mean zero invocations or zero
rows. The generated path also creates a writer using `expressions.length` in
`expressions/codegen/GenerateUnsafeProjection.scala:286–306`.

Spark's columnar representation stores row count independently from column count.
`sql/catalyst/src/main/java/org/apache/spark/sql/vectorized/ColumnarBatch.java:123–126`
accepts both columns and `numRows`; its iterator at :61–79 advances according to
`numRows`, not the number of columns. An explicit fixture constructs ten empty
rows under an empty schema in
`sql/core/src/test/scala/org/apache/spark/sql/SQLQuerySuite.scala:1910–1927`.
That fixture was read, not executed here.

Therefore a positive-length Sail batch must retain its length when the last
payload column is removed. A literal-only projection still needs one literal
result per input data row. Neither case permits inventing output for a marker.
Eliding an empty data batch is a different operation from losing positive-length
zero-column data.

## Filters retain true, reject false and null, and preserve genuine errors

Spark's `FilterEvaluatorFactory.scala:39–45` initializes a predicate and filters
the input row iterator with its Boolean result. The generated predicate returns
`!isNull && value` in
`sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/expressions/codegen/GeneratePredicate.scala:62–65`.
The whole-stage path likewise skips null or false predicates in
`basicPhysicalOperators.scala:161–177`. No special row with fabricated payload
is added to make a filter report progress.

For a strict string-to-integer example, `expressions/Cast.scala:921–926` uses
`UTF8StringUtils.toIntExact` under ANSI mode and a nullable conversion in legacy
mode. `sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/util/UTF8StringUtils.scala:33–51`
translates numeric parse failure into the cast error. Generated strict casts
use the same exact conversion at `Cast.scala:2113–2117`. TRY mode has a separate
null-on-error path at :1318–1328 and :1432–1440.

Consequently, the regression needs both a valid data row beside a marker and an
invalid actual data row. Marker isolation must remove the fabricated-input
failure; it must not convert every cast to TRY semantics or swallow the invalid
data error. Select an explicit strict mode so the test does not depend on a
session default. The same true/false/null selection must apply to payload and
retraction flags without evaluating the predicate separately for each.

## These data operators also ground Spark streaming behavior

`sql/core/src/main/scala/org/apache/spark/sql/execution/streaming/runtime/IncrementalExecution.scala:90–107`
adds streaming/stateful strategies and retains the session's ordinary planner
strategies. `sql/core/src/main/scala/org/apache/spark/sql/execution/SparkStrategies.scala:1035–1038`
maps logical projection and filter to the physical operators above. This supports
the design note's limited claim about ordinary data evaluation. It does not
provide an equivalent of Sail's encoded control-event transport.

Do not derive a universal function-call count or error-order contract from these
operators. Spark code generation can defer deterministic expressions, reuse common
subexpressions and evaluate non-deterministic attributes specially, as shown in
`basicPhysicalOperators.scala:64–95`. Tests of the Sail event boundary should
establish zero marker invocations and preserve the selected data evaluator's
results/errors. They should not require arbitrary optimizer-dependent invocation
counts across engines or promise volatile replay/retraction equivalence.

## Sail's existing contract independently requires these repairs

At the Sail baseline,
`crates/sail-common-datafusion/src/streaming/event/encoding.rs:20–24` explicitly
says payload fields are valid only when the marker is null. The decoder already
splits contiguous data runs around individual markers at :141–171. Its data
constructor at :137 omits an explicit row count when all payload columns are
gone. The rate source has the same zero-column construction boundary in
`crates/sail-data-source/src/formats/rate/reader.rs:315–339`.

`crates/sail-plan/src/streaming/rewriter.rs:71–87` retains an ordinary projection
and changes filter predicates to `user_predicate OR marker_present`.
`crates/sail-physical-plan/src/streaming/filter.rs:125–129` passes the entire
encoded batch to the filter evaluator. These paths expose placeholder payload
to user expressions despite the encoding contract. Splitting data runs without
moving markers directly restores that boundary.

Schema reconstruction drops schema-level metadata in
`crates/sail-common-datafusion/src/streaming/event/schema.rs:36–45,62–74`.
`crates/sail-common-datafusion/src/array/placeholder.rs:338–341` ignores requested
decimal parameters, and :356–379 constructs run-end placeholders through integer
casts and new run-array fields. These are Arrow fidelity issues, not reasons to
limit Sail to Spark's type set. Qualification must cover the applicable Arrow
types, field attributes and valid empty arrays as the design requires.

## Acceptance boundary and instruction compliance

No semantic blocker was found in either design note. The cumulative code review
must still check mixed marker/data batches, errors on real input, zero-column
cardinality, flag alignment, metadata, source projection, optimizer properties,
child replacement, physical-plan codec and supported asynchronous expressions.
Direct Rust marker tests and actual public-query tests cover different boundaries;
neither should be presented as the other. Successful marker handling does not
establish checkpoint alignment, durable success or recovery.

Confirmed reading of the full saved `REQUEST.txt`, the preceding engineering
request, grust-sdp `AGENTS.md`, and complete `LAKESAIL.md`, `SHEHAB.md`,
`CLARITY.md` and `WRITING-RULES.md`. These instructions are reread after compaction.
The current engineering directive governs over earlier compatibility defaults.
Only this evidence document was written; no Sail or Spark source was edited.

## Prospective cumulative review of three increments

Reviewed all 17 files in `review-logs/cumulative-three-increments.patch`,
SHA256 `d7fc1fab085e3aa5b22605dd350c488cdbd9365f0114d9c50864127dcd5a6c55`,
against Sail `b52144955b629314a000b1fe49eeea97fa3d0c5c`. This is a source
review of a prospective patch, not a verdict on a subsequently committed tree.
The failure design is `STREAMING-FAILURE-PROPAGATION.md` at documentation commit
`2192b091`. The earlier source-only and no-edit statements describe the initial
two-note review; the separately authorized protocol work below has a narrower
executed-test and implementation scope.

The event changes preserve explicit row counts, schema metadata and the requested
Arrow placeholder types. The filter evaluates contiguous data runs and forwards
marker runs without invoking the predicate. Filtering retains the existing
true/false/null behavior and propagates actual data errors. This increment repairs
filter evaluation; it does not implement the separately proposed projection
isolation. No additional Spark constraint is needed for those choices.

The failure increment stops consumption at the first execution error, propagates
console input/format/write errors, and publishes one `Stopped(optional cause)`
state only after dropping the execution stream. The single watch state prevents
observers from seeing a terminal query before its cause. Individual and manager
waits surface retained failures; manager reset leaves an individual query's
failure available. These choices follow the promised failure contract.

The pinned Spark source corroborates these limited public semantics:

- `sql/core/src/main/scala/org/apache/spark/sql/execution/streaming/runtime/StreamExecution.scala:363–390`
  captures a streaming failure. Its :414–425 cleanup precedes termination
  notification; :609–625 rethrows the retained cause for individual waits.
- `sql/core/src/main/scala/org/apache/spark/sql/classic/StreamingQueryManager.scala:113–149`
  makes manager waits observe termination history and resets that history.
  At :389–398 a failed termination supersedes a normal one; a later normal
  termination does not clear the failure.
- `sql/api/src/main/scala/org/apache/spark/sql/streaming/StreamingQuery.scala:105–135`
  documents repeated individual waits returning or throwing according to the
  retained outcome. Manager reset does not erase this individual outcome.
- `python/pyspark/errors/exceptions/connect.py:384–387,480`
  maps the streaming-query Java exception class to `StreamingQueryException`.
  The candidate's separate gRPC error translation supplies that class for waits.

The candidate retains existing manager membership snapshots: a pending manager
wait does not include queries registered later, and an empty captured set returns
immediately. This differs from Spark's global manager history. It also leaves
panic supervision, blocking stop semantics and the service's constant
`is_data_available`/`is_trigger_active` flags unchanged. These are scope limits,
not claims of complete lifecycle parity. No durable checkpoint completion or
recovery guarantee follows from local stream termination.

**Verdict on this patch: one required correction.** The retained first cause is
still serialized incorrectly by the unchanged exception-polling service branch.
No other semantic blocker was found within the inspected increments.

## Exception-polling protocol correction

At the Sail baseline,
`crates/sail-spark-connect/src/service/plan_executor.rs:372–387` sends the bare
retained message as `exception_message` and the Java class as `error_class`.
Pinned PySpark `python/pyspark/sql/connect/streaming/query.py:152–165` removes the
first `: `-delimited class prefix. A delimiter-free cause therefore raises
`IndexError`; a cause containing a colon loses its first segment. A substring
check for the tail of the cause cannot detect the latter failure.

Spark's server sends `e.toString()` and `e.getCondition` at
`sql/connect/server/src/main/scala/org/apache/spark/sql/connect/planner/SparkConnectPlanner.scala:3733–3738`.
The class prefix is explicit in
`common/utils/src/main/scala/org/apache/spark/sql/streaming/StreamingQueryException.scala:101–111`.
The polling field `error_class` denotes the condition, not the Java class.
Sail should leave it absent when no condition was recorded, rather than invent
`STREAM_FAILED` and its associated metadata.

The standalone decision note `STREAMING-ERROR-PROTOCOL.md` was committed as
`70c6a7c6` before delegated source edits. The resulting narrow implementation is
in `/Users/alexy/src/sail/tmp/streamsource-filter-20261105-b52144955`:

- `service/plan_executor.rs` uses the production response helper, prefixes the
  complete unchanged cause and copies only a recorded condition.
- `service/plan_executor_tests.rs` checks the producer's protobuf round trip,
  required one-prefix removal, complete cause, condition and no-failure cases.
- `test_streaming_failures.py` checks the actual PySpark protobuf and client
  reader and strengthens the live regression to compare the complete retained
  status cause with the polled exception.

The local delta is `failure-review/protocol-fix.patch`, SHA256
`015a0b3442b17414707b17bb4bd688aacd787bd6495eb0d4d6db22bd58c7843f`.
`failure-review/protocol-fix-receipt.json` records the three file hashes and
commands. Actual installed PySpark 4.2.1 client tests passed: nine passed, one
live test deselected. Running without repository fixtures produced one unknown
`spark` marker warning. No Sail or Spark engine was started. Ruff passed using
the integration worktree's generated Hatch configuration; the assigned Python
file and Rust files were formatted.

`failure-review/protocol-original-payload-control.json` records a separate
executed check through the actual protobuf/client reader with the original
payload shape. Plain and empty causes raised `IndexError`. Colon-containing and
Unicode causes failed complete-cause equality through truncation. This control
does not execute the Rust server. Rust builds/tests, the live query test and an
immutable combined candidate remain the integration owner's verification work.

The reviewer authored this narrow delegated correction, so its independent code
review must come from another specialist. No final cumulative readiness verdict
is claimed for the correction before integration and a new candidate pin. The
saved request and all governing files were reread after compaction before edits.

## Final cumulative source review

**Verdict: no unresolved semantic blocker in the reviewed 19-file patch.**
Read the complete 2,382-line `review-logs/cumulative-final.patch`, SHA256
`bda65fdba075378f3088a2b00681fdf63f57b9d9a66722ec78c8e1f688220163`,
against `b52144955b629314a000b1fe49eeea97fa3d0c5c`. Also read the complete
88-line `review-logs/failure-reporting-cost-fix.patch`, SHA256
`73baa58870461a4b5143a97d24145a5dc86d896e51338a5e42da7075499587f1`.
Both hashes were checked locally. This verdict is bound to these contents, not
an unexamined later commit or a completed full-workspace gate.

The complete patch includes the protocol correction described above. It supplies
the class prefix required by the actual PySpark reader, retains the complete
cause and keeps the Java exception class separate from an optional recorded
condition. The previous required correction is resolved in source. The reviewer
authored that narrow correction; this verification does not substitute for its
independent review by another specialist.

The filter's direct polling path at
`crates/sail-physical-plan/src/streaming/filter.rs:128–161` preserves the earlier
semantics. Pending mixed-batch runs are yielded before another input batch is
polled. A data-only batch, including an empty batch, uses the existing single
filter-kernel call without constructing a per-batch iterator. Marker-containing
batches retain ordered, lazy run processing at :211–239. Marker runs bypass
expressions, data errors remain errors and exhausted input is released before
yielding. This is an implementation-cost change, not a new expression contract.

Console formatting and string rendering finish before acquiring stdout's lock
at `crates/sail-data-source/src/formats/console/writer.rs:95–104`. A formatting
failure still exits through the stream's error path. The header and body still
share one lock, and both writes propagate errors at :112–120. The original
header/body output structure is preserved without keeping the lock during table
rendering. This inspection makes no throughput claim.

At `crates/sail-spark-connect/src/streaming.rs:68–85,227–238`, active-query
listing first borrows the single state and skips stopped queries. It builds an
active query's status from that same held borrow, avoiding both inactive-status
allocations and a second state observation. The performance correction therefore
preserves the atomic terminal-state/cause contract rather than weakening it.

No new tests, builds or runtime experiments were executed during this final
source review. The integration owner reported 232 affected Rust tests, 19 public
tests, format and strict clippy passing on the preceding candidate. Those results
are reported evidence, not execution by this reviewer and not qualification of
an unchecked later tree. The final focused and immutable full-workspace gates
were still pending at review time. Earlier disclosed projection, manager-wait,
panic, stop and status-field limits remain unchanged. Saved prompt and governing
instruction compliance remains confirmed; no production files were edited in
this final review.

## Immutable source pin confirmation

Verified the worktree HEAD is `2c9fa84994d317aade0d1c69faa9a378c780127d`
with tree `5d67cdc81cdd9ba7eb18a74eda17d84b9e5d30c7`. Its binary diff against
`b52144955b629314a000b1fe49eeea97fa3d0c5c` hashes to the reviewed SHA256
`bda65fdba075378f3088a2b00681fdf63f57b9d9a66722ec78c8e1f688220163`.
Tracked source and index are clean; only `review-logs/` is untracked. The source
verdict above therefore applies to this immutable commit. No builds or tests
were run for this confirmation. The integration owner reports workspace Clippy
passed and nextest remains running; this is not a completed-gate verdict.
