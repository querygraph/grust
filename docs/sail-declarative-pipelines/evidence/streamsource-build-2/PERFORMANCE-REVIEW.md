# Optimized streaming filter qualification

## Scope and current verdict

This review concerns the unchanged filter at local Sail commit
`2c9fa84994d317aade0d1c69faa9a378c780127d`, following the full foundation gate.
The new comparison has started but has not completed. No optimized-performance
verdict is available yet. No source edits, builds or benchmarks were performed
by this reviewer.

The saved request, repository `AGENTS.md`, `LAKESAIL.md`, `SHEHAB.md`,
`CLARITY.md` and `WRITING-RULES.md` were read. This report is supporting evidence,
not a founder-facing design decision or an upstream readiness claim.

## What the optimized probe can establish

The existing harness compares the actual candidate `StreamFilterExec` with an
exact source copy of the upstream filter at `b52144955b`. Both are compiled into
one test binary using the same dependency lock and execution context. The new
run requests the test profile with `CARGO_PROFILE_TEST_OPT_LEVEL=3` and debug
information disabled. That applies optimized code generation to the test-profile
build. It is distinct from the workspace release profile, which also enables
link-time optimization. The comparison must therefore be described as an
optimized test-profile diagnostic, not production release throughput.

The run directory is
`/Users/alexy/src/sail/tmp/streamsource-build-20261105-b52144955/review-logs/filter-cost/runs/20261105T231322.884712Z/`.
Its initial receipt identifies the immutable commit, an empty tracked diff,
filter hash `cb8b337f46395c0e76573eeca068586871e7ca7e84ee800756558fe0af3026dd`,
the optimization override and the exact harness source hashes. At inspection,
the log was still compiling dependencies. A complete receipt, `Finished` line,
successful test result and unchanged tracked source are needed before using ratios.

The same twelve cells cover batch lengths 128 and 8192, marker-free versus
alternating-marker inputs, and zero, half and full data selectivity. Both
implementations receive identical safe predicates. Before timing, both must
produce the exact expected sequence of marker bytes, retractions, values and
identifiers. Seven pairs reverse execution order, with two warmups per operator
and cell. Timing includes execution and draining the immediate consumer; planning,
construction, hashing and output retention are excluded.

The host is shared. CPU isolation, CPU-steal measurement, source input/output,
distributed execution, downstream retention and peak-memory qualification are
absent. More optimization or repetitions do not remove those boundaries. Keep
all cells and report ratios, including slowdowns.

## Structural cost and the smallest next experiment

The filter forwards each contiguous marker run and filters each contiguous data
run lazily. It must emit an earlier marker before evaluating subsequent data that
can fail. With alternating rows, each run contains one row. The earlier
unoptimized comparison therefore produced 65,536 candidate output batches from
512 or eight input batches. This output fragmentation follows directly from the
implementation; the contribution of individual allocations remains unmeasured.

One small follow-up can suppress zero-row filtered results while preserving
every marker, predicate evaluation and first-error position. It removes useless
downstream dispatch in selective cases without buffering or concatenation. It
cannot address full-selectivity fragmentation and must not be presented as a
complete batching solution. Skipping results must preserve bounded work per poll:
an unbounded loop over immediately ready, fully filtered batches would monopolize
the executor. Use a cooperative work budget if that experiment proceeds.

Before adding a combiner, measure marker placement and frequency separately:
boundary-only markers, sparse interior markers, adjacent marker groups and
alternating markers. Record kernel invocations and output batches independently
of elapsed time. That distinguishes ordinary per-marker cost from pathological
run fragmentation.

Combining already evaluated data with its immediately following marker is a
separate design choice. It can reduce output dispatch but adds copying and
retained bytes. It cannot remove the predicate invocation boundary before the
next data run. A candidate needs explicit byte and latency limits, and the
same ordering, error-position and input-lifetime checks. Gathering unevaluated
data across a marker changes the established evaluation contract.

## Final cumulative documentation review

Reviewed the changes against documentation commit `ea0874db` in the scalar
proposal, E1–E5 decisions, prototype-results qualification and implementation
plan, plus the complete new `EXTENSIONS-STREAMSOURCE-INTEGRATION.md` note.
No performance-related document blocker was found.

The updated documents correctly distinguish reduced DataFusion type coupling
from a stable cross-release binary interface. They preserve the existing route,
avoid an unmeasured preference for either boundary and make no throughput claim.
Their process-lifetime code-retention recommendation is a defensible initial
ownership choice, provided it does not also retain session allocations or memory
admissions. The integration note explicitly identifies the existing full-package
owner retention and makes separation of code and session state required porting
work, rather than claiming it already works. This addresses the main resource
risk in carrying the existing retention policy forward.

The documents require native memory admission to last until dependent native
allocations and task effects settle. They also require testing retained results
after dropping function, plan and session owners. Those are necessary ownership
checks, not demonstrated memory bounds or a substitute for testing cancellation
and quota settlement. The proposal describes them as unbuilt qualification.

The relation discussion no longer assumes that two small adapters provide a
complete relation contract. It separates scalar work from expression transport,
asynchronous execution, placement and replay. Nothing here requires importing
an entire Comet or Sedona runtime solely to adopt a C layout. Performance and
maintenance costs of any relation adapter remain an implementation decision.

The new note also preserves marker isolation and binds code/configuration identity
for replay. It does not present immutable declarations as proof of deterministic
external effects. That is the appropriate scope for the streaming integration.

At this final documentation inspection, the optimized filter log had advanced
through dependency compilation but still contained no completed comparison.
The source pin and initial receipt remained unchanged. No timing result is
claimed. This review performed no source edits, builds or runtime measurements;
the saved request and governing-file compliance remains confirmed.
