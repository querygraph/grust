# Projection composition test review

The saved request, pre-code first-principles plan and repository governance were
read. AGENTS, LAKESAIL, SHEHAB, CLARITY, WRITING-RULES and applicable Sail development
instructions govern this work. This role owns only the three new test files listed
below and this report. The implementation worktree is
`/Users/alexy/src/sail/tmp/projection-composition-20261105-6e4da8d3`, detached from
`6e4da8d33ba1bf4073fcb853123f81860ef18151`. Root owns production and all builds.

## Original counterexample

Inspected the retained participation diagnostic
`review-logs/performance/projection-alias-rule-v1.log` in the preceding worktree.
For inputs 1 through 4, two successive additions reusing alias v must produce
3 through 6. Direct analyzed execution and filter-pushdown-only execution do so;
isolated DataFusion 55.2 projection optimization instead returns 2 through 5.
Both variants, with and without interleaved filters, fail the independent oracle.
Identity-projection controls pass. This is a retained failed runtime diagnostic;
no corrected result or root cause is inferred merely from matching two optimized
paths. The published plan's proposed shortcut removal still needs its control run.

## Independent regression cases

The rule-only module contains three tests:

- Repeated same-name expressions at depths two and twelve preserve every addition,
  while identity controls remain identities. The result must actually collapse to
  one projection, prune the unused scan columns and remain stable on reapplication.
- Swapped aliases use simultaneous child bindings, rather than recursively applying
  substitutions in the wrong scope. Exact output expression, qualified output
  schema, nullable field, explicit field metadata and narrow scan projection are
  checked. This also discriminates simply disabling projection optimization.
- A scalar subquery and its enclosing projection both use v. The subquery's two
  additions remain in its own scope and the unrelated outer binding remains intact.

The session module contains three tests, each using production analyzer, logical
and physical optimizer registration and the shared Sail compiler:

- Batch and encoded-stream inputs run identity and arithmetic chains at depths two
  and twelve, with and without interleaved filters. Both direct analyzed execution
  without logical optimization and the actual compiler must match the original
  arithmetic oracle. Stream runs check ordered checkpoint and end-of-data markers.
- A volatile increment appears at one or two dependent levels, then its output is
  read twice. Results and exact call/row counts must retain each level without
  duplicating its child output evaluation. The function refuses marker placeholders.
- Two dependent conditional increments select only values greater than two. The
  immutable function rejects every other input, so hoisting or accidental marker
  evaluation fails. Both paths must produce zero, zero, five, six and retain the
  direct graph's two calls over four selected rows.

The public DataFrame module contains thirteen cases: eight bounded arithmetic and
identity cases, four bounded-demand Sail rate cases, and one simultaneous alias
swap with explicit metadata. Expected values, cardinality and multiplicity are
exact. Rows are compared as multisets because there is no global ORDER BY. The
rate source is limited before the repeated filters so these cases cannot require
unbounded input consumption. Only Sail-specific cases carry JVM exclusions;
ordinary DataFrame cases remain eligible for Spark execution. No JVM execution or
parity result is claimed here.

Rust tests target internal logical scopes, control markers and counted callbacks
that the public DataFrame surface cannot express. Public DataFrame tests supply
user-facing execution coverage alongside those internal contracts. This finite
corpus does not qualify arbitrary expression combinations, recursive depth limits,
performance, distributed execution, recovery or the full SDP implementation.

## Frozen first revision, execution pending

| File | SHA256 |
| --- | --- |
| `crates/sail-logical-optimizer/src/optimize_projections/composition_tests.rs` | `ad7f827e63281fa92d4bf078713e82fd90b3508b2b5062ec8c9f59886f49d340` |
| `crates/sail-session/src/projection_composition_tests.rs` | `6d0e62b0eb11f5c418436661540cfef74dfeb33443766da399f5e0c6ad9912b5` |
| `python/pysail/tests/_dev/spark/dataframe/test_projection_composition.py` | `c44cdb2ef7a2501bb8f4e69a005cf0aee4ef04e2070784a567ea15491f8e44db` |

