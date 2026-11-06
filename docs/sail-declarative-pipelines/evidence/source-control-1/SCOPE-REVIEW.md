# Scope review: live source control

## Before-code verdict

No scope blocker was found in the proposed increment. Read the complete saved
request, governance and the self-contained SOURCE-CONTROL plan, SHA-256
`259cfc01698316c1b0332eb2e755c2af258a6ab10d60a3905de6d7565bc9b2f5`. Baseline source inspection began at
`b6d73d6a644dc04b1e6749e171100808c874d788` in detached worktree
`/Users/alexy/src/sail/tmp/source-control-20261106-b6d73d6a`; tracked source was clean.
This is a design/baseline review, not an implementation or gate verdict.

## Coherent delivery boundary

The shared control contract, explicit controlled JobRunner entry point, physical
source binding/codec and actual native rate polling path form one usable local
capability. The result is more than a static source descriptor or an unexercised
registry: a caller obtains the execution owner's controller and observes an ordered
marker through the running reader. Each component is necessary to establish that
end-to-end boundary. A new durable store, checkpoint service, scheduler or parallel
source graph is not justified or proposed.

The plan fits the inspected existing seams. StreamSource constructs a physical
scan; RateSourceExec creates its live generator during execute. LocalJobRunner
executes directly through a TaskContext, while ClusterJobRunner delegates to its
driver. A fresh scoped TaskContext extension therefore belongs to execution rather
than a planning descriptor or session-global map. Its construction must preserve
all existing registries, configuration and runtime state, as the plan requires.

A named refusal at the new controlled-cluster entry point is an acceptable delivery
stage because ordinary cluster execution and codec reconstruction remain supported.
Distributed task/attempt routing remains required on the same contract. Local
qualification must not become the final end state or authorize a second controller
architecture when distributed routing is added.

## Correctness promises within this scope

An expected participant manifest and explicit NotReady status prevent an empty
registry from being treated as checkpoint success. In particular a source beneath
LIMIT0 remains a planned, nonexecuted participant. Distinct physical binding,
runtime-scope and registration identities address different ownership lifetimes;
none is presented as a durable source incarnation or replay position.

The one-pending-operation/latest-result contract bounds endpoint state and separates
retry from a new request. Unsupported, NotReady, Busy, Stale and Closed remain
observable outcomes. Timeout or dropped waiting does not rename or cancel an
operation. Marker encoding and handoff must precede acknowledgement, with no claim
that downstream alignment, table acceptance or durable completion has occurred.
The receipt wording should retain that exact boundary in code and results.

Zero-rate wakeup and backpressure tests must exercise actual polling rather than
mocking success. Registration lifetime, revocation, stale cleanup and replacement
must be tested through output/error/drop paths. A ready data deadline must retain
progress under requests. Existing ordinary queries and payload/type fidelity remain
controls. These are required guarantees of the chosen local scope, not capabilities
that can be waived by calling the implementation incremental.

Extracting a reusable encoder from the existing event code is appropriately narrow
if its data/marker schema and Arrow behavior remain unchanged. Native socket and
bounded adapters cannot acquire fabricated recoverable capabilities. Rate's live
emitted-row ordinal is explicitly nonreplayable, which preserves the distinction
between an ordered live cut and recovery.

## Full goal and compliance

The plan preserves the full SDP, both native Extension routes, mandatory target
fencing and typed YAML/JSON/API plus optional Dhall objective. Replay, distributed
routing/alignment, prepared effects and durable completion remain required subsequent
work. None is claimed from this live-control increment. The document explains
alternatives and dependencies from the technical problem without agent history.

Read AGENTS, LAKESAIL, SHEHAB, CLARITY, WRITING-RULES and source project/development/
Rust-review instructions. Only this report was written. No source edits, builds,
tests, measurements, cleanup, remote actions or maintainer messages were performed.
Final cumulative source review and immutable qualification remain required.
