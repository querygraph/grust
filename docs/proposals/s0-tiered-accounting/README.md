# S0 tiered accounting: a proposed change to the Sail fork, for review

This is the first step of the sequence in [`FABLE-ON-ASTRA.md`](../../FABLE-ON-ASTRA.md)
(S0, "separate staging from kernel in every measurement"), prepared on
the fork branch `work/s0-tiered-accounting` of `querygraph/sail` (commit
`e33d130f8` on top of `work/extensions-traversal-bench` at `b87fb27ac`).
The patch here is the reviewable copy. Per `AGENTS.md` "Sail Discipline" the
fork is ours to build in; nothing here is an upstream change.

`0001-s0-tiered-accounting.patch` touches ten files under
`examples/extensions/` and nothing in Sail's own crates:

- **Vendored Nutmeg** (`vendor/nutmeg-graph/src/lib.rs`, `session.rs`,
  `graph_tables.rs`): `canonicalize` reports the sort's admitted permutation,
  key and sorted-copy bytes, the schema fill, and its seconds; `swap_into`
  returns those beside the row count; each projection build records its
  seconds and the pool's live-byte delta. The public `Staging::finish` is
  unchanged; `finish_reporting` is added. `GraphInfo` gains
  `projection_builds`.
- **Extension** (`nutmeg/src/mutation.rs`, `diagnostics.rs`, `tests.rs`,
  `python/sail_nutmeg/client.py`, `tests/test_nutmeg.py`): the stage receipt
  gains sixteen columns (per part: sort permutation, keys, sorted copy, fill,
  normalized, retained bytes, sort seconds, sorted flag); the diagnostics
  JSON lists projection builds per graph.
- **Harness** (`benchmarks/measurement.py`, `graph_cell.py`): the sampler
  counts open descriptors per process, walks watched directories every
  twentieth scan, and keeps per-step peaks under the unchanged `execute`
  phase; the native cell marks `stage`, `projection` and `kernel` steps,
  records the native status after staging and after `projectionStats`, and
  checks afterwards that the kernel reused the projection that
  `projectionStats` built. The relational cell marks `rounds` and records
  per-round end times.

Measured boundary change to disclose: a native trial now runs
`projectionStats` between staging and the kernel, so the kernel step no
longer includes the projection build. `end_to_end_seconds` still spans
everything from input handles to the written result.

Verified so far: `cargo check --tests` of the extension and vendored crates
passes; the harness test suite on the untouched tip passes (68). The new
sampler and cell code has no tests yet. Not done: the cit-Patents and
Graph500-24 importers, the `--ulimit nofile` container option, summarizer
columns, documentation.

Note for the reviewer: the vendored Nutmeg copy under the fork has diverged
from `~/src/nutmeg` (it carries the optimized kernels and traversal work), so
this patch edits the vendored copy; the same change should be ported to
`~/src/nutmeg` when the two are reconciled.
