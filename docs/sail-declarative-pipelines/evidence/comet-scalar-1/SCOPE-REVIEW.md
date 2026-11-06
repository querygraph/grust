# Scope review: human review compendium

## Verdict

No scope blocker was found in the reviewed `HUMAN-REVIEW.md` draft. The document
contains 1722 words and has SHA-256
`eed251526e19a5380b73d1d704430f28a61447ed935170cb6551d7d41719e3fe`.

The opening retains the complete requested end state: Sail Declarative Pipelines,
ordered change capture and recovery, the existing native Extensions, Comet’s
additional Arrow-only C scalar interface, and measured performance advances.
It does not redefine success around the standalone scalar increment. Excluding
joins, arbitrary stateful operators and independent multi-pipeline transactions
is explicitly a first-delivery scope statement, rather than a claim that the
entire objective has already been completed.

## Fit with the requested compendium

The document supplies the technical context in place. Readers can understand the
stable-input/effect requirement from its crash example, why writer fencing is
required, how flow events and live task ownership fit Sail, and which extension
capabilities exist on the older integration branch. Links add detail rather than
carrying essential reasoning.

It identifies Sail’s existing resolver, codec, actors, catalog commits, memory
pools and extension loader as implementation seams. The coding guidance favors
focused operators, explicit ownership, feature-scoped optional dependencies and
narrowly attributed dependency ownership. These are maintainability constraints
that explain how the redesign should fit Sail rather than create a competing
framework.

The performance section retains correctness, ordering and fencing as constraints.
It treats old optimization branches as hypotheses requiring fresh validation and
keeps mixed-marker overhead visible. The current-state table distinguishes
implemented foundation repairs from unbuilt integrated recovery, enforced targets,
configuration and extension work.

The plans-before-code section explicitly requires self-contained problem,
guarantees, alternatives, recommendation, costs and discriminating verification.
Its dependency paragraph explains what earlier decisions constrain and permits
independent work. It reinforces small patches that a human can explain line by
line, immutable cumulative qualification and independent specialty review.

## Optional clarity finding

Define ABI as the binary calling contract at its first use in the Comet section.
This is an editorial improvement under `CLARITY.md`, not a scope or architectural
blocker. Sent to the integration owner; no reader-facing edits were made here.

## Evidence and compliance

Read the full new steering saved in `evidence/comet-scalar-1/REQUEST.txt` and reread
`AGENTS.md`, `LAKESAIL.md`, `SHEHAB.md`, `CLARITY.md` and `WRITING-RULES.md`.
Read the entire compendium as a standalone recipient. This verdict concerns
scope and review usability; it does not independently establish the source or
runtime claims summarized there. No source edits, builds, tests, performance
runs, cleanup or remote actions were performed. Only this report was written.

## Standalone scalar source review

Reviewed the 12-file source increment in
`/Users/alexy/src/sail/tmp/comet-scalar-20261105-2c9fa8499` against foundation commit
`2c9fa84994d317aade0d1c69faa9a378c780127d`. The staged snapshot was tree
`d8e9633355f2bac78ab9470e49aceda1992d2388`, increment SHA-256
`0561254aaed99782dd50a4901f4c28162f799748cfcdac7dd6f5f6ea08676d64`.
Also inspected the subsequent metadata-test strengthening, which requires the
named planned-return-field mismatch rather than accepting any error. The complete
working increment at that inspection had SHA-256
`39b1778d2aa2d9b6722391f8406f4d5a093c248b89bdc32ab736e5a284fb98e9`.

No source scope blocker was found. The increment adds `sail-c-udf`, a dedicated
fixture crate, and their workspace lock entries. The lock changes add only those
workspace package records; they do not advance existing dependency versions.
The implementation retains a narrow scalar boundary, loader and DataFusion scalar
adapter. It does not alter the session manager, package discovery, worker registry,
relation dispatch, StreamSource protocol, table commit path or pipeline planner.

The unsafe loader states the trusted-producer obligations explicitly. It refuses
non-immutable declarations before opening a library and retains admitted library
code for the process lifetime. Its retention registry does not store session
state or kernel instances. Bounded admissions and content identity remain explicit
package-integration obligations rather than silently invented loader policy.
The adapter passes actual argument fields through initialization and checks the
execution return field against planning. The tests cover retained result ownership,
metadata-sensitive behavior and named refusals as appropriate for this independent
component increment.

This fits the committed E1/E3/E4 and standalone adapter plan. Adding the C scalar
route does not remove the existing DataFusion-FFI route or substitute scalar-only
support for the full Extensions end state. Package admission, worker reconstruction,
cleanup, replay identity and relation integration remain required subsequent work.
The current HUMAN-REVIEW compendium retains those requirements and clearly marks
component evidence separately from integrated recovery and package readiness.

The lead reports 13 focused tests, strict affected-crate Clippy and two independent
SDK producer probes passed. This reviewer did not execute them. Final gates and
a final immutable source commit remain pending; this source-inspection verdict
must not be described as a completed gate. Refreshed the saved request and current
HUMAN-REVIEW/standalone plan; the previously read governing requirements remain
applicable. No source changes or builds were performed by this reviewer.

## Final frozen candidate confirmation

Inspected `candidate-snapshot-final.json` and independently verified every listed
file hash, the complete staged increment, the cumulative patch against upstream
`b52144955b629314a000b1fe49eeea97fa3d0c5c`, and working-tree/index equality.
The frozen candidate is tree `455101575ecbfbec6f843464ce178e0d09046f51`:

- Increment SHA-256:
  `7477e67e9b6262e5aec067714c586ef7ac49790e8e6ac7d14116829213bdf325`.
- Cumulative SHA-256:
  `743a1346feb7ae62a4cded0224b007312b471b09d80d149b2b0bdf5c25c25b30`.

No scope blocker was found in this final 15-file increment. It still touches
only the standalone scalar adapter, its dedicated fixture/tests and workspace
lock records. The added pinned Comet records and aliases preserve the intended
binary boundary rather than introduce another extension framework. The controlled
missing-probe library removes a test dependency on an unrelated system library.
Admitting nullary signatures lets each kernel determine actual arity, consistent
with the existing scalar contract.

Read the complete first-principles `COMET-SCALAR-NULLABILITY.md` decision note and
inspected `nulls.rs` and its call site. Enforcing a nonnullable scalar result is
part of the planned field contract, not an unrelated expansion into Arrow
validation. The predicate remains crate-private and is invoked only for planned
nonnullable outputs after the row-count check. It follows selected dictionary
keys, actual union IDs/offsets and physical run ranges without allocating a
logical-row bitmap. Ordinary nested child nulls are not confused with parent
nullability. This preserves applicable Arrow encodings instead of refusing them
or making an unsafe nonnull declaration. Correctness and performance qualification
of those mechanics belongs to the respective specialist reviews and final gate.

The standalone scope continues to preserve the full end state described in
HUMAN-REVIEW: existing native Extensions, the additional Comet route, StreamSource
pipelines, performance work and durable recovery. Neither the new predicate nor
the scalar adapter claims package integration, worker reconstruction, C relation
support or recovery readiness.

The lead reports 17 focused tests, affected strict Clippy, two independent SDK
probes and Rustdoc passed. Those are attributed reports, not executions by this
reviewer. Final broad qualification remains pending. This confirmation performed
read-only source/Git inspection and appended only this report; no builds or source
edits were performed. The saved continuation request, human-review compendium and
standalone plan were refreshed, and the previously read governance remains
applicable.