Rust files were formatted individually with nightly rustfmt. No build, test run,
dependency installation, source production change, commit or remote action was
performed by this role. Module registration, unchanged-copy negative control,
corrected execution, public execution and final cumulative review remain pending.

Recorded at 2026-11-06T06:56:39.796664+00:00.


## Explicit-schema and registration controls

Added three independent rule tests. An identity pair is built with
Projection::try_new_with_schema, exactly equal expression vectors and distinct
inner/outer qualifiers, field metadata and schema metadata. Preconditions pin
those distinctions. Both the stock and owned rules execute; the declared outer
schema remains the intended oracle. Any failure prints stock's comparison with
that oracle separately from the owned result. Source inspection suggests the
full stock rule can discard the declared schema later during projection pruning,
independently of the equal-expression shortcut. That is not an executed finding
at this entry and the intended preservation assertion was not weakened.

Two registration tests obtain the single named projection rule from the ordinary
optimizer and streaming preparation lists and execute the original two-addition
counterexample through each actual returned rule. A name-only registration check
cannot distinguish the stock implementation; these assertions can.

The prior rule file is archived unchanged at
`review-logs/composition-tests-before-schema-and-registration.rs`, SHA256
`ad7f827e63281fa92d4bf078713e82fd90b3508b2b5062ec8c9f59886f49d340`.
The new formatted rule file is frozen at SHA256
`1d2254d0aea16426515e8b792753a120752aa3e2bff428ffc10c3e8f39792808`.
The other two test files are unchanged. There are now nine Rust tests and thirteen
public cases. No builds or tests were run; negative controls and qualification
remain pending.

Recorded at 2026-11-06T07:03:09.153522+00:00.


## Executed controls and schema extensions

Inspected `unchanged-metadata-registration-v1.log` and its receipt: all three
selected tests fail on the unchanged owned copy. Both registrations drop one of
two additions. The identity fixture independently demonstrates the same loss in
stock and owned rules: the declared outer qualifier, field metadata and schema
metadata disappear. The original oracle is retained. The earlier unchanged-owned
arithmetic diagnostic also remains failed with identity controls passing. These
are pre-existing rule defects, not regressions introduced by its local copy.

Read the amended first-principles schema plan and its before-code snapshot,
SHA256 `29c6fb1fbda4c1a62797e489d3c0a3a489ed18f962ec6a3b916a3985f790694b`.
The independent tests now additionally cover:

- Equal-expression identity schemas across every Arrow type family, retaining
  the original nonnullable Int64 witness and nested child metadata. The finite
  matrix is not an exhaustive cross-product of type parameters.
- Functional-dependency reordering, loss of a determinant, loss of one member of
  a composite determinant, and zero-column output. Expected dependencies are
  written explicitly, without calling the production remapping helper as oracle.
  LIMIT separates projections so inner column pruning is exercised too.
- Actual physical execution of original and optimized declared-identity plans for
  the Arrow family matrix at lengths zero and three. Physical and emitted schemas,
  total row counts and exact ArrayData are checked against original typed inputs.
- A zero-column physical result retaining four rows and explicit schema metadata.
- A nullable Int64-to-Int32 cast followed by two increments. Output name, type and
  nullability are derived from valid expressions, not arbitrary schema overrides;
  both physical paths must retain metadata and return exactly `[3, NULL, 5]`.

The first logical matrix draft reused an Int64 scan while varying declared output
types. This was an inapplicable fixture, caught by source inspection. Its exact
source is retained as `composition-rule-tests-mismatched-arrow-matrix.rs`.
The corrected fixture builds a matching source datatype and nullability in each
case and retains every expected output assertion. The physical matrix used
matching typed arrays from its first revision. The root's corrected-tests-v1
compilation had already started during this correction, so that invocation is
provisional and cannot qualify the corrected logical matrix; a frozen rerun is
required. No success is claimed from constructor acceptance alone.

