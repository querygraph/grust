# Preserve projection values and declared schemas

Sail must preserve every computation when it combines consecutive projections.
The local reference repairs a DataFusion projection-optimization defect affecting
both ordinary queries and streaming preparation. It also preserves declared output
qualifiers and Arrow metadata when that rule reconstructs projections.

This is a logical-optimizer correction. It does not establish distributed streaming
recovery, durable publication or production performance.

## Why the rule needs ownership

A projection computes expressions over its input and gives the results names.
Two successive projections computing `v + 1 AS v` must add twice. Equal expression
text reads different input scopes. DataFusion 55.2 instead treats identical lists
as redundant and drops one computation. Twelve such additions return one addition.
The direct analyzed plan produces the intended result.

Disabling the rule would also disable useful column pruning. Renaming aliases
around it introduces another scoping mechanism and cannot control projection pairs
created inside optimization. Reconstructing discarded computation afterward cannot
recover the lost meaning. Sail therefore owns the existing rule and its private
helpers, with pinned attribution and exact comparisons against DataFusion 55.2.0.
About 1,142 existing production lines are carried; the optimizer framework remains.

The owned rule occupies the original position in ordinary optimization and the
existing projection slot in streaming preparation. Computed expressions undergo
ordinary simultaneous substitution through child outputs. The equal-list shortcut
is restricted to literals and identity columns whose qualifier and name match the
child field at the same position. Swapped aliases and dependencies on another
output position must still compose.

