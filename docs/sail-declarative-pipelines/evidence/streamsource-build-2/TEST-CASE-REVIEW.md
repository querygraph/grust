# Optimized filter probe review

The existing probe is suitable for the planned optimized comparison. No blocking
fixture or output-validation defect was found. This is source review only:
the new optimized run has no result yet, and this review ran no builds or tests.

Read the complete saved request and AGENTS.md, LAKESAIL.md, SHEHAB.md,
WRITING-RULES.md and CLARITY.md. The active scope includes the broader pipeline
and Comet extension objective; this assigned review covers only the filter probe.

## Source and optimization boundary

Verified clean tracked source at commit
`2c9fa84994d317aade0d1c69faa9a378c780127d`, tree
`5d67cdc81cdd9ba7eb18a74eda17d84b9e5d30c7`. The probe's baseline is the exact
filter source at `b52144955b629314a000b1fe49eeea97fa3d0c5c`. The runner compares
its saved baseline bytes with Git before staging it.

Reviewed files under the source worktree's `review-logs/filter-cost`:

| File | SHA-256 |
| --- | --- |
| `run_probe.py` | `5fe75e3bdec340b3695978df4fa8e224667bba173ff9f77f2b44fc91e56376a9` |
| `filter_cost_probe.rs` | `3553db11f2f6f05819bb51836c50df86b33ec5bf62f221cb3df12e2ebd53f9dd` |
| `summarize.py` | `ce7341a6b753e51353927b5e19be75e03ad55855cb1bc976dd67b674ce275069` |
| `baseline_filter.rs` | `1d17ab9ac93b416a4fa946ca763500e1a4a2a2422126bf0dcb00ae4a42a5abed` |

Use `CARGO_PROFILE_TEST_OPT_LEVEL=3` with the runner's `--profile test`.
The runner inherits and records that environment setting. Its `test-opt1`
option would override the setting to one and must not be used for this run.
The workspace manifest has no test-profile or package-specific optimization
override, so the chosen test profile applies to both the candidate library and
the baseline module in the probe. Both use the same resolved dependencies.

Retain compiler invocation or Cargo fingerprint evidence for the candidate
library and probe binary once compilation completes. The probe's
`cfg!(debug_assertions)` value alone cannot establish optimization level.
An optimized test profile can retain debug assertions and overflow checks;
it is not the workspace release profile with link-time optimization. The two
implementations also retain their documented compilation locations: a public
library implementation and a baseline module inside the probe. This is an
operator comparison, not a whole-engine build comparison.

## Coverage and preserved evidence

The Rust loops cover exactly twelve cells: two batch sizes, no markers or
alternating markers, and zero, half or full data selection. Before timing,
both operators must match the expected ordered rows exactly, including marker
bytes, retractions, values and row identifiers. Fingerprints supplement that
comparison rather than replacing it. The safe numeric predicate is identical
for both implementations and allows the old filter to preserve markers.

Two warmups precede seven paired samples per cell by default. Execution order
alternates within and across cells. The timer includes execution and stream
drain, with output consumed through `black_box`; construction, exact comparison
and hashing remain outside timing. Every timed run checks output row count and
records output batch count. The summary rejects missing cells, missing repeat
indices, inconsistent output counts, nonpositive timings and incomplete paired
orders. It retains all cells and samples, including slowdowns.

The runner creates a unique directory, copies the probe sources and candidate
filter, records command, environment, lock hash, host information and initial
tracked diff, and preserves the Cargo log and final diff. It refuses to replace
different existing staged probe files. It requires a successful completed build,
passing test and unchanged tracked candidate before producing a successful
summary. It performs no cleanup. The new receipt must identify the verified
commit above and an empty tracked diff.

## Minimal follow-up layouts

The twelve-cell rerun should remain directly comparable with the earlier run.
Before using it to select a batching design, add only two focused layouts at
8192 rows and half selection: one tail marker per input batch, and one middle
burst of adjacent markers. Those distinguish sparse boundary and grouped-marker
costs from the alternating worst case without another full cross-product.
Use global row and marker identifiers if comparing order across batches; the
current warm-input fixture deliberately repeats identical batches.

Any later buffering change must retain the existing marker-before-later-error
regressions. Add a bounded-retention and pending-input flush case only if the
chosen design introduces buffering. No such source change or extra execution
was performed for this review.

The probe remains a shared-host diagnostic with warm numeric inputs, immediate
downstream consumption and no CPU isolation or steal measurement. It does not
measure backpressure, retained-buffer memory, source I/O, arbitrary Arrow payload
cost, distributed execution, checkpoint recovery or extension interoperability.
Optimized results can inform the fragmentation decision without establishing
production throughput or removing these limits.

## Cumulative documentation review

Reviewed the cumulative documentation changes against `ea0874db`, including the
complete scalar proposal, E1–E5 decisions, new StreamSource integration design,
prototype-results qualification and redesign-plan addition. The coordination
entry introduces no new execution claim. No source edits, builds or tests were
performed for this review.

The P5 total remains three reported historical fixture tests. Its new
qualification correctly separates those results from independently built Comet
libraries, package loading, worker execution and result lifetime. The metadata
and library-retention concerns are identified as inspection findings rather than
executed failures. The proposal does not turn those concerns into a claim that
the adapter is already repaired or integrated.

The proposed tests distinguish the important alternatives: existing DataFusion
route controls versus C adapter failures, complete metadata versus reconstructed
argument fields, retained result callbacks versus function-only library ownership,
explicit boundary identity versus silent fallback, and marker isolation versus
evaluating native code on placeholder rows. Retained results after function,
plan and session teardown, release counts and quota settlement need separate
checks; scalar success alone is correctly insufficient. The planned independent
Comet binary is an interoperability check that the handwritten fixture cannot
replace.

The integration design correctly keeps host porting, scalar adapter development,
relation interface selection and durable recovery as distinct dependent work.
Comet purity admission, reserved constant-argument initialization, mixed-package
version checks and replay identity remain requirements to qualify. Projection,
asynchronous expression isolation, relation C integration and fenced effects are
not presented as completed by the foundation tests. No optimized filter result
is claimed while the unchanged-source run is still compiling.

Two editorial corrections were sent to the integration owner before commitment:
the scalar proposal's marker-safety sentence should state a requirement rather
than imply that every current streaming expression path is safe; the historical
P5 omission should describe unverified external-library interoperability rather
than session permissions. Apart from those wording qualifications, no test-count
or unsupported-qualification finding blocks this design checkpoint.
