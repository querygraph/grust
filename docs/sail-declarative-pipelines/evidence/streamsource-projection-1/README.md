# Streaming projection evidence

This directory records the local reference increment that isolates projection
expressions from flow-event markers. The implementation worktree is
`/Users/alexy/src/sail/tmp/streamsource-projection-20261105-06dd7e237`.
Source remains local and unpushed. Raw patches, logs, probe sources and binaries
remain under its `review-logs/` directory; no retained artifact was cleaned up.
The [artifact manifest](artifact-manifest.json) indexes 220 retained files by size
and SHA-256, including the local patches and server binaries.

The self-contained technical account is
[Streaming projection results](../../STREAMSOURCE-PROJECTION-RESULTS.md).
The complete goal and remaining obligations are in
[Human review](../../HUMAN-REVIEW.md).

## Identity and qualification

The starting parent is `06dd7e237eb5a343dcc6a6145e775f495e6c30de`.
The upstream comparison base is `b52144955b629314a000b1fe49eeea97fa3d0c5c`.
The final frozen tree is `bb8699fdfbc4ca88fa6c0e816e189af80e560efd`.
The increment changes 31 paths; the cumulative patch changes 58 files.

[The frozen snapshot](source-snapshot-final.json) records every cumulative file
hash and both patch hashes. Its pending status describes the time of freezing;
it is not a runtime verdict. The [qualification summary](qualification-summary.json) and
[immutable receipt](immutable-qualification.json) identify the verified commit,
commands, successful phases and new server binary. The commit is
`327572240365e2507f348ee92bc009cbfc67abe9`, retained on local branch
`work/streamsource-projection-20261105`. The immutable correctness qualification
passed 2,074 Rust tests with one pre-existing skip and 23 selected Python tests,
including 14 live-server tests and nine mocked client fixtures. A separate
source-erasure probe reproduced the open limitation. This is not production
performance, distributed recovery or upstream readiness.

Seven independently owned specialist reports retain findings and closures:
[Research](RESEARCH.md), [Design](DESIGN-QUALITY-REVIEW.md),
[Performance](PERFORMANCE-REVIEW.md), [Regression](REGRESSION-REVIEW.md),
[Scope](SCOPE-REVIEW.md), [Spark semantics](SPARK-SEMANTICS-REVIEW.md) and
[Test cases](TEST-CASE-REVIEW.md). A source-review verdict is distinct from
execution, performance or integrated recovery qualification.

## Plans and counterexamples

The saved request and constraints are in [REQUEST.txt](REQUEST.txt).
Before-code plan snapshots and timestamped hash records cover projection,
qualified source fields, nullable marker ownership, metrics, synchronous timing
and direct synchronous polling. Rejected representation choices remain archived.
These process records are evidence, rather than required reading for a design.

[Control outcomes](CONTROL-OUTCOMES.json) distinguish source failures, fixture
nonapplicability, rejected alternatives and test-API corrections. Raw failing
runs remain local. In particular, a run-end fixture initially encountered input
splitting rather than Arrow's length boundary; only its corrected full-batch
reproduction counts as evidence of the constructor panic.

[Arrow ownership](arrow-null-ownership.json) pins Arrow 59.2, the verbatim extract,
initial copy and adapted routine. The full comparison remains local. The routine
adds checked representability and fallible recursion; it does not promise
recoverable allocator failure or an execution memory budget.

## Measurements

[Final performance samples](performance-final.json) retain all eight cells and
every timing sample, exact-output assertions, profile, source hashes and host
load. They compare ordinary projection, the preceding instrumented node and
the repaired node within one process using rotating execution orders.
[Reference provenance](performance-reference.json) verifies that the preceding
production body is exact, with only trailing test-module declarations omitted.

The earlier instrumented and consolidation-only results are preserved separately.
They establish why a direct synchronous path was considered; they are not silently
relabelled as final-source measurements. Shared-host ratios do not establish
production throughput. The material mixed-marker cost remains open even when
data-only medians are close to ordinary projection.

[Preservation inventory](source-preservation.json) records the untouched runtime,
all original prototypes and qualified parent worktrees. Distributed alignment,
durable preparation, fencing, change capture, typed configuration and package/worker
integration remain unqualified by this increment.
