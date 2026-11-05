# Initial regression review: event fidelity and data-only filtering

**Initial verdict: no concrete introduced correctness regression found in the
inspected changes. This is not the final integrated-candidate verdict.**

## Reviewed source

The common baseline is upstream Sail
`b52144955b629314a000b1fe49eeea97fa3d0c5c`.

- Event worktree: `/Users/alexy/src/sail/tmp/streamsource-build-20261105-b52144955`.
  Its tracked cumulative diff at inspection had SHA-256
  `94201cb05627c37ea5ea1a78912ec1308e5066d59891e642960d87316781a194`.
- Separate filter offer:
  `/Users/alexy/src/sail/tmp/streamsource-filter-20261105-b52144955/filter-review/filter-increment.patch`,
  SHA-256 `756c669c7b57e09a593c3449955d4514cc4af0a67fe6a2966bda496853e00052`.

The event worktree contained the filter test module hook and an untracked filter
test file, but not the filter implementation at this inspection. The two patches
were reviewed as separate changes; their union still requires review and tests
at an immutable candidate. No builds or tests were run by this reviewer.

## Event fidelity

The decoder supplies the encoded row count when constructing the payload batch.
This repairs positive-length zero-column data without changing the two control
columns or their ordering. Existing empty-data elision is preserved. Schema
conversion copies schema metadata while retaining complete field definitions.

Decimal placeholders use the requested precision and scale through checked Arrow
builders. Run-end placeholders use zero runs for an empty result, check length
conversion before constructing children, and retain the requested field names,
nullability and metadata through checked ArrayData construction. No unsafe
construction or unchecked narrowing conversion is introduced.

The new regressions check complete types and full Arrow validation, not just
length or null count. They cover every supported type family, all decimal widths,
positive and negative scales, nested decimal fields, empty run-end children and
unrepresentable run lengths. Decoder tests compare ordered rows and markers over
every contiguous slice of mixed fixtures, including zero-column data and
retraction flags. Ordinary nonempty data and empty-data elision have controls.

The public rate test exercises literal-only and zero-column projection. Its native
execution result was pending at this inspection. The design explicitly permits
a necessary rate constructor repair; fixing only the decoder cannot prove that
the source constructs the zero-column batch correctly.

## Filter behavior

The filter keeps expressions bound to the encoded schema. It passes contiguous
marker runs unchanged and evaluates the predicate once per contiguous data run.
Payload and retraction columns receive the same kernel selection. Ordinary
data-only batches retain one kernel call, including empty batches. Mixed batches
remain lazy, so a later expression error does not suppress an earlier marker.

The six controls discriminate strict marker-placeholder casts, scalar true/false/
null predicates, marker-only input, ordinary data-only input, real data errors,
sliced buffers, adjacent markers, retractions and ordering across input batches.
They test both the plain predicate and the existing rewriter's OR-marker form.

Existing plan properties and encoded column indexing are unchanged. The inspected
construction sites use this node for flow-event plans and codec reconstruction.
This patch does not isolate projection expressions, qualify asynchronous
projection, repair reserved control-name collisions or establish checkpoint
alignment. The design note correctly leaves those claims outside the independent
filter repair.

## Pending verification and instructions

Review the final cumulative immutable patch after integration. Its verification
must distinguish module controls, affected native crate tests, strict linting,
the actual planner/codec path and public queries against the fresh executable.
Reported baseline and fixed counts from the lead are not independent executions
by this reviewer. No performance neutrality or distributed durability is inferred
from these correctness tests.

The exact saved build request and full AGENTS.md, LAKESAIL.md, SHEHAB.md,
WRITING-RULES.md and CLARITY.md were read, together with both preceding design
notes. The latest engineering directive overrides inferior compatibility defaults.
Only this assigned evidence file was written; no source files or builds were
changed. Prompt and governing instructions will be reread after compaction.

## Cumulative three-increment prospective review

**Verdict: no concrete introduced regression found in the inspected cumulative
patch. Final immutable-candidate verification remains pending.**

This verdict covers the 17-file patch at
`/Users/alexy/src/sail/tmp/streamsource-build-20261105-b52144955/review-logs/cumulative-three-increments.patch`,
SHA-256 `d7fc1fab085e3aa5b22605dd350c488cdbd9365f0114d9c50864127dcd5a6c55`,
against `b52144955b629314a000b1fe49eeea97fa3d0c5c`. The patch hash was
independently recomputed. Source and test inspection covered all three
increments, including the filter retention repair and atomic terminal-state
amendment. No builds or tests were executed by this reviewer.

