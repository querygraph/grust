# Coordinator helper snapshots

These are durable snapshots of the coordinator's current /tmp helpers, retained
for context/usage-limit handoff. They hard-code this workspace's coordinator
worktrees and branch names. They are not portable or parallel-Fable branch tools.
Read them before invocation and use unique labels/output directories.

make-candidate.py builds an immutable candidate with a temporary Git index and
checks it out in the detached Sail gate. library-gates.py checks format, strict
Clippy and library tests. advance-candidate.py compares candidate/source trees
and conditionally advances the coordinator branch: **it does not enforce passing
gate receipts itself**. Inspect exact receipts and gate HEAD, then advance only
in a conditional successful chain. Do not run it while another gate uses that tree.

For Grust, doc-commit.py prepare creates the exact documentation candidate and
selects the detached Grust gate; evidence-gate.py checks that candidate's retained
evidence/documents. doc-commit.py advance compares the current selected files
with the candidate and conditionally advances the branch. When selecting the
canonical log, take its persistent flock separately around prepare and advance,
never around long gates. A concurrent append requires a refreshed candidate/gate.

The scripts retain their historical /tmp candidate/receipt paths. library-gates.py pins and records PYO3_PYTHON, PYTHONPATH and VIRTUAL_ENV for
the Python3.12/PySpark4.2.1 workspace. PYO3_PYTHON alone selects the build
interpreter without adding its virtualenv modules to embedded Python. The
decimal-config packet retains the omitted-environment failure, env-only control
and successful same-source full gate that establish why all three are needed.
See the root FABLE-HANDOFF.md for current roles, pins, commands and limits.
SNAPSHOT.json hashes all other files in this directory.
