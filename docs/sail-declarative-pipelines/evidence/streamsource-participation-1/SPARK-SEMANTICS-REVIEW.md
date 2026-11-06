# Source participation: Spark semantics and correctness review

## Scope and inspected pins

Read the complete saved request and AGENTS, LAKESAIL, SHEHAB, CLARITY,
WRITING-RULES and source development/review instructions. Inspected Sail starting
commit `327572240365e2507f348ee92bc009cbfc67abe9` in the assigned detached worktree.
Its tracked source was clean at inspection. The cumulative upstream reference
remains `b52144955b629314a000b1fe49eeea97fa3d0c5c`.

The prescribed `/Users/alexy/src/sail/opt/spark` path does not exist. Verified and
inspected Spark 4.2.1 Git objects at
`617618396087429b5627a86ce933bb0f5d6645cb` in
`/Users/alexy/src/spark-sdp-4.2.1`. No Spark JVM, Sail test, build or benchmark was
run. This is source evidence and proposed contracts, not executed parity.

## Spark separates row elimination from streaming identity

Spark’s PruneFilters in catalyst `optimizer/Optimizer.scala` refuses false/null
filter elimination on a streaming child by default. SQLConf’s
`spark.sql.optimizer.pruneFiltersCanPruneStreamingSubplan` defaults false and
explicitly describes enabling it as restoring prior buggy behavior. This existing
Spark behavior supports the engineering need to preserve a stream under a
constant-false data filter; no undesirable compatibility choice needs copying.

EliminateLimits still substitutes empty LocalRelation for zero LocalLimit or
GlobalLimit, but copies `child.isStreaming`. LocalRelation explicitly carries
that Boolean and an optional SparkDataStream reference. This preserves classification
independently of executable row production; it does not itself prove that the
original source remains represented as a scan beneath that empty leaf.

`LogicalPlan.isStreaming` defaults to children.exists. SubqueryAlias, View and
Union therefore inherit streaming presence from their children unless transformed
away. PropagateEmptyRelation constructs empty leaves with `plan.isStreaming` and
can remove empty union children. It specially avoids eliminating streaming joins
because their state work extends beyond processing data. These source rules show
why participation cannot safely be inferred from surviving row-producing children.

MicroBatchExecution builds execution relations by transforming `analyzedPlan`,
collects sources and identifying names from that result, initializes sourceIdMap
and then uniqueSources. Offset discovery later uses that retained collection.
That architecture separates source bookkeeping from optimized batch computation.
It is evidence for the separation of responsibilities, not a reason to replace
Sail’s continuous flow model with Spark microbatches or its positional fallback.

UnsupportedOperationChecker rejects streaming sources in ordinary batch execution
and directs them to streaming/pipeline entry points. Sail can retain its useful
finite streaming collect behavior without inheriting this refusal mechanically;
its behavior needs an explicit execution-purpose contract.

## Current Sail defect and required contract

Sail `resolve_and_execute_plan` currently optimizes first, then detects streaming
TableScans in the optimized tree. An EmptyRelation can erase both classification
and source participation. Detecting the original streaming plan earlier fixes only
the Boolean. It does not preserve the original control topology, source identities,
checkpoint responses or errors. A metadata inventory disconnected from execution
also does not establish marker propagation.

For an admitted continuous transform, zero user rows must not mean zero control
participation. `S WHERE FALSE` should continue receiving source controls, forward
markers in order and surface source failures. Do not reevaluate eliminated user
expressions merely to keep the source alive. Predicate and projection optimizations
may still eliminate row work when control behavior remains represented separately
or the relevant control-aware operators preserve it.

A stronger general optimizer framework is not the only possible repair. A narrowly
owned streaming node boundary or a streaming-specific optimization policy can be
reasonable if its identity, schema, expression and control behavior are explicit.
The deciding experiment is actual logical and physical optimization retaining
required source occurrences and their markers, including dead union branches.
Disabling every optimizer is a broad performance tradeoff requiring evidence.

Aliases and expanded views must preserve source occurrence bindings and qualifiers.
Do not key participation only by a table name: two branches or aliases may refer
to the same connector while requiring distinct plan/control roles. Any sharing
of one underlying source must be intentional and retain every participating input’s
barrier relationship. A self-union cannot lose a branch merely because that branch
produces no rows. Stable identity across recovery remains a later integration
requirement, not something an in-process pointer establishes.

## Limits and completion need separate meanings

There are three distinct contracts:

- A zero-data continuous transform retains its control participation until the
  run’s declared completion or cancellation protocol ends it.
- A finite SQL consumer budget, including LIMIT 0, may return no rows and cancel
  input without waiting for future controls. Consumer cancellation must not be
  presented as durable pipeline completion.
- A durable finite run captures a source end and succeeds only after its required
  final checkpoint and effects complete. A data row limit alone does not prove it.

Current StreamLimitState polls input before handling fetch zero and closes input
on a subsequent data event when the limit has been consumed. Its source explicitly
notes the unimplemented end-marker/final-checkpoint propagation. Therefore preserving
that node is useful for finite collection but insufficient for continuous checkpoint
participation. Do not repair data-zero behavior by making finite collect wait forever.
Select and document execution purpose before reusing a limit as a pipeline operator.

