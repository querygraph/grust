# Streaming redesign discussion packet

Internal packet for owner review after ASTRA-REDESIGN-1. The immediate
question is whether the exact discussion text below gives maintainers enough
context to choose the initial recovery scope. This is a documentation
candidate, not approval of the prototype code or its replacement runtime.

## Read first and decide

| Order | Document | Purpose | Owner decision |
| --- | --- | --- | --- |
| 1 | [Redesign plan](REDESIGN-PLAN.md) | Current status, decision register and dependency order | Is the proposed venue and decision sequence suitable? |
| 2 | [Streaming proposal](STREAMING-ON-STREAMSOURCE.md) | Exact opening discussion text | Is the scope question clear enough to post? |
| 3 | [Change-capture proposal](CHANGE-CAPTURE-ON-STREAMSOURCE.md) | Exact companion reply explaining the two table effects | Include it in the initial discussion? |
| 4 | [Streaming decision notes](DECISION-NOTES-STREAMING.md) | Exact individual replies, S6 first, identifiers S1 to S13 retained | Approve S6 as the opening decision; keep remaining notes available as needed |
| 5 | [Architecture](STREAMING-ARCHITECTURE.md) | Internal explanation of alternatives, recovery obligations and reuse | Does the reference material preserve the required behavior without deciding for maintainers? |

Proposed initial outbound package: the two proposals and S6. Each proposal is
below 2,000 words and each decision note below 300. The later notes should
follow the maintainers' questions and chosen scope, not arrive as thirteen
simultaneous requests. No private evidence paths or coordination identifiers
are needed to read the outward text. Nothing is posted by preparing this
packet.

## The opening decision

Should the first version support only one append transaction, one flow
including change capture's two effects, or several independent sinks?

The counterexample is small: if one sink commits a checkpoint and another
does not, assigning different rows to the same identifier on restart can lose
rows. Allocating a fresh identifier for the replayed prefix can duplicate
rows. This motivates preserving prepared boundaries whenever effects depend
on them; it does not select an implementation or require a general multi-sink
coordinator before the maintainers choose the scope.

The proposed starting point is one flow, with change capture included only
if its two-effect recovery protocol is accepted. A narrower append-only first
step remains an explicit alternative. State retention, source participation,
completion and refresh identity follow from that decision.

## Evidence and its limits

| Record | What was checked | What it does not establish |
| --- | --- | --- |
| [Spark semantics](evidence/redesign-discussion-1/SPARK-SEMANTICS.md) | Direct inspection of Spark 4.2.1 at `617618396087429b5627a86ce933bb0f5d6645cb`, with file hashes | No new Spark execution or complete compatibility verdict |
| [Boundary model](evidence/redesign-discussion-1/checkpoint_boundary_model.py) and [result](evidence/redesign-discussion-1/checkpoint-boundary-model.json) | Two incorrect retry policies fail; fixed-boundary replay preserves both modeled append sinks | No execution of Sail, storage, stateful transforms or concurrent recovery |
| [Prototype results](PROTOTYPE-RESULTS-STREAMING.md) | Historical P1 to P4 runs and current source-review limits | No complete exactly-once protocol or performance envelope |
| [Prototype specifications](PROTOTYPE-SPECS.md) | Intended experiments, actual coverage and focused gaps | No authorization to implement all proposed components |
| [Corrected review](ASTRA-REDESIGN-1.md) | Technical findings and the required human decision process | No retrospective completion of the original review requirements |
| [Document checks](evidence/redesign-discussion-1/DOCUMENT-CHECKS.md) | Current specialist findings, resolutions and text checks | No production integration gate |

The code references remain P4 `4fad33ca5` over `62251e0a2`, P3 `ef5f848a7`
on integration ancestry, and the current runtime `99dc47788`. P4 includes
P1 and P2; P3 must not be represented as a clean upstream-only patch.

Fresh source verification changes several claims: available-now can use
multiple batches; raw-row validation precedes reduction; equal-sequence
winners are undefined; full refresh does not establish a connector-independent
absolute-origin rule. Archives, fencing and checkpoint transaction tags are
Sail mechanisms requiring their own evidence. Historical test counts have
not been promoted into fresh execution results.

## Human review and subsequent work

The governing instructions are [LAKESAIL.md](LAKESAIL.md),
[SHEHAB.md](SHEHAB.md) and [WRITING-RULES.md](WRITING-RULES.md).
The author must understand proposed code, and the owner approves the exact
outward text. Maintainers choose architecture while alternatives remain
open. Agent reviews support those decisions; they do not replace them.

After an answer, record its public reference and the implementation scope it
permits in the plan. Use a small local experiment only to distinguish an open
choice. Any selected implementation receives the seven specialist reviews
and the full immutable-commit integration gate. Several reference artifacts
may expose existing work; only selected, agreed pieces become small upstream
implementation PRs.

## Separate extensions and historical background

The extension track remains independent and is not approved by this streaming
revision. Its material remains [the proposal](EXTENSIONS-ON-ARROW-C-ABI.md),
[decision notes](DECISION-NOTES-EXTENSIONS.md) and
[historical results](PROTOTYPE-RESULTS-EXTENSIONS.md). The scalar fixture does
not establish that external Comet and Sedona binaries load unchanged.

[The original review](ASTRA-REDESIGN-0.md),
[the earlier runtime review](STREAMING-REVIEW-AGAINST-RUNTIME.md),
[model facts](STREAMING-MODEL-FACTS.md) and
[the bounded control-store brief](CONTROL-STORE-ASTRA-BRIEF.md) remain
historical background. Their older claims must be read with the corrected
proposals and evidence above.
