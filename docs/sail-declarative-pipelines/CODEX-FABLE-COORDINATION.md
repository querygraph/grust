# Codex–Fable coordination protocol

The live channel remains `/Users/alexy/src/grust-sdp/codex-to-fable.md`.
The operator authorized both agents to improve this protocol together. Keep one
channel for work offers, reviews, design discussion and short questions; a second
Q&A log would introduce another place to miss a reply.

## Read the live channel, then acknowledge what was read

At the start of each work session, and before offering or integrating a unit,
read the canonical log from the last acknowledged point through its current end.
The link in `/Users/alexy/src/sail-sdp-fable` targets that file. The tracked copy
in `/Users/alexy/src/grust-sdp-fable` is a historical Git snapshot, not a live inbox.
Do not infer current activity from an old ACK, a file's existence, or an old
worktree base. Runtime/process status requires actual observation.

The [append helper](../../scripts/sdp-coordination-append.py) allocates a unique,
increasing `Message-ID: CF-0001` under the same lock as the append. New messages
can include `Reply-To` references and a `Seen-Through` reference. Old messages
are referenced as `legacy:` followed by their exact generated ISO timestamp.
An ACK to a review should state which findings are accepted, disputed or still
being investigated, and the intended next scope. `Seen-Through` means read, not
agreement, successful delivery to another agent, or completed implementation.

A review is not treated as received merely because it was appended. The author's
next ACK/reply supplies that evidence. If two notes disagree about current status,
check the canonical path and references before inferring that work stopped or
that someone ignored a message.

## Keep entries short and thread them explicitly

Use these labels in the body; they are purposes, not rigid message schemas:

- ACK: received work/review, declared file scope, and next action.
- OFFER or DONE: completed unit offered for review, with ordered repository/commit
  hashes and evidence. This does not mean integration passed.
- REVIEW: findings tied to the offered commit and precise source or test evidence.
- QUESTION / ANSWER: short technical discussion in this same channel.
- DECISION: agreed interface, ordering or ownership choice and its scope.
- INTEGRATED: exact combined commit and passing gates, posted by the integrator.
- BLOCKED: concrete dependency or information needed to proceed.

Use Reply-To to connect a correction or answer to the relevant entry. Put detailed
reviews and raw evidence in focused Grust files and link them; do not repeatedly
copy the entire review into the log. Corrections append new entries. Never rewrite
another entry, including either agent's operator-requested verbatim feedback.
No heartbeat entries are needed.

For offered code, include repository/worktree, base/head, ordered commits, file
scope, gates and unresolved results. Distinguish source inference, direct reference
oracles, component tests, public runtime tests and a combined integration gate.
A passing branch is not a passing union. Any failed full-library run stays failed
even if failures reproduce on its base; investigate and retain the controls.

## Ownership does not prohibit investigation

Each agent edits and commits its own worktree. Declare shared-file scope before
changing it and coordinate overlaps. Read-only reviews and controlled experiments
in an agent's own isolated gate are welcome across ownership boundaries; a test
failure need not remain unexplained merely because another agent owns the source.
Do not modify the other agent's code, gate target directory or running processes.

Git worktrees share a stash stack. Do not use that stack to hand off or temporarily
hide work. Preserve edits in an agent-owned checkpoint commit/branch or explicit
local patch, and use detached clean controls for baseline experiments. Do not
rewrite already-offered history without coordination; the integrator can assemble
corrected granular units while preserving the offered commits as evidence.

## Locking and helper usage

The persistent companion is `/Users/alexy/src/grust-sdp/codex-to-fable.lock`.
Every write, including snapshot preparation/advancement, takes `fcntl.flock(LOCK_EX)`.
Never unlink or replace the lockfile. Hold the lock only for the read/append or
snapshot operation, not builds, review or waiting. The helper validates references
before mutation, preserves the body text, generates UTC under lock, flushes and
fsyncs the append, then prints the allocated ID. Existing invocations remain valid.

```sh
/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python \
  /Users/alexy/src/grust-sdp/scripts/sdp-coordination-append.py \
  --author Fable --body-file /tmp/fable-message.md \
  --reply-to CF-0001 --seen-through CF-0001
```

Read with the same helper instead of a tail. `--since REFERENCE` prints every
entry after the named one, verbatim and in order, from one snapshot taken under
a shared lock, and changes nothing; an unknown reference is an error. Its last
stderr line, `read-through: REFERENCE`, names the final entry in that snapshot
and is the only value to cite as the next `Seen-Through`: an entry appended
after the snapshot is not covered by it. Resume from the reference your last
entry acknowledged. This exists because one agent read the last thirty lines
after appending and missed an hour of review entries above them.

```sh
/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python \
  /Users/alexy/src/grust-sdp/scripts/sdp-coordination-append.py --since CF-0001
```

Use real existing references in place of the example. Repeat `--reply-to` for
multiple threads. Both agents may propose protocol improvements as a DECISION or
QUESTION entry. Codex commits snapshots of this canonical log; Fable continues
committing its own code/evidence and excludes the live-log symlinks from product
commits. No push, publication or release is authorized by this protocol.
