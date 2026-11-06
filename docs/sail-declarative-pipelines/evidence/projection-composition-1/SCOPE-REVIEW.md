# Scope review: projection composition

## Initial design and ownership verdict

No initial scope blocker was found. Read the full saved request in the detached
implementation worktree and the published first-principles plan. The reviewed
`PROJECTION-COMPOSITION.md` has SHA-256
`70f66f814b30d865258e5350c1c3cd4ed4eb58a4bf0fe7206a419da2d2d16bb3`.
Source inspection began in
`/Users/alexy/src/sail/tmp/projection-composition-20261105-6e4da8d3`, based on
`6e4da8d33ba1bf4073fcb853123f81860ef18151`. This is an initial design/ownership
review; the behavior correction and final frozen cumulative qualification remain
pending.

The example explains why two identical-looking projections are not the same
computation: each reads its immediate child's output. The plan compares disabling
projection optimization, renaming aliases around the rule and repairing the rule
itself. It preserves column pruning as a required capability rather than trading
it away for easier passing tests. The arithmetic oracle and identity controls
supply discriminating evidence, with Spark source inspection clearly distinguished
from executed JVM parity.

## Actual ownership surface

Inspected the copied OptimizeProjections implementation and its two private helper
modules, retained upstream sources and exact-copy/adaptation manifests. Compared
the current files directly against the retained pinned production module,
RequiredIndices implementation and index-walker functions. Current adaptations are
public import paths, source credit/license, helper placement, required formatting
and explicit recursion protection. The equal-expression shortcut is still present
for the unchanged-owned negative control. This review does not prematurely label
its candidate removal a verified fix.

The same owned implementation replaces the ordinary optimizer registration and
the explicitly selected streaming-preparation registration. This is necessary to
correct the demonstrated shared batch/streaming defect, not an expansion into a
second optimizer framework. RequiredIndices and referenced-index traversal remain
implementation helpers; their ownership does not imply a new planning protocol.
The explicit recursive dependency uses version 0.1.1 already present in Cargo.lock,
retaining protection that would otherwise depend on the original crate's feature
configuration. No new dependency-version or datatype policy is proposed.

Although roughly 1.1 thousand existing production lines are carried, the intended
behavioral change is one shortcut removal followed by ordinary composition. The
scope should continue to be assessed by that actual delta and integration burden.
Keep the exact upstream comparison available, and make the commit body distinguish
carried code from changed behavior. This gives a reviewer a manageable entry without
requiring another reader-facing design document.

## Qualification boundaries

The unchanged owned copy must fail the original arithmetic oracle before repair.
A corrected rule must preserve qualifiers, metadata, schema pruning, identity
projections, subqueries, volatile evaluation counts and conditional guards. Both
registration paths need executed tests and ordinary batch/public controls. A faster
result with a discarded addition is not an equivalent performance comparison.
Do not generalize from removing this one candidate branch to all projection
optimization correctness or arbitrary stateful/volatile expression safety.

The increment does not implement streaming source controls, durable preparation,
mandatory target fencing, CDC merges, typed YAML/JSON/API configuration or Dhall,
package/worker Extensions integration or C relation support. All remain full-goal
requirements. Fixing a shared optimizer defect is aligned foundation progress;
it is not a replacement for that requested end state.

## Compliance

Read the full request and governing AGENTS, LAKESAIL, SHEHAB, CLARITY and
WRITING-RULES, plus the source project/development/Rust-review instructions.
No source edits, builds, tests, measurements, cleanup, remote changes or maintainer
messages were performed. Only this report was written. The cold negative control
is being executed by the integration owner and is not counted as completed evidence
by this reviewer. Final cumulative scope review remains required after the repair
and mechanical preflight.

## Final frozen candidate source-scope verdict

No scope blocker was found in the final composition candidate. Verified all 85
source file hashes and 11 increment paths in the final snapshot, unchanged parent
`6e4da8d33ba1bf4073fcb853123f81860ef18151`, working/index equality and exact index
identity with tree `a4801a8e6fb2d10d041d07aef9fc9ec1b7ff2bb6`.
Independently recomputed:

- Increment SHA-256:
  `72d0cd710862bc0b4676f357e8c451813f365dfeb27f87fc3daf2dd03db82a0e`.
