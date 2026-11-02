# Coordination protocol gate

Grust `16a0a7f49700fb11d4347aeaa10236afd5808965` adds message IDs, reply
references and read-through acknowledgements to the persistent-lock append helper.
The [protocol](../../CODEX-FABLE-COORDINATION.md) keeps one canonical channel.
It distinguishes an offered unit from an integrated unit and a posted review from
an acknowledged review. It also permits short questions in the same channel.

Seven temporary-log tests passed in the detached exact-commit gate. The same seven
passed with Python `-O` while ten owned busy processes saturated the ten logical
CPUs; the harness terminated and joined all ten. Concurrent append coverage uses
twelve independent writer processes. Other assertions cover verbatim Unicode,
whitespace and CRLF bodies, reference validation before append, persistent lock
inode stability, CLI references and timestamps generated while holding the lock.
Tests never write the canonical channel. These are local coordination checks,
not an assertion that another agent has read or agreed with a message.

The raw [receipt](receipt.json), [normal log](tests.log),
[optimized log](optimized.log), [documentation log](docs.log),
[gate harness](gate-harness.py) and [documentation checker](documentation-gate.py)
are retained. The harness records historical absolute worktree paths and uses a
fresh output directory; it is evidence of that run, not an idempotent test runner.
The committed tests can be rerun directly with the Python interpreter named in
the receipt. `provenance.json` records the tested source hashes and every packet
file except itself.