## Examples and verification obligations

Test false and NULL predicates, constant contradictions exposed by folding, LIMIT 0,
finite LIMIT N, aliases, views, projection over an empty branch and unions with one
or all zero-data inputs. Include all marker kinds and source failure after the last
user row. Verify actual optimized trees and execution: no user output, expected
ordered controls, expected source errors and task identity. A global collect result
of an empty list is not proof that checkpoint participants survived.

For a finite consumer, verify prompt zero-row completion/cancellation and input
release separately. For continuous control tests, use a deterministic channel that
emits a marker after zero data and remains open; the query must not fabricate EOF.
For eventual durable qualification, inject process/task replacement and ensure
prepared records include every admitted participant. This increment cannot claim
that complete recovery protocol from planner or operator tests alone.

## Latest upstream compatibility boundary

Verified fetched commit `5411f84330e8172acb22dd477044f42c07fcc2e5` separately.
Compared its predicate resolver changes with upstream base b521: CASE/coalesce result
coercion now resolves final nested types earlier, including nested nullability that
constant folding can change. This is not part of the current parent baseline.
Participation tests using CASE/IF must state their dependency pin and should not
assume those newer typing repairs are present. Avoid introducing new parity features
or weakening nested type checks merely to obtain a source-retention test.

All observations and proposed contract distinctions were sent to the integration
owner. No production source was edited. Final implementation and cumulative source
review remain pending. Saved request and governance compliance are confirmed.


## Frozen v2 cumulative source assessment

Independently verified all seventy-seven snapshot file hashes and twenty-four
increment paths in the assigned worktree. The index tree is
`9f6047eba2df8bdc83fe69be300a021131829add`, parent
`327572240365e2507f348ee92bc009cbfc67abe9`. The increment SHA-256 is
`017f008512f88e7a7b7b0e7b52aefb7246d7b12ce5f01a1a2fbd9d044661f37a`;
the cumulative source SHA-256 against `b52144955b629314a000b1fe49eeea97fa3d0c5c`
is `317d792059a1d9bb1e405f9b835f9df88854738b1ec7b0c46630154c5de0ef3d`.
The earlier foundation/projection/scalar files remain tied to their reviewed
content; this assessment includes the full cumulative snapshot and new increment.

No additional introduced source-correctness blocker was found in the compiler
boundary, source occurrence identity or finite-zero-demand path. Final qualification
is still conditional on the pending full gate and resolving the failed planning
probe’s semantic premise, described below.

Mandatory preparation follows configured analysis and precedes optional optimizer
execution. It uses the actual session optimizer context, preserving timestamp and
configuration rather than constructing an unrelated folding context. The audited
preparation subset normalizes admitted unary/union graphs without running the
full pruning optimizer. Unsupported source-bearing relational shapes bypass that
subset and reach a named streaming refusal before elimination can hide them.
Expression subqueries containing streams are rejected before pruning; bounded
scalar subqueries retain their batch treatment. Already lowered graphs return
unchanged from preparation and then pass through the complete optimizer, with
reentry marker/failure checks added explicitly.

Discovery follows renamed providers, exposed logical view plans and expression
subqueries. A raw streaming view provider whose plan is not exposed as an admitted
flow graph receives a named refusal rather than an ordinary batch adapter. This
is a declared boundary, not evidence that every opaque provider or raw DataFusion
entry point now implements Sail’s protocol. Eager resolver entrances and supported
command wrappers reject declared streams before collection. Batch inputs remain
on the existing optimizer route. Explain shares preparation instead of silently
showing a source-erased plan while execution uses another representation.

Occurrence tokens participate consistently in equality, hashing and ordering.
Clones retain the same token; independently lowered scans receive different tokens.
The tokens preserve in-process graph distinctions without claiming restart-stable
checkpoint identity. The collector now retains logical qualifiers and metadata
while stripping private controls. These changes preserve name/schema behavior
needed when lowered graphs reenter configured analysis.

LIMIT 0 returns an empty encoded stream before executing its child. That is finite
consumer cancellation with no fabricated EndOfData or checkpoint receipt. A live
zero-output filter remains an unbounded source-backed plan and ordinary collect
is refused by the bounded collector. The public tests distinguish these cases,
verify source-preserving explain output, exact multiset values/multiplicities and
named refusals for unsupported operators hidden behind false filters. Positive
LIMIT exhaustion and durable final-checkpoint completion remain separate work.

The immutable common-expression controls compare actual function work and exact
results with the baseline; volatile controls retain separate calls. Conditional
controls use a partial function under its guard, so moving unused work outside
the condition would fail. Those are meaningful semantic checks, not merely plan
shape assertions. They do not establish every optimizer/dependency interaction.