An outer projection selecting every child output once in the same position is an
identity. The rule borrows through consecutive identities, proving each against its
immediate input. It reconstructs the surviving computations once with the outer
schema. This avoids comparing or cloning computations at every identity layer,
while preserving volatile and guarded child evaluation exactly once.
The replacement input remains alive while skipped uniquely owned projection nodes
are released iteratively. A fixed-stack control exposed an overflow when the
borrowed chain was instead destroyed recursively. The prior rule passed both
control depths; the failing borrowed variant remains retained separately.
The unchanged original probe now passes both depths with the final rule, while
permanent tests also cover a retained shared midpoint. The release uses Rust's
[atomic ownership-retirement contract](https://doc.rust-lang.org/std/sync/struct.Arc.html#method.into_inner);
its parallel-owner guarantee was checked in pinned standard-library source.
A newly reproduced concurrent failure is not claimed.

The declared outer schema survives composition. Pruning selects original qualified
fields and schema metadata. It remaps column-dependency guarantees to retained
positions, so removing or reordering fields cannot leave stale references. These
guarantees record which columns determine others. An identity projection is removed only when its complete schema equals
its input. The correction adds no casts, datatype inference or nullability policy.
Existing recursion protection uses the already locked dependency version.

## Correctness evidence

Immutable verification passed nightly formatting, strict Rust documentation,
workspace Clippy across all targets and features, and 2,110 Rust tests. One
pre-existing test remains skipped. The increment adds 19 Rust tests and 13 public
cases. A freshly built CLI and native import module passed 42 live-server cases
and nine mocked client fixtures. The actual server reported 4.2.1. Python formatting
and lint passed. PySpark 4.2.1 and PyArrow 26.0.0 remain preserved. This is not a
wheel, cluster or JVM differential qualification.

An unchanged owned copy reproduces the arithmetic failures while passing identity
controls. A separate unchanged-copy control loses explicit output qualifiers, field
metadata and schema metadata. The corrected copy passes the original expected
values and fields. Restoring only the broad equality shortcut fails both swapped
alias and cross-position controls; restoring the exact candidate passes them.

Tests cover two and twelve additions, identity and literal lists, NULL and empty
outputs, pruning, qualified names, metadata, subquery scopes and both registrations.
Full compiler tests compare batch and encoded streaming plans with direct analyzed
execution. Volatile functions retain their evaluation counts and conditional
expressions retain their guards. Physical execution checks values and complete
fields rather than relying on logical schema construction alone.

The explicit-schema matrix runs the owned rule directly, followed by physical
execution, across 67 Arrow type variants with zero and three rows. It covers the
admitted type families rather than every possible parameter. Dependency tests cover removal, reordering, composite determinants and
empty outputs. Separate physical expressions pin derived types, nullability and
exact nullable values. Public DataFrame tests cover repeated arithmetic, filters,
identity, alias swaps and metadata; finite rate-source tests exercise streaming.

Spark 4.2.1 source confirms dependent composition and alias metadata preservation.
The pinned source was inspected; a JVM differential run was not executed. This
correction follows the intended computation contract without adopting Spark's
microbatch architecture.

## Planning costs and limits

The probe compares the stock and owned rules on identical, correct plans. It checks
schemas, executed arrays, projection counts and source-column pruning before timing.
Only rule rewriting and plan cloning are timed. Analysis, physical planning and
execution remain outside timing. Each cell retains seven alternating paired samples
of 32 rewrites after warmups. Incorrect stock arithmetic results are excluded from
performance comparisons rather than treated as equivalent work.

A repair using only guarded expression equality takes 1.405 times stock time
on the deep, wide identity case in an optimized profile. Isolated diagnostic copies
retain all value/schema/pruning oracles: removing only schema comparison leaves that
cost, while removing only the repeated binding proof brings it near stock. Neither
weaker policy is a valid fix. Borrowed identity-chain folding instead preserves the
proof while avoiding redundant expression comparisons and reconstruction.

The final optimized ratios compare owned-rule time with stock time. The profile
uses optimization level three, disabled link-time optimization and sixteen codegen
units. Every cell and range is retained below.

| Input | Depth 2 median and range | Depth 32 median and range |
| --- | ---: | ---: |
| Single-column identity | 0.484 [0.467–0.494] | 0.641 [0.634–0.651] |
| Constant | 0.668 [0.657–0.682] | 0.853 [0.780–0.862] |
| Unique-alias arithmetic | 0.174 [0.170–0.179] | 0.053 [0.052–0.055] |
| 64-column qualified identity | 1.025 [0.976–1.028] | 0.917 [0.903–0.949] |
| 63 identity columns and one computed column | 0.412 [0.409–0.421] | 0.264 [0.262–0.266] |

The material deep-identity slowdown is resolved on these fixtures. The shallow
wide case retains a small 1.025 median ratio. Near-identity inputs check the cost
when the positional proof rejects the final computed column. These results qualify
this finite planning corpus, rather than arbitrary queries.

These are shared-host diagnostics without CPU isolation or steal measurements.
They do not establish production latency, throughput or memory admission. The
previously measured short-streaming compilation cost and mixed-marker execution
fragmentation remain separate unresolved limits.

## Review boundary and remaining work

The local branch `work/projection-composition-20261106` is the subject of these
results. Source commit `b6d73d6a644dc04b1e6749e171100808c874d788` has tree
`b337dfd145db4773ba1aa019028a8e9c86bbaa67` and parent
`6e4da8d33ba1bf4073fcb853123f81860ef18151`.

Seven specialist reviews cover the full cumulative patch against upstream
`b52144955`, as well as the increment. Newer upstream `5c0381bb3` was inspected
separately; this qualification does not establish integration onto it. Exact source
comparisons, negative controls, failed invocations and raw timing samples are retained.

The [composition plan](PROJECTION-COMPOSITION.md) explains the alternatives and
verification criteria. The [human review compendium](HUMAN-REVIEW.md) retains the
full pipeline, Extensions and performance goal. Detailed receipts are in the
[evidence directory](evidence/projection-composition-1/). Source and binary artifacts
remain local, and all earlier worktrees and the product environment are preserved.

Live source controls, checkpoint alignment, immutable prepared effects, mandatory
commit-time target fencing, deterministic change capture, strict typed configuration
with optional Dhall authoring, and native package/worker integration remain required
increments. A local optimizer correction does not qualify those guarantees.
