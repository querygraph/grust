# Review packet for 2026-11-05

Reading order, with what each document is for and what the reviewer decides.

| Order | Document | What it is | Decide |
| --- | --- | --- | --- |
| 1 | REDESIGN-PLAN.md | The approach: decision notes and prototypes posted early, two independent tracks, schedule | Venue; which prototypes start first; whether to post the proposals as they are |
| 2 | STREAMING-ON-STREAMSOURCE.md | The streaming proposal for the maintainers, under 2,000 words | Ready to post, or one more pass |
| 3 | DECISION-NOTES-STREAMING.md | S1 to S10, one post each | Order and wording of the first four posts |
| 4 | STREAMING-ARCHITECTURE.md | Components, data flow, recovery, failure cases, what is reused from the current code | Internal; whether the reuse table is right |
| 5 | EXTENSIONS-ON-ARROW-C-ABI.md | The extensions proposal: Arrow-only C boundaries, decoupled from streaming | Ready to post, or one more pass |
| 6 | DECISION-NOTES-EXTENSIONS.md | E1 to E5 | Whether E1 (adopt Comet's boundary unchanged) is the opening post |
| 7 | PROTOTYPE-SPECS.md | P1 to P6 with interfaces and the one test each | Which two to start on day 2 (plan says P1 and P5) |
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
- The ORC optional-crate unit: in the branch gate; lands on pass, not
  proposed upstream.