- Full cumulative source against upstream
  `b52144955b629314a000b1fe49eeea97fa3d0c5c`, SHA-256:
  `8898a1d1a5b0ae74c3189b022ae7f9c7947675cdde78ef0ff1eb5a29bb322b2f`.

Inspected the final owned rule, helper changes and retained comparisons against
pinned DataFusion 55.2.0. The behavioral scope remains projection composition,
including preserving the declared schema that composition/pruning must retain.
The separate schema counterexample justifies the qualifier, field/schema metadata
and functional-dependency remapping corrections. Keeping output positions and
selecting original fields during pruning does not introduce casts, a new nullability
policy or arbitrary datatype substitution.

The final equal-expression shortcut is narrower than the initial bad branch:
it admits only same-position identity columns or literals, leaving computed
expressions to child-output substitution. This is a focused correction within
the existing rule, preserving column pruning and the ordinary/streaming
registrations. Explicit recursion protection reuses the locked dependency version.
RequiredIndices and referenced-index traversal remain private implementation
helpers. Source credit/license and original/adapted comparison artifacts remain
available; no vendored crate or replacement optimizer framework is introduced.

The increment also adds direct rule, real session compilation and public DataFrame
regressions. The public tests assert exact arithmetic results at repeated projection
depths and keep identity controls, filtered variants, batch/streaming paths and an
alias-swap metadata example. The source tests qualify pruning/dependency metadata,
qualifiers, volatile calls, conditional evaluation and actual execution rather
than relying only on reconstructed schema width. Those checks fit the demonstrated
projection contract rather than broadening into unrelated optimizer features.

The temporary opt-in composition-cost probe is untracked and outside this staged
source pin. It is excluded from this source-scope verdict and needs explicit treatment
in the final gate. No source edits, builds or process intervention were performed
by this reviewer.

The preliminary public receipt records a successful fresh-server test invocation
with a PySpark 4.2.1 version probe. The lead reports 51 tests passed; it is not a
full immutable qualification verdict. The debug wide-64/depth-32 cost ratio of
1.439 remains a material diagnostic limitation, and the optimized comparison is
still pending. This scope review does not classify that cost as noise or certify
performance readiness. Incorrect old/new outputs must remain outside equivalent-work
timing claims.

Reread the complete saved request, current first-principles plan and governing
LAKESAIL, SHEHAB, CLARITY and WRITING-RULES. The full SDP, existing Extensions,
Comet route, mandatory fencing, typed configuration and optional Dhall objective
remains active. Correcting this shared optimizer defect is an incremental foundation
repair, not completion or narrowing of that goal. Full gates remain pending.
Only this report was appended; no builds, source edits, cleanup, remote actions or
maintainer messages were performed.

## Final v2 identity-chain correction and exact pin

Verified all 85 snapshot file hashes and 11 increment paths, unchanged parent
`6e4da8d33ba1bf4073fcb853123f81860ef18151`, working/index equality and exact
index equality with tree `1935edac69836542b67aa5ca25f5d794c14ee2b4`.
Independently recomputed:

- Increment SHA-256:
  `42199c5a97525b898e516db90d415ecfed8f6098415ec3f58383dcadabb56101`.
- Full cumulative source against upstream
  `b52144955b629314a000b1fe49eeea97fa3d0c5c`, SHA-256:
  `3dd8b8f09be9506f0fce1b3f4f611817d7567e47b4788c8a6b90eae0e5269bee`.

No scope blocker was found. The complete v1-to-v2 tree delta is limited to the
owned rule and two existing test files. Read `PROJECTION-IDENTITY-FOLD.md` and
the retained identity-chain plan snapshot. The new borrowed traversal is a narrow
application of positional identity within the same projection rule, addressing
measured deep-plan cost without introducing a proof cache, global state or another
optimizer framework.

Every skipped identity is checked against its immediate child. The code retains
the computed child's expressions/input and the outer declared schema. Equality
of expression lists can reuse an owned vector only after those identity checks;
it is not restored as a general license to discard a computed projection.
Reordered and partial selections retain the ordinary path. This fits the value,
schema and pruning contract and adds no datatype/nullability policy.

Inspected the two new tests in full. Direct rule coverage includes a 32-level chain,
outer qualified metadata and functional dependencies, reordered and partial/prefix
selections, empty output and optimization idempotence. Real session compilation
covers unchanged volatile and guarded immutable work in both batch and streaming
paths, with exact rows and function/row counters. These cases qualify the new
shortcut rather than widening delivery scope.

