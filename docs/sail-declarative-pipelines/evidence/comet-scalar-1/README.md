# Qualified standalone Comet scalar reference

The full SDP/Extensions/performance goal remains active. This evidence qualifies
one local reference increment, following committed E1/E3/E4 and the standalone
adapter plan. The logical-null plan preceded the stronger predicate implementation.
`HUMAN-REVIEW.md` remains the maintained overall compendium.

## Source and scope

- Local branch: `work/streamsource-comet-scalar-20261105`.
- Commit: `06dd7e237eb5a343dcc6a6145e775f495e6c30de`.
- Tree: `455101575ecbfbec6f843464ce178e0d09046f51`.
- Parent: `2c9fa84994d317aade0d1c69faa9a378c780127d`.
- Increment SHA-256: `7477e67e9b6262e5aec067714c586ef7ac49790e8e6ac7d14116829213bdf325`.
- Cumulative diff against upstream `b52144955b629314a000b1fe49eeea97fa3d0c5c`:
  `743a1346feb7ae62a4cded0224b007312b471b09d80d149b2b0bdf5c25c25b30`.

The detached worktree is
`/Users/alexy/src/sail/tmp/comet-scalar-20261105-2c9fa8499`.
Its `review-logs/` retains every patch, control, raw log, script, producer source,
manifest and binary. No source was pushed or upstream offer made.
`final-source.json` verifies the branch, commit, clean tracked source and verdict.

The increment adds two standalone crates and workspace lock entries. It preserves
field semantics, admits zero-argument kernels, requires trusted immutable producers,
retains callback code, and checks declared nonnullable outputs through selected
encoded values. It does not connect packages, workers or pipeline source controls.

## Immutable qualification

The precommit receipt records checks before the conditional local commit.
`immutable-receipt.json` names the resulting commit and verifies the same head,
tree, file hashes and cumulative patch before and after every phase.

| Check | Result |
| --- | --- |
| Workspace nextest | 2,034 passed; one pre-existing ignored type-coercion test skipped |
| New standalone adapter tests | 17 passed, included in workspace count |
| Python checks against fresh CLI and actual client | Ten live server tests and nine mocked-transport client fixtures passed |
| Independent pinned Comet SDK probes | Two passed after the final source changes |
| Workspace Clippy | All targets and features passed with warnings denied |
| Formatting and documentation | Whole-workspace Rust formatting, selected Python formatting and strict adapter Rustdoc passed |

The ignored test is `untyped_limit_parameter_remains_inferable_after_coercion`,
already ignored in upstream. No new skip or weakened assertion was introduced.
The native fixture and no-probe example were built explicitly before tests.
The CLI default-feature build completed and its copied binary was hashed.
The SDK probe is staged only for explicit qualification and preserved afterward
outside the normal test tree; it requires its separately built producer.

Rust was 1.98.1 with locked DataFusion 55.2.0 and Arrow 59.2.0. Each worktree
owns its target, incremental builds were disabled and the receipt records its
build environment. The unchanged product environment supplied PySpark 4.2.1 and
PyArrow 26, while upstream development configuration declares PyArrow 24.
A copied native module supplied fixture imports; live tests used the freshly
built standalone server. This is not full wheel or Spark-engine differential
qualification. The integration branch's frozen Spark ports, pipeline suites,
metastore/profile and name-by-name Delta suite were not run here.

## Controls and review findings

Historical snapshots remain separate from the final pin. The initial original-UDF
control with the compatible loader failed six metadata cases and passed two.
Disabling code retention reproduced a deterministic lifetime failure without
calling into unloaded code. Both controls restored candidate source afterward.

A precise planned-field assertion replaced an earlier broad error check. Removing
only that guard fails the strengthened test. Restoring only `VariadicAny` fails
the nullary planning test. A physical-only null check fails populated encoded-null
cases. Arrow's own logical-null helper fails a nonzero single-child dense-union
case; the selected-value predicate closes that defect, including nested dictionary
and run-end forms. Valid slices ignore unused null children. The million-row
run test retains two physical values; source inspection establishes absence of
logical-row bitmap construction, not a measured allocation envelope.

All seven specialty reports independently pin the final tree and close their
source findings. Their pending-gate statements describe review time; the completed
immutable receipt supplies execution evidence. Reviewers distinguish source/log
inspection from checks executed by the integration owner.

Strict Rustdoc initially rejected bare source links and interpreted the credit
marker as an unresolved link. Those failures remain local; documentation rendering
was repaired and the strict check passed. No runtime assertion was loosened.

## Independent producer and attribution

The producer uses unchanged SDK/test sources and member manifests from Comet
`0f7f8e45399847715093b3d3affdfa97614b39dc`, under an isolated minimal workspace
with inherited package fields and Arrow dependencies. This is not the complete
Comet workspace build. The producer receipt records exact source and manifest
hashes. A top-level LICENSE acquisition path returned 404 after source acquisition;
that setup failure is not counted as a producer/runtime failure.

The Comet C factory, instance and list records, defaults and releases are copied
verbatim with the Apache header, credit and pinned URL. The extracted region and
comparison remain local. Separate host loader/importer comparisons reconstruct
the final adapted source; the null-presence predicate is original Sail code using
public Arrow APIs. The independent probes exercise results/nulls/order, retained
output and SDK containment of initialization/execution panics in this build.
No cross-release ABI compatibility or arbitrary-library safety is established.

## Remaining work and preservation

Standalone process retention requires caller admission bounds; package integration
must add content identity and resource ownership. Synchronous callbacks supply no
preemption guarantee. Marker isolation for projection/asynchronous expressions,
worker/package integration, durable preparation, checkpoint alignment, fencing,
change capture and C relations remain full-goal requirements.

Original runtime, prototype and foundation worktrees were preserved. No cleanup,
product-environment mutation, remote source action or maintainer communication
was performed. Selected structured receipts are copied here; raw artifacts remain
local with hashes in `artifact-manifest-final.json`. Earlier documentation push
errors were resolved by a later successful retry.
