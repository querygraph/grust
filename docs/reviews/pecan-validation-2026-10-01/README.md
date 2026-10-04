# Typed Pecan integration and qualification evidence

This merge integrates the typed Pecan rewrite into the newer Sail fork
history. Graph validity is a caller contract: unique non-null BIGINT vertices,
valid endpoints and traversal source, and finite nonnegative DOUBLE weights with
finite path sums. Algorithms do not issue jobs to verify these properties.
Pydantic models check argument domains once; schema checks remain. The merge
preserves owned snapshots, checkpoint writes, cancellation and convergence
behavior while removing data-audit queries and unnecessary eager vertex counts.
The candidate and exact-commit gates passed. On one exact four-vertex DeltaStar control,
count calls fell from 12 to 0 and forwarded ExecutePlan calls from 49 to 37;
answers and three iterations matched. Merge commit [`6ae2e43a`](https://github.com/querygraph/sail/commit/6ae2e43a903c2cee02da170465c922c72b76198e)
is published on both fork branches below. This report makes no new timing,
memory, scale or cluster claim.

## Delivered source and qualification

| Item | Identity or status |
|---|---|
| Newer Sail base | `cab6bacc0ad0d1fc8b3070e9e4267e99751909fe` |
| Typed rewrite being integrated | `7145d107c772a98ce7c65637864c15eb21aee962` |
| Typed rewrite's parent | `837a8ecf5c2c3b8ad24e044c72c1cb69d9fc71f4` |
| Integration branches | `work/pecan-typed-integrated` and `work/stream-review-followup` |
| Authoring checkout | `/private/tmp/sail-pecan-typed-integrated` |
| Combined frozen tree | `4dc43a40ba4cea57deb69923e231e96a16b812b6` |
| Conditional merge commit | `6ae2e43a903c2cee02da170465c922c72b76198e` |
| Successful combined candidate gate | **PASS**: [receipt](typed-candidate-gate/receipt.json) |
| Exact-SHA gate | **PASS**: [receipt](typed-exact-gate/receipt.json) |
| Independent source review | No blocker found in typed options, optional N, WCC empty behavior or lifecycle ordering |
| Actual baseline / integrated action counts | **PASS**: [comparison](typed-candidate-gate/action-comparison.json) |
| Fork delivery | Both refs verified at the merge SHA: [receipt](sail-delivery.json) |

The rewrite starts from an older ancestor. Integration retains intervening host,
allocation, ownership, certificate and harness changes; a pass for either
component alone does not qualify their combination. The merge has both listed
source commits as parents. Its tree matches the tested staged candidate; the
candidate receipt names that tree and base HEAD, not an exact-commit verdict.

## Integrated behavior

There is no algorithm validation-policy flag. Invalid graph data has undefined
results, rather than a promised diagnostic. A caller needing graph validation
must use a separate explicit utility outside the algorithm's timer. Benchmark
output certification remains a separate concern from input preconditions.

Public and private package definitions have type annotations. Pydantic models
validate options, and typed records replace unstructured algorithm events.
Imports resolve at module scope through shared contracts; the public
`ConvergenceError` alias and module identity remain available.

`StagingRun.materialize(frame)` retains writes, schema comparison, cancellation,
owned paths and uncertain-write cleanup semantics. It has no expected-row or
row-audit option. `repartition_checkpoints=True` remains the default; disabling
it omits the keyless repartition without promising keyed distribution or a
fixed output-file count.

All three traversal implementations seed from `spark.range(1)` and typed
literals. BIGINT source/parent values are preserved at both signed extremes;
seeding needs neither a vertex scan nor local Arrow/configuration discovery.
Reference/frontier traversal and DeltaStar omit eager N. Push/pull BFS retains
N for direction switching; PageRank retains normalization counts. WCC omits
eager N, while preserving the algorithm's empty-result/contraction/convergence
operations. A bounded logical result does not promise bounded physical scanning.

Finite path sums are part of the contract. Weighted relaxations no longer
aggregate or query overflow evidence. They retain one expansion relation,
lexicographic distance/hops/parent selection, and the frontier on the left of
expansion joins. Algorithmic progress and convergence operations remain.

Grenada's relational entry path uses the same Pecan controller. Argentea client
adapters are reconciled with its typed signatures; this does not constitute a
new native-kernel or worker qualification. Historical results retain their
original source/runtime identities, including the scale-24 observation with
controller `3a9028057` and compact runtime `56194b170`.

## New gate and action-control scope

[run_typed_gate.py](run_typed_gate.py) checks the complete frozen source/index,
strict mypy, inherited Ruff rules and package annotation/import structure. It
collects all Pecan, Argentea-client and benchmark tests, verifies exact JUnit
identities, and runs live modules in fresh pytest processes. Required external
generator/control-binary skips remain explicit. The combined candidate collected
1,409 tests: 1,196 passed offline and 213 had declared skips. All 286 cases in
18 endpoint-configured modules passed with no skips, failures or errors:
183 cases use the Spark fixture; the other 103 repeat offline checks. Thus
1,379 distinct cases passed, with 30 external-generator/control-binary cases
left explicitly skipped. Strict mypy, Ruff and
source/runtime/client guards passed; all owned command/server groups were
absent after cleanup. The exact-commit gate repeated these counts and the
action comparison: [exact action receipt](typed-exact-gate/action-comparison.json).
Its verdict is:

```text
PECAN_TYPED_GATE PASS mode=exact head=6ae2e43a903c2cee02da170465c922c72b76198e tree=4dc43a40ba4cea57deb69923e231e96a16b812b6
```

The local CLI is the existing `a3462345a6764096024c055dc4d105a3c634e5a4`
build, SHA256
`4b976fd7a809cb059c72a2119293f490105ff0ed375feaf0ccb5f3e5dad88662`.
The gate requires matching host sources and separately pins candidate Python.
It uses CPython 3.12.8 / PySpark 4.0.1, two threads and a 2 GiB Sail pool.
Client source directories precede installed packages; the server sees only the
pinned client site-packages. Tool origins/versions are checked: Pydantic
2.11.10, mypy 2.3.1 and Ruff 0.16.9. No Rust rebuild is part of this gate.

[typed_action_probe.py](typed_action_probe.py) compares unchanged `cab6bacc`
and the integrated package using fresh clients on the same pinned local server.
Both must produce the same complete four-vertex DeltaStar oracle, including an
isolate and parent tie, with identical iterations. It records count callsites
and forwarded ExecutePlan requests, excluding setup, oracle and cleanup. The
baseline inventory includes input/cardinality/source/weight checks and one
remaining overflow check per expansion; the integrated fixture must issue zero
algorithm count calls. The request difference must be explained by the removed
counts. The candidate [baseline receipt](typed-candidate-gate/action-baseline/receipt.json)
and [integrated receipt](typed-candidate-gate/action-candidate/receipt.json) passed
that exact oracle and both completed three iterations:

| Count-call category | Baseline `cab6bacc` | Integrated candidate |
|---|---:|---:|
| Input graph checks | 5 | 0 |
| Vertex cardinality N | 1 | 0 |
| Source membership | 1 | 0 |
| Weight domain | 1 | 0 |
| Per-expansion overflow | 3 | 0 |
| Post-write vertex cardinality | 1 | 0 |
| **Total count calls** | **12** | **0** |
| **Forwarded ExecutePlan calls** | **49** | **37** |

The 12 fewer forwarded requests are accounted for by the 12 removed count
calls. This is one valid fixture within the public SSSP-call boundary, excluding
setup, exact-oracle collection and cleanup. It measures neither scanned bytes,
Spark jobs nor elapsed time, and is not a large-graph performance claim.

Prepared helper identities:

- Gate: `b6238fce62032d4d8e55f6712b6507b77434da36505109080e0e4142cdaf4758`.
- Probe: `709b97de4351c6a7adaf5e2c8798075de9212bca306f3939ba3318c6302b940b`.
- [Offline helper controls](typed-helper-controls/receipt.json) passed origin,
  parser, typed-AST and synthetic comparison/refutation controls. These do
  **not themselves** establish an actual action reduction; that comes from the
  candidate receipts above. The initial control-script
  [syntax failure](typed-helper-controls/attempt01.log) is retained.

## Retained history: superseded candidate, not combined qualification

The earlier optional-validation proposal was superseded by this integration.
[run_gate.py](run_gate.py) and [action_probe.py](action_probe.py) are historical
helpers. Their presence is not an action-probe result or a combined-source pass.

1. [Attempt 01](candidate-gate/receipt.json) failed two manifest tests because
   installed Nutmeg preceded candidate source; 1,225 passed and 228 skipped.
   The [environment control](env-control/receipt.json) rejects that old import
   origin and records both unchanged tests passing with source-first imports.
2. [Attempt 02](candidate-gate-02/receipt.json) recorded 1,237 passed and 236
   skipped, then failed the gate's JUnit identity check before SQL. A `::` inside
   a parameter was parsed as a class suffix. The
   [inventory control](env-control/inventory-control-receipt.json) matches all
   1,473 recorded cases and still rejects missing, duplicate or altered cases.
3. [Attempt 03](candidate-gate-03/receipt.json) passed 110 cases in four live
   certificate/metadata modules. Eight graph-fixture cases then failed before
   an algorithm ran: the server could not import PySpark and used Spark 3.5
   configuration defaults. This is an environment failure, not a graph result.

The [configuration control](config-control/receipt.json) reproduces that third
failure with unchanged `cab6bacc` fixtures. Restoring only installed client
site-packages makes the server report PySpark 4.0.1 and supplies all nine
requested defaults, including the two previously missing keys. Original
nonempty fixtures then create and return exact rows. No configuration values,
fixture assertions or host code were changed. Original failed receipts and logs
remain intact; narrower controls do not turn those gates into passes.

The frozen candidate gate, conditional merge commit, exact-SHA gate and fork
delivery are complete. Local SQL qualification leaves native extension,
process-cluster/Flight, scale and performance claims outside scope. The next
large-graph measurement must identify this controller separately from the
historical scale-24 controller and retain independent output certification.
