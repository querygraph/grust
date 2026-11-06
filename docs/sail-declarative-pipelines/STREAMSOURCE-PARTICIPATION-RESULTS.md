# Preserve streaming sources before data pruning

A streaming computation must retain its sources when no data rows pass a filter.
The local reference now protects Sail's executable flow graph before ordinary
logical optimization. This preserves ordered control markers and source failures
without replacing Sail's continuous execution with repeated bounded jobs.

This is a compiler-boundary qualification. It does not establish distributed
checkpoint alignment, durable source identity, target fencing or process-restart
recovery. A separate optimizer defect and measured compilation overhead remain
explicit limits.

## The contract and its fit with Sail

Sail's flow events contain data or ordered markers for latency, watermarks,
checkpoints and end of data. A query such as `WHERE FALSE` has no data output,
but must still carry those markers and report source errors. DataFusion's ordinary
batch optimizer can instead remove the scan and return a bounded empty relation.
Detecting a source after that removal cannot restore its execution path.

The implementation uses Sail's existing resolver, streaming rewriter and event-aware
operators. A shared mandatory compilation phase runs after name/type analysis and
before optional logical optimization, for both execution and explain. It receives
the actual session context, retaining the query timestamp and configuration.
Optional optimizer settings cannot disable this correctness boundary.

Before event lowering, four audited public rules preserve expression simplification,
filter pushdown, payload-column pruning and immutable-expression sharing. Preparation
has a fixed maximum of three rounds. Unsupported streaming relational shapes reach
named refusals before a pruning rule can hide their sources. Bounded scalar
subqueries retain their ordinary treatment.

Each in-process source occurrence receives a clone-preserved identity token, so
two reads of one provider remain distinct participants. This token supplies no
restart identity. The collector preserves qualified names and Arrow field metadata.
Declared streaming inputs are refused before eager tail counting, pivot inference,
crosstab inference, scalar time-travel evaluation, memory-table creation and
prepared-statement preparation.
Bare DataFusion APIs retain their separate batch-planning contract.

Zero initial consumer demand, such as `LIMIT 0`, returns without executing or
polling the child. That is cancellation of demand, not a final durable checkpoint.
Within streaming execution, a false-filtered unbounded source remains live.
Public batch collection refuses that unbounded result explicitly.

An optional first optimizer rule would disappear when optimization is disabled.
An analyzer-only rule lacks the actual query timestamp needed by simplification.
Owning the narrow DataFusion compilation routine makes the mandatory phase explicit;
its pinned attribution and exact comparison are retained. A second participation
graph would instead need duplicate-scan prevention and separate control routing.

## Executed evidence

The local branch `work/streamsource-participation-20261105` is the subject of these
results. Source commit `6e4da8d33ba1bf4073fcb853123f81860ef18151` has tree
`f71f8c5c97b08baa0c7f0f914ea7a2e24d150622` and parent
`327572240365e2507f348ee92bc009cbfc67abe9`. Seven specialist reviews cover the
cumulative patch against upstream `b52144955`. New upstream `5411f8433` was
inspected separately; these results do not qualify integration onto that revision.

Immutable verification passed formatting, strict Rust documentation, workspace
Clippy across all targets and features, and 2,091 Rust tests. One pre-existing
test remains skipped. The increment adds 17 Rust tests and 15 public cases.
A freshly built CLI and native import module passed 29 live-server cases and nine
mocked client fixtures. The server reported 4.2.1, with PySpark 4.2.1 retained.
Python formatting and lint checks passed. This is not a wheel or cluster qualification.

Controlled sources prove all marker kinds in order, zero-output source execution,
errors after markers, separate provider occurrences, exact and inexact filter
pushdown, selected-column materialization, zero-payload row counts, metadata and
full compilation re-entry. Tests also cover aliases, views, bounded scalar
subqueries, disabled optional optimization, eager command boundaries and ordinary
batch controls. Public tests retain foldable limits/offsets and currently working
scalar subqueries, while refusing unsupported hidden streaming operators explicitly.

Bypassing mandatory preparation fails both marker/failure controls; restoring exact
source bytes passes both. Restoring the prior occurrence and zero-demand
implementations fails two further controls; restoring the candidate passes them.
An immutable-function counter exposed three calls over twelve row evaluations
instead of one call over four rows after early lowering. Common-expression sharing
restores one call and four row evaluations, with unchanged data. Volatile and
conditional controls preserve their separate evaluation requirements.

Spark 4.2.1 source inspection supports protecting streaming inputs from false-filter
pruning and identifying sources before batch optimization. It does not require
Sail to adopt Spark's microbatch architecture. Executed JVM differential parity is
not claimed. Failed fixtures, build invocations, lint checks and diagnostic runs
remain retained separately from passing execution.

## Planning costs and the unresolved optimizer defect

Equivalent-output probes compare the previous late-lowering entry point with the
mandatory compiler on one source tree. They check direct analyzed execution, both
compiled schemas and exact results before timing. Each cell has seven alternating
pairs of 32 compilations after warmups. Physical planning and execution validation
are outside timing.

| Input | Nested projection/filter layers | Median new/previous time | Sample range |
| --- | ---: | ---: | ---: |
| Batch | 0 | 1.007 | 0.981–1.029 |
| Batch | 12 | 1.003 | 0.994–1.008 |
| Streaming | 0 | 1.660 | 1.573–1.771 |
| Streaming | 12 | 0.942 | 0.926–0.967 |

These are unoptimized-build diagnostics on a shared macOS host without CPU
isolation or steal measurements. They are ratios, not production throughput or
latency results. The short streaming graph has material compilation overhead.
Keep that startup cost visible for review; measure an optimized profile before
selecting a tuning policy. This increment does not repair mixed-marker execution
fragmentation or establish resource admission.

A separate probe repeatedly reuses the same output alias through twelve additions.
Direct analyzed execution returns the intended values 13 through 16. Both previous
and new optimized paths return 2 through 5, for batch and streaming input.
An isolated rule probe retains the expected two additions through analysis and
filter pushdown, then loses one addition when DataFusion 55.2 projection
optimization runs. Identity-projection controls remain correct. The defect is
therefore isolated to projection optimization, while its repair remains unbuilt.
Those failing cells are excluded from timing qualification. The passing
table uses distinct aliases; it does not waive the failed query's expected values
or establish general batch/streaming correctness.

## Review and implementation boundaries

The source-preservation boundary is now locally demonstrated on the admitted corpus.
The [plan](STREAMSOURCE-PARTICIPATION.md) explains the decision and alternatives;
the [human review compendium](HUMAN-REVIEW.md) supplies the full pipeline and
Extensions goal. The [evidence directory](evidence/streamsource-participation-1/)
retains exact source identities, controls, all planning samples and verification
receipts. Raw patches and binaries remain local.

The [composition plan](PROJECTION-COMPOSITION.md) bounds the logical correction;
[composition results](PROJECTION-COMPOSITION-RESULTS.md) qualify its repair at a
separate source pin. The failing findings above apply to the source named here.
Optimized-profile measurements must guide any startup-cost change. Recoverable
source controls, transport alignment, immutable prepared effects, enforced target
ownership, deterministic change-capture publication, typed configuration and native
package/worker integration remain separate implementation obligations. No upstream
publication or production-readiness claim follows from this local reference.
