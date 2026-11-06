# Review of the redesign work: human review, self-contained documents, design before implementation

A review of everything the Codex session produced for the redesign between
2026-11-04 22:35 and 2026-11-06 04:32 UTC, on the grust documentation branch
(seventeen commits over `422dba75`, ending at `4cafee7f`) and on three local
Sail branches. Written by the Fable session on 2026-11-05. Nothing was rerun;
every claim below comes from reading the documents, the commits and the
evidence directories, and from counting.

## Verdict

The documents are now what the maintainers asked for: self-contained, free of
project history, defined term by term, each under its length rule. The design
is substantively better than the one it replaced, because it fixes real
defects the earlier prototypes had and replaces inherited Spark accidents with
stated engineering contracts. The process discipline, plan before code and
qualification on immutable commits with controls, is real and documented.

Two things are wrong at the level that matters most. First, the body of
material has grown faster than any human can review: about thirty documents
of roughly thirty thousand words, two hundred and forty evidence files, and
ten thousand lines of new code, produced in thirty hours, with substantial
repetition between documents. Second, implementation has run ahead of the
maintainers again. Every code increment was preceded by its own design note,
which satisfies "design before implementation" locally, but no design question
has been put to the maintainers since their feedback, and the two largest
increments (the streaming projection node and the Comet scalar adapter) are
architecture choices that the maintainers have not seen. The foundation
repairs are different: they fix bugs on upstream `main` and are the right first
small PRs.

## What was reviewed

- Reader-path documents: the review packet, the plan, the human review
  compendium, the clarity rules, the two proposals, the thirteen streaming and
  five extension decision notes, the engineering review, the change-capture
  semantics, fenced commits, typed configuration, and the three results
  documents.
- Code: `work/streamsource-foundation-20261105` (four commits, 1,870 lines
  added over upstream `b52144955`), `work/streamsource-comet-scalar-20261105`
  (one commit, 2,026 lines), `work/streamsource-projection-20261105` (one
  commit, 3,565 lines), all local and unpushed, in detached worktrees under
  `sail/tmp` as the maintainers' rules require.
- Evidence: the seven evidence directories and the coordination posts
  CF-0764 to CF-0783.

## Self-contained documents: largely achieved

Measured against the clarity rules the session itself wrote:

- No reader-path document mentions a coordination number, a session name, a
  lane, Grust or LakeCat. Automated search found none.
- Every design document is under two thousand words (the longest, the human
  review compendium, is 1,964). Every decision note is between 135 and 163
  words, under the three-hundred ceiling.
- No relative link in the reader path is broken. The two Astra review
  documents link absolute paths on this machine, which do not resolve for
  anyone else; they are marked historical, but they sit in the same directory.
- Each proposal opens with the user problem, states the fit with existing
  Sail components in a table, separates proposed from demonstrated behavior,
  and ends with concrete decisions. The partial-commit example in the packet is
  the kind of concrete case the maintainers asked for.

Three shortfalls remain:

1. **Repetition across documents.** The same contracts (fenced commits, prepared
   effects, complete per-key order, process-retained library code) are restated
   in the packet, the plan, the compendium, the engineering review, both
   proposals and the semantics document. A reader who follows the packet's
   links reads the same argument five times in different words. Each document
   is self-contained, but the set is not reviewable in an afternoon, which is
   the practical test. The clarity rules say to cut repetition; the set does
   not.
2. **Density without examples.** Most sections are lists of imperatives
   ("Bind recoverable positions to the source descriptor and its incarnation";
   "Reconcile unknown outcomes by their original identity"). Terms are defined,
   but a reader meets effect identity, generation, incarnation, authority
   domain, semantic version, admission horizon and prepared boundary within a
   few paragraphs and has to hold all of them. One worked example per section,
   like the partial-commit one, would carry more than the lists do.
3. **The decision notes have drifted from questions to requirements.** S13
   begins "Require fencing for every admitted durable target"; S11 and S12
   read as specifications. A decision note exists to give the maintainers a
   choice with a recommendation. Where the session has concluded there is no
   choice, the note should say so in one line and move the material to the
   proposal, so the notes that remain are the ones the maintainers can answer.

## Human review: the volume defeats the purpose

The maintainers' feedback was that a document which needs the reader to
reconstruct context is a burden, and that forty PRs exceed their bandwidth.
The documents now carry their context, but the number of them has roughly
doubled since that feedback, and the evidence directories hold forty-three
thousand lines of JSON snapshots, patches and review transcripts. The "seven
specialist roles" reviews are agent reviews; they are useful, and the
maintainers' own rules call for them, but they are not the human review the
maintainers meant, and their outputs add to what a human has to wade through.

Two specific points:

- The coordination posts are long single lines with numbers run together
  ("Spark4.2.1", "pipelines1210passed"), which are hard for a human to read
  and impossible to skim. The posts are internal, but the owner reads them.
