# Comet scalar adapter test preparation

Prepared thirteen integration tests on the detached source worktree
`/Users/alexy/src/sail/tmp/comet-scalar-20261105-2c9fa8499`, based on
`2c9fa84994d317aade0d1c69faa9a378c780127d`. The original three P5 tests remain,
with the discovery expectation intentionally expanded for one new fixture kernel.
The ten additional tests are prepared, not yet qualified by this reviewer.
No build or test execution was performed. Targeted Rust formatting completed.

Read the complete saved request and AGENTS.md, LAKESAIL.md, SHEHAB.md,
WRITING-RULES.md and CLARITY.md. The committed E1, E3 and E4 decisions and
extension integration design precede this selected adapter increment.

## Independent fixture contract

`identity_field_c` requires argument metadata that independently states the
expected field name and nullability. It rejects absent metadata or a disagreement,
then returns the complete original field and argument array. The adapter cannot
satisfy this fixture by reconstructing a field from its array datatype alone.
The fixture also rejects a non-null reserved constant-argument pointer.

The tests first require successful field planning, then invoke the same kernel
with those fields. Original P5 invocation reconstructs empty names, nullable
fields and no metadata, so these cases should discriminate the metadata repair.
A missing-metadata negative fixture proves that the producer enforces the
contract instead of accepting every input.

## Prepared coverage

- Direct invocation and actual DataFusion execution preserve metadata, names and
  nullability. The DataFusion test also checks output values and metadata.
- Nonempty sliced nullable integers and strings, nested decimal structures with
  child metadata, and lists exercise data and offset preservation.
- Empty arrays cover every applicable Arrow type family, including all dictionary
  key widths and run-end index widths. This is empty-array coverage, not a claim
  that every nonempty Arrow representation has been qualified.
- Literal input expands into zero or multiple rows while initialization keeps the
  reserved constant-argument pointer null.
- Planned return-type, metadata and unsafe-nullability mismatches are refused;
  an output alias and safe nullable widening have a positive control.
- Stable and volatile declarations are refused for a nonexistent path before
  library opening. An immutable declaration reaches the open failure on the
  same path. This tests admission declarations, not automatic proof of purity.
- A returned array remains readable and releasable after function and library
  owners are dropped, including a surviving slice.

The lifetime test uses a weak reference to the same library handle retained by
the selected process-lifetime policy. If the handle has expired, it deliberately
forgets the tiny result before reporting failure, avoiding an unloaded release
callback during assertion unwinding. The successful path reads, slices and drops
the actual result. This is a deterministic retention discriminator, not a claim
of an observed crash or exhaustive callback accounting.

## Controls and qualification still required

The integration owner coordinates builds and negative controls. Restoring only
P5 invocation while retaining the new loader can demonstrate metadata loss but
cannot demonstrate the lifetime defect. The lifetime control must separately
disable retention or restore the prior loader with the necessary API shim.
Preserve the exact control patches and results, including setup failures.

The fixture is handwritten Sail-owned code. Passing these tests would not prove
interoperability with an independently built Comet SDK library, package or worker
integration, streaming projection isolation, cleanup of session memory, quota
settlement, durable replay, or hostile-library safety. Those remain separate
qualification boundaries. Final cumulative source review and pinned execution
receipts are still required.

## Human-review compendium assessment

Reviewed the complete `HUMAN-REVIEW.md` with SHA-256
`eed251526e19a5380b73d1d704430f28a61447ed935170cb6551d7d41719e3fe`.
Reread the saved request, its preceding request, AGENTS.md, LAKESAIL.md,
SHEHAB.md, WRITING-RULES.md and CLARITY.md after context compaction.

No must-fix finding from the Test Case Generation role. The compendium separates
qualified foundation repairs from unbuilt projection isolation, recovery, fencing,
configuration and extension integration. It treats the adapter as qualification in
progress and does not turn a compile, handwritten fixture or source inspection
into SDK or package interoperability evidence. Process-retained callback code is
distinct from session-state release, which remains integration work.

The stated sparse/grouped filter overhead agrees with the retained optimized
layout summary: exact outputs passed, output batches increased, and measured
shared-host ratios exceeded one. The compendium preserves the diagnostic boundary
and proposes measuring ordered outputs, error position, retained bytes, latency and
cooperative polling before choosing batching. It does not claim production speed
or performance completion.

The acceptance requirements are reviewable: fixed prepared effects must survive
retry without loss or duplication; stale owners must be rejected at commit;
expressions must exclude control records; native results must preserve fields and
valid callbacks. The remaining source, target and producer choices identify where
concrete integration fixtures are still needed. This review performed no build,
test execution or source change and supplies no new adapter execution result.
