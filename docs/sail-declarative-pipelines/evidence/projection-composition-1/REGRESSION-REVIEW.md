# Projection composition regression review

## Initial source assessment

The unchanged owned rule preserves the inspected upstream implementation and
reproduces its arithmetic defect. Removing the equal-expression shortcut is a
narrow candidate correction, pending executed controls and final cumulative
review. No additional introduced defect was identified in the ownership and
registration adaptations inspected here. This is not a readiness verdict.

Source worktree:
`/Users/alexy/src/sail/tmp/projection-composition-20261105-6e4da8d3`.
Verified starting HEAD `6e4da8d33ba1bf4073fcb853123f81860ef18151` and upstream
merge base `b52144955b629314a000b1fe49eeea97fa3d0c5c`. The existing 77-path
cumulative foundation remains in scope; the current increment is still WIP,
with untracked test and ownership files. Newly observed upstream
`5c0381bb3105ab38bf808cbe3e68a3e0aae619e6` is not part of this parent.

Read the saved request, snapshotted before-code plan, AGENTS, LAKESAIL, SHEHAB,
CLARITY, WRITING-RULES and applicable source instructions. The full SDP,
Extensions, mandatory fencing and configuration objective remains active.
No builds, test executions, source mutations, remote actions or cleanup were
performed by this reviewer.

## Ownership and integration preservation

Independently compared the retained full rule, RequiredIndices and utility
source archives with the installed DataFusion 55.2.0 source. They are exact
matches; all five initial archive hashes match their manifest. Read the complete
owned production rule and both helpers. The inspected comparison contains
public import adaptation, attribution, formatting and explicit recursion
protection. The equal-expression shortcut remains present for the control.

`optimize_projections/mod.rs:129` retains recursion protection. Sail already
enables DataFusion's corresponding feature, and the added direct dependency uses
the existing locked recursive version without a package-version change.
The NamePreserver import references the same public type re-exported by the
upstream utility module. The copied index walker retains scalar, EXISTS, IN and
quantified-comparison outer-reference discovery.

`sail-logical-optimizer/src/lib.rs:65` replaces the existing named rule in place;
`:112` selects it for mandatory streaming preparation too. Neither insertion
changes the rule order, preparation pass limit, source-shape admission or
ordinary optional optimizer settings. No new execution node or wire encoding
is introduced. Earlier source participation, marker handling, projection
execution and standalone native-adapter contracts are not changed by this WIP
integration.

## Failure evidence and correction boundary

At `optimize_projections/mod.rs:547`, syntactically equal projection expressions
discard one input layer before dependency substitution. Two instances of
`v + 1 AS v` reference different input scopes. The normal path below this branch
substitutes child expressions, protects repeated nontrivial work and restores
qualified output names.

Inspected `unchanged-owned-control-v2.log`: direct analyzed execution and the
filter-only stage return 3 through 6, while the owned projection rule returns
2 through 5, both with and without filters. Identity cases return 1 through 4
at every stage. The single diagnostic test deliberately fails after reporting
all cells. The earlier lockfile refusal is a setup failure, not a semantic
control result. These are lead-produced execution records, not reviewer runs.

Read Spark source pinned at `617618396087429b5627a86ce933bb0f5d6645cb`:
CollapseProject substitutes child aliases, preserves relevant output metadata,
and considers producer determinism and use counts. AliasHelper uses upward
traversal to avoid recursively substituting newly inserted bindings. This
supports dependent composition semantics; no JVM comparison was executed.

## Preservation checks before final qualification

The new fixtures inspect arithmetic at depths 2 and 12, direct graph execution,
identity projections, filters, scan pruning, output schema, simultaneous alias
swaps, metadata, scalar-subquery scope, shared volatile child outputs and partial
immutable functions inside conditions. Session fixtures configure Sail analysis,
logical and physical optimizers. Public fixtures exercise both bounded and rate
sources. Their presence is not a passing result, and the new unit modules must
be wired into the frozen candidate before their coverage is claimed.

Additional useful controls target the branch being removed directly:

- Identical expression lists carrying qualified aliases and field metadata.
  The current metadata case uses different lists and therefore does not exercise
  the former shortcut. Check exact schema, not only displayed names.
- Identical literal, null, empty and reordered projections. Preserve row count,
  nullability and column pruning when no input column is referenced.
