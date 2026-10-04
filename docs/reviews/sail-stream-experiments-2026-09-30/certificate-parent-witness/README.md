# Parent/hop certificate witness

The Python certificate can prove rooted tight-edge reachability from validated
parent/hop output, avoiding its separate tight-edge BFS in those cases. The
certificate still checks every edge inequality and reports the same conservative
error bound. This changes validation work, not the graph algorithm or its rounds.

Source: `querygraph/sail`, branch `work/certificate-parent-witness`, commit
`cab6bacc0ad0d1fc8b3070e9e4267e99751909fe`, direct child of
`fc094a0c25a49edeac2f9f0195aa973421a21a43`, tree
`cd73d093230153857de196abc17ea8e98464149b`. The four changed files are pinned
in [frozen.json](frozen.json) and [candidate.patch](candidate.patch). Delivery is
outside this immutable component folder; this evidence closes before push.

## Acceptance and fallback

Integral non-null hops must decrease by exactly one along existing tight parent
edges to the unique zero-hop source. The proof uses the certificate's original
float tight-edge relation, including its explicit null guards. It also bounds
hops below the vertex count and at or below the supplied round cap. Unreachable
rows must retain null parent/hop metadata. A successful proof reports
`witness_method=parent_hops`, `witness_rounds=null`, and the observed maximum
parent depth. It does not invent a count of BFS rounds.

Missing, unsuitable or invalid parent fields, and parent depth above the cap,
fall back to the original tight-edge BFS. A parent tree deeper than the cap can
still have a shorter tight path, so it must not be rejected solely by this fast
proof. The original caller's stricter parent-output validator remains unchanged
and still runs after the certificate; the fast proof does not replace it.
Distance-only native output retains the original BFS behavior.

Both branches use the original Pecan partition and input-schema validators.
The initial implementation omitted those preconditions; all six refuting cases
were retained in [candidate-preconditions01](candidate-preconditions01/receipt.json),
against the passing unchanged baseline in
[baseline-preconditions01](baseline-preconditions01/receipt.json). The fixed
checks reject zero, boolean and non-integer partition counts, Int32 vertex/edge
IDs, and duplicate extra vertex-column names. Their corrected controls and
all-edge/BFS body preservation are reviewed in
[independent-source-review.json](independent-source-review.json).

## Gates and runtime boundary

The conditional original candidate gate passed before the commit, as recorded
in [commit-and-gate.log](commit-and-gate.log). Final candidate and exact checks
use [run_sql_gate.py](run_sql_gate.py) with a fresh client subprocess for each
unchanged SQL test module. Each gate requires 337 benchmark unit passes and
136 skips (473 collected), plus 71 server-configured cases: **67 actual SQL cases
and 4 pure argument-rejection cases**. Module inventories are 9, 43, 6, 6 and 7;
all must pass with no skips. Source/index/HEAD/tree and runtime/test-input hashes
are checked before and after. The owned local Sail server is stopped and reaped.

The final receipts are [candidate-gate02](candidate-gate02/receipt.json) and
[exact-gate02](exact-gate02/receipt.json). Tests cover weighted/unweighted graphs,
Int8/16/32/64 hops, zero cycles, unreachable vertices, null/missing/wrong parents,
invalid roots/hops, missing edges, strict parent tolerance, distance-only output,
cap fallback, schema/partition preconditions and an independent distance oracle.

The runtime is the existing guarded local debug CLI SHA
`4b976fd7a809cb059c72a2119293f490105ff0ed375feaf0ccb5f3e5dad88662`, pinned
CPython 3.12.8 and client environment, local builtin GraphUtils, two configured
threads and statistics collection enabled. Host crate/lock sources are unchanged
from the CLI's union source; [runtime-provenance.json](runtime-provenance.json)
records the precise comparison. No Rust build, Linux worker, Flight, production
replay, combined native extension, timing, RSS or cluster qualification is claimed.

## Every measured work cell

[work-comparison.json](work-comparison.json) retains all 14 raw cells and seven
matched pairs. Counters cover `certify` only: client ExecutePlan iterator
invocations, staging materializations and Pecan `_run` calls. They exclude input
setup, schema/config RPCs, the subsequent stricter parent validator, retries and
worker execution. They are not distributed job counts or elapsed time.

| Case | ExecutePlan iterator calls before → after | Materializations before → after | Pecan runs before → after |
|---|---:|---:|---:|
| Parent depth 0 | 30 → 18 | 3 → 0 | 1 → 0 |
| Parent depth 1 | 36 → 18 | 5 → 0 | 1 → 0 |
| Parent depth 2 | 43 → 18 | 7 → 0 | 1 → 0 |
| Parent depth 4 | 57 → 18 | 11 → 0 | 1 → 0 |
| Parent depth 8 | 85 → 18 | 19 → 0 | 1 → 0 |
| Distance only, depth 4 | 57 → 57 | 11 → 11 | 1 → 1 |
| Parent depth 2 above cap 1, tight BFS depth 1 | 36 → 37 | 5 → 5 | 1 → 1 |

The over-cap case adds one validation call. No performance or allocation claim
is extrapolated from these tiny local fixtures.

## Retained failed attempts and gate correction

- `baseline01`: the original createDataFrame fixture hit an unsupported Spark
  configuration lookup before certificate execution. Test input creation changed
  to PyArrow Parquet; the certificate assertions did not change.
- `baseline02`: builtin GraphUtils was not enabled. The gate now explicitly sets
  its required experimental flag and owned staging root.
- `baseline03`: all six SQL controls passed, but system Python 3.14 could not
  parse JUnit XML because its expat module was unavailable. The gate driver now
  requires pinned CPython 3.12.8. `baseline04` closes the unchanged six controls.
- `candidate-preconditions01`: six actual acceptance regressions in the first
  draft, corrected with the exact existing validators before the final commit.
- `exact-gate`: 337 unit passes; 39 SQL failures in the parent-witness module and
  32 other server-configured passes. The retained error is PySpark's
  `cannot schedule new futures after shutdown`. Source/runtime guards passed and
  the server was reaped. This is not an exact PASS.

The focused [lifecycle control](lifecycle-control01/receipt.json) shows that
finalizing a stopped old Spark session after creating a new one shuts the
process-global release executor. A previously selected submit then raises the
same error; a subsequent fresh query recreates the executor and succeeds. This
proves a cross-session lifetime hazard, **not the precise GC interleaving in the
failed gate**. The corrective gate isolates modules in fresh pytest processes,
without dependency monkeypatches, production edits, retries of individual tests
or weaker assertions. [gate-isolation-change.json](gate-isolation-change.json)
and [gate-isolation.patch](gate-isolation.patch) retain the change; the original
helper remains byte-exact as
[run_sql_gate-before-isolation.py](run_sql_gate-before-isolation.py). The original
`frozen.json` helper pin records that earlier helper intentionally.

This test-lifecycle evidence makes no claim about the older distributed stream
loss. All earlier candidate/work/precondition attempts remain available with
commands, receipts and original logs. Private generated Parquet fixtures stay
outside the published evidence; their observed outcomes remain here.
