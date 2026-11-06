# Standalone native scalar adapter: component evidence

The standalone adapter now preserves complete argument fields and retains callback
code after its functions are dropped. Focused tests and an independently compiled
Comet SDK producer passed. Seven specialty source reviews and immutable workspace
qualification passed on local commit `06dd7e237`, on branch
`work/streamsource-comet-scalar-20261105`. This qualifies the standalone component;
package and worker integration remain separate increments.

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
| Repaired adapter with Sail-owned fixture | Seventeen tests passed |
| Pinned Comet SDK producer | Two interoperability probes passed |
| Full workspace on the immutable commit | 2,034 tests passed; one pre-existing ignored test remained skipped |
| Selected Python checks | Ten live tests against the fresh server and nine client fixtures passed |
| Lint and documentation | Strict workspace Clippy across all targets/features, formatting and strict adapter Rustdoc passed |

The seventeen adapter tests are included in the workspace count, not additional
unique tests. The Python checks preserve foundation behavior; they do not invoke
a package-registered C function through Spark SQL.

The metadata tests include actual DataFusion expression execution, direct invocation,
literal expansion, representative sliced/nonempty nested data and empty arrays
across Arrow families. The lifetime control checks the same library handle without
calling into unloaded code. The repaired case reads, slices and drops results
after dropping function/library owners.

Additional controls remove only planned-field agreement, restore the old nonempty
signature, or replace logical checks with physical validity; each fails its targeted
test. Arrow's own logical-null helper also failed a nonzero single-child union
control. The adapter now uses a recursive null-presence predicate over public typed
APIs, covering nested dictionary/run-end/union values and valid slices. A million-row
run fixture retains two physical values. Source inspection establishes that the
guard avoids a logical-row null bitmap; no allocation or throughput benchmark ran.
The [nullability plan](COMET-SCALAR-NULLABILITY.md) explains this contract and cost.

The independent producer uses unchanged SDK and test-library sources and member
manifests from Comet commit `0f7f8e45399847715093b3d3affdfa97614b39dc`.
An isolated minimal workspace supplies inherited package fields and Arrow dependencies;
this is not a build of the complete Comet workspace. Tests exercised discovery,
ordinary results, nulls, argument order, retained output and SDK containment of
initialization/execution panics.

## Qualification boundary

The implementation extends foundation commit `2c9fa8499` in a separate detached
worktree. The checked commit and source stayed unchanged throughout qualification.
The [evidence record](evidence/comet-scalar-1/README.md) identifies the exact tree,
patch hashes, exact controls, commands, source receipts and retained artifacts.
The [adapter plan](COMET-SCALAR-ADAPTER.md) states its design contract.

To inspect the internal utility contract by hand on that branch, build its explicit
test libraries, then run its tests:

```sh
cargo +1.98.1 build --locked -p sail-c-udf-fixture --lib --examples
cargo +1.98.1 test --locked -p sail-c-udf --tests
```

No package-loader bridge, Spark SQL endpoint, worker loading, cross-version ABI
matrix or production performance envelope is established here. Existing Extensions
still need integration with the StreamSource runtime. Marker isolation, replay
identity, prepared output and enforced target fencing remain prerequisites for
durable pipeline use.
