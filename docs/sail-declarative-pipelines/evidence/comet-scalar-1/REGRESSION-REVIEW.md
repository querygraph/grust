# Regression review of the human-review compendium

**Verdict: no introduced requirement regression or unsupported implementation
qualification found in the reviewed compendium.**

Reviewed the full `HUMAN-REVIEW.md`, SHA-256
`eed251526e19a5380b73d1d704430f28a61447ed935170cb6551d7d41719e3fe`, against the
current pipeline plan, extension integration decisions, standalone scalar plan,
foundation results and filter-batching note. This verdict covers the compendium,
not the work-in-progress scalar adapter or its still-unqualified test controls.

## Requirements and evidence retained

The document preserves the full end state: declarative table maintenance, ordered
change capture, crash recovery, existing native extension behavior, the added Comet
scalar route and measured performance improvement within Sail's execution model.
The smaller first delivery explicitly defers capabilities without replacing the
overall objective.

Prepared original effects, fixed input/computation identity, saved output or proven
identical replay, uncertain-outcome reconciliation and commit-time fencing remain
requirements. The document distinguishes cancellation, stream closure and durable
completion. Change capture retains complete ordering, symmetric upsert/delete
comparison, deletion versions, validation before reduction and the stated scope
of historical conflict checking. Ordinary table behavior remains protected; a
sidecar does not acquire an unsupported cross-table atomicity claim.

The extension summary preserves existing version guards, including mixed packages,
worker identity, explicit boundary selection, memory funding and lifetime
obligations. Process-retained code does not justify retaining session resources.
It correctly treats Comet purity and pointer validity as producer obligations
that a numeric probe cannot prove. It does not claim that scalar layout provides
a relation protocol, recovery or package integration.

The status table places metadata/lifetime qualification in progress and package,
worker and durable integration in future work. It explicitly distinguishes
inspection, fixture success, compilation and qualified interface behavior. The
new adapter's negative controls were compiling at the time of the review request;
the compendium reports no result for them.

The performance discussion retains the mixed-marker regression and requirements
for exact outputs, retained bytes, latency and cooperative polling. Inspected the
existing optimized sparse/grouped summary and receipt under
`evidence/streamsource-build-2/optimized-layouts/`: they report overhead on both
layouts and unchanged source at foundation commit
`2c9fa84994d317aade0d1c69faa9a378c780127d`. They support the compendium's limited
overhead statement, not a production throughput claim. A batching prototype is
proposed and conditional on preserving marker-before-later-error order.

## Review scope and compliance

The document reinforces self-contained plans before dependent code, focused
changes, negative controls and cumulative immutable qualification. It keeps local
implementation progress separate from upstream readiness. Detailed plan contracts
remain in force; the compendium does not state that its summary supersedes them.

Read the exact saved request and latest steering. The full AGENTS.md, LAKESAIL.md,
SHEHAB.md, WRITING-RULES.md and CLARITY.md were read earlier in the continuing
review; verified they are unchanged from baseline `ea0874db`. No context compaction
occurred since that reading. No source edits, builds, tests or benchmarks were
performed. Only this assigned evidence file was written.