The cumulative event and filter changes preserve the properties described
above. The rate reader now supplies an explicit row count when constructing a
projected batch, addressing the source-side zero-column case. The filter takes
ownership of pending input for each step and retains it only when successful
processing leaves rows. Its new tests check release before the next downstream
poll, both for data-only input and after the final run of mixed input. The output
may still legitimately retain shared buffers. The change does not promise to
release buffers that the output itself needs.

The query implementation publishes one `Stopped(optional_error)` value after
the selected input future is dropped, at
`crates/sail-spark-connect/src/streaming.rs:86–111`. Status therefore cannot
observe a retained query error paired with an active state. Input consumption
returns at the first execution error. The tests independently observe input
destruction before terminal publication for error, exhaustion and explicit
stop, and require waiting APIs and status to observe the same terminal result.

Individual waits retain the failure after manager reset. Manager waits exclude
reset completed queries and check retained failures before and after selecting
a completed waiter, preserving the intended priority over a known success.
These behaviors are explicit in the preceding failure-propagation design note,
not accidental compatibility changes. Ordinary completion and explicit stop
remain represented as completion without a retained execution error.

Console input, formatting and output-write errors now reach the result stream
instead of being logged and discarded. Tests check first-error short-circuiting,
formatting failure, writer failure at the header and body, and successful output.
The public failure test connects console execution failure to query exception,
inactive status, individual waits, manager waits and reset behavior.

The lead reported negative controls and earlier fixed runs separately; this
review does not convert those reports into independent executions or claim that
the final combined candidate has passed. Task panic/channel-closure treatment,
queries registered after a manager wait begins, projection-expression isolation,
codec transport, durable completion and recovery remain outside this verdict.
The bounded source inspection supplies no performance-neutrality claim.

The saved build request, its preceding engineering request and full AGENTS.md,
LAKESAIL.md, SHEHAB.md, WRITING-RULES.md and CLARITY.md were reread after
compaction. The preceding event, expression and failure design notes informed
the review. Only this assigned evidence file was modified.

## Four-note cumulative delta and context review

**Verdict: no introduced correctness defect found. Performance qualification and
the final immutable-candidate gate remain unresolved; this is not blanket
regression-free readiness approval.**

Reviewed the 19-file cumulative patch
`review-logs/cumulative-four-design-notes.patch` in the implementation worktree,
SHA-256 `6782613a31c5278296421622c5a5fcea918603506a70de62c0f77671fa0f3376`,
against the same `b52144955b629314a000b1fe49eeea97fa3d0c5c` baseline.
Independently recomputed the hash and compared the complete patch with the prior
17-file patch. Unchanged changes retain the preceding source-review verdict;
all intervening source and test changes were inspected in their cumulative
context. No build, test or benchmark was executed by this reviewer.

At `crates/sail-physical-plan/src/streaming/filter.rs:128–161`, the polling
closure now invokes the existing kernel directly for data-only batches, including
empty ones. It releases the consumed input before yielding and avoids creating
the per-batch inner stream. Pending mixed input still goes through the same lazy
iterator. It is drained before polling another input, preserving marker order,
data-run predicate boundaries, preceding markers before later errors and the
retention repair. The closure returns after each yielded result or pending input
poll; it does not introduce a loop that drains arbitrary data-only batches within
one poll. Error propagation remains compatible with the query runner's first-error
termination reviewed above.

The new exception-response helper at
`crates/sail-spark-connect/src/service/plan_executor.rs:419` prefixes the retained
message with the exception class and a single separator. It sends a recorded
condition in `error_class`, or leaves that optional field absent. This follows
`STREAMING-ERROR-PROTOCOL.md`, committed as `70c6a7c6` before the source change.
The helper does not change individual-await gRPC translation or manufacture
structured metadata.

Inspected the local Spark 4.2.1 client at
`/Users/alexy/src/spark-sdp-4.2.1/python/pyspark/sql/connect/streaming/query.py:152–165`:
it removes exactly the first class separator. Its Connect exception constructor
at `python/pyspark/errors/exceptions/connect.py:273–275` adds the supplied reason
to the displayed message. The candidate's protobuf round trips and actual-client
fixtures check complete causes without separators, with multiple separators,
with Unicode and newlines, and with an empty string. They distinguish missing
failure from an empty failure, and absent condition from a recorded condition.
The live console test compares the whole polled cause with status instead of
accepting a substring that could hide truncation. These are source assessments
of the tests, not independent test results.

