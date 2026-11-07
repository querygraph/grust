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

**1. "You built it again before asking."** The message leads with "a tested local
Delta append implementation demonstrates recovery". Behind that sentence is
13 commits and about 27,500 added lines against their `main`, the largest
single commit 7,248 lines, all built since their feedback and none seen by
them. Their feedback was that review at the end is too late and AI output
exceeds human bandwidth. The memo is the design conversation they asked for,
but it arrives after the implementation, and the closing question ("which
piece should we prepare for focused code review first?") reads as an
invitation to review that code. Expect: "Thanks, but we asked to discuss the
design first; we can't review this."

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

## Proposed changes

1. **Close #2930** with one line ("superseded by a shorter design memo") before
   sending anything.
2. **Paste the memo into their discussion thread** rather than linking Grust.
   Drop the dependency on `HUMAN-REVIEW.md`: put its one relevant sentence of
   status in the memo.
3. **Say plainly what the code is and is not.** One sentence: "To test the
   design we wrote a local prototype; we are not proposing it for review and
   will rebuild what you approve as small PRs." Do not describe it as tested
   evidence of readiness.
4. **Split question 1** into coordination (job runner and task actors) and
   operators (new nodes versus adapting yours), and state the dense-marker
   cost with the alternative.
5. **Make the Delta choice explicit in question 2**: "Pipeline targets would carry
   a Sail writer feature that other writers must refuse. Is that acceptable for
   a first target, or should ownership live in a catalog or commit service?"
   Mention the new CLI entry as a separate yes-or-no.
6. **Replace "which piece should we prepare for focused code review"** with a
   concrete offer: the foundation bug fixes as four or five small PRs, each
   with its failing test, ready now.
7. **Hold the Flink comparison** until someone asks; offer it in one line.

## Suggested message

> We'd like your direction on building declarative pipelines and change capture
> on Sail's continuous `StreamSource` execution, before we write production code.
> The memo below explains the fit and the choices.
>
> To test the design we built a local prototype of one recoverable Delta-to-Delta
> append pipeline. We are not proposing it for review; we will rebuild whatever
> you approve as small PRs.
>
> Four questions:
>
> 1. Coordination: should checkpoint coordination go through the existing job
>    runner and task actors?
> 2. Operators: user expressions must not run on control markers. Should that be
>    new streaming filter and projection nodes, or changes to the existing ones?
>    The new nodes are correct but slow down sharply when markers are dense.
> 3. First target: pipeline target tables would carry a Sail-specific Delta writer
>    feature so that other writers must refuse them. Is that acceptable for a first
>    target, or should ownership live in a catalog or commit service? Is surviving
>    a process crash (not power loss) a reasonable first milestone?
> 4. Extensions: should Comet's Arrow-only scalar interface sit alongside the
>    existing native interface? This is independent of the rest.
>
> Separately, while testing we found and fixed several bugs in the current
> streaming code on `main` (marker encoding loses decimal parameters and schema
> metadata, filters evaluate casts on marker placeholders, query failures can be
> reported as success). We can open these now as small PRs with failing tests.
> We also have a comparison with Flink's design if that is useful.

## What this review did not do

It did not run any code or verify test results; it read the memo, the Flink
comparison, the append recovery design and its evidence summary, and measured
the local commits against upstream `b52144955`.
