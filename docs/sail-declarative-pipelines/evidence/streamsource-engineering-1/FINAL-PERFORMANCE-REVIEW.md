# Final cumulative Performance review

## Candidate and verdict

**No must-fix Performance findings in this documentation candidate.** The
revised design carries the source-backed resource limitations forward without
claiming measured performance or trading away correctness to reduce cost.

- Documentation baseline: `f23da50ccdf4ac1258fa1c6803aeb54df042a03e`.
- Cumulative patch SHA-256: `2a619d67564fa3090733def44d5cf97c5ac4437ca0d8accc6abcf258a250a05c`.
- `candidate-files.json` identifies 22 reader-facing, governance and reference-scope documents. All 22 working-file hashes matched that manifest during review.
- Evidence basis: `PERFORMANCE-AUDIT.md` and its 27-file `performance-source-manifest.json`, with pinned upstream, P4, P3 and bounded-runtime source revisions.

This verdict covers the cumulative documentation changes within the Performance
specialty. It is not an implementation, benchmark or integrated runtime verdict.
The main proposals, architecture, event semantics, plan, decision notes, fencing,
runtime-reuse and typed-configuration documents were read in their resulting
form; prototype and reference-scope changes were checked in the cumulative patch.

## Findings resolved in the design

| Concern | Candidate treatment | Assessment |
| --- | --- | --- |
| Bounded channels conceal unbounded replica overflow | `STREAMING-ARCHITECTURE.md:176` accounts for retained transport, preparation, state, snapshot workspace and metadata across tasks; the plan requires graph-wide progress under slow consumers | Correctly identifies the missing accounting and the risk of replacing overflow with naive blocking queues |
| Periodic checkpoints treated as memory limits | `DECISION-NOTES-STREAMING.md:112` separates operational time/volume triggers from byte limits and snapshot/commit work | No arbitrary period or unsupported hard bound is claimed |
| Whole-memory preparation and archives | `REDESIGN-REVIEW-PACKET.md:81` and `STREAMING-REVIEW-AGAINST-RUNTIME.md:53` require immutable chunks, incremental digests/scans and budgets while retaining pending artifacts | Preserves exact retry meaning and validation rather than removing sealing to save I/O |
| Full-state snapshots assumed scalable | `STREAMING-ARCHITECTURE.md:183` and state-storage note at `DECISION-NOTES-STREAMING.md:130` restrict full snapshots to a qualified envelope and retain incremental/partitioned alternatives | Cost and practical limits remain unmeasured and explicitly require qualification |
| History checking silently becomes an unlimited index | `CHANGE-CAPTURE-SEMANTICS.md:82` distinguishes current-version validation from optional exhaustive fingerprint retention with a horizon, frontier and budget | No mandatory all-history ledger; no unsafe arbitrary expiry is proposed |
| Resource pressure permits unsafe reclamation | `STREAMING-ARCHITECTURE.md:170` separates temporary spill from durable artifacts and retains all required recovery points; tombstone retirement requires a durable source frontier | Resource limits do not override accepted-effect recovery or anti-resurrection guarantees |
| Atomic state publication treated as a free or existing capability | Storage alternatives explicitly require target metadata, recovery and all-writer qualification; sidecar recovery remains available and view substitution remains a product choice | One atomic publication is a proposed correctness boundary, not a measured latency or write-amplification advantage |
| Source progress confused with a memory or completeness bound | Source identity, partition participation/discovery, end capture and event-time progress remain explicit contracts | Neither captured offsets nor idleness establishes a resource bound or source completeness |
| New coordination or runtime added without necessity | Existing job/task/catalog ownership is preferred; a new commit authority needs enforcement and operational justification; Dhall compiles outside execution | No unnecessary window store, broker client or language evaluator becomes a prerequisite for stateless append |
| Component results promoted into performance evidence | `PROTOTYPE-RESULTS-STREAMING.md:143` and `:182` disclaim a measured memory/throughput envelope and distinguish component probes from integrated qualification | No unsupported throughput, latency, scalability or memory measurements found |

## Remaining implementation evidence

The numerical envelope, reservation implementation, bounded chunking and resource
exhaustion behavior are still work to implement and qualify. A latest-version
register can grow with distinct live or deleted keys even without an exhaustive
history ledger. Default within-interval conflict checks also need a resource
policy for large intervals. The documents require budgets; they do not prove
those mechanisms already exist.

Qualification must include large individual batches, slow/unread replicas,
stalled watermarks, growing key counts, pending accepted effects, storage
exhaustion, cancellation and restart. Benchmarking candidate storage or
transport choices follows correctness qualification under matched workloads
and budgets. No new build, runtime test or benchmark was performed for this
final document review. Focused probes reported by other reviewers were checked
for scope language; they were not independently rerun here.

## Prompt and governing instructions

The saved engineering request was reread for this final pass, together with the
complete repository AGENTS.md, LAKESAIL.md, SHEHAB.md, WRITING-RULES.md and
CLARITY.md. Earlier saved requests were read in the preceding review passes.
The latest engineering-over-Spark directive governs this assessment. No context
compaction occurred during this final pass. Only this assigned review evidence
was written; no main document or source worktree was edited.

## Addendum: original-version conflict checks

**No must-fix Performance findings in the final candidate**, cumulative patch
SHA-256 `8dd7bac1e54a6b463f74f91c37b9cb604e15872b4c30772b5fba6089ee7e57b9`,
against the same documentation baseline. This supersedes the earlier candidate
hash for the final verdict. Both preserved and current patch hashes were
verified, and all 22 current document hashes match `candidate-files.json`.

The delta from candidate `2a619d67` changes only CHANGE-CAPTURE-SEMANTICS.md,
CHANGE-CAPTURE-ON-STREAMSOURCE.md and REDESIGN-PLAN.md. Exact prior versions were
reconstructed from the preserved patch and verified against the prior manifest
before comparing them with the current files.

The correction checks original event versions against a pinned durable-state
snapshot before maximum reduction can discard conflicting evidence. It binds
that snapshot to the commit precondition and requires safe reconciliation or
revalidation of the same immutable normalized input if state changes. The plan
explicitly budgets that original-version check without reevaluating the source.

This adds real lookup and possible revalidation work that implementation must
account for. It preserves the declared validation guarantee instead of omitting
it for speculative speed. It does not require an all-history conflict index:
exhaustive checking remains a separate bounded-horizon option. Normalized input
must remain available for any required revalidation, so retained artifacts and
retry work still need the existing memory/disk and admission limits. No new
performance result, constant-memory claim or free retry assumption is introduced.

The saved request was reread for this delta pass; the complete governing files
read above remain applicable, and no context compaction intervened. This was a
documentation-only review. No source was changed and no build, benchmark or
runtime test was run.