Before-extension test files are preserved as
`composition-rule-tests-before-schema-extension.rs` and
`composition-session-tests-before-schema-extension.rs` under review-logs.
Current formatted, frozen source hashes are:

| File | SHA256 |
| --- | --- |
| Rule tests | `01c6088f4d58ce3bfe5e07fcf523ee737613749b500b5f9868c6c85f3abd3754` |
| Session tests | `d392e969e8861fbb6c8ff408734c0ee89e9fa68e66e80c01d8c875515e0a22fc` |

The public file is unchanged. There are thirteen Rust tests and thirteen public
cases. This role ran no build or test. Corrected execution, negative controls for
new schema paths, public execution and final cumulative review remain pending.

Recorded at 2026-11-06T07:22:24.954059+00:00.


## First corrected build stopped before execution

Inspected `corrected-tests-v1.log`: compilation stops because the session data
fixture returned ArrowError where its signature requires DataFusionError. No
tests ran. The corrected logical matrix was compiled, so the terminal result is
a fixture compile failure, not a semantic result or matrix qualification.

Changed only the fixture's return conversion to `Ok(RecordBatch::try_new(...)?)`.
All inputs and assertions remain unchanged. Its exact prior source is archived as
`review-logs/composition-session-tests-before-result-conversion.rs`, SHA256
`d392e969e8861fbb6c8ff408734c0ee89e9fa68e66e80c01d8c875515e0a22fc`.
The formatted, frozen session file now has SHA256
`5bbefb0ee8c2d01cedf2a54184562c18def962c4bf2a88b90af83cd849ede5d8`.
Rule and public files are unchanged. This role ran no builds or tests; the frozen
suite rerun remains pending.


## Corrected execution and positional shortcut controls

Inspected `corrected-tests-v2.log`: all 160 selected tests passed, with one
pre-existing skip. This includes the thirteen new Rust tests and actual physical
Arrow-schema execution after the fixture corrections. That verdict applies to
that pre-shortcut source, not automatically to the following revision.

The retained shared-host cost probe reports material deep identity and constant
regressions, approximately 4.17 and 6.66 times stock cost respectively. Those
correct-output cells are not discarded. Read the amended performance plan and
its before-code snapshot, SHA256
`80a12697beac7ac9f4397ba40d74cbdc172665d54476fcbe52ff4136ac22edff`.
The intended shortcut admits only equal lists of positional qualified identity
columns or literals, preserving the declared outer schema; computed expressions
must retain ordinary composition.

Added two rule tests and one physical execution test. Positive cases combine an
identity column, a literal and a typed NULL, and also exercise two empty
projections. They override outer field/schema metadata and qualifiers without
changing expression-derived names, types or nullability, so the safe shortcut's
schema preservation is covered. Negative cases use exactly equal swapped-alias
lists and equal `[7 AS a, a AS b]` lists. The former must swap twice; the latter
must return seven in both columns. A broad equality or name-only shortcut would
lose these computations. Direct Projection construction and equality preconditions
ensure builder qualification cannot turn the intended equal-list cases into
unequal lists. Physical checks execute both original and optimized plans and
require exact arrays, metadata and four output rows, including zero-column output.
All prior arithmetic, volatile and conditional assertions remain unchanged.

Previous files are archived as
`review-logs/composition-rule-tests-before-positional-controls.rs` and
`review-logs/composition-session-tests-before-positional-controls.rs`.
Current formatted, frozen hashes:

| File | SHA256 |
| --- | --- |
| Rule tests | `5d5320cf6505740641210cd6f97aebed0d7daebb937f84a065ac01edf93a2c23` |
| Session tests | `79a5a10f18cdb1fb1659285335908beec648877fc57aefc3213de2fdc755611c` |

There are now sixteen Rust tests and thirteen public cases. No builds or tests
were run by this role. Execution and performance qualification of the shortcut
revision remain pending.

Recorded at 2026-11-06T07:42:11.081518+00:00.


## Python preflight fixture correction

