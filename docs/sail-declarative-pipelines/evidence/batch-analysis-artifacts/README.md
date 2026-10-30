# Pipeline analysis artifacts before owner migration

Sail `954e025c5631adc1fa25d204613183ddd613a5f4` on
`17b8ac254139e9213327dfcc7fc8badb4fdd27b2` adds four test-only characterizations.
No production behavior, provider ownership or execution path changes.

A mock DataSource creates one provider with a Weak-observable lease and a scan
callback that fails if invoked. Normal graph analysis retains that lease only in
pipeline temporary-view plans; materialized-table and persisted-view outputs
export EmptyRelation/schema artifacts and release it. The temporary case includes
a downstream materialized output, whose artifact is also schema-only. All cases
resolve actual registered SQL and graph analysis, check one provider creation,
output schema/shape, zero scans and lease release after artifact drop. A fourth
case resolves Sail current_timestamp in a temporary definition and checks the
TimestampNow ScalarFunction remains present; normal graph analysis has not folded
it to an analysis-time literal. These are mocks and normal-path observations,
not live Delta/SDK or arbitrary-rule guarantees.

Exact detached fmt/strict all-target/all-feature Clippy and139 Connect libraries
pass with explicit venv/PYTHONPATH exposing PySpark4.2.1. Preserve both initial
failures:7f8dd259c strict-Clippy unused import, then corrected954's first full
library run137pass/2existing ORC failures (Snappy versus Zstd) without the explicit
PySpark path. The same source AND identical test binary, with the explicit env,
gives139pass. environment-control.json records the binary hash observed unchanged
before the negative source control; this is an environment correction, not an ORC
code fix or a relabelled failed run.

Control `4b49628623205f73bdafc59def2f597e89b3014d` changes only analysis's
artifact selection to retain full plans for every output. Four unchanged tests
give1pass/3fail: clock still passes, retention/schema-shape tests detect the
change. No scheduling/concurrency mechanism or background I/O is added; no new
optimized stress or public CLI verdict is claimed. Latest public CLI remains09.

The test captures historical artifact shape for this migration checkpoint; it
must evolve deliberately when the exported artifact contract changes, alongside
stronger owner-release/metadata-equivalence checks. It is not a requirement to
retain temporary providers forever. Source audit and design are separate packets.
SHA256.json covers packet files except itself. Historical absolute paths identify
advancement-time inputs; replay only into fresh worktrees/output directories.
