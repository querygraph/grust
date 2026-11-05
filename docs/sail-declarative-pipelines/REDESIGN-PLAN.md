# Redesign plan for streaming and extensions

Internal plan for owner review. Streaming proposals are revised after
[ASTRA-REDESIGN-1](ASTRA-REDESIGN-1.md). Local prototypes exist; no maintainer
answer is recorded here. A recommendation or passing prototype does not
permit production implementation of an unanswered design choice.

## What is ready to discuss

Streaming builds on Sail's existing flow events, stream sources and markers.
The immediate deliverable is the exact text in the streaming and
change-capture proposals, followed by short decision notes. The opening
question is the recovery scope in S6: which effects belong to a checkpoint,
and what must survive a crash between those effects?

The owner reviews the complete text before any external post. Maintainers
then choose architecture and upstream scope. Local experiments may resolve
one stated question; they do not silently become a production subsystem.
The author must understand and explain every proposed code change.

## Venue and reading order

Propose one GitHub Discussion per track in `lakehq/sail`, opened by the
owner. For streaming, use STREAMING-ON-STREAMSOURCE.md as the opening post
and CHANGE-CAPTURE-ON-STREAMSOURCE.md as its companion reply. Start with the
first user scenario and its recovery domain in S6. Use S8 and S11 to make
operator scope and change-capture behavior concrete where needed.

Resolve ownership in S1 against that domain, then discuss source positions,
barrier alignment and completion together in S2, S4 and S9. Those contracts
explain which progress and effects must survive a crash. Scheduling and
resources in S3, state storage in S5, and watermarks in S7 follow the selected
operators, with feedback if their costs change the scope. Resolve S11 to S13
before durable change-capture implementation, including validation, refresh
identity and stale-writer protection. S10 can proceed alongside the source
contract; Iggy dependency choices need not block another accepted source.

This order exposes dependencies rather than prescribing thirteen serial
approvals. It does not require a stateless append path to wait for a window
state store. The [review packet](REDESIGN-REVIEW-PACKET.md) explains the
tradeoffs and gives a reading order from user behavior to architecture and
then this work register. Identifiers remain stable for traceability.

Each decision note is exact reply text under 300 words. It presents the
situation, options, a recommendation and what would settle the question.
No reader needs our private repository or coordination log. Publish no local
prototype link until a separately authorized public reference exists.

## Streaming decision register

All entries are proposed. The maintainer answer is **not recorded** for every
row. Evidence supports discussion only; permitted production scope remains
**none until the relevant answer is recorded**. When an answer arrives, add
its public link and the exact scope it permits to that row.

| Note | Question and options | Proposed recommendation | Evidence and limits |
| --- | --- | --- | --- |
| S6 | One append transaction, one flow with several effects, or several independent sinks per checkpoint? | Start with one flow; retain prepared boundaries and separate effect progress if change capture is included | P2 tests one file sink; partial commits remain unresolved |
| S1 | Job runner ownership or one driver in every mode? | Job runner locally and driver in cluster mode if the recovery domain fits one job | P1 is in process; local mode has no driver |
| S2 | Extend StreamSource or expose separate checkpoint capability? | Separate optional capability | Rate counter exercises protocol, not replay; P3 has real positions |
| S4 | Align barriers or capture in-flight rows? | Alignment with serialized requests | P1 covers controlled inputs, not overlapping requests |
| S9 | Finish on source end or globally completed final checkpoint? | All source ends plus completed final effects | End and close accounting has an open prototype finding |
| S3 | Final checkpoint only, or intermediate checkpoints too? | Permit intermediate checkpoints plus a mandatory final one | Final-only buffering grows with the whole backlog; no resource bound measured |
| S5 | Arrow segments and manifests or another state store? | Files initially, retaining every required recovery point | P4 covers recorded replay; GC and durable storage protocol remain open |
| S7 | How should event-time lateness fit the existing watermark contract? | Agree on the contract before adding its operator | P4 consumes recorded markers; it does not implement watermark generation |
| S8 | Append first, then windows and deduplication, or wider stateful scope? | Narrow initial operator set; defer joins | Only window and interval-reduction mechanisms prototyped |
| S10 | Optional Iggy source now or after dependency alignment? | Keep optional and defer upstream dependency expansion | P3 is on integration ancestry; bound-time incarnation race is open |
| S11 | Stable source order or archived winners for equal sequences? | Retain sealed winners without claiming cross-partition ordering | P4 resolves ties only in recorded row order |
| S12 | How should key changes and full refresh reset identity? | Explicit refresh generation and source-origin admission | Spark source and current runtime inform the choice; new reset path unbuilt |
| S13 | Which targets require stale-writer fencing? | Preserve existing fenced guarantees; decide additional target scope | Catalog commit ordering alone is not a fencing proof |

