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

## Frozen source review

Reviewed the complete adapter, fixture and thirteen tests in staged tree
`d8e9633355f2bac78ab9470e49aceda1992d2388`, against foundation commit
`2c9fa84994d317aade0d1c69faa9a378c780127d`. Verified all twelve source hashes
against `review-logs/candidate-snapshot.json`. Increment patch SHA-256:
`0561254aaed99782dd50a4901f4c28162f799748cfcdac7dd6f5f6ea08676d64`.
Cumulative patch SHA-256:
`59706bb772a2ef606b2bab5657fbe2fe8f18507661110eb0baf53dac50caa376`.
Earlier foundation changes retain their separately reviewed scope. Reread the
current saved request and governing documents, including the new compendium rule.

One test-quality correction is required before final acceptance:
`inconsistent_planned_return_fields_are_rejected` accepts any error. In the
original-adapter control it passes because metadata loss fails initialization
before the planned-field guard is reached. Require the named planned-field error,
then remove only that guard from the repaired adapter and verify the test fails.
The integration owner accepted this correction; a later addendum must bind its
result to the amended source snapshot. No additional production defect was found
within this review's specialty.

Inspected the retained execution logs rather than rerunning them. The candidate
has thirteen passing tests: four fixture tests, one lifetime test and eight
metadata tests. The controls show six metadata failures with original invocation
and a separate lifetime failure with retention disabled. The original controls
use the repaired loader API and are not a complete original P5 build. Strict
focused Clippy passed. These are focused working-tree checks, not an immutable
workspace gate.

The immutable-admission test exercises Stable and Volatile refusals before opening
a nonexistent path, plus an Immutable control reaching the open error. This is
one test with three declarations, and does not prove producer purity. The empty
Arrow matrix and representative nonempty coverage retain the limits described
above. The output null check matches Arrow 59.2's physical-null field validation;
it does not establish exhaustive logical-null checking for dictionary, run-end,
union or Null arrays. Safe planning widening and ignored top-level result aliases
remain intentional, while nested fields are checked as part of the datatype.

Also inspected the two passing temporary probes against the pinned independent
Comet SDK producer. Source files and member manifests in the isolated build are
byte-identical to the retained pinned originals. The workspace manifest is
deliberately different and pins Arrow 59.2. These probes establish ordinary result,
null and argument-order behavior, retained outputs, and the SDK's containment of
deliberate initialization and invocation panics. They do not establish that this
host can contain arbitrary unwinding C callbacks. They are retained experiment
sources, outside the thirteen committed fixture tests, and are not a full Comet
workspace build or package/worker qualification.

No build, test execution or source modification was performed during this review.

## Deliberate logical-null contract: prepared regression

The subsequent `COMET-SCALAR-NULLABILITY.md` design, SHA-256
`fbbdff7b63028bc85a207d1c71200f96a9c95f4ee37950c88f9a692e35105e0c`,
selects a stronger scalar-result guarantee than physical Arrow batch validity.
The preceding physical-null analysis remains accurate about the earlier candidate;
it is not the acceptance contract for this new change. Nonnullable scalar results
must now exclude evaluated logical nulls regardless of their Arrow representation.
Nullable outputs remain admitted with their nulls intact.

Prepared and formatted one table-driven test in `tests/nullable.rs`, SHA-256
`dafb6bf6cbe1ce7779d826c7cb3e654952a87ae708008a7366a1ab14389c8cdd`.
It exercises dictionary, run-end, dense union, sparse union and Null arrays with
nonzero logical null counts and zero physical null counts. Each nullable output
must preserve exact array data and the logical-null mask. Each nonnullable output
must fail with the named result-nullability error. Positive slices of the encoded
arrays select valid values while retaining unselected null children; an empty
Null slice is also accepted. This distinguishes exact logical checking from a
conservative rejection merely because some child can contain nulls.

The root will run the same test with only `logical_null_count()` replaced by
`null_count()`, then qualify the amended candidate. These executions are pending
at preparation time. No compilation or test execution was performed by this role.

The cost is representation-dependent. Arrow 59.2's dictionary override can scan
keys when dictionary values contain nulls. Run-end arrays use the default count
through a computed logical-null bitmap, so a highly compressed output can require
work and temporary storage proportional to its logical row count. Union arrays
can also compute a bitmap. Ordinary primitive null counts are already stored;
the nullable-result branch short-circuits the check entirely. The regression
establishes intended semantics when run, not the cost envelope for large encoded
results. That envelope still needs measurement and explicit resource treatment
when these results join the full extension host.

## Final v3 source review and finding closure

