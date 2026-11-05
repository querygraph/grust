# Final cumulative regression review

**Verdict: no unresolved introduced documentation regression found.**

Reviewed the complete cumulative diff for all 22 documents in
`candidate-files.json`, within the regression specialty, against baseline
`f23da50ccdf4ac1258fa1c6803aeb54df042a03e`.

The reviewed `cumulative-documents.patch` SHA-256 is:

```text
8dd7bac1e54a6b463f74f91c37b9cb604e15872b4c30772b5fba6089ee7e57b9
```

All 22 current document hashes match the candidate manifest. This verdict covers
that candidate, not subsequent changes or an implementation.

## Findings resolved and guarantees preserved

- Source descriptors and checkpoint participants are explicitly bound to
  preparations. Added partitions require discovery and bootstrap policy;
  retained-only history is not silently declared complete.
- Required incarnation-bearing event provenance survives projection or comes
  from an admitted envelope. Native event IDs are optional when a proved derived
  identity supplies the required replacement-event guarantee. Source identity
  and business ordering remain distinct.
- Original normalized values are validated before reduction. The durable `8:A`
  versus incoming `8:B, 9:C` example prevents a winning later event from hiding
  a current-version conflict. The validation snapshot is bound to acceptance
  preconditions; changed state requires reconciliation or revalidation of the
  same immutable input. Exhaustive historical checking is not falsely claimed.
- Immutable prepared work, separate effect outcomes, retained recovery state
  and unknown-outcome reconciliation remain required. Already accepted effects
  cannot be abandoned merely because refresh or ownership changes.
- Ordering and storage changes require migration, resolution of old pending
  effects and fencing of old owners. Missing ties, versions or deletion history
  cannot be reconstructed by changing a comparator. Snapshot-plus-frontier
  bootstrap remains conditional on authoritative reconstruction data.
- Ordinary-table interoperability remains an explicit requirement. Atomic
  key-state publication is proposed capability work; filtered views do not
  silently replace public tables. All permitted writers must participate in
  enforcement. Neither catalog ordering nor external single-writer assurances
  remains an admitted durable fallback.
- Historical prototype counts are unchanged. The added marker reproductions,
  parser execution and semantic model remain distinct from source inspection,
  integrated execution and durability qualification. The new marker summary
  agrees with TEST-EVIDENCE.md, including 29 expected errors and separate
  metadata-loss verification. No Dhall/CUE integration is claimed as executed.
- Reference-scope notices supersede inferior compatibility requirements without
  rewriting their recorded observations. ASTRA-REDESIGN-0.md and
  ASTRA-REDESIGN-1.md are byte-identical to the baseline.

## Limits and instruction compliance

This final pass reviewed documents and retained evidence. It ran no source,
runtime, broker, Spark, fencing, build or distributed tests. The earlier direct
source inspection and its hashes are in REGRESSION-AUDIT.md. Target adapters,
source admission, migration and external-writer behavior still need implementation
and qualification at the real source/commit boundaries.

The saved current request was reread for this pass. Complete governing AGENTS.md,
LAKESAIL.md, SHEHAB.md, WRITING-RULES.md and CLARITY.md were read for the audit;
the final LAKESAIL amendment was reviewed in this cumulative diff. Instructions
and saved prompts were reread after the preceding context compaction. The latest
engineering directive takes precedence over earlier compatibility defaults.
Only this assigned final review file was written during the final pass.
