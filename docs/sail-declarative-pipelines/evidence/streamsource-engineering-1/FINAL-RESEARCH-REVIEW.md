# Final Research review

Verdict: no must-fix Research finding in the reviewed documentation candidate.
This is a source, attribution and evidence-boundary verdict, not implementation
approval or an integrated runtime qualification.

## Candidate identity and review scope

- Baseline: `f23da50ccdf4ac1258fa1c6803aeb54df042a03e`.
- Cumulative patch: `cumulative-documents.patch`.
- Patch SHA-256: `8dd7bac1e54a6b463f74f91c37b9cb604e15872b4c30772b5fba6089ee7e57b9`.
- The patch contains 22 changed document paths. All 22 current file hashes
  match `candidate-files.json`; the patch hash also matches that manifest.

Reviewed the cumulative document changes within the Research specialty and
the resulting substantive proposals, architecture, decision notes, plan,
prototype descriptions and results. Checked the reference-scope notices in
the older documents. Reviewed the typed-configuration research, fencing audit,
marker-test evidence and relevant semantic/source evidence supporting the
outward claims. The final typed proposal's recommendation is an authoritative
strict model with optional Dhall, not an unresolved choice about whether
server-side validation is necessary.

The latest saved request, its referenced prior prompts, `AGENTS.md`,
`LAKESAIL.md`, `SHEHAB.md`, `CLARITY.md` and `WRITING-RULES.md` were reread for
this final review. The new engineering directive governs over earlier parity
defaults. No source changes, builds, installations or integration runs were
performed during this final pass.

## Findings resolved in the candidate

The configuration proposal separates the PySpark project loader, Sail's typed
application settings and repository YAML used to generate connector parsers.
It also separates client-only file discovery from execution settings that
the server validates. Python, SQL and direct API options share admission;
a validated authoring file is not presented as sufficient to validate a graph.

The existing parser's observed acceptance of malformed scalar types, duplicate
names and unknown nested fields remains explicitly a focused parser result.
The merge-order and unknown parse-mode fallback findings remain source-derived.
The retained experiment body and stdout hashes recompute to the recorded values:
`bec19d937caa03c565552b86641c9b7c7eb659e5676acd749ede37f4d5baf1a6`
and `3808a1f6a55164ed21c34e7218e9e36c0f8eac3bbb4cc0938cd9dd48614a1189`.
No downstream execution result is inferred from those parser outcomes.

Dhall remains optional external compilation against Sail's expected type,
followed by ordinary strict and semantic admission. Primary documentation
supports the stated export, import, integrity-hash and resource-limit
considerations. The Rust implementation's maintenance limitation is attributed
to that implementation, not to every Dhall tool. CUE and strict YAML/JSON plus
a generated schema are reasonable alternatives with their different costs
stated. JSON Schema defaults are correctly described as annotations. No
frontend is claimed to prove replay availability, ownership enforcement or
complete semantic correctness.

The wider design consistently limits deterministic change-capture output to
valid, completely ordered replacement events. Native or derived event identity
is allowed under an explicit uniqueness contract. Pinned-state validation
must inspect original versions before reduction, and its snapshot is bound
to publication. The default does not promise exhaustive or schedule-independent
detection of invalid superseded history. Stronger fingerprint retention remains
an explicit, budgeted option.

Atomic row/version-state publication and managed-target fencing are proposed
capabilities requiring adapter evidence. Ordinary catalog serialization and
Sail-only table properties are not presented as universal fences. The sidecar
alternative retains partial-effect recovery and disclaims cross-table atomic
visibility. A table-to-view change remains an explicit public-contract choice.

Historical prototype counts remain reported results. New marker reproductions
are identified as unchanged-module component tests; the semantic model remains
an algebra model. Source-path races, distributed behavior, target takeover and
resource envelopes are not relabelled as executed failures or proven fixes.
The older documents' notices preserve their observations while clearly
superseding incompatible design requirements.

## Limits

This review does not establish a working strict loader, schema generator,
Dhall/CUE integration, replacement planner, deterministic streaming reducer,
atomic state adapter or distributed fence. Live external documentation URLs
are research references as inspected; implementation must pin its actual
compiler, schema and dependency versions. No compiler performance or diagnostic
quality was measured. No new Spark, Sail, broker, storage or distributed runtime
execution occurred in this final review. The candidate states those material
limits and asks for evidence at the actual execution and commit boundaries.
