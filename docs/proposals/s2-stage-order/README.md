# S2, first step: the Spark client chooses Nutmeg's staging order, for review

Prepared on the fork branch `work/s2-stage-order` of `querygraph/sail`
(commit `80a750067` on `work/s0-tiered-accounting` at `7f00735ad`); the patch
here is the reviewable copy. It touches only `examples/extensions/` (the
Nutmeg extension, its Python client and the benchmark harness), so under
`AGENTS.md` "Sail Discipline" it is fork work, not an upstream change.

## Why

The vendored `nutmeg-graph` library stages a part either `canonical` (every
row sorted, with the sort's permutation, keys and sorted copy admitted from
the memory budget first) or `asStaged` (arrival order, no sort), and its
refusal message ends with "stage with `order` = `asStaged` to skip the sort".
The Sail extension hard-coded `StageOrder::Canonical` in `mutation.rs`, and
its request schema is `deny_unknown_fields`, so no Spark client could follow
that advice. On Graph500 scale 25 (536,870,912 edges) the canonical sort's
admitted working space came to 404 GB against the 80 GiB quota: 8.6 GB of
permutation, about 396 GB of sort keys at the `admission.rs` bound (16 times
the key buffers plus 128 bytes per row per key column) and 141 GB for the
sorted copy. Every native cell at scale 24 and 25 was refused in 65–92 s.
This is the same refusal Sem hit with `pagerankDelta`.

## The change (`0001-stage-order-passthrough.patch`)

- `nutmeg/src/lib.rs`: `Request.order` (optional), parsed with
  `StageOrder::parse` for `stage`; every other verb rejects it.
- `nutmeg/src/mutation.rs`: `Operation::Stage` carries the order to
  `registry.replacing`.
- `python/sail_nutmeg/client.py`: `Nutmeg.stage(..., order=None)` sends the
  option only when given, so a server without it still accepts the default.
- `benchmarks/graph_cell.py --stage-order {canonical,asStaged}` (default
  canonical, not sent), `traversal_cell.py`, and a suite-level `stage_order`
  in `run_matrix.py`.
- Tests: `asStaged` reports no sort tiers and `edgeSorted = false`; the
  default still sorts; a misspelled or misplaced `order` is a plan error. 48
  extension tests and 196 harness tests pass (on Capitola, arm64).
- `nutmeg/README.md` documents the client option.

## What it does not do

It does not change the default, tighten the sort-key bound, or make kernels
declare whether they read order; those are the rest of S2 in
`FABLE-ON-ASTRA.md`. BFS and SSSP build their CSR from the staged rows and
do not read the row order, so `asStaged` is the right setting for the
capacity cells; the `capacity-*-asstaged` suites of `gn-capacity-ac000b6e.json`
on morrobay measure exactly that at scale 24 and 25.