- Correlated expression references retained by RequiredIndices. The current
  scalar-subquery case is uncorrelated; it does not prove outer-reference
  retention for the copied helper.
- Volatile and conditional work counts against the direct graph, plus planning
  and execution cost for already-correct identity and unique-alias queries.
  Correct arithmetic cannot justify an unmeasured work multiplier elsewhere.

These are preservation risks and control recommendations, not demonstrated
new defects. Keep the existing participation planning and mixed-marker cost
qualifications explicit. Final judgment requires the corrected source pin,
exact upstream comparison, failing unchanged control, restored results and
cumulative review after integration.

## Frozen cumulative source review

**No unresolved introduced correctness defect identified in the frozen source.
Performance qualification, fresh public execution and the complete immutable
gate remain pending. This verdict does not establish general readiness.**

Independently regenerated both binary diffs and checked all 85 file hashes
against Git objects and working files, all 11 increment paths and the complete
cumulative path inventory. Tracked files equal the frozen candidate:

| Item | Verified value |
| --- | --- |
| Tree | `a4801a8e6fb2d10d041d07aef9fc9ec1b7ff2bb6` |
| Starting HEAD | `6e4da8d33ba1bf4073fcb853123f81860ef18151` |
| Upstream base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Increment SHA-256 | `72d0cd710862bc0b4676f357e8c451813f365dfeb27f87fc3daf2dd03db82a0e` |
| Cumulative SHA-256 | `8898a1d1a5b0ae74c3189b022ae7f9c7947675cdde78ef0ff1eb5a29bb322b2f` |

Re-read the request, governance, source instructions and the schema/performance
plan amendments. Reviewed the full increment in cumulative context. Prior
foundation, participation and native-adapter contents outside the listed
integration paths remain byte-identical to the reviewed parent. Both optimizer
registrations select the owned rule at the existing positions; their tests now
execute arithmetic through each registration and require exactly one matching
rule. Test modules are registered in the frozen source.

Independently regenerated the three final upstream comparison artifacts. Their
hashes match the manifest; the main-module comparison covers the production
excerpt with its trailing newline normalized and excludes the new test-module
registration. Helper behavior remains unchanged. Main-rule changes are the
restricted shortcut, schema preservation and integration adaptations described
in the amended plans.

At `optimize_projections/mod.rs:549`, equal expression lists only bypass
composition when each expression is a literal or references its own child-output
position with the same qualifier and name. Alias unwrapping does not admit
computed expressions. Swapped columns and cross-position literal references
therefore use ordinary substitution. This retains the inexpensive identity path
without treating equal text as equal computation.

Composition retains the declared outer schema. Pruning selects the original
qualified fields and metadata and invokes DataFusion's index-remapping operation
for functional dependencies. An identity projection disappears only when the
full declared schema matches its input. Inspected that dependency operation and
the constructor: `try_new_with_schema` checks field count, so physical execution
tests are necessary evidence. The candidate supplies them for expression-derived
types/nullability, empty outputs with positive row counts and a finite matrix of
Arrow type families at zero and positive lengths. This is not exhaustive coverage
of all values or legal type parameters.

The earlier metadata, positional binding, literal/null and empty-output control
recommendations are addressed. Composite dependency tests retain, reorder or
drop determinants and check idempotence. Existing volatile-sharing and conditional
partial-function controls compare exact results and work against direct analyzed
execution in batch and streaming. Uncorrelated subquery scope is covered;
correlated-reference helper behavior is copied unchanged and remains supported
by existing suites rather than a new exhaustive matrix.

Inspected execution logs separately from source reasoning: the unchanged owned
rule fails arithmetic; unchanged schema/registration controls fail three tests;
the corrected arithmetic diagnostic passes. Replacing only the positional guard
with broad equality fails two tests, then restoration passes both. The selected
final Rust run reports 163 passed and one skipped; strict affected Clippy and
Rustdoc finish successfully. Earlier lockfile and fixture-compile failures remain
retained and are not semantic test passes. These are lead-produced records; this
reviewer ran no tests.

