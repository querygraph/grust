# Design Quality review of the cumulative implementation

Recorded: 2026-11-05T20:10:56.180321+00:00

## Candidate and verdict

Reviewed all changes in the 19-file cumulative patch
`/Users/alexy/src/sail/tmp/streamsource-build-20261105-b52144955/review-logs/cumulative-four-design-notes.patch`.
Its SHA256 is `6782613a31c5278296421622c5a5fcea918603506a70de62c0f77671fa0f3376`.
The source baseline is `b52144955b629314a000b1fe49eeea97fa3d0c5c`.
The patch hash was independently recomputed before reading.

**No Design Quality blocker found in this candidate.** The changes repair
existing representation, unary evaluation and error-reporting boundaries without
introducing checkpoint coordination, an alternative execution engine or a new
lifecycle service. This is a source review, not an immutable integration verdict
or authorization to offer upstream changes.

## Architectural assessment

The Arrow repairs are narrowly placed. The event decoder and rate constructor
retain explicit row counts when there are no payload columns. Schema conversion
copies schema metadata while retaining original field definitions. Decimal
construction uses checked precision and scale; run-end construction checks
capacity and preserves the exact requested fields through checked `ArrayData`.
There is no justification here for changing the flow-event wire representation
or owning a dependency implementation.

The filter remains the existing physical node with unchanged expression indexing,
codec and plan-property policy. It delegates data selection to the existing batch
kernel and handles only Sail's marker boundary. The new direct-poll path drains
pending slices before polling input, forwards the source's pending state with its
waker, and filters data-only batches without an inner stream allocation or marker
buffer clone. Mixed input remains lazy: a marker preceding invalid data is yielded
before the error. Data and retraction flags receive the same selection. Exhausted
input is released before yielding, including the direct data-only return.

The iterator still accepts data-only input, although production normally bypasses
it. This small overlap is not a separate behavioral mechanism or a blocker. It
would not justify a refactor during final verification. The filter does not claim
that every error fuses its upstream stream; the query runner owns terminal
execution failure. Projection and asynchronous expression isolation remain
unfinished and must not be described as implemented by this patch.

The single query-state watch is simpler and stronger than separate cause and
stopped notifications. `Running` and `Stopped(optional cause)` exclude the
half-published failure state. The runner releases the input future before publishing
termination. Status and active-list filtering read one state snapshot. Individual
waits retain errors after manager reset. Manager scans before and after waiting
serve a distinct purpose: a known failed query must not be hidden by another
query's successful waiter. These scans are not a global atomic snapshot and do
not establish broader query-manager linearizability.

The exception response helper is the right integration boundary. It adds the
class prefix required by the existing PySpark reader and preserves the whole
retained cause, including embedded colons and Unicode. The condition field comes
only from recorded condition metadata. I independently inspected Spark commit
`617618396087429b5627a86ce933bb0f5d6645cb`: the client at
`python/pyspark/sql/connect/streaming/query.py:152–165` removes one `: ` prefix;
the server at
`sql/connect/server/src/main/scala/org/apache/spark/sql/connect/planner/SparkConnectPlanner.scala:3733–3738`
sends the exception string and condition separately. No client modification,
invented condition or new error transport is needed.

## Verification boundary and remaining work

The cumulative tests exercise exact Arrow type families, mixed event slices,
marker isolation, retractions, first-error consumption, input release, atomic
publication, failed waits, reset behavior, protobuf serialization and actual
PySpark client decoding. The live failure test now compares the entire retained
cause rather than accepting a matching substring. Final combined builds, strict
Clippy, tests and the fresh executable checks remain the integration owner's
work; earlier candidate results cannot certify this hash. I ran no build, test or
benchmark during this review and make no throughput claim.

Pending manager waits still consider their initial query snapshot. Selection
among multiple failed queries, task-panic supervision and closed-channel behavior
remain explicit limitations. Normal exhaustion does not imply durable checkpoint
completion. No recovery, fencing or stateful streaming guarantee follows from
these foundational repairs.

The filter and initial query-state implementation were authored by this reviewer;
the cumulative reassessment is not a substitute for the other specialists'
independent reviews of those changes. The direct-poll optimization, protocol
helper and active-list snapshot correction received independent examination here.

## Instruction compliance

The saved full request and AGENTS.md, LAKESAIL.md, SHEHAB.md, CLARITY.md and
WRITING-RULES.md were read, including the required reread after compaction.
The saved request was reread for this candidate. The relevant implementation notes
precede code, including atomic-publication amendment `2192b091` and exception
protocol note `70c6a7c6`. This review changed no source, ran no builds and performed
no external action.

## Final performance-correction review

Recorded: 2026-11-05T20:21:51.385995+00:00

Recomputed both supplied hashes. The three-file delta against local candidate
`d57946ee2` is
`73baa58870461a4b5143a97d24145a5dc86d896e51338a5e42da7075499587f1`.
The resulting full 19-file patch at
`review-logs/cumulative-final.patch` is
`bda65fdba075378f3088a2b00681fdf63f57b9d9a66722ec78c8e1f688220163`.
Comparing the full patch sections against the previously reviewed candidate
confirmed changes only in console writer, its tests and query streaming code.

**No Design Quality blocker in the final cumulative patch.** Console formatting
and rendering now occur before acquiring the shared stdout lock. The fallible
write helper accepts ready text and still returns errors from both header and
body writes. Formatting errors still return through the production execution
stream before output. This restores the earlier lock scope without weakening
terminal failure propagation or introducing another output abstraction.

`status_with_state` centralizes status construction from an already borrowed
state. Active-query listing checks and constructs the result under that same
borrow, preserving the atomic-state correction while avoiding allocations for
retained stopped queries. This helper removes work rather than creating a second
state authority or a duplicate status policy. The changed utility tests continue
to exercise header/body write failures and exact ready-text output; the existing
actual sink test still covers formatting failure.

The prior full-context assessment and limitations apply to this hash. The parent
reports 232 Rust tests, 19 public tests, formatting and strict Clippy passed on the
preceding candidate. Those reported results are not relabelled as results for
this correction. I performed source and patch comparison only, ran no build or
test, and make no quantified performance claim. The correction's gate and final
immutable source pin remain pending.

## Immutable source confirmation

Recorded: 2026-11-05T20:30:31.161330+00:00

Read-only Git checks confirmed source HEAD
`2c9fa84994d317aade0d1c69faa9a378c780127d` and tree
`5d67cdc81cdd9ba7eb18a74eda17d84b9e5d30c7` in the implementation worktree.
The binary diff from baseline `b52144955b629314a000b1fe49eeea97fa3d0c5c`
hashes to `bda65fdba075378f3088a2b00681fdf63f57b9d9a66722ec78c8e1f688220163`,
exactly the reviewed final patch. Its 19 changed paths match that candidate.
`git status --porcelain --untracked-files=no` returned no entries, confirming
tracked source is clean. This binds the source-review verdict to the immutable
commit; it does not claim that the integration gate has passed.

The next-decision note `STREAMSOURCE-FILTER-BATCHING.md` was read end to end.
It explains fragmentation, alternatives and the required marker/error order
without presupposing a new coordination subsystem. Its reported diagnostic
ratios remain explicitly unoptimized shared-host evidence, and optimized dense-
marker performance remains unqualified. The proposed bounded combiner is
conditional on evidence of useful savings. No design blocker was found; two
minor wording suggestions were sent to define retractions and explicitly label
the ratio as new versus previous elapsed time. No source edits or builds ran.
