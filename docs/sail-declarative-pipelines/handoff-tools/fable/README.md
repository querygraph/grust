# Fable's durable helpers

Snapshots of the scripts Fable used from its session scratchpad; the
coordinator helpers one directory up are Codex's and advance Codex's branch,
which Fable must not do. Paths are hard-coded to Fable's worktrees.

- `sail-gate.sh <sha>...`: detached exact-commit gate for the Fable Sail
  branch. Own worktree `/Users/alexy/src/sail-sdp-fable-gate` (created on
  first use with `git worktree add --detach`), own target directory
  `/Users/alexy/src/sail-sdp-fable-gate-target`, own venv
  `/Users/alexy/src/sail-sdp-fable-gate-venv` rebuilt from the Spark 4.2.1
  environment's `uv pip freeze` (without pysail). Per commit: fmt --check
  (sail-common, sail-spark-connect), strict all-target/all-feature Clippy,
  `cargo test -p sail-common --lib root_lowercase`, `cargo test -p
  sail-spark-connect --lib pipelines::`, `maturin develop --uv` into the gate
  venv, `pytest python/pysail/tests/spark/pipelines`. Prints one `VERDICT
  commit=<full sha> ...` line only if HEAD did not move during the run.
  `CARGO_INCREMENTAL=0`, toolchain 1.98.1. Not a full-library run.
- `upstream-run.py <sail worktree> <spark source> <report>`: starts an
  in-process PySail Spark Connect server and runs Sail's pinned upstream
  Spark pipeline tests (`scripts/spark-pipelines-tests/run.py`) against it.
  Run with the Spark 4.2.1 venv's Python after `maturin develop`.

Fable-side environment facts: Spark 4.2.1 venv `.venvs/fable-spark-4.2.1`
inside the Sail worktree (uv, Python 3.12, pyspark[connect]==4.2.1 plus the
hatch test dependencies including pyiceberg); Oracle JDK 17.0.8 at
`/Library/Java/JavaVirtualMachines/jdk-17.jdk` for every JVM oracle; pinned
Spark source `/Users/alexy/src/spark-sdp-4.2.1`; pinned Iggy worktree
`/Users/alexy/src/iggy-fable-pin` (153fdf46, rustc 1.99.1, Homebrew hwloc,
target `/Users/alexy/src/iggy-fable-pin-target`, release `iggy-server`
built) with the harness in `evidence/fable-iggy-harness/run.sh`.
