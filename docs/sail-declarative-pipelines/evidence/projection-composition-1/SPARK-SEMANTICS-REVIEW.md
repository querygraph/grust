# Projection composition: Spark semantics and correctness review

## Review boundary

Read the saved full request in the implementation worktree, the published
first-principles plan and applicable repository, LAKESAIL, SHEHAB, CLARITY,
WRITING-RULES and source review/development instructions. Full SDP, deterministic
CDC, fencing, typed configuration and both extension routes remain active scope.
This review concerns the narrower optimizer repair and supplies no completion
claim for those obligations.

The implementation starts at `6e4da8d33ba1bf4073fcb853123f81860ef18151` in
`/Users/alexy/src/sail/tmp/projection-composition-20261105-6e4da8d3`. Upstream
reference remains `b52144955b629314a000b1fe49eeea97fa3d0c5c`. The plan’s SHA-256
at inspection is `70f66f814b30d865258e5350c1c3cd4ed4eb58a4bf0fe7206a419da2d2d16bb3`.
The owned rule is currently the unchanged copy with tests and wiring; the cold
negative-control build belongs to the lead and remains pending at this review.
No production edit, build, test or timing run was performed by this reviewer.

## Intended dependent computation

A projection evaluates expressions against its immediate child’s output. An upper
`v + 1 AS v` therefore refers to the value produced by the lower projection,
not to the lower projection’s original input. Composing two such layers must
produce `(input_v + 1) + 1`. Inputs one through four must produce three through
six. Twelve layers must add twelve. Identity layers remain identity. These small
integer examples have no overflow or floating-point reassociation ambiguity.

The isolated rule probe executed by the lead in the preceding increment establishes
that direct execution and filter pushdown retain the intended result while public
OptimizeProjections drops an addition. That is reported executed Sail/DataFusion
evidence, distinct from the Spark source confirmation below. Both filtered and
unfiltered arithmetic cases and identity controls are necessary to assign the
failure to composition rather than filtering or source participation.

## Verified Spark 4.2.1 source

Verified the sparse Spark checkout at
`617618396087429b5627a86ce933bb0f5d6645cb`. Inspected Git objects and checked
retained source hashes against `review-logs/spark-source/manifest.json`.

Catalyst `Optimizer.scala` defines CollapseProject beginning at line 1234. For
adjacent projects it merges producer/consumer expressions; buildCleanedProjectList
uses the lower project’s alias map and substitution. AliasHelper maps references
to lower producer expressions, while AttributeMap keys by expression identity.
A repeated printed label therefore does not identify the same binding across
projection layers. The dependent-project test in CollapseProjectSuite explicitly
expects the nested arithmetic expression after composition. ProjectExec binds
expressions to child output and evaluates actual data rows.

This confirms the intended composition contract. It does not mean copying Spark’s
whole optimizer or adding Spark-only features. No Spark JVM was run and no runtime
parity claim is supplied.

## Source-derived correction and guards

The copied DataFusion rule contains a shortcut comparing the complete previous
and current expression vectors for equality. When equal, it returns the current
expressions over the grandchild, bypassing normal substitution. That comparison
cannot establish equivalent computation when each vector is interpreted under a
different input schema. Removing the shortcut and using the existing child-schema
index substitution is a coherent narrow correction candidate.

The existing substitution looks up each Column in the immediate child schema and
replaces it with that child’s producer expression. Preserve simultaneous bindings:
swapped aliases must not cascade through replacements as though every name belonged
to one flat scope. Outer aliases, qualifiers, metadata and nested field types remain
output contracts independent of the composed arithmetic. Scalar subquery bodies
have their own scopes and must not bind to equally named outer projection columns.

Keep ordinary column pruning and expensive-expression sharing behavior. A repeated
nontrivial child value should not be recomputed once per output alias merely because
substitution is possible. Volatile computation cannot be merged by identical text
or duplicated under repeated references. Spark CollapseProject similarly protects
nondeterministic producers and checks repeated consumption/cheapness; its physical
ProjectExec requires evaluation of nondeterministic outputs rather than deferring
them arbitrarily.

Conditional evaluation needs a stronger control than a determinism flag. A pure
function may be undefined for rows excluded by its guard. Rewriting must not hoist
it into unconditional work or reduce two dependent guarded layers to one. The
proposed fixture’s partial immutable function and exact call/row counters are
appropriate. They protect evaluation scope without claiming that every pre-existing
optimizer transformation has been proved correct.

