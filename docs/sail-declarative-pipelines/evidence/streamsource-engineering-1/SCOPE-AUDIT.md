# Scope and clarity audit

## Review boundary

This review applies the saved request in `REQUEST.txt`: engineering quality
takes precedence over Spark SDP conformance, admitted durable writers require
fencing, and typed configuration should include an optional authoring path.
AGENTS.md, LAKESAIL.md, SHEHAB.md, WRITING-RULES.md and CLARITY.md were read.
The latest user directive controls over earlier compatibility defaults.

The documentation baseline is
`f23da50ccdf4ac1258fa1c6803aeb54df042a03e`. The four new technical documents
were read end to end: STREAMSOURCE-ENGINEERING-REVIEW.md,
CHANGE-CAPTURE-SEMANTICS.md, FENCED-TABLE-COMMITS.md and
TYPED-PIPELINE-CONFIG.md. The foundation, semantics, fencing, performance,
typed-configuration and executed-probe evidence reports were also read.

This is an independent document scope and reasoning review. It did not repeat
the source inspections, compile code, execute the marker probes, run Spark or
qualify a storage backend. References to those results retain their recorded
evidence boundaries. The existing main documents are being revised; their
unrevised baseline paragraphs are not counted as overlooked findings here.
Final cumulative review remains pending.

## Findings requiring resolution

### SC1. Legacy files still present superseded requirements as current

Several discoverable design files conflict with the new engineering direction.
A date or source pin alone does not limit a heading such as “Required behavior”
or “selected architecture for implementation.” A future implementation could
follow these directions while believing it complies with the current design.

| File and baseline location | Competing requirement | Minimum correction |
| --- | --- | --- |
| `DESIGN.md:8,108–143,224,264` | Spark behavior is the compatibility target; the proposed `CommitMode::{Fenced, Observed}` admits managed-target writes without enforced ownership | Mark streaming, change-capture and configuration portions as bounded-implementation references. Explicitly supersede observed-only durable admission and compatibility as a correctness gate. Preserve source observations and unrelated integration guidance. |
| `SAIL-SDP-DESIGN-DECISIONS.md:24,56,252,304,433,452,464` | “Current” design record requires traversal-driven configuration, Spark error-row selection, arrival-order ties, millisecond/batch watermark rules and only combined watermark persistence | Identify the record as the pinned implementation's decisions, not the StreamSource requirements. Name the replacements: deterministic effective configuration, complete event ordering, coherent event-time progress and retained per-input recovery state. |
| `FLOW-CONFIGURATION-DESIGN.md:37–67,116–135` | “Required behavior” makes configuration depend on graph traversal and invokes a flow function again after successful first analysis | Preserve the measured compatibility trace as evidence, but state that the new pipeline contract resolves effective settings before dependent planning and does not require repeated evaluation of effectful definitions. |
| `STREAMING-MODEL-FACTS.md:12–22,48–61,65–76` | Says there are three markers and no bounded completion; says old watermark/late-row rules and control sequencing carry over unchanged | Scope the file to its old source comparison. State the current foundation has an end-of-data marker and that checkpoint identity does not prove semantic or state-recovery equivalence. |
| `STREAMING-REUSE.md:78–101` | Prescribes extraction of a separate control model/kernel and implementing Spark CDC only after a fixed streaming sequence | Retain the connector findings as source evidence. Treat extraction, sequencing and Spark-shaped CDC as historical recommendations; existing Sail execution and catalog seams are evaluated first. |
| `CDC-CONTROL-STORE-DESIGN.md:3–13,127–143,169–198` | Selects a new authority/service, bounded-only admission, Spark checkpoint layout, a fixed two-table layout and local unfenced compatibility mode | Scope these as the bounded reference design. Keep its exact-byte acceptance and recovery reasoning, but do not mandate its service, storage layout or unfenced mode for new durable writes. Current fencing and storage capability requirements govern replacement. |
| `CDC-UNITS.md:1–9,731` | “Current base” unit plan inherits the old design constraints and resets individual watermark progress to reproduce Spark | Label as an implementation/evidence ledger at the recorded revisions. Do not rewrite observed results or treat those outcomes as new correctness requirements. |
| `SDP-FABLE-DESIGN-REVIEW.md:9–13,807–815` | Objective requires all applicable Spark behavior passing and retains batch-dependent equality/tie behavior | Label as the earlier pinned review brief. Its compatibility objective and semantic recommendations are superseded for the replacement; its source observations and failures remain evidence. |

