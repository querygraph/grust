# Standalone native scalar adapter: component evidence

The standalone adapter now preserves complete argument fields and retains callback
code after its functions are dropped. Focused tests and an independently compiled
Comet SDK producer passed. This is component evidence for an uncommitted candidate;
final cumulative source review and immutable qualification remain pending.

## Behavior under test

The adapter uses Comet’s pinned Arrow C scalar layout. It requires an explicit
immutable declaration and an unsafe caller contract for trusted, well-formed,
non-unwinding producers. Other declared volatility is refused before loading.
The declaration does not prove purity or make arbitrary native code safe.

Library code remains loaded for the process lifetime, including opened libraries
later refused by discovery. Kernel instances and session state are not retained
in that code registry. Each opening consumes retained resources; bounded package
admission and content identity remain integration work.

Planning and execution use actual DataFusion argument fields. Execution checks
argument counts, types and lengths, then checks its initialized return field against
planning before importing results. Top-level return names are ignored according
to DataFusion’s contract. Types, nested fields and metadata must agree; safe
nullability widening is permitted.

## Checks and controls

| Check | Result |
| --- | --- |
| Original adapter with retained loader API, metadata suite | Six failed, two passed |
| Original adapter with code retention disabled | Deterministic result-lifetime test failed |
| Repaired adapter with Sail-owned fixture | Thirteen tests passed |
| Pinned Comet SDK producer | Two interoperability probes passed |
| Affected crates | Strict all-target/all-feature Clippy and formatting passed |

The metadata tests include actual DataFusion expression execution, direct invocation,
literal expansion, representative sliced/nonempty nested data and empty arrays
across Arrow families. The lifetime control checks the same library handle without
calling into unloaded code. The repaired case reads, slices and drops results
after dropping function/library owners.

The independent producer uses unchanged SDK and test-library sources and member
manifests from Comet commit `0f7f8e45399847715093b3d3affdfa97614b39dc`.
An isolated minimal workspace supplies inherited package fields and Arrow dependencies;
this is not a build of the complete Comet workspace. Tests exercised discovery,
ordinary results, nulls, argument order, retained output and SDK containment of
initialization/execution panics.

## Qualification boundary

The candidate extends foundation commit `2c9fa8499` in a separate detached worktree.
The [evidence record](evidence/comet-scalar-1/README.md) identifies the staged tree,
patch hashes, exact controls, commands, source receipts and retained artifacts.
The [adapter plan](COMET-SCALAR-ADAPTER.md) states its design contract.

No package-loader bridge, Spark SQL endpoint, worker loading, cross-version ABI
matrix or production performance envelope is established here. Existing Extensions
still need integration with the StreamSource runtime. Marker isolation, replay
identity, prepared output and enforced target fencing remain prerequisites for
durable pipeline use.
