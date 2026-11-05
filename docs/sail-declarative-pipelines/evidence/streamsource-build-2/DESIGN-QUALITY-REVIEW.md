# Extension and streaming integration design review

Reviewed at 2026-11-05T23:16:23.802501+00:00.
Document: `EXTENSIONS-STREAMSOURCE-INTEGRATION.md`, SHA-256 `1f6dd4133abd84e493ad99ee92f97bca2bcfd284ed9cd3a47bb0e0a2be1a6f10`.

## Architectural assessment

The proposed split fits Sail's existing extension and continuous flow-event
architecture. It preserves package discovery, exact worker identity, native-owner
retention, memory admission and bound relation dispatch while adding an independent
Arrow-only scalar adapter. It avoids treating an Arrow batch relation as a
recoverable source without a snapshot/replay contract. It keeps markers and
retractions under Sail's control and correctly ties projection/async isolation to
native function admission in those expression positions. Target fencing remains
mandatory for durable effects.

The document identifies a useful bounded increment: establish the existing host
contracts on the foundation, qualify the scalar adapter independently, then connect
package admission and distributed lookup. Arrow-only relations deserve a separate
provider contract rather than being inferred from a scalar ABI.

## Findings sent to the integration owner

1. Recommend process-retained library code for the first adapter because it matches
   the existing host's retained native scalar registry. Present ownership on every
   exported allocation as the more complex unloadable alternative. The draft lists
   both but does not recommend one, leaving the immediate implementation choice
   underspecified.
2. Clarify that porting host contracts precedes package integration, while the
   standalone scalar adapter and fixture can proceed independently. The draft's
   “First preserve” followed by “Add ... independently” can imply an unnecessary
   dependency.
3. Apply the primary-source Comet corrections being integrated by the owner:
   scalar constant arguments are reserved/null in ABI v1, immutable functions are
   required by that interface, and Arrow-only arguments do not make Comet's custom
   ABI stable across releases. Preserve field metadata and prove callback/library
   lifetime rather than treating a successful scalar result as sufficient evidence.

The first two are decision-clarity corrections rather than rejection of the
architecture. The third contains contract precision required before dependent code.
The draft should not be treated as final until those corrections are integrated.

## Inspection and limits

Inspected the existing native scalar owner/identity registry and package import
path in the integration branch, plus the C scalar prototype's ABI and evaluation
path. Confirmed the prototype reconstructs argument fields from array types at
execution and retains a library through its UDF; the returned array itself does
not visibly retain that handle. This is source inspection, not a reproduced
unload crash or native-lifetime execution test. No source files, builds, tests,
benchmarks or remote state were changed by this reviewer.

Read the saved full request and the user clarification “from Comet”, repository
`AGENTS.md`, `LAKESAIL.md`, `SHEHAB.md`, `CLARITY.md` and `WRITING-RULES.md`.
No context compaction occurred after those reads. The complete document was read
as a standalone founder-facing argument. The existing implementation-versus-new
foundation distinction and the durability limits are explicit.
