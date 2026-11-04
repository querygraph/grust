# Redesign plan: streaming on the flow-event model, extensions over Arrow-only C boundaries

For review on 2026-11-05. Status: proposal, nothing started.

## The approach

The maintainers want to shape the design before code exists, and they want to
read small things. So the redesign is run as a sequence of **decision notes**,
each one page, each presenting one question with the options, a
recommendation, and what would settle it, posted where the maintainers can
answer in a sentence. Where a decision is better shown than argued, a
**prototype** on a branch from upstream `main` accompanies the note: a few
hundred lines that make the option concrete and testable, thrown away or kept
as the maintainers say. Nothing is built for real until the notes it depends
on are answered.

Two tracks, kept independent: streaming (the proposal in
STREAMING-ON-STREAMSOURCE.md) and extensions (EXTENSIONS-ON-ARROW-C-ABI.md).
They share no decision and no prototype.

## Venue

One GitHub Discussion thread per track in `lakehq/sail`, opened by the owner
with the proposal as the first post. Each decision note is a reply in that
thread, numbered, under 300 words, with the prototype branch linked when there
is one. The maintainers answer in the thread; the answer is recorded in the
note's section of this plan. This keeps everything in their repository and
nothing in ours that they would have to open.

## Streaming decisions, in the order they unblock each other

| # | Question | Options | Recommendation | Settled by |
| --- | --- | --- | --- | --- |
| S1 | Where does the checkpoint coordinator live? | In the session beside the streaming-query manager; in the execution driver beside job state | Driver: distributed runs need the driver to own positions, and local mode runs a driver too | Their preference; prototype P1 shows the driver placement |
| S2 | How does a source learn that a checkpoint starts and report its position? | A method pair on the stream-source trait; a separate checkpointable-source interface that only some sources implement | The separate interface: the rate and socket sources stay untouched | Their preference; P1 implements it for the rate source |
| S3 | When do checkpoints start? | Fixed period; adaptive on volume; once at the end for a bounded run | Period for continuous runs, once at the end for bounded runs; the period is a run option | Their preference |
| S4 | How do operators align markers from several inputs? | Wait for the marker on every input, then forward (barrier alignment); forward the first and reconcile later | Barrier alignment: it is the only scheme the marker format supports without an extra field | P1 shows a union of two sources |
| S5 | What is the state store? | A per-run directory with immutable segments and a manifest; an embedded key-value store | The directory: no new dependency, recovery is a manifest read, segments are Arrow files | P4 writes and recovers it |
| S6 | How does a sink commit? | One transactional write per checkpoint tagged with the id, skipped on replay; write-ahead log plus apply | The tagged write: Delta and Iceberg carry the tag in the commit, file tables stage and rename | P2 shows it with a file table and Delta |
| S7 | Watermark semantics | Source-emitted marker, late rows dropped and counted; plus an allowed-lateness window | Source-emitted, dropped, counted; allowed lateness as a later option | P4 |
| S8 | Which stateful operators first | Windowed aggregate, key-latest, deduplicate; joins now or later | The three; joins later, named as out of scope | Their preference |
| S9 | How a bounded pipeline run ends | The source emits end-of-data at the positions seen at start; the sink finishes after the next checkpoint | As stated; no microbatch concept remains | P1 and P3 |
| S10 | Iggy as a source | Optional crate with the broker client; positions are offsets per partition; retention gaps fail the run | As stated; the crate's client dependency floor is checked against their lockfile first | P3 |

## Extensions decisions

| # | Question | Options | Recommendation | Settled by |
| --- | --- | --- | --- | --- |
| E1 | The scalar boundary | Comet's scalar kernel (Sedona v1 shape) with its discovery symbol and version probe; a Sail-named copy of the same structs; keep `datafusion-ffi` | Comet's, unchanged, including symbol names, so Sedona's functions import with no edit; follow the header if it moves to DataFusion or Arrow | P5 loads Comet's test library and Sedona's functions |
| E2 | The relation boundary | Sedona's table provider and execution plan structs; keep `datafusion-ffi` | Sedona's; depend on its Rust crate for the import and export adapters if the maintainers accept the dependency, else carry the two adapters | P6 |
| E3 | What a package declares | Header versions, the Arrow C interface version and the Sail extension API version; no DataFusion version | As stated | Their preference |
| E4 | The memory lease | Keep Sail's C record; offer it to the same shared home as the scalar header | Keep; offer later | Their preference |
| E5 | What stays out | Optimizer rules, planner extensions, command plugins, catalog providers | Out, named as such | Their preference |

## Prototypes

Each on its own branch from upstream `main` on the fork, with one test file
that is its whole claim. Sizes are what the prototype adds, not the final
feature.

| # | Shows | What it is | Size | Order |
| --- | --- | --- | ---: | --- |
| P1 | S1, S2, S4, S9 | A checkpoint coordinator in the driver; the rate source gains the checkpointable interface and emits checkpoint and end-of-data markers; the collector finishes a bounded query after end-of-data and the next checkpoint; a union of two rate sources aligns | ~600 lines | first |
| P5 | E1 | Load Comet's published test UDF library through its discovery symbol and version probe, resolve `add_one_c` as a Sail scalar function, call it from Spark SQL; then Sedona's spatial functions the same way | ~400 lines | first, in parallel |
| P2 | S6 | A table append sink that stages rows between checkpoints and commits them tagged with the checkpoint id; a restart replays and skips the committed id; file table and Delta | ~500 lines | after P1 |
| P6 | E2 | Import a Sedona C table provider through the header's structs, scan it through Sail's bounded-relation dispatch with a child plan exported across the boundary | ~500 lines | after P5 |
| P3 | S10, S2 | Iggy as a stream source with the four markers; a bounded run ends at the offsets seen at start; a retention gap fails the run | ~800 lines, reusing the broker client and decoding already written | after P2 |
| P4 | S5, S7, S8 | A windowed aggregate with watermark eviction over a recorded input, snapshotting state to segments and recovering from the manifest | ~900 lines | after P2 |

## Schedule

| Day | Streaming | Extensions |
| --- | --- | --- |
| 1 (review day) | Review this plan; open the discussion thread with the proposal; post S1 to S4 | Open the thread; post E1 |
| 2 to 3 | P1 built and linked from S1 | P5 built and linked from E1 |
| 4 to 5 | Answers to S1 to S4 recorded; post S5 to S9; start P2 | Post E2 to E5; start P6 |
| Week 2 | P2 and P4; P3 once the Iggy dependency floor is checked | P6; record answers |
| Week 3 | Build the real pieces in the order the answers allow | Scalar channel for real, then the relation boundary |

The schedule assumes the maintainers answer within a few days; if a decision
stays open, the prototypes that do not depend on it continue and the dependent
ones wait.

## What happens to the existing branch

The bounded-microbatch streaming, the AutoCDC runtime on it and the Iggy
bounded source stay on the branch as the working system until the new pieces
pass the same ported Spark tests, then they are removed in one change. Nothing
from that path is proposed upstream. The batch pipelines, the catalogs and the
general engine improvements are unaffected by either track and remain the
first reference material.

## What this plan needs from the owner

- Agreement on the venue (discussion threads in their repository).
- Which prototypes to start on day 2: the plan says P1 and P5.
- Whether to post the two proposals as they are or after one more pass.
