# How the maintainers would likely receive the proposed message, and what to change

A pre-send review of the message and memo proposed for the Sail maintainers
(`REDESIGN-REVIEW-PACKET.md` at `695c533e`, with `FLINK-COMPARISON.md` as
optional reading). Written by reading the documents and the local code as of
2026-11-06 and imagining the reader who gave the earlier feedback: busy, wants
design agreement before code, finds AI output beyond review bandwidth, rejected
bounded microbatches, and asked that documents need no outside context.

## What they will like

- The memo is about 1,100 words, stands on its own, defines its terms, and ends
  with three questions. That is the form they asked for.
- It builds on their continuous `StreamSource` model and says plainly that
  Spark compatibility does not justify weaker behavior, which matches their rules.
- It separates the Extensions question so it can be answered independently.
- The Flink comparison is careful and sourced; whoever owns streaming may find
  it useful.

## Where they will push back

**1. Unexplained code arriving with the design.** The message leads with "a tested
local Delta append implementation demonstrates recovery". Behind that sentence are 13
commits and about 27,500 added lines against their `main`, built since their feedback.
Their objection was to a queue of forty-odd PRs they could not digest, not to a few
large reference PRs, so offering the code is acceptable if each piece is properly
explained. As sent, it is not: seven of the thirteen commits had no message body,
including the 7,248-line append commit, and "which piece should we prepare for focused
code review first?" hands them the job of working out what the code is. Expect: "What
are we being asked to review, and why is it this size?"

**2. A product decision is buried in question 2.** "Recording ownership and
writes together in Delta's log" means adding a Sail-specific required writer
feature to pipeline target tables, so that ordinary Sail writers and other
engines refuse to write them, plus a new `sail pipeline run --config` command
outside the Spark SDP API. Those are user-visible changes to what a Delta
table is and to how pipelines are launched. The memo states them only in
passing and in its supporting documents. Expect a no on the Delta protocol
change, or a request to see it argued on its own.

**3. Question 1 bundles two decisions, one with an open cost.** Job-runner
coordination is a reasonable yes. The operator question (new streaming
filter and projection nodes versus adapting theirs) carries a measured
hundred- to thousand-fold slowdown on dense markers, which the memo mentions
only as "expensive small batches". The maintainers own those operators and
will want that number and the alternative up front.

**4. The links still point into Grust.** Both URLs are `querygraph/grust`.
They previously called Grust a "random" reference. The memo also says its
qualification status "is recorded in the human review summary", so a decision
step depends on a second document.

**5. The earlier draft PR is still open.** lakehq/sail#2930, the document they
called unreadable, remains an open draft. They will see both.

**6. Nothing small and mergeable is offered.** The foundation repairs are bug
fixes on their `main` with failing control tests: zero-column decode, decimal
and metadata loss in marker encoding, strict casts evaluated on marker
placeholders, failures reported as success. These are exactly the small PRs
they asked for, and the message does not offer them.

## Changes made

Applied on 2026-11-06, after the owner noted that a few large PRs are acceptable when
properly explained:

1. **Every commit now has a full message.** The seven body-less commits were given
   messages stating the defect or decision, the change, known costs, the tests, and the
   design document behind them. Trees, authors and dates are unchanged; the old-to-new
   hashes are in `COMMIT-MAP.md`. The append pipeline tip now has its own branch,
   `work/delta-append-recovery-20261106`.
2. **The memo asks four questions, not three.** Coordination and the operator boundary
   are separate decisions, and the operator decision states the measured cost (about two
   to three times with one marker per batch, a hundred to a thousand times when markers
   alternate row by row) and the alternative of changing Sail's existing operators.
3. **The Delta choice is explicit.** The memo says pipeline targets carry a Sail-specific
   required writer feature that other writers must refuse, and asks for agreement. The
   separate `sail pipeline run` entry point is asked as its own question.
4. **The code is framed as a few explained reference PRs**, not a review queue and not
   "ready". The memo describes what the local implementation does and its limits in its
   own words, so it no longer depends on the human review summary.
5. **The bug fixes are offered as one small PR now**, with the defects named.
6. **The memo has no required links.** The Flink comparison and other documents are
   mentioned as optional detail, to be attached rather than linked into Grust.

Still for the owner to do before sending: close lakehq/sail#2930 with a one-line note
that it is superseded, and paste the memo into the discussion thread rather than linking
the Grust repository.

## Suggested message

> We'd like your direction on building declarative pipelines and change capture on Sail's
> continuous `StreamSource` execution. The memo below explains the fit and asks four
> questions: where checkpoint coordination lives, how user expressions are kept away from
> control messages, how the first Delta target rejects obsolete writers, and whether
> Comet's Arrow-only scalar interface should sit alongside the existing native interface.
>
> To test the design we built a local Delta-to-Delta append pipeline that survives process
> crashes. We can share it as a few large reference PRs, each explaining one boundary,
> once you've told us which boundaries you would keep or change.
>
> Separately, testing found defects in the current streaming code on `main`: marker
> encoding loses decimal parameters and schema metadata, filters evaluate casts on marker
> placeholders, and a failed streaming query can be reported as successful. These fixes
> are independent of the decisions, each has a test that fails on `main`, and we can open
> them as one small PR now. A comparison with Flink's design is attached for anyone who
> wants it.

## What this review did not do

It did not run any code or verify test results; it read the memo, the Flink
comparison, the append recovery design and its evidence summary, and measured
the local commits against upstream `b52144955`.