The eight valid debug cost cells retain matching output and pruning checks.
Identity, constant and unique-arithmetic cells improve in that diagnostic;
wide qualified identity remains 1.0598 at depth 2 and 1.4392 at depth 32 relative
to stock. Those shared-host, one-rule planning ratios neither prove production
cost nor permit dismissing the wide-plan regression. Optimized confirmation and
its disposition remain required. Prior participation planning and mixed-marker
execution qualifications also remain explicit. Fresh public results and the
full gate were pending at this review boundary. No production, recovery,
fencing or Extension integration claim follows. No source edits or builds were
performed; only this report was appended.

## Frozen v2 cumulative confirmation

**No additional introduced correctness defect identified. The identity-chain
fold preserves the inspected binding and evaluation contracts. Full immutable
qualification and public v2 execution remain pending; no global performance or
production-readiness conclusion follows.**

Independently verified all 85 hashes against tree objects and working files,
the 11 increment paths, the full cumulative inventory and regenerated binary
diffs. Tracked files equal the candidate tree:

| Item | Verified value |
| --- | --- |
| Tree | `1935edac69836542b67aa5ca25f5d794c14ee2b4` |
| Starting HEAD | `6e4da8d33ba1bf4073fcb853123f81860ef18151` |
| Upstream base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Increment SHA-256 | `42199c5a97525b898e516db90d415ecfed8f6098415ec3f58383dcadabb56101` |
| Cumulative SHA-256 | `3dd8b8f09be9506f0fce1b3f4f611817d7567e47b4788c8a6b90eae0e5269bee` |

Reviewed the complete v1-to-v2 diff in the cumulative context. Only the owned
rule and two test files change. The final upstream comparisons regenerate
exactly and match all recorded source, production-excerpt and comparison hashes.
All other cumulative content retains the preceding review's scope and limits.

At `optimize_projections/mod.rs:551`, the new path first requires the outer
expressions to be bare columns matching every immediate child field, in order
and with equal width. Each further skipped projection is independently proved
against its own immediate input at line 554. The traversal stops at the first
computation and retains that projection's expressions and input, rebuilding once
with the original outer schema. Expression equality at line 561 only chooses
which already-equivalent vector to reuse; it cannot authorize another skip.
The existing helper rejects aliases, literals, partial prefixes and reordered
columns on this path. The guarded literal/alias path remains unchanged.

This preserves computed, volatile and conditional child expressions without
duplicating evaluation. Empty identities preserve the same child row-producing
graph. Schema equality remains required before removing the resulting projection
entirely. The added 32-level controls check declared metadata and dependencies,
reordering, both partial selections, empty outputs, idempotence and exact volatile
or guarded work against direct execution in batch and streaming. Existing
arithmetic, schema and broad-equality negative controls remain retained.

Inspected the selected test log reporting 165 passes and one skip. As recorded
by the lead, the additional prefix-selection case was added afterward; it is
not covered by that earlier passing run. The mechanical-v3 receipt binds format,
full-workspace strict Clippy and strict Rustdoc success to this exact tree.
Those checks do not replace the pending complete gate.

The optimized ten-cell diagnostic's source hashes match every frozen increment
file, and its retained probe hash matches the receipt. It validates all values
against direct execution before timing, plus known projection and scan-pruning
counts. Deep wide identity is now 0.9104 relative to stock, compared with the
earlier optimized 1.4048. This resolves that measured deep-cell regression in
the retained diagnostic. Shallow wide identity remains 1.0269 and is disclosed;
near-identity cells are 0.4099 and 0.2631. These are shared-host one-rule rewrite
ratios including plan cloning, excluding analysis and physical execution.
They establish neither production latency nor closure of prior participation
planning and mixed-marker execution qualifications.

Reread the saved request, governance, applicable source instructions,
PROJECTION-IDENTITY-FOLD and the snapshotted identity-chain plan. No builds,
tests or source mutations were performed by this reviewer; only this report
was appended.


## Frozen v4 ownership correction and cumulative confirmation

**The introduced unique-owner destruction regression is closed in the inspected
v4 source and the retained exact-probe rerun. No further introduced regression
was identified. Full immutable qualification remains pending.** This supersedes
the v2 statement that no additional correctness defect was identified: the later
fixed-stack experiment exposed a real lifecycle defect that the earlier shared
plan fixtures did not exercise. Its failure remains part of this record.

