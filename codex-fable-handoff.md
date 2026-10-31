# Fable: Sail streaming and CDC handoff

For a replacement agent resuming current work, start with the living
[FABLE-HANDOFF.md](FABLE-HANDOFF.md), then read the live coordination channel.

Current CDC implementation workspace: **`/Users/alexy/src/sail-sdp-fable-cdc-build`**,
branch **`work/sdp-cdc-build`**, based on accepted Sail
`a690e2ce96075b433edaf17faadb00088a30e9f9`.
The user reaffirmed Codex=batch and Fable=CDC on 2026-10-31. Recent read-only
reviewer directions are superseded. Port/reuse existing Fable CDC work from
`/Users/alexy/src/sail-sdp-fable` and its component/C5 branches without rewriting
those offered histories. Choose and implement the next missing CDC unit; routine
implementation does not wait for another assignment or per-commit approval.

Use **`/Users/alexy/src/grust-sdp-fable`** for design notes and evidence on its own
`work/sdp-streaming-cdc-fable` branch. Keep product code/tests in Sail and design
and review artifacts in Grust. Read each repository's applicable AGENTS guidance.
Do not edit Codex's implementation or detached gate worktrees. Do not use the
independently active `/Users/alexy/src/sail` checkout.

## What to build next

The sequence below is the original plan. Reuse completed work and choose the
next missing CDC implementation unit; do not redo completed validation as a new
review exercise.

Read the [parallel implementation handoff](docs/sail-declarative-pipelines/STREAMING-CDC-PARALLEL-HANDOFF.md)
and [Fable review with responses](docs/sail-declarative-pipelines/SDP-FABLE-DESIGN-REVIEW.md).
Start with Spark4.2.1 CDC argument/definition validation in a small separate commit,
then original-row validation and a deterministic bounded streaming source. The
handoff specifies the six independent units, source pins, and admission limits.
Keep original Spark assertion identity, error behavior and failed attempts in the
evidence. Iggy is required; use the pinned sail-iggy and src/iggy reviews.

Codex owns resource scopes, task contexts/monitors, local/distributed execution
cleanup and ORC. Fable owns new pipeline streaming/CDC modules, source adapters
and their tests. Coordinate before editing shared existing pipeline orchestration,
session/configuration, protobuf, catalog publication or Delta commit modules.
Request Astra review before the production durability/recovery choices listed in
the handoff; this is not approval to invent or activate an unresolved protocol.

## How to communicate and share changes

Follow the current [coordination protocol](docs/sail-declarative-pipelines/CODEX-FABLE-COORDINATION.md),
including canonical-log reads, message references and read-through acknowledgements.
Short questions and answers belong in the same live log.

The **only live coordination file** is
`/Users/alexy/src/grust-sdp/codex-to-fable.md`, also linked from the Sail worktree.
Append under `/Users/alexy/src/grust-sdp/codex-to-fable.lock`; do not write to the
copy in another Grust worktree. The helper takes that lock, generates a UTC
heading, appends and flushes the entry. Never unlink or replace the lockfile.

Write the message body to a temporary file, then run:

```sh
/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python /Users/alexy/src/grust-sdp/scripts/sdp-coordination-append.py --author Fable --body-file /tmp/fable-message.md
```

Post ACK with scope/files before starting; post DONE with repository, branch,
base/head hashes, ordered commit hashes, changed files, exact checks and results,
remaining gaps and evidence paths. Post BLOCKED for concrete dependencies. Do not
hold the lock while testing or waiting. New entries correct earlier entries.

Commit each logical unit in Fable's own branch. Shared Git object storage makes
those commits immediately visible to Codex; no copied source directories or push
is needed. Codex reviews and cherry-picks the listed commits, then gates the
combined commit in a detached worktree with its own target directory. Separate
passing branches do not qualify their union. Coordinate rebases; do not rewrite
commits already offered for integration without a new log entry.

Keep Grust implementation evidence in focused new paths to reduce conflicts.
Codex alone commits snapshots of the shared live log. Fable should exclude the
worktree-local handoff/log symlinks from product commits. No push or release is
part of this handoff. Disk space is tight: inspect free space before builds and
never share Codex's target directory or remove another process's artifacts.

The shared log records current activity and ownership; do not infer live status
from these starting commit pins. Fable has acknowledged unit 1 and Codex has
resumed. Foundation work does not yet qualify streaming/CDC runtime behavior.
