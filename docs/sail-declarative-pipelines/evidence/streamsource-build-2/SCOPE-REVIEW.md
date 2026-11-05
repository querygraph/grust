# Scope review: Extensions in the StreamSource redesign

## Verdict and reviewed boundary

No scope blocker was found in the new integration proposal and corrected scalar
ABI proposal. They preserve the requested end state: recoverable declarative
pipelines built on StreamSource, incorporating the existing extension host and
an additional Comet C scalar route. They do not redefine the full objective as
a standalone scalar loader or imply the replacement runtime is complete.

The reviewed documentation baseline is `ea0874db`. This review inspected the
current files and their differences from that baseline, including the new
untracked integration note. These hashes identify the exact drafts read:

| Document | SHA-256 |
| --- | --- |
| `EXTENSIONS-STREAMSOURCE-INTEGRATION.md` | `d43d6e8e7b0f7ce2714a8f01c794d0fa9c87fb2a713ec9a243ca105641afacb4` |
| `EXTENSIONS-ON-ARROW-C-ABI.md` | `077b88d8f7e20e11bcdeaddf15e3796a3bf3841fba48e6c1bbad8a26b251f93a` |

## Scope boundaries that are appropriately explicit

- Existing package identity, worker lookup, owner retention, memory admission,
  relation dispatch, cancellation and cleanup remain capabilities to preserve.
  Their presence on the older integration branch is distinguished from the new
  upstream-based foundation branch.
- Comet scalar work is an independently testable increment. The existing
  DataFusion route remains available; adding that increment does not discard
  native relations or claim that Comet defines their interface.
- Arrow-only relations remain part of the design scope with a separate mechanism
  decision. This avoids silently imposing scalar-only delivery as the final state.
- Marker isolation, stable identities, prepared output and enforced target fencing
  remain requirements of recoverable pipelines. A native function or Arrow stream
  is not automatically admitted as a replayable source.
- Prototype fixture observations are presented as narrower evidence than package,
  worker, Comet-library or durable-recovery qualification. No ready-for-upstream
  or production claim is made.

The corrected ABI proposal also appropriately keeps exact DataFusion/Arrow guards
for packages still using DataFusion FFI. It does not silently broaden admission
for mixed packages when adding the pure C scalar route.

## Findings sent to the integration owner

Two consistency improvements should accompany publication:

1. `PROTOTYPE-RESULTS-EXTENSIONS.md` still says that the scalar import sequence is
   correct and that the recommendation is unchanged. Preserve the historical
   three-test observations, but add the newly identified argument-metadata and
   returned-array lifetime qualification. A past fixture pass should not be read
   as discharging those production obligations.
2. Add an explicit Extensions section or link in `REDESIGN-PLAN.md`, so the main
   implementation plan carries the expanded user objective. The companion note
   alone should not be the only location recording required extension integration.

`DECISION-NOTES-EXTENSIONS.md` still contained the older claims when inspected.
The integration owner already declared ownership of its correction; this review
therefore does not duplicate those edits. A final consistency check must verify
that its scalar, relation and mixed-package admission decisions agree with the
corrected proposal.

## Evidence and compliance

Read the complete saved request for this increment, `AGENTS.md`, `LAKESAIL.md`,
`SHEHAB.md`, `CLARITY.md` and `WRITING-RULES.md`. The latest clarification names
Comet. This is document/source-scope inspection only. No builds, runtime tests,
performance measurements or source changes were performed. Only this report was
written. Reported Comet facts are reviewed as documented constraints; independent
primary-source verification belongs to the Research review. No context compaction
occurred after the governance reads.
