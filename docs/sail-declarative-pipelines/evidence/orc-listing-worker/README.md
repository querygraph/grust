# Partition directory bindings and ORC worker transport

Two independent Sail commits pass exact detached gates:

| Commit | Scope | Library tests |
| --- | --- | ---: |
| `242134aae8` | Shared logical partition / physical directory bindings | 192 data-source |
| `5efdf40db8` | ORC worker codec and real decoded-source execution | 173 execution |

Both pass formatting and strict all-target/all-feature Clippy. The binding unit
retains chosen logical names but uses observed directory keys for layout
validation, file parsing, equality-prefix listing and remaining partition-filter
evaluation. Explicit selectors resolve through the selected field to the actual
directory key. Identity names, both selector-alias directions, equality and
non-equality filters, empty results, exact ObjectMeta preservation and invalid
mapping counts are tested. Logical filters are rewritten once, including swapped
names. Default schema-selection policy is unchanged: omitted directory fields,
case-sensitive field classification, inferred types and mixed directory casing
still require shared follow-up units.

Two prior binding candidates are retained. The first failed test compilation on
the old ExecutionPlan downcast API. The second passed 191 tests and failed one:
the test's col("PART") lowercased the identifier, so it did not reference the
logical PART field. Column::from_name corrects the fixture while preserving the
Exact-pruning assertion. Independent review also identified and fixed an explicit
partition selector regression, adding both selector/schema alias directions.

The codec adds node68 and reuses field67 immutable file identity. It carries
configured limits with explicit presence, captured timezone/profile identity,
display zone, case policy, full schema/projection and checkpoint partitioning.
Workers validate the descriptor and use their own memory pool. Ten new tests
cover wire failures/roundtrips and actual retained TIME, interval and timestamp
files, replaced or identityless objects, invalid ranges before GET, both pool
rebinding directions and drop-time reservation release. An additional 32-bit
width-overflow test exists but was not executed on this 64-bit host.

[The frozen codec handoff](codec-handoff/HANDOFF.md) retains wire scope and
remaining task-preparation checks. General scan-limit narrowing and omitted
opaque extensions remain explicit transport limits. Separately decoded worker
file groups, later preparation's partitioning preservation, public format
registration, semantic inference and writing are still separate work. No CLI,
public SDP, streaming/Iggy or CDC runtime count is added.
