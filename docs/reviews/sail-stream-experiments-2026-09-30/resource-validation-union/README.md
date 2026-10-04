# Combined resource and validation gate

This combines three separately reviewed Sail fork changes on
`work/stream-review-followup`: Argentea owned-input lifetime `7f5b80d0`,
PageRank metadata validation `7df2f32f`, and Parquet floating-statistics handling
`837e8e82`. The common base is `200d1cf8`; the combined source tree is
`d43293b4e5de64878c85c1d3d756077e2b7b749b`.

The integration is committed and pushed as `a3462345a6764096024c055dc4d105a3c634e5a4`.
Its separate exact gate reports
`RESOURCE_VALIDATION_UNION_GATE PASS a3462345a6764096024c055dc4d105a3c634e5a4 exact commit`.
[Exact gate](exact-gate/receipt.json), [independent audit](independent-exact-review.json),
and [delivery](../resource-validation-union-delivery.json) are recorded separately.
[Source preparation](source-preparation.json) and the
[independent source review](independent-preparation-review.json) bind the exact
component subtrees and unchanged surrounding source. The implementation and
detached gate have separate checkouts; the gate uses private target directories.

## Changes and boundaries

- Argentea releases raw BFS/SSSP vectors and their admission after CSR creation,
  before allocating initial partition state. The component controls measure
  lower requested-heap peaks; simultaneous raw/CSR construction still remains.
- Both PageRank validation policies now reject inconsistent or null iteration
  and convergence metadata. Reference row checks use one aggregate. Full
  reference and fixed-point verification remain separate policies.
- The Parquet reader clears floating file bounds before caching and aggregation,
  preventing the reproduced statistics-dependent replacement of NaN with a
  finite value. Counts and integer bounds remain usable. This sacrifices
  floating-bound optimizations, including on finite files; the cost is not yet
  measured. Other reader paths and raw footer pruning remain outside scope.

The gate requires 77 data-source tests, 120 Argentea core tests and 51 native
tests, with 45 Argentea tests registered in the native executable. Core/native
release suites also run with every local core saturated. Host and core changes
receive formatting and strict Clippy checks; native formatting is scoped to the
changed files because the inherited full native formatting check fails.

A freshly built local Sail CLI must pass 333 benchmark unit tests (97 explicit
integration skips), 58 local SQL tests without skips, and a separate actual
Parquet control with statistics collection enabled. That control must preserve
physical NaN and reject it under both PageRank policies, while a finite fixed
point passes. The installed old Sail binary cannot substitute for this CLI.

This is a local source/runtime gate. It does not rebuild and load the combined
native extension in distributed workers, qualify Linux/Flight execution, measure
performance, or establish multi-host scaling. The large compact replay uses its
separately pinned older controller/native runtime and host binary.

## Retained failed attempts

The [first gate](candidate-gate/receipt.json) completed all 51 native tests, but
its line-oriented parser counted only 42 of the 45 Argentea test names because
concurrent receipt output interrupted three status lines. It failed and made no
commit. The corrected driver binds a separate complete test registry to the
same executable and requires all 51 tests to pass with none ignored or filtered.
[Independent correction review](independent-registry-review.json).

The [second gate](candidate-gate02/receipt.json) passed the host, core/native
ordinary and saturated checks, and CLI build. Its Python unit step failed two
generator fixtures before starting the SQL server. The fixture shebang selected
Python 3.14 while inheriting Python 3.12's library path. A same-script control
changing only PATH restored the expected 192 output bytes and exit status 7.
[Reproduction](sql-helper-controls/attempt-failed02/path-control.json).
The implementation and assertions are unchanged; this failure also made no
commit. All original drivers, logs and failure receipts are retained.

The third candidate and exact-commit gates both pass the complete inventory above.
Their fresh CLI is pinned by SHA-256; the statistics-enabled NaN control preserves
NaN and both policies reject it. The finite two-vertex fixed point passes both
policies with zero residual. All ten saturation processes and the local SQL
server are reaped. Evidence integrity, benchmark correctness, and performance
qualification remain separate.