Inspected `preflight-python-format-v1.log`: three FBT001 diagnostics concern
positional boolean pytest parameters. The preflight stopped before the CLI/native
build or public test execution. Added only keyword-only separators to the two
test signatures. Parameter values and every assertion remain unchanged; there is
no lint suppression. Prior source is archived as
`review-logs/projection-composition-public-before-keyword-only.py`, SHA256
`c44cdb2ef7a2501bb8f4e69a005cf0aee4ef04e2070784a567ea15491f8e44db`.
The frozen Python file now has SHA256
`6057f05410b00f15fd8094f35bf5e934f008e3d6085e1ca5584e254e2682ee1e`.
This role ran no lint, build or test and made no Rust change. Public execution
remains pending the lead's rerun.


## Final exact-pin source and test review

**No outstanding correctness or test-oracle finding within this role's specialty
for tree `a4801a8e6fb2d10d041d07aef9fc9ec1b7ff2bb6`. Performance readiness and
the full immutable gate remain unresolved.** This is not a release or full-goal
completion verdict.

Independently verified all 85 cumulative file hashes, the complete 11-path
increment and cumulative inventories, unchanged parent HEAD
`6e4da8d33ba1bf4073fcb853123f81860ef18151`, index tree and absence of unstaged
tracked changes. Regenerated binary diffs exactly match both saved patches:

- Increment SHA256: `72d0cd710862bc0b4676f357e8c451813f365dfeb27f87fc3daf2dd03db82a0e`.
- Cumulative against `b52144955b629314a000b1fe49eeea97fa3d0c5c`:
  `8898a1d1a5b0ae74c3189b022ae7f9c7947675cdde78ef0ff1eb5a29bb322b2f`.

The 74 cumulative-only files are byte-identical to the previously reviewed parent.
Their foundation, C scalar, Arrow utilities, projection, participation, codec,
metrics and terminal-error reviews carry forward unchanged. Reviewed the complete
new increment and its interactions with ordinary and streaming compilation. Both
registrations use the owned rule. The pinned ownership comparison confines
behavioral changes to projection composition, schema retention, dependency
remapping and the safe positional shortcut. RequiredIndices remains sorted and
deduplicated, supporting the unchanged-length schema reuse. The index visitor's
subquery traversal remains copied behavior; recursion protection is explicitly
enabled. Ownership source and comparison hashes were verified. The main module's
comparison hash covers its production prefix before the test-module declaration,
trimmed to one trailing newline; the two helper hashes cover their whole files.

The sixteen Rust tests retain the original arithmetic, complete declared-schema,
physical-array, row-count, dependency and invocation-count oracles. Their current
hashes match the independently authored frozen files. The equal-list negative
fixtures prove applicability before optimization; constructor-only acceptance is
not used as evidence of physical correctness. The finite Arrow matrix covers every
family, all dictionary index widths and all run-end widths, representative nested
metadata and decimal parameters. It is not an exhaustive type/shape/parameter
cross-product. Physical matrix inputs match their declared types. The original
nonnullable Int64 witness and the nullable cast result remain separate controls.

Inspected completed evidence:

| Evidence | Observed outcome |
| --- | --- |
| `corrected-tests-v3.log` | 163 selected Rust tests passed, one pre-existing skip, including all sixteen new Rust tests. |
| `guard-control/before.log` | Both selected tests fail when only the broad equal-list shortcut is restored while schema repairs remain. Physical output performs one swap instead of two. |
| `guard-control/restored.log` | Both tests pass after restoring the positional guard. |
| `composition-preliminary-public-pytest.log` and receipt | 51 passed in 13.47 seconds; server version probe reports 4.2.1. Source inspection separates 42 live-server cases from nine mocked client-parser cases. All thirteen new DataFrame cases are live-server executions. |
| Mechanical preflight logs | Affected strict Clippy, strict Rustdoc and Python lint/format checks complete successfully. |

Earlier unchanged-copy failures, stock metadata loss, compile/format fixture
failures and the inapplicable first logical matrix remain retained with their
original classifications. No original value or schema assertion was weakened.
The public tests preserve exact values and multiplicities without inventing global
collect order; no JVM Spark runtime parity is claimed.