Use short, specific status text with optional pointers to the current technical
documents. Merely adding a generic “see newer design” link leaves the conflict
implicit. Do not delete historical results, rewrite old execution receipts or
mark unrelated SQL semantics defective solely because they agree with Spark.
The lead has accepted this correction; edited-file verification is pending.

### SC2. Independent native event identity is an unnecessary admission constraint

CHANGE-CAPTURE-SEMANTICS.md initially requires an immutable native event
identifier in addition to a complete per-key order. A source may provide a
reliable entity key and version without another native identifier. For the
declared full-row replacement semantics, source incarnation, canonical key and
complete per-key order can already derive a stable identity for the normalized
event. Equal-version action/payload checks retain the duplicate/conflict rule.

Require a separate native event identifier only for a guarantee that consumes
it, such as transport-level duplicate detection or provenance across a
transformation. Otherwise this extra requirement rejects useful sources without
strengthening the stated maximum-version or prepared-retry guarantee.

The lead accepted derived identity as sufficient and owns the document change.
The semantics reviewer was notified. Verify that the event table and admission
paragraph agree, and that the other summaries do not reintroduce a mandatory
independent identifier. This finding does not relax source incarnation,
canonical comparison, stable transformation identity or conflict checks.

## Scope and complexity checks that passed

- Fencing is required implementation work for filesystem Delta, managed Delta
  and Iceberg. The document covers creation, metadata mutation, refresh,
  worker authority transport, uncertain outcomes and external-writer bypass.
  Temporary refusal is an implementation dependency, not a permanent
  single-writer exception. Exact accepted bytes may finish after takeover;
  this is clearly separated from authorizing a new stale-owner effect.
- A separate commit service is conditional on backend inability to enforce
  ownership and on exclusive publication access. The default is reuse of
  existing catalog/commit seams. No second general streaming coordinator is
  asserted necessary by the counterexamples.
- Full-row replacement is an explicit limit of the maximum-version law.
  Patch updates, historical versions and arbitrary stateful transformations
  are not silently admitted. Canonical comparison and target type support
  remain capability requirements rather than copied Spark type restrictions.
- The default does not require an unbounded history-conflict database.
  Exhaustive conflict detection has a separate retained horizon and budget.
  The finite latest-state default's inability to detect every superseded
  invalid event is stated with a concrete example.
- Atomic key-state publication is a proposed target capability, not an
  established Delta or Iceberg feature. The fenced sidecar alternative remains
  available. A physical state table plus view is an explicit product migration,
  not a transparent substitute for an ordinary user table.
- Typed configuration distinguishes the client project file, application
  configuration and build-time connector metadata. It does not replace all
  application configuration. Dhall remains optional, compiled outside the
  server into the same admitted model; CUE is an alternative, not another
  simultaneously required frontend.
- Configuration checks cover Python/SQL entry points and connector options.
  The document does not claim that type checking proves replay availability
  or storage fencing, and it does not claim an executed Dhall integration.

## Founder readability and evidence limits

Each new document explains its problem, existing Sail foundation, proposed
mechanisms and unresolved choices without requiring the reader to open an
audit or companion document. The four drafts contain 1,764, 1,650, 1,407 and
1,491 words respectively at this review. Optional source links substantiate
the argument rather than supply missing reasoning.

The engineering summary correctly distinguishes marker component
reproductions from SQL/distributed workloads. The semantic model is not
presented as proof of a finite conflict index or a durable storage protocol.
Fencing source tests are not promoted into managed-catalog, Iceberg, external
writer or distributed execution coverage. No runtime or throughput claim is
introduced by this document review.

The current review therefore supports the four-document direction subject to
SC1 and SC2 and the final cumulative check. It does not approve implementation,
claim completed fencing, or replace the required backend and recovery evidence.