Reread the saved request, AGENTS, LAKESAIL, SHEHAB, CLARITY, WRITING-RULES,
applicable source instructions, PROJECTION-CHAIN-OWNERSHIP and the snapshotted
atomic-retirement plan after compaction. Independently regenerated both binary
diffs, verified all 85 hashes against tree objects and working files, and checked
the 11 increment paths. Tracked files equal the frozen tree. Regenerated all
three exact DataFusion comparisons and verified their archived-source,
production-excerpt, complete-owned-source and comparison hashes.

| Item | Verified value |
| --- | --- |
| Tree | `b337dfd145db4773ba1aa019028a8e9c86bbaa67` |
| Starting HEAD | `6e4da8d33ba1bf4073fcb853123f81860ef18151` |
| Upstream base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Increment SHA-256 | `d0be097703b5ce7ba7f1e8400dfd486ee492f9d64f2c91437a8e4f86409cc227` |
| Cumulative SHA-256 | `01226d1ed79d26afa4cd9e36d1e331b365d3ad4ba93c434fbbc50636262c991c` |

Reviewed the complete v2-to-v4 delta in the cumulative context against upstream.
Only the owned projection rule and its composition tests change. The preceding
binding, schema, pruning, volatility and streaming participation review remains
applicable to the unchanged bytes; this is not a fresh execution claim for the
other foundation or Comet units.

At `crates/sail-logical-optimizer/src/optimize_projections/mod.rs:566`, the rule
clones the retained input before releasing anything. Lines 570–575 consume each
removed projection owner and move its child into the next loop iteration.
Pointer equality stops before the retained subtree; shared ownership stops
without changing the other owner's graph. The borrowed proof already established
that every preceding node is a projection. Expressions and the declared outer
schema are selected before retirement and retain the earlier semantics. This
bounds destruction of the removed projection chain without moving the boundary
to unrelated children or adding a cache.

The final `Arc::into_inner` choice also closes the source-derived retirement
concern in the intermediate `try_unwrap` version. Independently inspected Rust
1.98.1's implementation: it suppresses ordinary Arc Drop, atomically decrements
the strong count, and either returns no value or hands the value to the caller.
Thus this loop cannot itself accidentally recursively destroy an unclaimed
shared chain through an error value. This reasoning follows the
[pinned Rust implementation](https://github.com/rust-lang/rust/blob/1.98.1/library/alloc/src/sync.rs#L1230-L1254).
No concurrent runtime failure or stress qualification is claimed. External owners'
destruction and arbitrary expression destructors remain outside this correction.

The retained original run at
`review-logs/performance/identity-drop-v1/runs/20261106T090745.131823Z/current.log`
reaches unique ownership and overflows before rewrite completion at depth 8192.
The exact original probe SHA-256
`228e0d58d9cce8fd48763db48c7b5d7db6f41d8b86b10ff8d840c49e88a2c866`
and runner SHA-256
`94d0392c28cc3a9b38fde197f2f495599b4f48d3115f1ecc9c00a9559f5cf10e`
are byte-identical in the v3 rerun at
`review-logs/performance/identity-drop-v3/runs/20261106T092201.365516Z`.
Verified the rerun log hashes. Both baseline and final candidate complete depths
8192 and 16384 on a 1 MiB stack, with exact schema and original empty-leaf checks.
The probe asserts all input strong counts are one before moving the plan into
the public rule. It therefore exercises the previously masked condition.

The permanent test at `optimize_projections/composition_tests.rs:623` additionally
covers a shared middle tail, verifies its original depth survives, and consumes
that tail through the public rule for controlled fixture teardown. The retained
selected run reports 166 passes and one skip before the final Arc API substitution;
it is not a full final-tree test verdict. The final-tree mechanical-v5 receipt
records formatting, strict workspace Clippy and strict Rustdoc success. The
exact-probe rerun above does cover the final API choice.

Verified the final optimized cost probe hash and every recorded increment source
hash against this candidate. Its ten cells retain 70 samples and correctness and
pruning oracles. Shared-host one-rule ratios for wide identity are 1.0247 at depth
2 and 0.9169 at depth 32; near-identity ratios are 0.4123 and 0.2637. The shallow
cost remains disclosed. These observations do not establish production latency,
complete compiler cost, or closure of earlier mixed-marker qualifications.

No builds, test execution or source changes were performed by this reviewer.
Only this report was appended. Full gate and final public qualification are not
claimed by this source-review verdict.