## Initial test and integration assessment

The logical tests cover depth two and twelve, identity versus arithmetic, schema
retention, exact composed expressions, one remaining projection, column pruning
and idempotence. Swapped aliases check qualified output metadata/nullability and
input pruning. Scalar-subquery tests keep independent alias scope.

The session tests compare direct graph execution with configured batch and Sail
streaming compilers, with and without filters. Volatile fixtures check per-layer
calls and shared repeated outputs. Guarded partial-function fixtures check both
results and admitted work. Streaming checks must continue verifying marker order
and retractions, rather than counting only data output.

Both ordinary optimizer registration and streaming preparation now point to the
same owned rule. This is necessary: a streaming-only workaround would preserve the
known wrong batch end state. Exact-copy attribution/comparison, recursion behavior,
unchanged-copy failing controls, corrected cumulative tests and measured cost remain
qualification requirements. The current unchanged copy does not count as a fix.

## Status

No additional semantic objection to the first-principles correction plan was found.
Final cumulative source review and execution evidence remain pending. Earlier
source-inspection conclusions do not establish actual patch correctness. No new
Spark parity feature, durable recovery guarantee or broad optimizer readiness is
claimed. Saved prompt and governance compliance are confirmed; no context compaction
occurred during this review, and only this report was written.


## Final frozen cumulative review

Independently verified all eighty-five cumulative file hashes and eleven increment
paths against `candidate-snapshot-final.json` in the assigned implementation worktree.
The final index tree is `a4801a8e6fb2d10d041d07aef9fc9ec1b7ff2bb6`.
Parent is `6e4da8d33ba1bf4073fcb853123f81860ef18151`.
The increment SHA-256 is
`72d0cd710862bc0b4676f357e8c451813f365dfeb27f87fc3daf2dd03db82a0e`;
the complete cumulative diff against upstream b521 SHA-256 is
`8898a1d1a5b0ae74c3189b022ae7f9c7947675cdde78ef0ff1eb5a29bb322b2f`.
The opt-in untracked cost probe is outside this reviewed source snapshot and was
not treated as production source. No new source-semantic blocker was found.

The final correction restricts rather than entirely removes the equal-list shortcut.
Each expression, after stripping aliases, must be a literal or a Column matching
the immediate child’s same-position qualified field. This supports genuinely
idempotent positional identity/constant layers, including mixed lists, without
using expression equality to discard dependent arithmetic or function calls.
Swapped aliases and cross-position literal dependencies fail that condition and
use ordinary child-scope substitution. Their positive controls independently verify
the resulting composed expressions. Empty projections retain row cardinality and
the declared empty schema.

For nontrivial expressions, substitution remains simultaneous over the immediate
child schema. Existing repeated-expression placement guards are retained, rather
than duplicating expensive or volatile producers under every parent use. Session
controls compare exact outputs, per-layer volatile calls and shared child results.
Partial immutable-function controls retain their conditional guards and admitted
work. These tests distinguish arithmetic correction from accidentally collapsing
computation, broad hoisting or extra evaluation.

The owned reconstruction now preserves the declared outer schema when output
positions remain unchanged. Column pruning selects original qualified fields and
metadata, then projects functional dependencies to the retained indices. Identity
removal additionally requires complete input/output schema equality. Thus a
value-preserving projection is not removed if it still carries a different output
contract. Tests cover qualifiers, field/schema metadata, composite/reordered
dependencies, dropped determinants, aliases, actual physical field types/nullability
and Arrow representations. This is stronger evidence than asserting only logical
column counts. No cast or new scalar-nullability policy is introduced by the rule.

Spark 4.2.1 source confirmation remains applicable: CollapseProject substitutes
lower producers into upper consumers using resolved attribute identity; ProjectExec
binds expressions to child output; aliases retain output names and supported
metadata through the configured substitution paths. This supports the intended
composition and metadata concern, but does not make every Spark metadata option
a new Sail requirement. Sail must preserve its own declared schema contract.
No JVM engine comparison was executed.

The source registry replaces the ordinary optimizer’s named projection rule and
uses that same owned implementation in streaming preparation. Recursive protection
and pinned ownership/comparison records remain part of qualification. The unchanged
owned-copy and stock-rule failures provide baseline controls for the fix; their
execution is owned by the lead, not this reviewer. Previously reviewed participation,
marker-isolated projection and Comet scalar files are included in the cumulative
hash and retain their stated qualification limits.

