# Writing rules for documents we send to Sail's maintainers

These rules exist because a document we sent was found unreadable by people
without our context. They apply to every design document, pull-request
description, discussion post and review reply from this project. A document
that breaks one of them is not sent.

## Before sending

1. Read the whole document once as the reader will: someone who maintains
   Sail, has never seen our repositories or logs, and has ten minutes.
2. For every name, ask: would that reader know what this is? If not, define
   it where it first appears, or remove it.
3. For every decision, ask: does the reader know why this was ever a question?
   If not, state the situation that forced it before stating the choice.
4. Cut what the reader does not need to act. A design document is not a log of
   what we did.

## Names and references

- Never use a name from our own process: no lane names, no coordination
  message numbers, no gate or script names, no session dates, no "the user".
- Never mention our other repositories or products by name unless the
  document is about depending on them, and then say in one sentence what the
  thing is.
- Refer to Sail code by path when the reader has to open it, and only then.
- Refer to Spark behavior by what Spark does, with the version, not by test
  names or suite names, unless the document is about the tests.
- Link to public things (issues, discussions, pull requests, published
  pages). Do not link to files on a branch unless the document says the
  branch is the subject.

## Each concept, once, before use

- Define a term the first time it appears, in the same sentence or the one
  after, in plain words. Do not rely on a glossary the reader must jump to.
- Use one name for one thing throughout. Do not alternate between synonyms.
- Do not introduce a concept the document does not go on to use.

## Sentences and structure

- One idea per sentence, in active voice, about twenty words.
- State the conclusion first, then the reason, then the evidence.
- A list holds parallel items of one kind; a sentence holds an argument.
  Do not pack an argument into a bullet.
- Headings name what the section decides or explains, not where it came from.
- No numbers in prose unless the reader will act on them; a measurement goes
  in a short table with what was measured and how.
- No parentheses, no em-dashes, no arrows, no abbreviations the reader has
  not seen defined.

## Design documents in particular

- Open with what the thing is for the user, in three sentences, then what it
  is not.
- Say how it fits what the maintainers already have, by naming their
  existing component and what changes for it.
- For each design choice: the situation, the choice, what it replaced, how it
  was checked. Four short sentences, not a paragraph each.
- Deliberate differences from Spark get their own section and nothing else is
  presented as parity. Sail does not conform to Spark's obsolete or inferior
  choices: where Spark's behavior is a bug, an incorrect error, or an
  inconsistency, say so and state the consistent behavior Sail chooses
  instead, which is the maintainers' own rule.
- Open questions are questions, with what would settle them.
- Keep it under two thousand words. If it needs more, it is two documents.

## Pull-request descriptions

- First sentence: what the change does for a user of Sail.
- Second: why it is needed, with the Spark behavior or the failure it fixes.
- Then: what it touches, by crate; how it was tested, with counts only if the
  reader would act on them; what it deliberately does not do.
- One pull request does one thing. If the description needs "and also", split
  the pull request.