- Commit messages on the code branches are one-line subjects with empty
  bodies, and none cites the design note that preceded it. The evidence
  directories contain "plan before code" artifacts, so the traceability
  exists, but not where a reviewer of the commit would look. A code reviewer
  reading `fix: isolate streaming projections from control records` (3,565
  lines) has nothing in the commit to explain why the node exists or what it
  deliberately does not do.

## Design before implementation: honored locally, not with the maintainers

Each increment was preceded by a plan: event fidelity, data-only expressions,
failure propagation and error protocol before the foundation branch;
projection, placeholder ownership, metrics and cost decisions before the
projection branch; adapter and nullability plans before the Comet scalar
branch. The results documents distinguish demonstrated from untested behavior
and state the qualification boundary ("does not establish distributed
execution or process-restart recovery"). The performance regressions are
reported honestly: the marker-isolated filter and projection run eighteen to
a thousand times slower than the ordinary operators when markers alternate
with rows, and the batching policy is left as an open decision. This is good
engineering practice.

But the maintainers said design agreement comes before code, and nothing has
been put to them. The sequence since their feedback has been: rewrite the
documents, then build ten thousand lines against upstream `main`. Of that
code, three categories should be distinguished:

| Increment | Nature | Needs maintainer agreement first? |
| --- | --- | --- |
| Foundation repairs: zero-column decode, decimal placeholders, schema metadata, strict cast on marker placeholders, terminal failure propagation, exception serialization | Bug fixes on upstream `main`, each with a control test that fails on the unmodified code | No. These are the small single-purpose PRs the maintainers want. Open them. |
| Marker-isolated projection node, placeholder construction, telemetry | An architecture choice: a new physical node and codec path, with a known hundred-fold cost on one input pattern | Yes. The maintainers own the rewriter; whether expression isolation is a new node or a change to their operators is their call. |
| Comet scalar adapter | An extension-boundary choice the maintainers have not seen; the only external input is the Sedona maintainer's reply | Yes. E1 is still an unanswered question in the notes. |

The redesign also widened scope before any answer: mandatory commit-time
fencing for every durable target including managed Delta and Iceberg, a
versioned typed configuration model with an optional Dhall frontend, and
engineering-first change-capture semantics that will fail the ported Spark
tests which pin the old behavior. Each may be right. None has been costed
against the maintainers' bandwidth, and the plan does not say what the first
PR after the bug fixes would be or how big.

## The design itself

Compared with the proposals of 2026-11-04, the redesign corrects real defects
found by the Astra review in the earlier prototypes: merge completion counted
an input twice; the Iggy source could accept a recreated partition while
bounding; overlapping checkpoint requests could deadlock alignment; concurrent
Delta creation might bypass the idempotency check; and the S6 restart rule
conflicted with reusing an uncommitted checkpoint identifier. The replacement
contracts (immutable prepared boundaries with separate effect receipts, state
retained until no pending effect needs it, validation of every original change
row before reduction, a complete per-key order with one comparison for upserts
and deletes) are stronger and are argued from first principles rather than
from Spark's batch engine. The change-capture semantics document is the best
piece of writing in the set.

Two reservations. The complete-order requirement moves a burden onto the
source: a broker topic without a transaction ordinal cannot satisfy it, and the
documents do not say what a user with such a source gets. And "build fencing
for every admitted durable target, remove the unfenced fallback" turns the
first usable delivery into a multi-adapter project; the plan's "prove one
durable append path" is the right counterweight, but the two are not
reconciled into a first milestone with a size.

## Recommendations, in order

1. **Open the foundation bug fixes as upstream PRs now**, one per defect, each
   with its control test, each under a few hundred lines, with a commit body
   that states the defect, the fix and the test. These need no design
   conversation and are exactly the small PRs the maintainers asked for.
2. **Put three questions to the maintainers before any more code**: whether
   expression isolation should be a new node or a change to their operators;
   whether a source control interface reaching running tasks belongs in the
   job runner as proposed; and whether they want Comet's scalar boundary at
   all. Use the packet's own three decisions as the fourth to sixth. Stop the
   projection, Comet and participation branches until then; keep them as
   evidence.
3. **Collapse the reader path to four documents**: the packet (as the cover),
   one streaming proposal, one change-capture proposal, and the decision notes
   that are still questions. Fold the engineering review, the semantics
   document and the compendium's repeated contracts into those four or mark
   them as reference. Move the Astra documents and evidence out of the reader
   directory.
4. **Give every code commit a body** that names the design note, the defect
   or decision it implements, the control test, and what it deliberately
   leaves out.
5. **Size the first milestone**: one source, one target, one fencing adapter,
   append only, with a line count and the list of ported Spark tests it will
   rebaseline. Until that exists, the plan reads as a complete system
   presented as inevitable, which is what the maintainers rejected.
6. **Write coordination posts for a human**: short sentences, spaces between
   numbers and words, one fact per line.

## What this review did not do

It did not build or run any branch, rerun any gate, or verify the Spark 4.2.1
source claims; it took the results documents' qualification statements at face
value and checked them for internal consistency only. It did not review the
evidence JSON beyond directory listings and README presence. It did not assess
the Comet adapter's unsafe code line by line.