Inspected the preliminary public receipt: it identifies the actual fresh binary,
server version 4.2.1 and a successful selected pytest invocation. The owner reports
fifty-one passes, comprising forty-two live server checks and nine mocked-transport
PySpark client fixtures. These are not fifty-one server executions or a Spark JVM
parity run. No full immutable cumulative gate has completed at this review point.

The wide-identity unoptimized cost ratio near 1.439 is material and remains pending
optimized assessment. Correctness cannot be traded away to recover that number;
the safe shortcut’s measured benefit must still be qualified without timing wrong
results as equivalent work. Optimized build activity is not a completed comparison.
No broad optimizer performance, durable recovery or full-system readiness claim
is supplied by this source verdict.

Reread the saved REQUEST and applicable governance; reviewed the updated standalone
plan. No context compaction occurred during this pass. No builds, tests, source
edits, cleanup or remote actions were performed. Only this review report was
appended, and full-goal obligations remain active.


## Final v4 borrowed identity and ownership confirmation

Verified all eighty-five cumulative file hashes, eleven increment paths and index
tree `b337dfd145db4773ba1aa019028a8e9c86bbaa67`. Increment SHA-256 against parent
`6e4da8d33ba1bf4073fcb853123f81860ef18151`:
`d0be097703b5ce7ba7f1e8400dfd486ee492f9d64f2c91437a8e4f86409cc227`.
Full cumulative SHA-256 against b521:
`01226d1ed79d26afa4cd9e36d1e331b365d3ad4ba93c434fbbc50636262c991c`.
Also independently verified all three v4 ownership comparison records: retained
raw originals, recorded owned source scopes and exact comparison-patch hashes.
This source pin supersedes the earlier reviewed tree.

Read the identity-fold and chain-ownership first-principles plans. No additional
source-semantic blocker was found. A bare same-position identity reads the child’s
already computed values without reevaluating them. The new borrowed traversal proves
that property separately at every skipped layer against its immediate input.
It stops at the first nonidentity producer and reuses that producer’s expressions
and original input. Reordered, partial, aliased and computed selections retain
the existing guarded/substitution paths. Comparing expression vectors afterward
only chooses which owned vector to reuse; it no longer licenses skipping a
computation. The complete outer declared schema remains authoritative.

This law is compatible with the pinned Spark source’s child-bound projection
semantics; it is not an additional Spark-specific optimization requirement. The
source tests retain arithmetic, metadata, qualified scope, empty-output and
functional-dependency oracles. Existing session tests still distinguish volatile
per-layer work and shared child outputs, and keep partial immutable calls inside
their conditions. The new positional-fold tests preserve a computed child and
exercise reordered/partial selections as controls, rather than testing only an
all-identity happy path.

The replacement input is retained before discarded owners are consumed. Iterative
Arc::into_inner handling moves one uniquely owned projection input onward per
iteration, preventing recursive destruction of the demonstrated removed chain.
It stops at the retained tail or shared ownership. Non-skipped subtrees remain
owned by the replacement, and independently held shared tails remain unchanged.
The fixed-small-stack test checks uniquely owned and shared-tail chains at both
depths, exact schemas and original leaves. It also consumes the retained shared
fixture through the public rule, avoiding teardown that conceals an ownership
crash. The helper concerns the chain it removes; it does not promise arbitrary
external plan/expression destructors are stack bounded.

Using Arc::into_inner follows the stated standard-library ownership contract.
This review makes no newly reproduced concurrent-retirement failure claim and no
independently executed concurrency-stress claim. The retained same original
identity-drop probe, both variants/depths and restored outcome supply the lead’s
reported narrow regression evidence. The source review does not relabel it as
broader concurrency qualification.

The owner reports 166 permanent tests passed with one skip before the final API
line correction, strict workspace Clippy/format/Rustdoc passed mechanically, and
the final optimized comparison covered ten correctness-qualified cells and seventy paired timing samples.
Reported deep-wide and shallow-wide ratios are 0.9169 and 1.0247. These final
optimized diagnostics refine the earlier unoptimized cost concern but establish
no universal speedup or production throughput. Full immutable gate and fresh
public qualification remain pending for this exact tree. No builds, tests,
source edits or timing runs were performed by this reviewer. Saved REQUEST and
governance compliance remain confirmed; no JVM comparison was executed.