One planning performance fixture remains unqualified. Its raw depth-twelve batch
plan repeatedly adds one to a four-row input, so its independent expectation is
thirteen through sixteen. The old path reportedly produced two through five.
This is an exact-result failure before valid timing comparison, not noise in a
performance ratio. Fixture ambiguity, a baseline defect or another cause must be
isolated before interpreting that cell. Retain the original failing result and
avoid using it as evidence of broad batch-semantics neutrality or silently changing
the assertion to the observed baseline. The integration owner and Performance role
are investigating; this reviewer did not execute that probe.

The owner reports 217 affected Rust tests with one pre-existing skip passed before
the final reentry assertions, followed by both reentry tests passing. Preparation
negative controls failed both targeted cases and passed after restoration. Thirty-eight
selected public checks passed against fresh artifacts and server protocol 4.2.1.
These are reported retained results, not tests run here. The full immutable gate
remains pending. No JVM Spark differential was executed; Spark source conclusions
above retain that limit. Distributed checkpoint alignment, restart-stable identity,
durable preparation, fenced CDC effects and full extension integration remain
unbuilt obligations. Saved prompt and governance compliance remain confirmed;
no production source edits, builds, tests or cleanup were performed by this reviewer.


## Final participation pin and diagnostic resolution

Verified final index tree `1501e3dcaf84158319a99fd4c3122c2dcb84bfc1`, all
seventy-seven file hashes and twenty-four increment paths. Parent remains
`327572240365e2507f348ee92bc009cbfc67abe9`. Increment SHA-256:
`2bc3f0275441454387ed32baa8764642bf4f35edef299f63dc796b65ed4aea6d`.
Cumulative SHA-256 against upstream b521:
`e4f922d5c38697aa487fe256d9b1885227bbe506e600500a30be9e9e9b978b1a`.
This is the final reviewed pin and supersedes the frozen v2 pin above.

Inspected the full delta from v2. It replaces fixture panic-style conversions
with fallible error paths, and adds narrow lint declarations for intentional
raw DataFusion command inspection and fixture catalog access. Existing assertions
remain intact. It changes no admitted source identity, preparation traversal,
checkpoint-marker handling or finite-consumer semantics. No introduced source
correctness blocker was identified. The previously reviewed cumulative foundation,
Comet scalar, projection and participation boundaries remain qualified only within
their stated scope.

The same-alias investigation resolves the earlier fixture uncertainty. Direct
execution of the analyzed depth-twelve graph returns thirteen through sixteen;
both old and new optimized paths return two through five. This demonstrates a
shared optimized-path semantic failure for the intended graph, rather than an
incorrect expected-value assertion. Its exact responsible optimizer rule remains
unassigned. The diagnostic is retained as a failure and cannot support throughput
or broad optimizer-correctness claims. The owner reports the final diagnostic
covers batch and streaming forms; this reviewer inspected the retained direct/old/new
comparison and did not execute it.

The unique-alias fixture is a separate valid computation. Its fresh planning-v3
run passed exact execution checks for all four cells. It does not replace or
invalidate the same-alias defect. Median new/old planning ratios were approximately
1.007, 1.003, 1.660 and 0.942. The short-stream overhead is meaningful and remains
visible; the below-one nested-stream cell cannot cancel it. The experiment uses
an unoptimized profile on a shared host and establishes neither production planning
latency nor data throughput. The earlier planning-v2 artifact’s reused binary is
invalid evidence for its intended fixture; it remains separately labeled.

Strict affected Clippy and thirty-eight selected public checks are reported passed.
The full immutable cumulative gate remains pending. No new Spark JVM execution or
runtime parity is claimed. Source-preserving compilation and LIMIT 0 cancellation
remain distinct from restart-stable identities, distributed checkpoint alignment
and durable completion. The shared optimizer defect, short-stream planning cost,
prior mixed-marker performance gaps and broader recovery work remain open.

Read the saved request, literal continuation-request.txt containing “continue,”
and applicable governance. No context compaction occurred in this confirmation.
No production edits, builds, tests, cleanup or external communications were performed.


## Final v5 documentation-only pin confirmation

Verified all seventy-seven file hashes, twenty-four increment paths and final
index tree `f71f8c5c97b08baa0c7f0f914ea7a2e24d150622`. Increment SHA-256:
`15fd96913eecd7d1d1e64fd1083d12bc34630a13c93802541d2cd14bb73941c7`.
Cumulative SHA-256 against upstream b521:
`0b71c28974776dedaf643028bf12cc7959a0856b751db223b883393818e3d59a`.
This pin supersedes v4. The complete v4-to-v5 tree diff is one Rustdoc line:
the CREDIT label is formatted as inline code in optimizer.rs. No executable
method, assertion or producer/consumer contract changed.

The earlier semantic verdict and limitations therefore apply unchanged. No
introduced semantic blocker was identified; the shared same-alias optimizer defect,
short-stream planning overhead, mixed-marker costs and broader durable recovery
obligations remain explicit. The initial gate stopped before commit and its
failed receipt was retained. The owner reports strict Rustdoc now passes; the
full gate remains a separate pending qualification. No builds, tests or source
edits were performed for this confirmation. Saved request and governance compliance
remain confirmed; no JVM parity claim was added.