All cost cells remain in the record. The initial deep identity and constant
regressions motivated the guarded shortcut. The later debug diagnostic still
reports a material wide qualified-identity ratio of approximately 1.439 at depth
32. This result is not dismissed as noise. Optimized compilation is pending at
this review, so it supplies no timing verdict yet. The temporary untracked cost
probe is an opt-in diagnostic, not part of the 85-file source snapshot. These
shared-host rewrite measurements do not establish production throughput, latency
or distributed behavior.

The saved full request and governing LAKESAIL, SHEHAB, CLARITY and WRITING-RULES
were reread for this review; previously read AGENTS and source development
instructions remain applicable. No builds, tests, source edits or remote actions
were performed during final review. Only this report was appended. Broader
qualification, recovery, fencing and the full SDP/Extension objective remain
outside this source/test verdict.

Final pin verified at 2026-11-06T08:19:40.725544+00:00.

The companion `review-logs/ownership/comparison-scope.json` now explicitly records
the verified production-prefix and whole-file hash distinction. Inspected it;
the original comparison receipt and source patches remain unchanged.


## Final v4 cumulative source and test verdict

**No outstanding correctness or test-oracle finding within this role's specialty
for tree `b337dfd145db4773ba1aa019028a8e9c86bbaa67`.** The demonstrated unique-owner
stack failure is closed by the unchanged counterexample on this tree. The final
immutable workspace gate and refreshed public execution remain pending. This is
source-review readiness for those gates, not a claim that they have passed.

Independently reverified every one of the 85 cumulative file hashes, all eleven
increment paths, both inventories, parent HEAD
`6e4da8d33ba1bf4073fcb853123f81860ef18151`, exact index tree and absence of unstaged
tracked changes. Regenerated binary diffs match the saved v4 patches byte for byte:

- Increment SHA256: `d0be097703b5ce7ba7f1e8400dfd486ee492f9d64f2c91437a8e4f86409cc227`.
- Cumulative against `b52144955b629314a000b1fe49eeea97fa3d0c5c`:
  `01226d1ed79d26afa4cd9e36d1e331b365d3ad4ba93c434fbbc50636262c991c`.

Reviewed the complete cumulative and increment within this specialty. Against the
previously reviewed v1 candidate, only the owned optimizer module and its two
composition test modules differ; the other 82 cumulative files are unchanged.
The earlier cumulative reviews therefore carry forward with their original
limits. Rechecked the final ownership source, production-prefix, whole-file and
comparison-patch hashes. Their scopes are explicit in
`review-logs/ownership/comparisons-final-v4.json`.

The added fold admits only equal-width, positionally matching bare columns, with
both qualifier and field name checked against each immediate child. It stops at
computed outputs. Reusing expressions after that proof does not revive the
unsafe equal-expression shortcut. The final projection retains the complete outer
schema. Partial, reordered, aliased, literal and computed selections retain the
appropriate existing composition paths. The retained input Arc is established
before removed projection owners are consumed iteratively. Shared ownership stops
that retirement. The final `Arc::into_inner` change follows the documented
consumption guarantee; this review does not claim a concurrent stress execution.

The three added Rust tests bring this increment to nineteen Rust tests while its
thirteen public DataFrame cases remain unchanged. The new tests discriminate:

- A 32-level identity chain above a computation, with full, reordered, partial
  and empty outputs, exact outer qualifiers and metadata, functional dependencies,
  expected expressions and idempotence.
- Batch and supported streaming execution through 32 identities, preserving exact
  volatile invocation counts and guarded immutable selected-row work. Marker
  payloads remain outside the function domain and must not invoke it.
- Deep unique-owner and shared-midpoint chains at depths 8192 and 16384 on a
  1 MiB thread stack. Ownership preconditions are asserted before moving the plan
  into the rule. The shared subtree must remain intact and is subsequently consumed
  through the rule. The fixture does not clone the unique plan before rewriting.

