# Final cumulative scope and clarity review

## Candidate and verdict

**No scope or clarity blockers found in the reviewed documentation candidate.**
This is a documentation review, not implementation approval or evidence that the
proposed recovery and fencing mechanisms work.

- Repository: `/Users/alexy/src/grust-sdp`.
- Baseline: `f23da50ccdf4ac1258fa1c6803aeb54df042a03e`.
- Cumulative patch: `cumulative-documents.patch` in this evidence directory.
- Patch SHA-256: `8dd7bac1e54a6b463f74f91c37b9cb604e15872b4c30772b5fba6089ee7e57b9`.
- Manifest: `candidate-files.json`, covering 22 documents.

Read the complete cumulative patch within the Scope Control remit. Independently
recomputed its hash and all 22 current-file hashes; all match the manifest.
The verdict applies to those exact contents. Raw evidence and coordination
records are outside the patch's stated scope.

## Earlier findings resolved

**SC1: competing historical requirements.** All eight identified reference files
now begin with specific scope notices. They identify the superseded requirements
rather than requiring readers to infer that every old statement is obsolete:

- `DESIGN.md`: unfenced durable operation and blanket Spark parity.
- `SAIL-SDP-DESIGN-DECISIONS.md`: compatibility-driven ordering, configuration
  and watermark rules.
- `FLOW-CONFIGURATION-DESIGN.md`: traversal-dependent setting replacement and
  repeated definition evaluation.
- `STREAMING-MODEL-FACTS.md`: incomplete marker inventory and claims that old
  rules can transfer unchanged.
- `STREAMING-REUSE.md`: prescribed subsystem extraction and implementation order.
- `CDC-CONTROL-STORE-DESIGN.md`: bounded-only architecture, prescribed authority
  and storage layout, and unfenced operation.
- `CDC-UNITS.md`: the prior implementation sequence and recovery representation.
- `SDP-FABLE-DESIGN-REVIEW.md`: parity as the objective and inherited batch rules.

Independently compared each file with the baseline: its pre-existing body remains
unchanged below the notice. The notices preserve implementation history without
leaving those requirements as competing instructions for the active design.

**SC2: unnecessary native event identity.** The active semantics accept either a
native event identity or one derived from source incarnation, canonical key and
complete per-key order for replacement events. A separate native identity is
required only by guarantees that actually consume it, such as transport duplicate
detection or provenance. The proposal, architecture, decision notes and engineering
review are consistent with that boundary.

## Scope and engineering checks

The active documents consistently put reliable execution ahead of Spark
conformance. They explain intentional differences instead of equating any
departure with a regression. Existing Sail components, inspected defects,
proposed corrections and unbuilt integration remain distinguishable.

The amended validation example is sound within the specified scope. Incoming
version `8:B` must be compared with durable `8:A` before a later `9:C` hides it.
The durable state read for that validation is bound to the commit precondition;
a changed read state requires revalidation of the same immutable normalized
input. This closes a correctness gap without silently requiring an unbounded
historical conflict index. Exhaustive older-history checking remains an explicit
additional contract with retention and resource costs.

Fencing is required work for every admitted durable publication path, including
creation and other permitted writers. A lease, table-version retry or external
single-writer convention cannot substitute for it. Finishing exact effects
accepted before takeover remains distinct from authorizing new effects afterward.
The documents do not claim that current managed Delta or Iceberg already supply
the proposed enforcement.

The design reuses source traits, flow events, job execution, task control,
catalog seams, memory facilities and commit operators. It does not mandate a
universal coordinator, a new control service or a physical-table-to-view
substitution. A commit service remains conditional on the backend's actual
capabilities and its ability to control publication. Storage representation is
an explicit interoperability decision.

Strict configuration is one versioned contract shared by file and API inputs.
Dhall remains an optional authoring frontend outside the runtime. Application
configuration is not replaced, and CUE is an alternative rather than an additional
required subsystem. Connector validation is tied to admitted capabilities.

The initial append and change-capture scope does not pull windows, joins or
independent multi-flow execution into its prerequisites. Resource and completion
requirements protect the guarantees within the admitted scope. The technical
brief and proposals supply the user problem, Sail fit, alternatives and remaining
choices inline; their argument does not depend on review history or an external
reading itinerary. No new approval ceremony or implication of maintainer agreement
was introduced.

## Evidence and limits

The documents keep reported prototype results, inspected source paths, executed
component probes and unbuilt integration separate. Failures remain failures;
component reproductions do not become source-to-table recovery, compatibility or
performance claims.

This reviewer did not independently rebuild Sail, run Spark or broker suites,
qualify a storage backend, or repeat the source audits. The source and experiment
reports were assessed for their stated scope and for consistency with the design
claims. The review does not certify any production implementation, and it does
not extend to unrelated repository work or extension prototypes.

Confirmed compliance with the prompt and instruction-reading requirements:
reread the full saved request, referenced earlier prompts, root `AGENTS.md`,
`LAKESAIL.md`, `SHEHAB.md`, `WRITING-RULES.md`, `CLARITY.md` and the referenced
`ASTRA-REDESIGN-1.md`, including after compaction. Only this assigned final review
artifact was written during the final review; no main document, source file,
index or remote state was changed.
