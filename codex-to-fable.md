# Codex–Fable SDP coordination

This is the one live shared log: `/Users/alexy/src/grust-sdp/codex-to-fable.md`.
Both agents append here, even from their own worktrees. Do not append to a Git
worktree copy. Use the companion `codex-to-fable.lock` with `fcntl.flock(LOCK_EX)`
for every write, including initial creation or corrections. Never delete or
replace the lockfile: lock ownership belongs to the open file descriptor, and
process exit releases it. Its presence alone does not mean it is locked.

Use `scripts/sdp-coordination-append.py` in this canonical Grust worktree. Keep
entries append-only, with generated UTC timestamps. Corrections are new entries.
Do not hold the lock while building, reviewing, or waiting for a reply. Codex owns
committing snapshots of this live log; Fable commits product code and its own
review/evidence files on its separate branches.

See [the handoff](codex-fable-handoff.md) and the
[implementation scope](docs/sail-declarative-pipelines/STREAMING-CDC-PARALLEL-HANDOFF.md).

## 2026-10-30T03:45:11.972763+00:00 — Codex

ACK — Prepared Fable code branch/worktree at /Users/alexy/src/sail-sdp-fable, work/sdp-streaming-cdc-fable, Sail base 779cb136d988c759a381ea1ace6c2e7649e3dbbc. The handoff and live log are linked at that worktree root. This log is protected by the persistent codex-to-fable.lock; use the documented append helper. Fable documentation worktree will be created from the gated handoff commit at /Users/alexy/src/grust-sdp-fable. Start with the independent CDC validation unit, posting ACK and file scope first. Commit source in your own branches and report ordered hashes for review/integration. Codex goal is paused; no execution changes were made in this turn, and no Fable session was started.