Read the cost comparison summary and receipt in
`review-logs/filter-cost/runs/20261105T200822.823114Z/`. The receipt names this
exact cumulative patch hash and reports unchanged tracked source during the run.
Its unoptimized shared-host data-only median ratios are 0.9915–1.0052. Alternating
markers still produce median ratios of 17.8927–141.1032 and 65,536 output batches
from 512 or eight input batches. This is a substantial unresolved adverse-case
cost, not measurement noise or evidence of performance neutrality. The fast path
does not resolve marker fragmentation. Optimized qualification and a decision
about that cost remain necessary; source inspection alone cannot establish a
production performance envelope.

The lead's earlier 229 Rust passes and strict lint result precede these deltas
and do not qualify this final patch. The exact final gate and immutable pin are
pending. Previous exclusions concerning projection, codec transport and durable
recovery remain in force. Prompt and full governance had been reread after the
most recent compaction; the new protocol note was read in full. Only this
assigned evidence file was modified.

## Final failure-reporting cost delta

**Verdict: no introduced correctness defect found in the final inspected source.
The two failure-reporting cost issues are resolved by source inspection. The
marker-heavy performance qualification remains unresolved.**

Independently verified delta
`review-logs/failure-reporting-cost-fix.patch`, SHA-256
`73baa58870461a4b5143a97d24145a5dc86d896e51338a5e42da7075499587f1`,
and final 19-file cumulative patch `review-logs/cumulative-final.patch`, SHA-256
`bda65fdba075378f3088a2b00681fdf63f57b9d9a66722ec78c8e1f688220163`.
Both paths are relative to the implementation worktree. The cumulative baseline
remains `b52144955b629314a000b1fe49eeea97fa3d0c5c`. Compared the entire final
patch with the previously reviewed cumulative patch; the only changes are the
three files in this delta.

Console formatting and rendering into a string now finish before the stdout
lock is acquired. This restores the baseline's lock scope while preserving the
new formatting-error propagation. The lock still covers both header and body
writes, and both write failures remain returned. Rendering already produced a
string before locking in the baseline; the repair does not introduce that
allocation relative to the baseline. The helper tests now check writing supplied
text rather than formatting a batch inside the helper. The unchanged sink-level
invalid-timezone test still exercises formatting failure and short-circuiting.
The altered helper-success test alone is not an end-to-end successful-formatting
test.

Active-query listing borrows the query state once, excludes stopped queries
before constructing their status, and builds active status from that same borrow.
It avoids allocating names or retained error messages for inactive queries while
preserving the atomic state observation. `status()` delegates to the same
construction helper. No additional state transition or lock lifetime across an
await is introduced.

This closes those two local source-level cost findings, not the alternating-marker
fragmentation cost recorded above. The lead reported 232 Rust tests, 19 public
tests, formatting and strict lint passing on the preceding candidate. Those
results do not qualify this later three-file delta. Its focused gate and final
immutable pin were pending at review. No tests, builds, benchmarks or source edits
were performed by this reviewer. The saved prompt and governance compliance
record above remains current; no compaction occurred between these delta reviews.

## Immutable source pin verified

Independently verified implementation worktree HEAD
`2c9fa84994d317aade0d1c69faa9a378c780127d` and tree
`5d67cdc81cdd9ba7eb18a74eda17d84b9e5d30c7`. `git status --porcelain
--untracked-files=no` returned no tracked changes. The binary-capable diff from
baseline `b52144955b629314a000b1fe49eeea97fa3d0c5c` to that explicit commit
has SHA-256 `bda65fdba075378f3088a2b00681fdf63f57b9d9a66722ec78c8e1f688220163`,
exactly matching the final reviewed patch. The preceding source verdict therefore
applies to this immutable commit, with the same marker-heavy performance
qualification and stated scope limits.

At this check the lead reported workspace Clippy passing and nextest reporting
2,017 passed and one skipped. CLI and public-test stages were still running.
Those are reported gate results, not independent executions by this reviewer,
and do not establish that the complete gate passed. No builds, tests or source
changes were performed for this pin verification.