Earlier arithmetic, scope, simultaneous-alias, schema, pruning, dependency,
empty-row-count and invocation-count assertions are unchanged. The Arrow matrix
contains 67 representative types spanning every family, with all dictionary key
and run-end widths and representative nested metadata. Physical cases use zero
and three rows with matching input types. It is finite family coverage, not every
parameter combination, nested shape or invalid schema. The original nonnullable
Int64 witness and nullable cast control remain separately exercised.

The stack evidence is particularly discriminating. In
`identity-drop-v1/runs/20261106T090745.131823Z`, the baseline passes both depths;
the borrowed-fold variant reaches rewrite at depth 8192 and then reports stack
overflow and SIGABRT. It never reaches its depth-16384 case. In
`identity-drop-v3/runs/20261106T092201.365516Z`, both variants complete both depths.
The executed probe SHA256 is unchanged:
`228e0d58d9cce8fd48763db48c7b5d7db6f41d8b86b10ff8d840c49e88a2c866`.
The executed runner is also byte-identical, SHA256
`94d0392c28cc3a9b38fde197f2f495599b4f48d3115f1ecc9c00a9559f5cf10e`.
The final receipt pins this v4 tree, verifies the same executable for both variants
and verifies complete restoration. This closes the observed removed-chain failure;
it does not establish safety of arbitrary expression destructors or teardown by
external owners. The destructor explanation remains source-derived, without a
debugger backtrace.

Execution evidence remains separated by revision:

| Evidence inspected | What it establishes |
| --- | --- |
| `corrected-tests-v6.log` | 166 selected tests passed with one pre-existing skip before the final `try_unwrap` to `into_inner` line change. It is not a whole-suite v4 result. |
| `mechanical-v5/receipt.json` | Final v4 formatting, strict workspace Clippy and strict affected-crate Rustdoc passed. |
| Final identity-drop v3 receipt and logs | The unchanged unique-owner counterexample passes on final v4 at both depths, with baseline and restoration controls. |
| Final optimized cost receipt, source and log | Ten correctness/pruning cells pass; all seventy paired timing samples are retained, seven per cell. These are ten oracle cells, not seventy separate oracle cases. |
| Earlier preliminary public receipt | The earlier candidate passed 51 cases, comprising 42 live-server cases and nine mocked parser cases, with actual server version 4.2.1. It is not refreshed public qualification of v4. |

The final cost probe executes original, stock-optimized and owned-optimized plans
against independently calculated values before timing. It checks exact schemas,
projection counts and requested scan columns. All five workloads run at depths
two and 32. Timed work is rule rewriting, including the shared-plan clone; it is
not query execution. The optimized diagnostic uses optimization level three,
LTO disabled and sixteen codegen units. Its receipt pins the eleven increment
files and reports unchanged source; it does not itself hash all 85 files during
the run. Those 85 files were independently checked for this review.

The wide qualified-identity median ratios are 1.0247 at depth two and 0.9169 at
depth 32. These are ratios on a loaded shared macOS host, with load recorded and
steal unavailable. The earlier material regressions remain retained, including
the approximately 1.439 debug ratio and the optimized deep-wide slowdown that
motivated this fold. No result is relabelled as noise. The final diagnostic
resolves those particular cells without claiming a universal planning cost,
production latency or distributed performance guarantee. The fixed-stack control
separately covers ownership that shared-plan timing does not exercise.

All earlier unchanged-copy failures, stock metadata loss, shortcut-negative
controls, fixture applicability failures and compile/format failures remain in
the record. No original expected value or schema assertion was weakened. The
saved full request, AGENTS, LAKESAIL, SHEHAB, CLARITY, WRITING-RULES, source
development/review instructions, the identity-fold and ownership plans, and their
before-code snapshots were reread for this review, including after compaction.
No builds, test executions, source changes or remote actions were performed by
this role during final review. Only this report was appended. Full SDP recovery,
fencing and extension integration remain outside this increment's qualification.

Final v4 pin reverified and verdict recorded at 2026-11-06T09:41:21.457374+00:00.