The lead reports the earlier 165-test/one-skip affected run predates the last prefix
case, while full workspace mechanical checks passed before freeze. Final runtime
qualification must include the complete frozen test set. The reported optimized
10-cell comparison reduces the deep/wide ratio to 0.9104 from the prior optimized
1.4048, with shallow 1.0269 and near-identity 0.410/0.263. The Performance review
clears its material introduced-cost blocker on that finite corpus. This reviewer
did not run those measurements and makes no production performance claim.
The earlier debug limitation remains retained history, not the current optimized
verdict.

Final public-v2 and immutable full gates remain pending. The full SDP, both native
Extension routes, enforced fencing and typed YAML/JSON/API with optional Dhall
objective remains active. Only this report was appended; no source edits, builds,
measurements, remote actions or cleanup were performed.

### Pending unique-ownership destruction finding

After this source-scope inspection, Research identified an unproven lifecycle
risk in borrowed-chain reconstruction: returning the new projection can drop an
original uniquely owned Arc chain through recursive LogicalPlan destruction,
without the rule's per-level recursion protection. The lead is preparing a
fixed-stack, uniquely owned control comparison against v1. No source changed from
tree1935edac at this notification. This is an explicit unresolved correctness/
lifecycle finding; a cleared performance cost on the measured corpus does not
resolve it. Overall readiness must remain pending until the control settles the
risk and any required correction is reviewed. No probe or build was run by this
reviewer.

## Final v4 ownership repair and exact cumulative pin

Verified all 85 source hashes and 11 increment paths, unchanged parent
`6e4da8d33ba1bf4073fcb853123f81860ef18151`, working/index equality and exact
index equality with tree `b337dfd145db4773ba1aa019028a8e9c86bbaa67`.
Independently recomputed:

- Increment SHA-256:
  `d0be097703b5ce7ba7f1e8400dfd486ee492f9d64f2c91437a8e4f86409cc227`.
- Full cumulative against upstream `b52144955b629314a000b1fe49eeea97fa3d0c5c`,
  SHA-256: `01226d1ed79d26afa4cd9e36d1e331b365d3ad4ba93c434fbbc50636262c991c`.

Independently verified raw pinned-original hashes, complete current owned hashes,
the documented production-prefix normalization and all three exact regenerated
ownership comparisons in `comparisons-final-v4.json`. The substantive delta remains
projection composition/schema preservation plus the narrow identity-chain cost
and lifecycle corrections; no unrelated optimizer or datatype policy enters.

No scope blocker was found. Read the current chain-ownership plan and retained
atomic-retirement-before-code snapshot. Relative to v2, only the rule and its direct
ownership test change. The rule retains the replacement tail first, then consumes
proven skipped projection wrappers iteratively using Arc::into_inner. It stops at
the retained tail or shared ownership. This repairs the demonstrated destruction
problem locally without imposing a depth threshold, adding a cache, changing all
LogicalPlan destructors or changing execution ownership. The separate use of the
standard atomic retirement API is justified by its documented ownership guarantee;
a concurrent failure was not itself reproduced and must not be presented as one.

Inspected the added fixed-stack test for uniquely owned and shared-tail cases,
including exact schema/leaf checks, ownership counts and subsequent cleanup of the
retained shared subtree through the same public rule. Also inspected the retained
identity-drop-v3 receipt and logs for run20261106T092201.365516Z: both baseline and
current variants completed depths8192 and16384, using the same binary; restoration
was verified. This is executed evidence read from the lead's artifacts, not a test
run by this reviewer. It settles the previously recorded reproduction at those
fixtures, without proving arbitrary expression destruction or external-owner drops.

The lead reports full mechanical-v5 preflight passed and the final optimized
comparison covered ten correctness-qualified cells and seventy timing samples, with deep/wide ratio0.9169 and
shallow1.0247. Current Performance and Design reviews clear their introduced
blockers on the tested corpus. Those bounded results do not establish production
throughput or universal stack safety. The full frozen runtime/public gate is still
pending; an earlier166-test affected run preceded the last API-line correction.

The full SDP, existing Extensions, Comet, mandatory fencing and typed configuration
objective remains active. This correction remains a human-reviewable local
foundation increment; no upstream offer or maintainer agreement is inferred.
Only this report was appended. No source edits, builds, measurements, cleanup,
remote actions or maintainer messages were performed.
