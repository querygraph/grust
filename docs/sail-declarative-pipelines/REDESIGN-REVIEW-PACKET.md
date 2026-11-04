# Review packet for 2026-11-05

Reading order, with what each document is for and what the reviewer decides.

| Order | Document | What it is | Decide |
| --- | --- | --- | --- |
| 1 | REDESIGN-PLAN.md | The approach: decision notes and prototypes posted early, two independent tracks, schedule | Venue; which prototypes start first; whether to post the proposals as they are |
| 2 | STREAMING-ON-STREAMSOURCE.md | The streaming-tables proposal for the maintainers, under 2,000 words | Ready to post, or one more pass |
| 2a | CHANGE-CAPTURE-ON-STREAMSOURCE.md | The change-capture proposal, companion to 2, under 2,000 words | Ready to post, or one more pass; whether it goes as a second post in the same thread |
| 3 | DECISION-NOTES-STREAMING.md | S1 to S10, one post each | Order and wording of the first four posts |
| 4 | STREAMING-ARCHITECTURE.md | Components, data flow, recovery, failure cases, what is reused from the current code | Internal; whether the reuse table is right |
| 5 | EXTENSIONS-ON-ARROW-C-ABI.md | The extensions proposal: Arrow-only C boundaries, decoupled from streaming | Ready to post, or one more pass |
| 6 | DECISION-NOTES-EXTENSIONS.md | E1 to E5 | Whether E1 (adopt Comet's boundary unchanged) is the opening post |
| 7 | PROTOTYPE-SPECS.md | P1 to P6 with interfaces and the one test each | Which two to start on day 2 (plan says P1 and P5) |
| 7a | PROTOTYPE-RESULTS-STREAMING.md | What P1 to P4 showed, by the second session (snapshot of their branch at 32f858e8) | Whether the four establish enough to post the proposals |
| 7b | PROTOTYPE-RESULTS-EXTENSIONS.md | What P5 showed, in the results format | Whether to run Comet's and Sedona's libraries through it yourself |
| 7c | STREAMING-REVIEW-AGAINST-RUNTIME.md | The second session's review of the streaming documents against the current change-capture runtime (snapshot at 10385dde); already folded in | Read for the reasoning behind the change-capture proposal |
| 7d | STREAMING-MODEL-FACTS.md | The second session's fact base on what carries over from the current streaming layer and what is replaced (snapshot at 9ecdcff9); note it predates the end-of-data finding | Background only |
| 8 | WRITING-RULES.md | The standard every outward document meets | Adopt |
| 9 | SHEHAB.md | The maintainers' own agent rules, verbatim | Read once |

Facts verified today, against sources, that the documents rely on:

- Spark 4.2.1 pipelines run every streaming flow with the available-now
  trigger and have no continuous mode (graph executor source; pipeline
  command protocol; installed client).
- Sail's `main` defines four markers, including end of data with "sink waits
  for the next checkpoint, then the job finishes"; no source emits checkpoint
  or watermark markers; the rewriter refuses windows, aggregates, joins and
  repartitions.
- Comet's scalar UDF boundary is Sedona's v1 kernel with a discovery symbol
  and a version probe; Sedona's header also defines table providers,
  execution plans and streams over Arrow only; Sedona's extension crate has
  no DataFusion FFI dependency.

Still open, by owner:

- The maintainers: nothing posted since the feedback; the draft reply on
  the scalar ABI (DISCUSSION-2001-REPLY-2.md) waits for the go.
- The second implementation session: a review of the streaming documents
  against the current change-capture runtime, requested; its findings go
  into the documents before posting.
- The ORC optional-crate unit landed (branch root `99dc47788`), not
  proposed upstream; the frozen harness now builds with the branch's
  optional features.
- Prototypes built so far, all local and unpushed: P1 (checkpoints end to
  end) and P2 (append sink with tagged commits, file table and Delta) by the
  second session, with two findings already folded into S1 and S6. P2's
  Delta half implements Delta's idempotent writes (`txnAppId`, `txnVersion`),
  declared upstream but unsupported until now, verified on both engines; it
  stands alone and is a candidate for a small general-track PR at your call;
  P4 (windowed aggregate with state, the state store, and the interval
  reduce for change capture) is built too, four tests over a recorded input
  including a restart from a checkpoint, all on upstream main plus P1 and
  P2, and the merge now combines watermarks as S7 states; P3 (Iggy as a
  stream source with checkpoint positions, on the integration branch) with
  three broker tests including a retention gap and a recreated partition;
  P5 (the Arrow-only scalar kernel loader with a Sail-owned fixture,
  three tests) by this session.
