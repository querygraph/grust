# A2 run04 admission and compatibility

Observed 2026-10-01T22:57:52.091505+00:00, on Morrobay's shared gate VM. This is correctness and
preparation evidence; no timing ratio is concluded here.

- Pecan source: `f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a` (B9/B10).
- Exact helper commit: `c68b3162f9d65c2701a384f9f493e5925550fe18`.
- Same A1 image and external binary; 16 CPUs / 32 GiB / no swap.
- Staging, full input validation, and compatibility finalized with certain
  owned-container closure/removal and released queue locks.
- Original input hashes were preserved before/after every phase.

## Input and source

Full declared domain: 3,774,768 unique vertices, 16,518,947 directed edges,
zero isolates. Source `750000` is absent. Both engines now explicitly use
`5795784`, selected outside timing by maximum outgoing edge-row count,
ties by minimum original ID (770 outgoing rows). This does not reproduce
Sem's historical landmark. The full independent BFS reference has 126,298
reachable vertices, 3,648,470 unreachable, maximum finite distance 13.
Every edge was examined for the triangle certificate; every reached
non-source vertex has a predecessor witness.

Portable full references remain on Apo and in the gate volume, indexed by
SHA-256 and format in the archive manifest: ascending IDs and full hop
distances as signed 64-bit little-endian arrays, unreachable = -1. The
existing WCC reference is independent union-find membership.

## Five ordinary controls passed

Official test-wcc-directed: graphframes, Pecan randomized, Pecan min_label.
Official test-bfs-directed: graphframes and Pecan frontier. Exact named
column types, complete vertex coverage, raw physical output and official
references were checked after engine exit. Graphframes' physical BFS
column order is preserved; the adapter resolves the exact columns by name.

## B9 signed-isolate mismatch confirmed

Valid vertices: `1`, `2`, `-7694170072594669674`; edge `1 -> 2`.
With seed 42 and canonical labels, expected components are
`{1: 1, 2: 1, -7694170072594669674: -7694170072594669674}`.
Actual raw output assigns all three to `-7694170072594669674`.
This is the predicted collision between an affine representative and an
isolated original ID. Engine exit and lifecycle cleanup passed, but the
answer did not. It is recorded as `known_mismatch`, not a correctness pass.
Generic signed-ID WCC is unqualified.

The accepted scope is only the admitted cit-Patents input with verified
zero isolates and a complete physical oracle in every full cell. A2 then
A3 continue under that scope; the mismatch is retained separately.

## Evidence

`run04-preflight.tar.gz` preserves all three phase receipts/orchestration,
small raw outputs, and tiny references. `run04-preflight-index.json` lists
every archive member's bytes/SHA-256, external full references and source
pins. Full archive: `/Volumes/Apo/graph-tests/results/sem-review-20261001/A2-run04`.

PageRank remains not comparable pending a matching finite-step or stopping
contract with graphframes' delta method; static Pregel and current delta
recurrences do not match merely by normalizing final ranks.
