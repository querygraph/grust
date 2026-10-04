# PageRank validation metadata parity

Recorded UTC: 2026-09-30T23:15:26.638121+00:00

Repository `querygraph/sail`, branch `work/pagerank-certificate-metadata`,
commit `7df2f32f070e041eed5416eb44f7ff8fa4ce0d01` is pushed and remotely verified.
[Delivery](delivery.json), [exact gate](exact-gate/receipt.json), and
[independent review](independent-candidate02-review.json).

## Reproduced gap and change

The unchanged `200d1cf8` harness accepts five malformed cases under PageRank's
certificate policy that its reference policy rejects: one null convergence
flag, one null iteration count, negative iterations, iterations beyond the cap,
and different iteration counts across vertices. Both scores are exactly 0.5 on
a two-vertex cycle, so the fixed-point vector itself is valid. SQL `min` and
`max` ignore null values; they cannot establish that every metadata row is valid.
[Original observations](baseline/receipt.json) retain all sixteen policy/case
outcomes, including valid, nonconverged and wrong-score controls.

A shared row-validation helper now checks scores and metadata before nullable
reductions in both policies. The certificate path also requires consistent
iteration and residual values and the declared residual bound. The
nonconvergence decision still precedes the converged residual bound, preserving
`nonconverged` for an exhausted run with a finite large residual. Optimized zero
iterations and the existing optional baseline residual convention remain valid.
Vertex coverage, reference comparison and independent fixed-point proofs remain.

One aggregate replaces the reference path's two invalid-row scans (three for
native/optimized outputs). The certificate retains one such scan with the
additional checks included. These are source-level action counts; no validation
wall-time or whole-algorithm speedup was measured.

The detached candidate and exact-commit gates each pass **333 benchmark tests**
with **97 integration skips**, then **52 PageRank and 6 WCC actual SQL tests**
with no skips. The SQL server is the pinned installed macOS Sail 0.7.0 runtime,
not a newly built candidate runtime or distributed qualification. Tests cover
all-row null/bound checks, mixed iterations/residuals, required residual
finiteness, invalid scores, the separate cap outcome, valid optional/zero
metadata and rejection of an incorrect score vector. No Rust runtime changed.

## Separate statistics-dependent NaN substitution

The first SQL gate failed two NaN-score cases. A direct read control on the
unchanged harness showed why: PyArrow reads `[NaN, 0.5]` from the written Parquet
file, while this installed Sail runtime reads `[0.5, 0.5]` and reports neither
value as NaN. Both old verification policies then accept the substituted fixed
point. The original bytes and fixtures are retained privately with their paths
in the receipts; all control source and observations are retained here.

Two controls isolate the statistics dependency:

- [Default statistics](baseline-nan/receipt.json): the NaN is substituted.
- [Output statistics omitted](baseline-nan-no-statistics/receipt.json): Sail
  returns NaN and both unchanged validators reject it.
- [Reader statistics collection disabled](baseline-nan-no-collection/receipt.json):
  the original statistics-bearing file also returns NaN and is rejected.

The validator regression fixtures therefore omit output statistics and directly
check NaN readback before invoking validation. Their rejection assertions were
retained. This qualifies the Python checks on intact values; it does **not** fix
or qualify the production reader. The ordinary production read configuration is
unchanged by this metadata commit. A separate Sail Parquet mitigation is under
review. These controls do not establish corrupted historical results or a
stream-loss cause.

[The original failed gate](candidate-gate/failure-recovery.json) retains both
SQL failures and its logs/XML. Its system Python 3.14 driver also failed while
loading `pyexpat` to finalize its receipt; the tests themselves used the pinned
Python 3.12 environment. The passing driver uses that same 3.12 environment,
records its identity, and fails closed on receipt parsing or missing SQL test
coverage. [Candidate02](candidate02-gate/receipt.json) is distinct from the
failed first candidate; no failure was overwritten.
