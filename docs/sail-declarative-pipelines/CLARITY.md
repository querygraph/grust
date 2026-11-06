# Clarity requirements for technical design documents

Write for busy Sail founders and maintainers deciding whether a design fits
Sail's existing architecture and intended direction. Assume they understand
systems engineering but have no knowledge of the work that produced the
proposal. They should be able to assess it from the document in front of them.

These requirements apply to proposals, architecture documents, decision notes
and implementation plans. Evidence reports need the same clear terminology
and distinction between demonstrated behavior and open questions.

Maintain `HUMAN-REVIEW.md` as the overall review compendium. Begin with the full
SDP, Extensions and performance goal, explain its fit with Sail, and keep verified
behavior distinct from pending work. Write each self-contained plan from first
principles before its dependent implementation; keep human review and maintainability
as design constraints rather than end-of-work presentation tasks.

## Make the document stand alone

Explain the user problem, relevant existing behavior, proposed change,
alternatives, tradeoffs and requested decision within the document itself.
Define each necessary term before using it. Use one name consistently for
one concept, and distinguish similar concepts when the distinction matters.

A review sequence may establish a shared model and then develop its consequences.
Each document must supply the context needed for its own question, including a
short explanation of any shared guarantee it uses. It need not repeat the full
argument that established that guarantee. Never require session history, a private
repository, a separate glossary or an explanation from the author.

Links provide optional evidence and deeper implementation detail. They must not
substitute for the reasoning needed to answer the document's question. A short
decision note states its premises and alternatives even when it belongs to a
larger collection.

## Make the sequence cumulative

Assign each document one purpose and each substantial explanation one home. The
overview explains the goal, architectural fit and readiness. The shared proposal
establishes the execution and recovery model. Later proposals explain the behavior
they add and the choices that addition creates. A review agenda lists decisions;
an implementation plan explains delivery dependencies. Neither retells the proposals.

Use a brief recap where a reader needs a shared premise. Repeat a requirement only
when its application changes the current decision. Put the worked example and full
tradeoff in the document that owns them. Do not reproduce the same failure example,
component table, status report or correctness argument across the sequence.

Keep the primary reading path short and explicit. Mark detailed architecture,
specialist notes, implementation plans and evidence as references rather than
required stops. Assess the total reading burden as well as individual lengths.

## Show the fit with Sail

Name the existing components and explain what each already provides.
Distinguish those capabilities from proposed additions and unbuilt integration.
Show where the new behavior belongs, which contracts it preserves, and which
contracts it would change. Explain how the proposal advances the intended
capability without assuming that a new subsystem is necessary.

A compact comparison of existing foundation, proposed addition and
architectural consequence often makes this clearer than a component list.
Do not make the reader inspect code to discover the basic architectural fit.

## Explain why there is a decision

Present the situation that forces a choice before listing options. Explain
why the existing behavior or an obvious alternative is insufficient. Use a
small concrete example when a failure or tradeoff is otherwise abstract.

For each consequential choice, state:

- The capability or guarantee at stake.
- The reasonable alternatives and their costs or limitations.
- The recommended option and the reason for it.
- The evidence that supports the recommendation and what remains unproven.
- The question to answer and what would settle it.

Separate required correctness properties from selectable delivery scope.
Choosing a smaller scope can defer a capability; it does not waive the
correctness promised within that scope. A counterexample can reject an unsafe
policy without proving that one particular architecture is the only solution.

## Explain dependencies instead of prescribing a sequence

If one question comes before another, explain what its answer constrains.
Distinguish reading order, decision dependencies and implementation order.
Do not present numbered notes as a mandatory sequence of approvals.

Make conditional dependencies explicit. A path needs the contracts for the
capabilities it uses. Independent work can proceed, and later evidence can
change an earlier scope choice. State which questions must be resolved before
the selected implementation, rather than asking readers to infer this from
an ordered list.

## Keep authoring history out of the argument

Discuss the technical problem and reasonable ways to solve it. Exclude agent
sessions, conversation history, prior review rounds, coordination identifiers,
author assignments, approval bookkeeping and narratives about editing the
document. Those records belong outside the reader-facing design.

Existing implementation behavior matters when it explains a constraint or
reuse opportunity. Describe that behavior directly, with enough context to
understand it. Do not refer vaguely to “our current runtime” or an internal
prototype label as if the reader already knows what it means.

## Be precise about evidence

Distinguish existing behavior, proposed behavior and demonstrated behavior.
Keep source inspection, executed tests, reported results and untested
inferences distinct. A component test does not establish an integrated
recovery protocol, compatibility guarantee or performance envelope.

State limitations where they change the decision, next experiment or supported
scope. Retain enough technical detail to explain the claim. Remove chronology
about how the evidence was gathered when it adds nothing to its meaning.
Intentional differences from Spark must be explicit and justified.

## Respect the reader's time

Lead with the user value and proposed direction, then explain architectural
fit and the consequential tradeoffs. End with a small set of concrete questions.
Use plain language and connected paragraphs. Use tables for comparisons and
lists for genuinely parallel choices or steps.

Keep a design document under 2,000 words and each standalone decision note
under 300. These are ceilings, not targets. Cut repetition and process detail
before cutting the context needed to understand a decision. Separate proposals
must answer distinct questions rather than divide one repeated system description.

## Read it as the recipient

Read the whole document once without relying on another file or conversation.
Check whether the reader can explain the problem, Sail fit, alternatives,
recommendation, unresolved risks and requested decision after that reading.

For every unfamiliar name, define it or remove it. For every decision, check
that its cause and consequences are clear. For every ordering claim, check
that the dependency is explained. For every link, check that the argument
still works without opening it. Revise any passage that needs the author
beside the reader to supply missing context.

Then read the primary documents in sequence. Check that each advances the argument,
that shared terms retain their meaning, and that recaps are shorter than the new
material. Remove repeated explanations even when each would be clear in isolation.
