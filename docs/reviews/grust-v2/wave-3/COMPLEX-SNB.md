# Complex SNB query and synthetic scale qualification

This extends the integrated draft resolver with unchanged official LDBC SNB
Interactive v1 IC2, IC8 and IC9. Independent answers come from the pinned CSV
fixture through `live/snb_complex.py`; no SQL plan supplies expected answers.
The five previously qualified short queries remain in the gate.

## Added semantics

- Nonoptional all-path MATCH may apply a WHERE filter after a ranged or named
  path. OPTIONAL/selected ranged paths retain an explicit capability refusal
  until their different predicate placement contract is implemented.
- Entity equality compares graph, kind, group and identity, with null propagation.
  It does not compare projected property payloads or require identical inherited
  property schemas.
- Function metadata can declare `ListArgument(i)`: a list of the argument type.
  Declared graph-value provenance survives collection, alias projection and
  UNWIND, so a collected entity can be bound in a subsequent MATCH. Arbitrary
  user structs do not become graph entities by resembling the wire shape.
- The Sail provider maps the registered collection to `collect_list`, preserves
  DISTINCT and duplicate semantics, and qualifies empty/null collection results.

These changes live only in the nonpublished Wave 2/3 draft workspaces. Production
parser/API crates are unchanged. IC9 combines ranged friendship, identity
exclusion, distinct entity collection, UNWIND/rematch, date filtering, hidden
ORDER BY expressions and a bounded final result.

## Protocol

Official query files are used byte for byte at SNB implementation commit
`f9c394a92cd55e535893f6c9907b141d6533c817`. Fifteen complex parameter bindings
cover productive and absent persons, empty date intervals, and equality
boundaries for IC2's `<=` and IC9's `<`. Query bytes, parameter bindings,
ordered rows and the statistics dataset identity are checked independently
before running either plan.

Resolved and optimized plans receive a warmup each, then ABBA twice, giving
four measured cells per variant. Native macOS release Sail performs the SQL,
scans, materialization/traversal, final collection and cleanup. CSV preparation,
Parquet conversion and compilation stay outside that boundary. Shared-host
reports publish ratios rather than absolute timings; all outcomes remain in
receipts. Estimates and rewrite traces are preserved for every admitted binding.

## Larger-input control

The optional gate scales are **10 and 100 disjoint replicas** of the official
development fixture. These are synthetic controls, not official LDBC scale
factors or an audited LDBC benchmark. Each replica adds a checked Int64 identity
offset to all vertices, edge identities and endpoints. Property values and dates
remain unchanged. The first replica therefore has the original exact answers,
while unrelated data increases scans, joins, statistics and working-set pressure.

The transformation and its exact NDV formulas have separate independent tests.
No runtime graph validation is introduced. Larger-input source/metadata digests
are distinct from the base CSV digest. Peak sampled server RSS is qualified
separately from paired timing runs and is not presented as an OS memory limit.
The managed Sail pool, returned result caps and refused/errors remain distinct
from sampled native-process resident memory.

## Gate and evidence

The full detached integration gate includes production parser controls, Wave 2
and Wave 3 checks, all existing native relational/frontend/semantics tests,
short and complex official-query oracles, and requested synthetic scales.
The detached full gate **PASSED** at source
`b2d5d8b1f3866272bc637fb76e544f35c2c3321c`, with unchanged HEAD and clean
working tree. [Preserved gate log](complex-evidence/source-gate.log) records
the complete command sequence and verdict. Native Sail is the optimized macOS
binary at `9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3` (SHA-256
`ee80ac3cf9d028639561f3cf32435985192719d629807fcf6a368324fa84946e`).

The native gate exercised 868 query cells: 860 returned passes and eight
expected arithmetic errors. This includes 130 short-query cells and 150 complex
cells at each of base, 10× and 100×. All requested exact ordered oracles passed.
The 18 explicit capability refusals remain recorded separately.

| Input | Vertices | Edges | Optimized / resolved median ratio range |
|---|---:|---:|---:|
| Base | 10,629 | 18,136 | 0.912–0.985 |
| 10× | 106,290 | 181,360 | 0.920–1.012 |
| 100× | 1,062,900 | 1,813,600 | 0.927–1.554 |

Ratios above one mean the optimized plan was slower. The largest three 100×
ratios were IC8/person 8796093022220 (1.554), IC8/person 2199023255711
(1.373), and IC2/person 8796093022220 with the maximum date (1.305).
These shared-host results establish neither a universal speedup nor a cause
for the slower cells. Per-binding ratios, all outcomes and content-addressed
SQL programs are in [the evidence directory](complex-evidence/).
The short-query ratio range was 0.854–1.016.

IC2 and IC8 have known metadata estimates; IC9 retains an unknown total cost.
Unknown is not converted to zero. Cost estimates are abstract optimizer inputs,
not calibrated elapsed-time predictions. Rewrite traces retain the decision
made for each binding.

A separate 100× memory run passed six productive IC2/IC8/IC9 cells, covering
both variants. Its 200 ms sampler observed 464,691,200 bytes (443.16 MiB)
maximum Sail-server RSS over 14 samples. This is a sampled maximum, not a
continuous peak or an OS memory limit. It includes native allocations outside
the 256 MiB managed pool and excludes preparation, the Python harness and
browser. [Memory receipt](complex-evidence/memory-100/receipt.json).

Receipts remove absolute elapsed and compilation times for shared-host
publication; measured cells retain ratios to their binding's resolved median.
Raw receipts, full plans and development failures are retained on Apo under
`/Volumes/Apo/graph-tests/workspaces/grust-v2-complex-20261008/`.
Development compilation failures around collected graph-value UNWIND were
fixed before the detached source gate; they are not represented as passing runs.

## Consolidated progress

1. [Combined PR integration](../INTEGRATION.md): production parser and both
   draft workspaces passed together; PRs #40–46 are integrated.
2. Complex query resolution now qualifies unchanged IC2, IC8 and IC9 with
   independent CSV answers and typed collection/entity semantics above.
3. Paired execution, cost traces, synthetic larger inputs and a separate RSS
   control are preserved here, including slower and unknown-cost cases.
4. [Cosmolang live slice](https://github.com/querygraph/grust/blob/work/cosmolang-live/docs/reviews/sem-research-2026-10-03/visualization/cosmolang/live/README.md)
   connects the actual Cosmograph SDK to a native Sail/Nutmeg gateway and MCP.
   It remains a bounded two-level prototype, not a billion-node deployment.

These results qualify the implemented subset. They do not claim full Cypher,
all SNB queries, distributed qualification, or an audited LDBC benchmark.
