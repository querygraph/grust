# Regression review of extension integration documents

**Verdict: no introduced documentation regression or unsupported production
qualification found in the reviewed candidate.** This is a document and source
inspection verdict, not approval of an implemented extension integration.

## Scope and preserved evidence

Reviewed the complete cumulative changes against Grust baseline `ea0874db` in
`DECISION-NOTES-EXTENSIONS.md`, `EXTENSIONS-ON-ARROW-C-ABI.md`,
`PROTOTYPE-RESULTS-EXTENSIONS.md` and `REDESIGN-PLAN.md`, together with the complete
new `EXTENSIONS-STREAMSOURCE-INTEGRATION.md`. Read the final documents in context,
including the plan's unchanged recovery and migration requirements.

The prototype report adds qualification without removing its prior observations.
Its three reported fixture tests, results, null behavior, argument-order check,
error propagation, missing-probe refusal and formatter/lint observations remain.
The report now explicitly limits those observations to the fixture. It does not
convert them into evidence for independently built Comet or Sedona binaries,
package admission, workers, metadata fidelity or result lifetime.

The rewritten proposal removes unsupported claims of stable release compatibility,
interchangeable Sedona binaries and trivial relation adapters. It preserves the
existing DataFusion-FFI route and its exact host checks, including mixed packages.
Explicit boundary selection prevents a missing implementation from silently
changing semantics. Existing relation dispatch, placement, memory admission,
cancellation and cleanup remain required host contracts.

The new integration design distinguishes the existing pipeline branch from the
upstream-based foundation. It does not claim that the extension host has already
been ported. It also distinguishes process-retained code from session resource
retention: the current full-package registry ownership needs separation rather
than being presented as already-correct session cleanup.

Streaming markers and retractions remain Sail-owned. Projection/asynchronous
expression isolation, live-source checkpoint participation, replay identity,
prepared output for nonreproducible computations and fenced external effects
remain required integration work. Finite Arrow output is not treated as proof of
recoverability. Existing pending-effect migration and ordinary-table requirements
in the plan are unchanged.

## Source checks and limits

Directly inspected the P5 adapter at
`/Users/alexy/src/sail-proto-p5/crates/sail-c-udf/src/udf.rs`: it retains the library
in the function, reconstructs execution fields from array types, passes null for
constant initialization arguments and marks imported functions immutable. These
support the new qualification rather than a claim that those gaps are repaired.

Read the official pinned Comet
[SDK contract](https://github.com/apache/datafusion-comet/blob/0f7f8e45399847715093b3d3affdfa97614b39dc/native/comet-udf-sdk/src/lib.rs)
and [C interface](https://github.com/apache/datafusion-comet/blob/0f7f8e45399847715093b3d3affdfa97614b39dc/native/comet-udf-sdk/src/c_abi.rs).
They support the corrected release-stability limits, SDK support boundary,
reserved null constant pointer and pure immutable-function restriction. No
independent producer binary was built or loaded during this review.

Inspected the optimized filter probe receipt and current compiler log under
`review-logs/filter-cost/runs/20261105T231322.884712Z/` in the foundation worktree.
The receipt names source commit `2c9fa84994d317aade0d1c69faa9a378c780127d` and
requests test optimization level 3. Its empty working-tree diff hash is not the
baseline-to-candidate patch hash. At inspection compilation was still running;
there was no completion receipt or summary. No optimized performance result is
claimed. The plan correctly retains marker-heavy performance as unqualified.

## Candidate identity and compliance

SHA-256 hashes of the inspected documents:

| Document | SHA-256 |
| --- | --- |
| DECISION-NOTES-EXTENSIONS.md | `7b7af5d7ffe5ffb7f4da2366f0fe83025c7b6fd3d61be5247dda65c737efdeb7` |
| EXTENSIONS-ON-ARROW-C-ABI.md | `077b88d8f7e20e11bcdeaddf15e3796a3bf3841fba48e6c1bbad8a26b251f93a` |
| EXTENSIONS-STREAMSOURCE-INTEGRATION.md | `900d5168cc7122ccd6c5cf00a5efa1e3ba6e74ce4ec46261a3ede450a15205fa` |
| PROTOTYPE-RESULTS-EXTENSIONS.md | `0a451cfdc8980100a6408a0bd2c855c87ca28bc9135448b6aa88c13d2f72613a` |
| REDESIGN-PLAN.md | `fe258daadd05adfe6e8d42576ee7cc36338e5d95029cb7ed38142dd0f7005179` |

Read the exact saved continuation request and full AGENTS.md, LAKESAIL.md,
SHEHAB.md, WRITING-RULES.md and CLARITY.md. The user instruction to incorporate
Comet and preserve existing extensions governs this scope. No builds, tests,
benchmarks or source edits were performed. Only this assigned evidence file was
written. Subsequent substantive document changes need affected-area review.