See DECISION-NOTES-STREAMING.md for the alternatives and acceptance questions,
and evidence/redesign-discussion-1/SPARK-SEMANTICS.md for source verification.

## Prototype status

| Prototype | Current state | What remains outside its evidence |
| --- | --- | --- |
| P1 | Built locally; stacked in P4 at `4fad33ca5` over `62251e0a2` | Driver placement, durable recovery, overlapping requests, staggered completion |
| P2 | Built in the same stack; file-sink restart tests and separate Delta write cases | Multiple sinks, change-capture merges, concurrent first-write inference |
| P3 | Built at `ef5f848a7` on integration ancestry | Planner registration, bound-time races, upstream dependency fit |
| P4 | Built in the P4 stack; recorded windows, snapshots and interval reduction | Live watermark replay, cleanup, cross-partition ties, integrated recovery |

The test counts in PROTOTYPE-RESULTS-STREAMING.md are historical reports,
not fresh execution. PROTOTYPE-SPECS.md distinguishes intended claims from
what those tests cover. The existing branches remain local and unpushed.

## Extensions remain a separate track

This streaming revision does not assess or approve the extensions proposals.
Keep EXTENSIONS-ON-ARROW-C-ABI.md and DECISION-NOTES-EXTENSIONS.md as their
separate discussion material, with an independent owner review.

| Note | Existing proposed direction | Evidence status |
| --- | --- | --- |
| E1 | Adopt Comet's Arrow-only scalar boundary unchanged | P5 reports a Sail-owned fixture; external Comet and Sedona libraries remain unverified |
| E2 | Sedona table-provider and execution-plan boundary | P6 remains a proposed experiment |
| E3 | Declare boundary and Sail API versions | Maintainer answer not recorded |
| E4 | Keep the memory lease and discuss a shared home later | Maintainer answer not recorded |
| E5 | Keep optimizer and catalog plugins out of initial scope | Maintainer answer not recorded |

PROTOTYPE-RESULTS-EXTENSIONS.md retains the historical P5 report. Neither the
old calendar nor the existence of P5 authorizes the next extension step.

## Work follows decisions

1. Complete the corrected packet, source checks and end-to-end reading pass.
2. The owner reviews the exact outward text and decides whether to post it.
3. Record each maintainer answer and its permitted scope. An unanswered
   dependency keeps the dependent implementation pending.
4. Use a small local test only where it distinguishes alternatives. Record
   failures and limits as well as successes in the corresponding note.
5. Prepare the selected implementation as a small, single-purpose change.
   A few larger reference PRs may expose existing work when authorized;
   maintainers select the pieces that become implementation PRs.
6. Apply seven specialist reviews to the cumulative candidate and repeat
   affected reviews after fixes. These support human judgment.
7. Gate the exact combined commit through the LAKESAIL integration procedure.
   Preserve receipts, verify the freshly built binaries and required features,
   and land only the tree and parent that passed.

For each session, preserve the prompt and governing instructions, distribute
both to reviewers, and reread after compaction. Keep one writer per file and
one integration owner. Documentation evidence is distinct from an executable
integration verdict.

## Existing runtime and replacement criteria

Keep the working bounded runtime until the selected replacement has evidence
for its declared scope. Preserve raw-row validation, sealed winners, archives,
separate effect receipts, contract identity and stale-writer fences where
already supported. Stronger prepared validation receipts remain pending
wiring; their presence as a component is not a production guarantee.

Replacement requires recovery tests, relevant Spark comparisons and explicit
acceptance of deliberate behavior differences. Passing inherited tests alone
does not prove the newly introduced checkpoint protocol. Batch pipelines,
catalogs and general engine changes remain separate work.
