# What the streaming layer assumes, and what survives a continuous source model

> **Reference scope.** This is a source comparison at the older revision named below, not the current
> StreamSource specification. Its three-marker description missed end of data:
> the current foundation has four markers and an explicit bounded-completion
> ordering contract. Spark watermark and late-row rules do not carry over unchanged;
> checkpoint IDs alone do not establish semantic or recovery equivalence. Use
> Sail’s actual marker contract, explicit per-input recovery state and deterministic
> change-event order as described in
> [StreamSource architecture and engineering changes](STREAMSOURCE-ENGINEERING-REVIEW.md).
> The line counts below describe only the recorded source snapshot.

A fact base for the user's response to the maintainers' direction (relayed in
CF-0738): streaming as bounded microbatches is not a direction they will take;
their foundation is the continuous `StreamSource` model. This note says, from
the two source trees at `93ca6ef4e`, what in the branch's streaming and
AutoCDC layer is specific to the bounded model and what carries over. It states
no preference.

## The two models, as the code has them

**Upstream's continuous model** (`sail-common-datafusion/src/streaming/{source.rs,event/}`,
unchanged since 2025-09 apart from edition and DataFusion bumps). A
`StreamSource` has a data schema and a `scan` that returns an unbounded
execution plan whose output is a stream of `FlowEvent`s: retractable data
batches (a batch plus a per-row retraction mask) and markers, of which three
exist: a latency tracker, a watermark (`source`, `timestamp`) and a checkpoint
(`id`). Two sources implement it, `rate` and `socket`; the driver and task
runner carry the event streams between tasks. There is no contract for a
source's positions or retention, no notion of a read that ends when the
available data is consumed, and the watermark is a marker the source emits,
not a value the engine computes from rows.

**The branch's bounded model** (`streaming/bounded.rs`, `pipelines/streaming/`,
`pipelines/append.rs`, `pipelines/autocdc/`). A `BoundedSource` names its
partitions, their current and earliest positions and whether a partition
retains its origin; the pipeline decides each batch's end before the batch
runs (Spark's AvailableNow), scans the ranges as ordinary table providers,
computes the watermark from the rows it read (Spark's rule: the maximum event
time in milliseconds minus the delay, never moving back, the least across
sources), and records progress as digests of the positions. A run completes
when every source is drained. This is the model Spark's Declarative Pipelines
have in 4.2.1: a `run` returns when its flows have processed what was
available, and streaming tables are AvailableNow microbatches; Spark has no
continuous mode for pipelines.

## What is specific to the bounded model

| Part                                                                     |                      Lines | What binds it to bounded ranges                                 |
| :----------------------------------------------------------------------- | -------------------------: | :-------------------------------------------------------------- |
| `streaming/bounded.rs` (C1), `sail-iggy-bounded`, Delta `lake_source.rs` | ~500, 2,900, part of 1,400 | the contract itself: positions, ranges, retention, incarnations |
| `pipelines/streaming/intent.rs`                                          |                        171 | a batch's ranges and progress digests, decided before the batch |
| `pipelines/append.rs`, the range and bounded-plan plumbing               |              ~400 of 1,621 | plans one bounded scan per source per batch                     |
| `autocdc/flow_source.rs`, the leaf and batch-plan half                   |              ~700 of 1,369 | reads each stream's ranges for the batch                        |
| `autocdc/run.rs`, `durable.rs`, `execute.rs`, the batch loop             |            ~1,000 of 2,514 | sequences intents, archives a batch's rows, replays by intent   |
| `sail-sdp-control`, the batch intent and progress digest                 |              part of 4,200 | the lease, fence and guard are keyed by a batch sequence        |

Under a continuous model these are replaced, not adapted: a source would be a
`StreamSource` that emits checkpoint markers, and "the batch" would be the
interval between two markers.

## What carries over

| Part                                                                     |          Lines | Why it is model-neutral                                                                                                                                                                                                                           |
| :----------------------------------------------------------------------- | -------------: | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| The flow binder and admission (`binding.rs`, `admission.rs`, `lower.rs`) |          1,446 | decides which query shapes a streaming flow may contain and how its reads bind, over the Connect plan, before any source is read                                                                                                                  |
| The watermark model (`watermark.rs`) and the late-row rule               |            355 | Spark's rule, computed from rows; under the continuous model the value would come from the watermark marker instead, and the windows, the late-row rule and the per-source minimum stay as they are                                               |
| The stateful operators (`stateful.rs`, `carry.rs`, `state.rs`)           |          1,370 | `dropDuplicates`, `dropDuplicatesWithinWatermark`, stream-stream join eviction, as Spark defines them, driven by a watermark value and an eviction point; the state store keys snapshots by a progress digest, which would become a checkpoint id |
| AutoCDC definitions, name folding and the oracle (C5)                    | ~3,600 + 1,400 | parse Spark's AutoCDC statements and fold names as Spark does; no source model                                                                                                                                                                    |
| The SCD1 MERGE paths (`merge.rs`, `write.rs`, `microbatch.rs`)           |          1,116 | take a batch of change rows and merge them; a lakehouse commit is bounded by nature, so a continuous flow still commits per checkpoint interval                                                                                                   |
| The control model's lease, fence, guard and reset rules                  |  most of 4,200 | keyed by a sequence number; the checkpoint marker's id can be that sequence                                                                                                                                                                       |
| The Spark 4.2.1 oracle suites                                            |       75 files | assert table contents after runs; the harness's "run to completion" would become "run to checkpoint N"                                                                                                                                            |

## The question the direction turns on

Spark's pipelines API has a run that ends: `dp.run` returns, and a materialized
view or streaming table is complete for that run. A continuous `StreamSource`
expresses an unbounded flow with checkpoint markers. For the branch's
semantics to live on the continuous foundation, that model needs one thing it
does not state today: a way for a flow to end when its sources have no more
available data, which is AvailableNow by another name, and a checkpoint marker
at each such boundary so that the SCD1 merge, the state snapshots and the
control store have a sequence to key on. If the maintainers' model admits that
(a terminating stream plus checkpoint markers), the tables above say what
moves and what stays; if it does not, Spark 4.2.1's pipeline semantics cannot be
met on it, which is a fact about the compatibility goal rather than about
either implementation.

## Where the numbers come from

Line counts are `wc -l` on the files at `93ca6ef4e`; the "part of" estimates
are by reading, with a count of references to ranges, intents, cursors and
incarnations per file as the coupling measure (`append.rs` 49, `flow_source.rs`
42, `intent.rs` 23; `watermark.rs`, `stateful.rs`, `merge.rs`, `write.rs` 0).