Final reviewed staged tree: `ad453e21427f3f702a342a033dc6c488ab9a7195`.
Increment patch SHA-256:
`a4a1634ae6c0d087f5735cb911da43be19529fec10145ff4333c947562214224`.
Cumulative patch SHA-256:
`094bbb2510294c4e705cb0bd1dce41366b6bcb74d12bc25ba372af09d67406a3`.
Verified both retained patch hashes, all fourteen source-file hashes in
`candidate-snapshot-v3.json`, the staged tree and absence of unstaged tracked
changes. Reread the latest saved request, HUMAN-REVIEW.md and all five governing
documents. Reviewed the amended production code and tests in their full context.

**Verdict: no outstanding must-fix finding from Test Case Generation for this
source snapshot.** The planned-field test now requires the intended error.
Its guard-only control removed the comparison from otherwise repaired invocation
and failed on an erroneous successful result. This closes the earlier false
positive caused by accepting any initialization error.

The physical-only null guard control fails on the first dictionary fixture, which
contains a logical null despite valid physical keys. The final table-driven test
passes nullable preservation, nonnullable refusal and valid-slice acceptance for
dictionary, run-end, dense union, sparse union and Null representations. This is
one named test, and the control stops at its first counterexample; it is not five
independently executed failing controls. The deliberate stronger scalar contract
and its cost limits remain as documented above.

The new nullary test goes through actual DataFusion planning and collection and
checks three result rows. Restoring only `VariadicAny` fails during planning;
the combined nullary/variadic signature passes. The missing-probe refusal now
uses a purpose-built loadable library without that symbol, avoiding assumptions
about whether the platform can load the current test executable. Both changes
make their claimed behavior observable at the intended boundary.

Inspected `final-focused-tests.log`: fifteen tests pass, comprising five fixture
tests, eight metadata tests, one lifetime test and one logical-null test. The
affected-crate Clippy log completes successfully. The exact copied Comet factory,
instance and discovery record section matches the pinned source byte for byte;
the retained record comparison is empty. Sail-facing aliases leave those records
unchanged. The two independent SDK probes remain separate experimental evidence,
not two additional tests in the committed fifteen-test suite.

This closes source/test review for v3, not the pending broad or immutable gate.
No build, test execution or source change was performed during this final review.
Package integration, workers, hostile-code safety and the cost of large encoded
nonnullable outputs remain outside these passing component checks.

## Final null-presence repair and source pin

The preceding v3 conclusion is superseded by the subsequently reproduced Arrow
59.2 helper defect. A single-child dense union with type ID 3 selected a null
child, but Arrow gathered its null mask as if the type ID were 0. The independent
regression derived its expected values from `[null, 7]`, without consulting that
helper. `arrow-union-control.log` records the erroneous successful nonnullable
result before Sail's predicate replaced the helper.

Reviewed final tree `455101575ecbfbec6f843464ce178e0d09046f51`.
Increment SHA-256:
`7477e67e9b6262e5aec067714c586ef7ac49790e8e6ac7d14116829213bdf325`.
Cumulative SHA-256:
`743a1346feb7ae62a4cded0224b007312b471b09d80d149b2b0bdf5c25c25b30`.
Verified all fifteen file hashes, both patch hashes, the staged tree and absence
of unstaged tracked changes. The v4-to-final delta changes only Rustdoc formatting
in two files. The saved request and revised nullability plan were read; the
previously reread governing requirements remain applicable.

**Final verdict: no outstanding must-fix source or test finding within this
role's specialty.** The dedicated predicate follows actual union type IDs and
offsets, dictionary keys and intersecting physical runs. It recursively checks
selected encoded values, while preserving parent nullability for present lists
and structures. The run-range calculation agrees with Arrow's public slice
accessors, handles empty inputs before index calculation and excludes runs outside
the logical slice. Result row count is checked before this traversal; nullable
outputs bypass it.

The independent-oracle regression now covers the union directly, dictionary and
run-end wrappers, and both mixed nesting orders. Each case checks nullable exact
preservation, nonnullable rejection and acceptance of the offset slice selecting
7 despite retained null children. The compressed-run test checks one million
valid logical rows while retaining two physical values, then refuses the full
array containing its final null run. Its structural assertions do not measure
temporary allocation. The conclusion that the new predicate avoids a logical-row
null bitmap comes from source inspection, not a memory profiler or timing result.

Inspected final recorded results: seventeen tests pass, comprising five fixture,
eight metadata, one lifetime and three nullability tests. Focused strict Clippy
passes. Both pinned SDK interoperability probes were rerun after the null-presence
repair and pass, separately from those seventeen tests. Earlier failing controls
remain retained with their original scope and counts. Empty-array coverage spans
all Arrow families and index widths; nonempty encoded and nested coverage remains
representative rather than an exhaustive type/shape cross-product.

This source review closes the Arrow-helper finding and preserves the prior
planned-field finding's closure. The immutable gate and broader integration
qualification remain separate. This role ran no builds or tests and made no
source changes during the final review. Package admission budgets, worker use,
arbitrary producer safety and a production performance envelope remain unproven.
